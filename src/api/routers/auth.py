import ipaddress
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
from sqlalchemy.orm import Session

from src import config
from src.aac_app.models import User
from src.aac_app.services.audit_service import audit_service
from src.aac_app.services.auth_service import (
    get_password_hash,
    verify_password_and_update,
)
from src.aac_app.services.credential_service import mark_credentials_changed
from src.aac_app.services.lockout_service import lockout_service
from src.aac_app.utils.jwt_utils import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from src.api import schemas
from src.api.deps import get_current_active_user, get_db
from src.api.routers.auth_helpers import (
    conditional_limiter,
    ensure_username_email_available,
    validate_email_format,
    validate_password_strength,
)

router = APIRouter()


def _is_loopback_client(host: str | None) -> bool:
    """Return True if the client host is a local loopback address or test runner."""
    if not host:
        return False
    if host in {"localhost", "testclient"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@router.get("/setup-status", response_model=schemas.SetupStatusResponse)
def get_setup_status(db: Session = Depends(get_db)):
    """Check whether the initial administrator setup is required."""
    has_admin = db.query(User).filter(User.user_type == "admin").first() is not None
    return schemas.SetupStatusResponse(
        setup_required=not has_admin,
        has_admin=has_admin,
        app_name=config.APP_NAME,
        app_version=config.APP_VERSION,
    )


@router.post("/setup", response_model=schemas.SetupResponse)
@conditional_limiter("5/minute")
def initial_admin_setup(
    request: Request,
    payload: schemas.InitialAdminSetupRequest,
    db: Session = Depends(get_db),
):
    """Create the initial administrator account on first run."""
    client_ip = request.client.host if request.client else "unknown"
    if not _is_loopback_client(client_ip):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Initial administrator setup is only permitted from local loopback (127.0.0.1 / ::1).",
        )

    existing_admin = db.query(User).filter(User.user_type == "admin").first()
    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Initial administrator setup has already been completed.",
        )

    if payload.password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match.",
        )

    if payload.password.strip().lower() == config.DEFAULT_BOOTSTRAP_ADMIN_PASSWORD.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The development default password is not permitted for administrator setup.",
        )

    validate_password_strength(payload.password)

    username = payload.username.strip() or "admin1"
    display_name = payload.display_name.strip() or "Administrator"

    if payload.email:
        validate_email_format(payload.email)

    ensure_username_email_available(db, username, payload.email)

    admin = User(
        username=username,
        display_name=display_name,
        email=payload.email,
        user_type="admin",
        password_hash=get_password_hash(payload.password),
        is_active=True,
    )
    db.add(admin)
    db.flush()
    db.refresh(admin)

    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_account_created(
        db=db,
        new_user_id=admin.id,
        new_username=admin.username,
        new_user_type="admin",
        created_by_username="initial-setup",
        ip_address=client_ip,
    )
    db.commit()

    access_token = create_access_token(
        data={
            "sub": admin.username,
            "user_id": admin.id,
            "user_type": admin.user_type,
            "sec_ver": admin.security_version or 1,
        }
    )
    refresh_token = create_refresh_token(
        data={
            "sub": admin.username,
            "user_id": admin.id,
            "sec_ver": admin.security_version or 1,
        }
    )

    logger.info("Initial administrator setup completed for username '{}'", admin.username)
    return schemas.SetupResponse(
        message="Administrator account created successfully",
        user=schemas.UserResponse.model_validate(admin),
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
    )


@router.post("/token")
@conditional_limiter("10/minute")  # Max 10 login attempts per minute per IP
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    OAuth2-compliant token endpoint.
    Returns a signed JWT access token for valid credentials.

    Rate limited to 10 attempts per minute per IP to prevent brute force attacks.
    Implements account lockout after 5 failed attempts.
    """
    # Get client IP
    client_ip = request.client.host if request.client else None

    # Check if account is locked
    is_locked, locked_until = lockout_service.is_locked(db, form_data.username)
    if is_locked:
        # Log lockout attempt
        audit_service.log_login_failed(
            db=db,
            username=form_data.username,
            ip_address=client_ip,
            reason=f"Account locked until {locked_until}"
        )
        # Authentication failures intentionally persist their security events
        # even though the request raises and the dependency would otherwise
        # roll the transaction back.
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is temporarily locked due to multiple failed login attempts. Try again after {locked_until.strftime('%Y-%m-%d %H:%M:%S UTC')}.",
        )

    user = db.query(User).filter(User.username == form_data.username).first()
    if not user:
        # Record failed attempt
        lockout_service.record_failed_attempt(db, form_data.username, client_ip)
        audit_service.log_login_failed(
            db=db,
            username=form_data.username,
            ip_address=client_ip,
            reason="User not found"
        )
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if account is active
    if not user.is_active:
        audit_service.log_login_failed(
            db=db,
            username=form_data.username,
            ip_address=client_ip,
            reason="Account inactive"
        )
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact an administrator.",
        )

    if not user.password_hash:
        logger.error(f"Token request failed: User '{form_data.username}' has no password hash")
        raise HTTPException(status_code=500, detail="Account configuration error")

    password_valid, updated_password_hash = verify_password_and_update(
        form_data.password, user.password_hash
    )
    if not password_valid:
        # Record failed attempt and check if should lock
        is_locked, locked_until, attempt_count = lockout_service.record_failed_attempt(
            db, form_data.username, client_ip
        )

        reason = f"Invalid password (attempt {attempt_count}/{lockout_service.MAX_ATTEMPTS})"
        if is_locked:
            reason = f"Account locked after {attempt_count} failed attempts"

        audit_service.log_login_failed(
            db=db,
            username=form_data.username,
            ip_address=client_ip,
            reason=reason
        )
        db.commit()

        if is_locked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account locked due to multiple failed login attempts. Locked until {locked_until.strftime('%Y-%m-%d %H:%M:%S UTC')}.",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if updated_password_hash:
        user.password_hash = updated_password_hash
        mark_credentials_changed(user)
        db.add(user)
        db.flush()
        # Commit before the token is issued: the token embeds the bumped
        # security version, and a follow-up request would otherwise reject it
        # against the still-uncommitted user row.
        db.commit()

    # Login successful - reset failed attempts
    lockout_service.reset_attempts(db, form_data.username)

    # Log successful login
    audit_service.log_login_success(
        db=db,
        user_id=user.id,
        username=user.username,
        user_type=user.user_type,
        ip_address=client_ip
    )

    # Create JWT token with user information
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "user_type": user.user_type,
            "sec_ver": user.security_version or 1,
        }
    )

    refresh_token = create_refresh_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "sec_ver": user.security_version or 1,
        }
    )

    logger.info(f"Token issued for user '{user.username}' (id={user.id}, type={user.user_type})")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }


@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Revoke every token issued for the current account."""
    mark_credentials_changed(current_user)
    db.add(current_user)
    db.commit()
    return {"ok": True}


@router.post("/refresh")
@conditional_limiter("30/minute")  # Max 30 refresh attempts per minute per IP
def refresh_access_token(
    request: Request,
    refresh_token: str,
    db: Session = Depends(get_db)
):
    """
    Refresh endpoint to get a new access token using a refresh token.

    This allows users to get a new access token without re-authenticating,
    preventing session interruption for long-running sessions.

    Rate limited to 30 attempts per minute per IP.
    """
    # Decode and validate refresh token
    payload = decode_refresh_token(refresh_token)
    if not payload:
        logger.warning("Refresh token validation failed: Invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user info
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Refresh token missing user_id claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning(f"Refresh token valid but user {user_id} not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_security_version = payload.get("sec_ver")
    if token_security_version is not None:
        token_is_revoked = token_security_version != (user.security_version or 1)
    elif user.credentials_changed_at is not None:
        token_issued_at = payload.get("iat")
        token_is_revoked = (
            token_issued_at is None
            or datetime.fromtimestamp(token_issued_at, UTC).replace(tzinfo=None)
            < user.credentials_changed_at
        )
    else:
        token_is_revoked = False
    if token_is_revoked:
        logger.warning("Refresh token security state mismatch for user {}", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if account is still active
    if not user.is_active:
        logger.warning(f"Refresh attempt for inactive user '{user.username}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact an administrator.",
        )

    # Issue new access token
    new_access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "user_type": user.user_type,
            "sec_ver": user.security_version or 1,
        }
    )

    logger.info(f"Access token refreshed for user '{user.username}' (id={user.id})")
    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@router.post("/register", response_model=schemas.UserResponse)
@conditional_limiter("5/hour")  # Max 5 registrations per hour per IP to prevent spam
def register(request: Request, user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user account.

    Public registration always creates 'student' accounts to prevent privilege escalation.
    Admin/teacher accounts must be created by an administrator via /auth/admin/create-user.

    Rate limited to 5 registrations per hour per IP to prevent spam.
    """
    # Validate password strength using shared validation function
    validate_password_strength(user.password)

    # Validate email format if provided
    validate_email_format(user.email)

    ensure_username_email_available(db, user.username, user.email)

    # SECURITY: Force user_type to 'student' for public registration
    # Only admins can create teacher/admin accounts via /auth/admin/create-user
    if user.user_type and user.user_type != 'student':
        logger.warning(
            f"Registration attempted with privileged user_type '{user.user_type}' for username '{user.username}'. "
            "Forcing to 'student'."
        )

    # Create new user with enforced student role
    new_user = User(
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        user_type='student',  # Always 'student' for public registration
        password_hash=get_password_hash(user.password),
        is_active=True
    )

    db.add(new_user)
    db.flush()
    db.refresh(new_user)

    # Log successful account creation in the same request transaction.
    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_account_created(
        db=db,
        new_user_id=new_user.id,
        new_username=new_user.username,
        new_user_type="student",
        created_by_username="self-registration",
        ip_address=client_ip
    )

    # Commit before responding so a follow-up login/token request cannot read
    # the account before registration is durable.
    db.commit()
    logger.info(f"New student account registered: {new_user.username} (id={new_user.id})")
    return new_user


@router.post(
    "/login",
    response_model=schemas.UserResponse,
    deprecated=True,
)
def login(credentials: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Deprecated JSON login endpoint; use ``/auth/token`` for JWT login."""
    logger.info(f"Login attempt for username: {credentials.username}")

    user = db.query(User).filter(User.username == credentials.username).first()
    if not user:
        logger.warning(f"Login failed: User '{credentials.username}' not found")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        logger.warning(f"Login failed: User '{credentials.username}' is inactive")
        raise HTTPException(
            status_code=403,
            detail="Account is inactive. Please contact an administrator.",
        )

    if not user.password_hash:
        logger.error(f"Login failed: User '{credentials.username}' has no password hash")
        raise HTTPException(
            status_code=500,
            detail="Account configuration error. Please contact administrator.",
        )

    password_valid, updated_password_hash = verify_password_and_update(
        credentials.password, user.password_hash
    )
    if not password_valid:
        logger.warning(f"Login failed: Invalid password for user '{credentials.username}'")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if updated_password_hash:
        user.password_hash = updated_password_hash
        mark_credentials_changed(user)
        db.add(user)
        db.flush()
        # Commit the rehash before responding so the durable user row matches
        # the security version the issued token carries.
        db.commit()

    logger.info(
        f"Login successful for user '{credentials.username}' "
        f"(id={user.id}, type={user.user_type})"
    )
    return user

