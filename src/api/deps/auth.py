"""Authentication and role-based access dependencies."""

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import StudentTeacher, User
from src.aac_app.services.translation_service import get_translation_service
from src.aac_app.utils.jwt_utils import decode_access_token

from .db import get_db

# The token URL is relative to this API's auth router; it is not a credential.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


# User types allowed to perform staff actions (teacher rosters, board
# assignment, content management). Single source of truth for the role
# check repeated across routers and dependencies.
STAFF_USER_TYPES = frozenset({"admin", "teacher"})


def validate_token(token: str, db: Session) -> User | None:
    """Validate a JWT and return its database user, if present.

    Account activity is checked by callers that need an active session so this
    helper can retain its existing lookup semantics for authentication flows.
    """
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        logger.debug("Token validation failed: Invalid or expired token")
        return None

    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Token payload missing user_id claim")
        return None

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning(f"Token valid but user {user_id} not found in database")
            return None

        token_security_version = payload.get("sec_ver")
        if token_security_version is not None:
            if token_security_version != (user.security_version or 1):
                logger.warning("Token security version mismatch for user {}", user_id)
                return None
        elif user.credentials_changed_at is not None:
            token_issued_at = payload.get("iat")
            if token_issued_at is None:
                logger.warning("Legacy token missing issuance time for user {}", user_id)
                return None
            token_issued_at_dt = datetime.fromtimestamp(token_issued_at, UTC).replace(
                tzinfo=None
            )
            if token_issued_at_dt < user.credentials_changed_at:
                logger.warning("Legacy token predates credential change for user {}", user_id)
                return None
        return user
    except Exception as exc:
        logger.error(f"Database error while validating token: {exc}")
        return None


def validate_active_token(token: str, db: Session) -> User | None:
    """Validate a JWT and return only an active database user."""
    user = validate_token(token, db)
    if user is None or not user.is_active:
        return None
    return user


def get_text(
    user: User | None = None,
    key: str = "errors.unknown",
    accept_language: str | None = None,
    *,
    namespace: str = "common",
    **kwargs,
) -> str:
    """Translate a message using user or request language preferences."""
    service = get_translation_service()
    lang = service.resolve_language(user, accept_language)
    return service.get(lang, namespace, key, **kwargs)


def get_request_text(
    request: Request,
    key: str = "errors.unknown",
    *,
    user: User | None = None,
    namespace: str = "common",
    **kwargs,
) -> str:
    """Translate a message using the request's Accept-Language header.

    Single choke point for the header lookup previously repeated at every
    translated error site, so a header-name typo cannot silently fall back
    to the default language in one endpoint.
    """
    return get_text(
        user=user,
        key=key,
        accept_language=request.headers.get("accept-language"),
        namespace=namespace,
        **kwargs,
    )


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate the current request and return its user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=get_request_text(request, "errors.credentialsInvalid"),
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        logger.debug("No token provided in request")
        raise credentials_exception

    user = validate_token(token, db)
    if user is None:
        logger.debug("Token validation failed")
        raise credentials_exception

    logger.debug(f"Authenticated user: {user.username} (id={user.id})")
    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require that the authenticated user has an active account."""
    if not current_user.is_active:
        logger.warning(f"Inactive user attempted access: {current_user.username}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=get_text(user=current_user, key="errors.inactiveAccount"),
        )
    return current_user


def get_current_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Require an active administrator account."""
    if current_user.user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=get_text(user=current_user, key="errors.insufficientPrivileges"),
        )
    return current_user


def get_current_staff_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Require an active teacher or administrator account."""
    if current_user.user_type not in STAFF_USER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=get_text(user=current_user, key="errors.insufficientPrivileges"),
        )
    return current_user


def verify_student_access(
    student_id: int,
    current_user: User,
    db: Session,
) -> User:
    """Verify the student exists and the current user can access their profile.

    Admins can access every student; teachers can access only students in their
    explicit roster. A teacher with no roster has no student access.
    """
    student = db.query(User).filter_by(id=student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=get_text(user=current_user, key="errors.guardian.studentNotFound"),
        )

    if student.user_type != "student":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_text(user=current_user, key="errors.guardian.onlyForStudents"),
        )

    # Admin can access all students
    if current_user.user_type == "admin":
        return student

    # Check the requested student first; this is the common authorized path and
    # avoids counting the entire roster before doing the actual access lookup.
    assignment = (
        db.query(StudentTeacher)
        .filter(
            StudentTeacher.teacher_id == current_user.id,
            StudentTeacher.student_id == student_id,
        )
        .first()
    )
    if assignment is not None:
        return student

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=get_text(
            user=current_user, key="errors.guardian.studentNotAssigned"
        ),
    )


def authorize_user_access(
    target_user: User,
    current_user: User,
    db: Session,
    *,
    forbidden_detail: str = "Not authorized",
) -> None:
    """Authorize access to another user's resource.

    Self-access and administrators are allowed. Teachers must use the same
    explicit student-roster policy as student-specific endpoints; all other
    cross-user combinations are forbidden.
    """
    if current_user.id == target_user.id or current_user.user_type == "admin":
        return

    if current_user.user_type == "teacher" and target_user.user_type == "student":
        verify_student_access(target_user.id, current_user, db)
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=forbidden_detail)
