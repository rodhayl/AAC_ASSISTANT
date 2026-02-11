from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Optional
from loguru import logger
import re

from src.api import schemas
from src.api.dependencies import get_db, get_current_active_user, get_current_admin_user
from src.aac_app.models.database import StudentTeacher, User, UserSettings
from src.aac_app.services.auth_service import get_password_hash, verify_password
from src.aac_app.utils.jwt_utils import create_access_token, create_refresh_token, decode_access_token
from src.aac_app.services.audit_service import audit_service
from src.aac_app.services.lockout_service import lockout_service

router = APIRouter()

# Import limiter from main app
from slowapi import Limiter
from slowapi.util import get_remote_address
from functools import wraps
import os

_limiter_instance = Limiter(key_func=get_remote_address)

def conditional_limiter(rate: str):
    """
    Apply rate limiting only in non-testing environments.
    
    Args:
        rate: Rate limit string like "10/minute"
    
    Returns:
        Decorator that applies rate limiting in production, passthrough in tests
    """
    def decorator(func):
        # Apply the actual limiter decorator
        limited_func = _limiter_instance.limit(rate)(func)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # At runtime, check if we're testing
            if os.getenv('TESTING', '0') == '1':
                # Skip rate limiting, call original function
                return func(*args, **kwargs)
            else:
                # Use rate-limited version
                return limited_func(*args, **kwargs)
        
        # Return wrapper with same metadata as original
        return wrapper
    
    return decorator


def validate_password_strength(password: str) -> None:
    """
    Validate password meets strength requirements.
    
    Requirements:
    - At least 8 characters
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one digit (0-9)
    
    Args:
        password: Password to validate
    
    Raises:
        HTTPException: 400 with specific error message if validation fails
    """
    if not password or len(password.strip()) == 0:
        raise HTTPException(status_code=400, detail="Password is required")
    
    if len(password) < 8:
        raise HTTPException(
            status_code=400, 
            detail="Password must be at least 8 characters long"
        )
    
    # Check password complexity: at least one uppercase, one lowercase, one digit
    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one uppercase letter"
        )
    if not re.search(r"[a-z]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one lowercase letter"
        )
    if not re.search(r"[0-9]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one number"
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
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact an administrator.",
        )
    
    if not user.password_hash:
        logger.error(f"Token request failed: User '{form_data.username}' has no password hash")
        raise HTTPException(status_code=500, detail="Account configuration error")
        
    if not verify_password(form_data.password, user.password_hash):
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
            "user_type": user.user_type
        }
    )
    
    refresh_token = create_refresh_token(
        data={
            "sub": user.username,
            "user_id": user.id
        }
    )
    
    logger.info(f"Token issued for user '{user.username}' (id={user.id}, type={user.user_type})")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token
    }


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
    payload = decode_access_token(refresh_token)
    if not payload:
        logger.warning("Refresh token validation failed: Invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify this is a refresh token
    if payload.get("type") != "refresh":
        logger.warning("Token type mismatch: Expected refresh token, got access token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected refresh token.",
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
            "user_type": user.user_type
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
    if user.email:
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, user.email):
            raise HTTPException(
                status_code=400,
                detail="Invalid email format"
            )
    
    # Check if username exists
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Check if email exists (if provided)
    if user.email:
        existing_email = db.query(User).filter(User.email == user.email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already registered")
    
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
    db.commit()
    db.refresh(new_user)
    
    # Log successful account creation
    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_account_created(
        db=db,
        new_user_id=new_user.id,
        new_username=new_user.username,
        new_user_type="student",
        created_by_username="self-registration",
        ip_address=client_ip
    )
    
    logger.info(f"New student account registered: {new_user.username} (id={new_user.id})")
    return new_user

@router.post("/login", response_model=schemas.UserResponse)
def login(credentials: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    Login endpoint that returns user info.
    
    NOTE: This endpoint returns user info but not a token. 
    For JWT authentication, use /auth/token instead.
    Consider deprecating this endpoint in favor of /auth/token.
    """
    logger.info(f"Login attempt for username: {credentials.username}")
    
    # Find user
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user:
        logger.warning(f"Login failed: User '{credentials.username}' not found")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Check if account is active
    if not user.is_active:
        logger.warning(f"Login failed: User '{credentials.username}' is inactive")
        raise HTTPException(
            status_code=403, 
            detail="Account is inactive. Please contact an administrator."
        )
    
    logger.debug(f"User found: id={user.id}, username={user.username}, type={user.user_type}")
    
    # Check if user has a password hash (safety check for data integrity)
    if not user.password_hash:
        logger.error(f"Login failed: User '{credentials.username}' has no password hash")
        raise HTTPException(status_code=500, detail="Account configuration error. Please contact administrator.")
    
    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        logger.warning(f"Login failed: Invalid password for user '{credentials.username}'")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    logger.info(f"Login successful for user '{credentials.username}' (id={user.id}, type={user.user_type})")
    return user

@router.post("/admin/create-user", response_model=schemas.UserResponse)
def admin_create_user(
    request: Request,
    user: schemas.UserCreate, 
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Create a new user account with any role (admin only).
    
    Only administrators can use this endpoint to create teacher or admin accounts.
    Enforces password strength requirements.
    """
    logger.info(f"Admin '{current_user.username}' creating user '{user.username}' with type '{user.user_type}'")
    
    # Validate password strength using shared validation function
    validate_password_strength(user.password)
    
    # Validate email format if provided
    if user.email:
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, user.email):
            raise HTTPException(
                status_code=400,
                detail="Invalid email format"
            )
    
    # Validate password confirmation for admin-created users
    if not user.confirm_password:
        raise HTTPException(
            status_code=400,
            detail="Password confirmation is required"
        )
    
    if user.password != user.confirm_password:
        raise HTTPException(
            status_code=400,
            detail="Passwords do not match"
        )
    
    # Validate user_type
    valid_types = ['student', 'teacher', 'admin']
    if user.user_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid user_type. Must be one of: {', '.join(valid_types)}"
        )
    
    # Check if username exists
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Check if email exists (if provided)
    if user.email:
        existing_email = db.query(User).filter(User.email == user.email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user with admin-specified role
    new_user = User(
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        user_type=user.user_type,
        password_hash=get_password_hash(user.password),
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Log admin action and account creation
    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_admin_action(
        db=db,
        admin_id=current_user.id,
        admin_username=current_user.username,
        action="create_user",
        description=f"Created {user.user_type} account '{new_user.username}'",
        ip_address=client_ip,
        endpoint="/api/auth/admin/create-user"
    )
    audit_service.log_account_created(
        db=db,
        new_user_id=new_user.id,
        new_username=new_user.username,
        new_user_type=new_user.user_type,
        created_by_id=current_user.id,
        created_by_username=current_user.username,
        ip_address=client_ip
    )
    
    logger.info(
        f"Admin '{current_user.username}' created new {new_user.user_type} account: "
        f"{new_user.username} (id={new_user.id})"
    )
    return new_user

@router.get("/me", response_model=schemas.UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current authenticated user's information.
    
    This endpoint returns the user info for the currently authenticated user
    based on the JWT token provided in the Authorization header.
    """
    return current_user

@router.get("/users", response_model=List[schemas.UserResponse])
def get_users(
    skip: int = 0, 
    limit: int = 100, 
    user_type: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all users (Admin/Teacher only)"""
    if current_user.user_type == 'student':
        raise HTTPException(status_code=403, detail="Not authorized to view user list")

    allowed_types = {"student", "teacher", "admin"}
    if user_type is not None and user_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid user_type filter")

    # Teachers can only view their assigned students
    if current_user.user_type == "teacher":
        if user_type is not None and user_type != "student":
            return []
        assignment_count = (
            db.query(StudentTeacher)
            .filter(StudentTeacher.teacher_id == current_user.id)
            .count()
        )
        if assignment_count == 0:
            query = db.query(User).filter(User.user_type == "student")
        else:
            query = (
                db.query(User)
                .join(StudentTeacher, User.id == StudentTeacher.student_id)
                .filter(StudentTeacher.teacher_id == current_user.id)
                .filter(User.user_type == "student")
            )
        return query.offset(skip).limit(limit).all()

    # Admin: all users, optionally filtered by role
    query = db.query(User)
    if user_type is not None:
        query = query.filter(User.user_type == user_type)
    return query.offset(skip).limit(limit).all()

@router.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user(
    user_id: int, 
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user by ID"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Permission check
    if current_user.user_type != "admin" and current_user.id != user_id:
        if current_user.user_type == "teacher" and user.user_type == "student":
            # Teacher can view all students until explicit roster assignments exist.
            assignment_count = (
                db.query(StudentTeacher)
                .filter(StudentTeacher.teacher_id == current_user.id)
                .count()
            )
            if assignment_count > 0:
                assigned = (
                    db.query(StudentTeacher)
                    .filter(
                        StudentTeacher.teacher_id == current_user.id,
                        StudentTeacher.student_id == user_id,
                    )
                    .first()
                )
                if not assigned:
                    raise HTTPException(status_code=403, detail="Not authorized to view this user")
        else:
            raise HTTPException(status_code=403, detail="Not authorized to view this user")
            
    return user

@router.post("/change-password")
@conditional_limiter("10/hour")  # Max 10 password changes per hour per IP
def change_password(
    request: Request,
    payload: schemas.ChangePasswordRequest, 
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Change password endpoint for authenticated users.
    
    Rate limited to 10 attempts per hour per IP.
    """
    
    # If it's the user themselves
    if current_user.username == payload.username:
        if not verify_password(payload.current_password, current_user.password_hash):
            raise HTTPException(status_code=401, detail="Current password incorrect")
    else:
        # Trying to change someone else's password
        # Even admin shouldn't use this endpoint if it requires current_password of the target.
        # Admin should use a reset-password endpoint (not implemented yet, or use update_user).
        raise HTTPException(status_code=403, detail="Cannot change another user's password via this endpoint")

    # Validate new password strength using shared validation function
    validate_password_strength(payload.new_password)
    
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
        
    user = db.query(User).filter(User.username == payload.username).first() # Should be current_user
    user.password_hash = get_password_hash(payload.new_password)
    db.add(user)
    db.commit()
    
    # Log password change
    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_password_changed(
        db=db,
        user_id=user.id,
        username=user.username,
        changed_by_admin=False,
        ip_address=client_ip
    )
    
    logger.info(f"Password changed for user '{user.username}' (id={user.id})")
    return {"ok": True}

@router.put("/users/{user_id}", response_model=schemas.UserResponse)
def update_user(
    user_id: int, 
    payload: dict, 
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Update user fields (admin only)"""
    # Note: using get_current_admin_user enforces admin check
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Allowed fields
    for key in ["display_name", "user_type", "email", "is_active"]:
        if key in payload:
            setattr(user, key, payload[key])
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int, 
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Delete user (admin only)"""
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"ok": True}

@router.get("/preferences", response_model=schemas.UserPreferencesResponse)
def get_preferences(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get current user's preferences"""
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings:
        # Return defaults if no settings exist
        return schemas.UserPreferencesResponse()

    return schemas.UserPreferencesResponse(
        tts_voice=settings.tts_voice or "default",
        tts_language=getattr(settings, "tts_language", None),
        ui_language=getattr(settings, "ui_language", None),
        notifications_enabled=settings.notifications_enabled if settings.notifications_enabled is not None else True,
        voice_mode_enabled=getattr(settings, "voice_mode_enabled", True)
        if getattr(settings, "voice_mode_enabled", None) is not None
        else True,
        dark_mode=settings.dark_mode if settings.dark_mode is not None else False,
        dwell_time=int(getattr(settings, "dwell_time", 0) or 0),
        ignore_repeats=int(getattr(settings, "ignore_repeats", 0) or 0),
        high_contrast=bool(getattr(settings, "high_contrast", False) or False),
    )

@router.put("/preferences", response_model=schemas.UserPreferencesResponse)
def update_preferences(
    prefs: schemas.UserPreferencesUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update current user's preferences"""
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    updates = prefs.model_dump(exclude_unset=True)
    for k in ["dwell_time", "ignore_repeats"]:
        if k in updates and updates[k] is not None and int(updates[k]) < 0:
            raise HTTPException(status_code=400, detail=f"{k} must be >= 0")

    for key, value in updates.items():
        setattr(settings, key, value)
    
    db.commit()
    db.refresh(settings)
    logger.info(f"Updated preferences for user {current_user.username}")

    return schemas.UserPreferencesResponse(
        tts_voice=settings.tts_voice or "default",
        tts_language=getattr(settings, "tts_language", None),
        ui_language=getattr(settings, "ui_language", None),
        notifications_enabled=settings.notifications_enabled if settings.notifications_enabled is not None else True,
        voice_mode_enabled=getattr(settings, "voice_mode_enabled", True)
        if getattr(settings, "voice_mode_enabled", None) is not None
        else True,
        dark_mode=settings.dark_mode if settings.dark_mode is not None else False,
        dwell_time=int(getattr(settings, "dwell_time", 0) or 0),
        ignore_repeats=int(getattr(settings, "ignore_repeats", 0) or 0),
        high_contrast=bool(getattr(settings, "high_contrast", False) or False),
    )


def _ensure_can_access_user_prefs(
    *, current_user: User, target_user: User, db: Session
) -> None:
    if current_user.user_type == "admin":
        return
    if current_user.id == target_user.id:
        return
    if current_user.user_type == "teacher" and target_user.user_type == "student":
        assigned = (
            db.query(StudentTeacher)
            .filter(
                StudentTeacher.teacher_id == current_user.id,
                StudentTeacher.student_id == target_user.id,
            )
            .first()
        )
        if assigned:
            return
    raise HTTPException(status_code=403, detail="Not authorized to access preferences")


@router.get("/users/{user_id}/preferences", response_model=schemas.UserPreferencesResponse)
def get_user_preferences(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    _ensure_can_access_user_prefs(current_user=current_user, target_user=target, db=db)

    settings = db.query(UserSettings).filter(UserSettings.user_id == target.id).first()
    if not settings:
        return schemas.UserPreferencesResponse()

    return schemas.UserPreferencesResponse(
        tts_voice=settings.tts_voice or "default",
        tts_language=getattr(settings, "tts_language", None),
        ui_language=getattr(settings, "ui_language", None),
        notifications_enabled=settings.notifications_enabled if settings.notifications_enabled is not None else True,
        voice_mode_enabled=getattr(settings, "voice_mode_enabled", True)
        if getattr(settings, "voice_mode_enabled", None) is not None
        else True,
        dark_mode=settings.dark_mode if settings.dark_mode is not None else False,
        dwell_time=int(getattr(settings, "dwell_time", 0) or 0),
        ignore_repeats=int(getattr(settings, "ignore_repeats", 0) or 0),
        high_contrast=bool(getattr(settings, "high_contrast", False) or False),
    )


@router.put("/users/{user_id}/preferences", response_model=schemas.UserPreferencesResponse)
def update_user_preferences(
    user_id: int,
    prefs: schemas.UserPreferencesUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Teachers can only update student preferences
    if current_user.user_type == "teacher" and target.user_type != "student":
        raise HTTPException(status_code=403, detail="Not authorized to update preferences")

    _ensure_can_access_user_prefs(current_user=current_user, target_user=target, db=db)

    settings = db.query(UserSettings).filter(UserSettings.user_id == target.id).first()
    if not settings:
        settings = UserSettings(user_id=target.id)
        db.add(settings)

    updates = prefs.model_dump(exclude_unset=True)
    for k in ["dwell_time", "ignore_repeats"]:
        if k in updates and updates[k] is not None and int(updates[k]) < 0:
            raise HTTPException(status_code=400, detail=f"{k} must be >= 0")

    for key, value in updates.items():
        setattr(settings, key, value)

    db.commit()
    db.refresh(settings)
    logger.info(f"Updated preferences for user {target.username} by {current_user.username}")

    return schemas.UserPreferencesResponse(
        tts_voice=settings.tts_voice or "default",
        tts_language=getattr(settings, "tts_language", None),
        ui_language=getattr(settings, "ui_language", None),
        notifications_enabled=settings.notifications_enabled if settings.notifications_enabled is not None else True,
        voice_mode_enabled=getattr(settings, "voice_mode_enabled", True)
        if getattr(settings, "voice_mode_enabled", None) is not None
        else True,
        dark_mode=settings.dark_mode if settings.dark_mode is not None else False,
        dwell_time=int(getattr(settings, "dwell_time", 0) or 0),
        ignore_repeats=int(getattr(settings, "ignore_repeats", 0) or 0),
        high_contrast=bool(getattr(settings, "high_contrast", False) or False),
    )

@router.post("/admin/unlock-account")
def admin_unlock_account(
    request: Request,
    username: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Unlock a locked user account (admin only).
    
    Removes account lockout after failed login attempts.
    """
    # Verify user exists
    target_user = db.query(User).filter(User.username == username).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Unlock the account
    lockout_service.unlock_account(db, username)
    
    # Log admin action
    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_admin_action(
        db=db,
        admin_id=current_user.id,
        admin_username=current_user.username,
        action="unlock_account",
        description=f"Unlocked account '{username}'",
        ip_address=client_ip,
        endpoint="/api/auth/admin/unlock-account"
    )
    
    logger.info(f"Admin '{current_user.username}' unlocked account for '{username}'")
    return {"ok": True, "message": f"Account '{username}' unlocked successfully"}

@router.put("/profile", response_model=schemas.UserResponse)
def update_profile(
    profile: schemas.UserProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile (display name, email)"""
    if profile.display_name is not None:
        current_user.display_name = profile.display_name
    if profile.email is not None:
        # Check email uniqueness
        existing = db.query(User).filter(User.email == profile.email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = profile.email
    
    db.commit()
    db.refresh(current_user)
    logger.info(f"Updated profile for user {current_user.username}")
    return current_user

