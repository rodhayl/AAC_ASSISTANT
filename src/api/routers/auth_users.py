from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import (
    BoardAssignment,
    CommunicationBoard,
    StudentTeacher,
    User,
)
from src.aac_app.services.audit_service import audit_service
from src.aac_app.services.auth_service import get_password_hash, verify_password
from src.aac_app.services.lockout_service import lockout_service
from src.api import schemas
from src.api.deps import get_current_active_user, get_current_admin_user, get_db
from src.api.routers.auth_helpers import (
    conditional_limiter,
    validate_email_format,
    validate_password_strength,
)

router = APIRouter()

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
    validate_email_format(user.email)

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

@router.get("/users", response_model=list[schemas.UserResponse])
def get_users(
    skip: int = 0,
    limit: int = 100,
    user_type: str | None = None,
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


@router.get(
    "/users/student-summaries",
    response_model=list[schemas.StudentBoardSummaryResponse],
)
def get_student_summaries(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Return visible students and assigned boards without per-student requests."""
    if current_user.user_type not in {"admin", "teacher"}:
        raise HTTPException(status_code=403, detail="Not authorized to view user list")

    query = db.query(User).filter(User.user_type == "student")
    if current_user.user_type == "teacher":
        assignment_count = (
            db.query(StudentTeacher)
            .filter(StudentTeacher.teacher_id == current_user.id)
            .count()
        )
        if assignment_count:
            query = (
                query.join(
                    StudentTeacher,
                    StudentTeacher.student_id == User.id,
                )
                .filter(StudentTeacher.teacher_id == current_user.id)
                .distinct()
            )

    students = (
        query.order_by(User.id)
        .offset(max(skip, 0))
        .limit(min(max(limit, 1), 500))
        .all()
    )
    student_ids = [student.id for student in students]
    if not student_ids:
        return []

    assignments = (
        db.query(BoardAssignment)
        .filter(BoardAssignment.student_id.in_(student_ids))
        .order_by(BoardAssignment.id)
        .all()
    )
    board_ids_by_student: dict[int, list[int]] = {}
    all_board_ids: set[int] = set()
    for assignment in assignments:
        student_board_ids = board_ids_by_student.setdefault(assignment.student_id, [])
        if assignment.board_id not in student_board_ids:
            student_board_ids.append(assignment.board_id)
            all_board_ids.add(assignment.board_id)

    boards_by_id = {}
    if all_board_ids:
        boards = (
            db.query(CommunicationBoard)
            .filter(CommunicationBoard.id.in_(all_board_ids))
            .all()
        )
        boards_by_id = {board.id: board for board in boards}

    return [
        schemas.StudentBoardSummaryResponse(
            id=student.id,
            username=student.username,
            email=student.email,
            display_name=student.display_name,
            user_type=student.user_type,
            is_active=student.is_active,
            created_at=student.created_at,
            assigned_boards=[
                schemas.BoardSummaryResponse(
                    id=boards_by_id[board_id].id,
                    user_id=boards_by_id[board_id].user_id,
                    name=boards_by_id[board_id].name,
                    description=boards_by_id[board_id].description,
                    category=boards_by_id[board_id].category,
                    is_public=boards_by_id[board_id].is_public,
                    is_template=boards_by_id[board_id].is_template,
                    created_at=boards_by_id[board_id].created_at,
                    updated_at=boards_by_id[board_id].updated_at,
                    grid_rows=boards_by_id[board_id].grid_rows,
                    grid_cols=boards_by_id[board_id].grid_cols,
                    ai_enabled=boards_by_id[board_id].ai_enabled,
                    ai_provider=boards_by_id[board_id].ai_provider,
                    ai_model=boards_by_id[board_id].ai_model,
                    locale=boards_by_id[board_id].locale,
                    is_language_learning=boards_by_id[board_id].is_language_learning,
                )
                for board_id in board_ids_by_student.get(student.id, [])
                if board_id in boards_by_id
            ],
        )
        for student in students
    ]


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
    lockout_service.unlock_account(db, username, current_user.username)

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
