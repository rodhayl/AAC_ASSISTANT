from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from src.aac_app.models import (
    Achievement,
    AppSettings,
    BoardAssignment,
    BoardSymbol,
    CollaborationSession,
    CommunicationBoard,
    FailedLoginAttempt,
    GuardianProfile,
    GuardianProfileHistory,
    LearningMode,
    LearningPlan,
    LearningSession,
    LearningTask,
    Notification,
    SavedTopic,
    StudentTeacher,
    SymbolUsageLog,
    User,
    UserAchievement,
    UserProgress,
    UserSettings,
)
from src.aac_app.services.audit_service import audit_service
from src.aac_app.services.auth_service import get_password_hash, verify_password
from src.aac_app.services.credential_service import mark_credentials_changed
from src.aac_app.services.lockout_service import lockout_service
from src.api import schemas
from src.api.deps import (
    STAFF_USER_TYPES,
    authorize_user_access,
    get_current_active_user,
    get_current_admin_user,
    get_db,
    get_request_text,
    get_text,
)
from src.api.routers.auth_helpers import (
    apply_student_safety_at_creation,
    conditional_limiter,
    ensure_username_email_available,
    validate_email_format,
    validate_password_strength,
)

router = APIRouter()

@router.post("/admin/create-user", response_model=schemas.UserResponse)
def admin_create_user(
    request: Request,
    user: schemas.StaffStudentCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Create a new user account with any role (admin only).

    Only administrators can use this endpoint to create teacher or admin accounts.
    Enforces password strength requirements.
    """
    logger.info(f"Admin '{current_user.username}' creating user '{user.username}' with type '{user.user_type}'")

    accept_language = request.headers.get("accept-language")

    # Validate password strength using shared validation function
    validate_password_strength(
        user.password,
        accept_language=accept_language,
        user=current_user,
    )

    # Validate email format if provided
    validate_email_format(
        user.email,
        accept_language=accept_language,
        user=current_user,
    )

    # Validate password confirmation for admin-created users
    if not user.confirm_password:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user,
                accept_language=accept_language,
                key="errors.auth.passwordConfirmationRequired",
            ),
        )

    if user.password != user.confirm_password:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user,
                accept_language=accept_language,
                key="errors.auth.passwordsDoNotMatch",
            ),
        )

    # Validate user_type
    valid_types = ("student", "teacher", "admin")
    if user.user_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user,
                accept_language=accept_language,
                key="errors.auth.invalidUserType",
                types=", ".join(valid_types),
            ),
        )

    ensure_username_email_available(
        db,
        user.username,
        user.email,
        accept_language=accept_language,
        user=current_user,
    )

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
    db.flush()
    db.refresh(new_user)

    # Log admin action and account creation; the request dependency commits
    # the user and its audit entries atomically after the handler returns.
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

    # Optional one-step safety configuration for students (age, filter level,
    # forbidden topics/words, feature gates). Admins may set admin-locked
    # fields; the payload is ignored for non-student roles.
    apply_student_safety_at_creation(db, new_user, user.safety, current_user)

    # Commit before responding: FastAPI resumes this yield dependency's
    # teardown after the response is sent, so a follow-up request could
    # otherwise read the new user before the create transaction commits.
    db.commit()
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
    skip: int = Query(0, ge=0, le=100_000),
    limit: int = Query(100, ge=1, le=1000),
    user_type: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all users (Admin/Teacher only)"""
    if current_user.user_type == 'student':
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.auth.unauthorizedUserList"
            ),
        )

    allowed_types = {"student", "teacher", "admin"}
    if user_type is not None and user_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.auth.invalidUserTypeFilter"),
        )

    # Teachers can only view their assigned students
    if current_user.user_type == "teacher":
        if user_type is not None and user_type != "student":
            return []
        query = (
            db.query(User)
            .join(StudentTeacher, User.id == StudentTeacher.student_id)
            .filter(StudentTeacher.teacher_id == current_user.id)
            .filter(User.user_type == "student")
            .distinct()
        )
        return query.order_by(User.id).offset(skip).limit(limit).all()

    # Admin: all users, optionally filtered by role
    query = db.query(User)
    if user_type is not None:
        query = query.filter(User.user_type == user_type)
    return query.order_by(User.id).offset(skip).limit(limit).all()


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
    if current_user.user_type not in STAFF_USER_TYPES:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.auth.unauthorizedUserList"
            ),
        )

    query = db.query(User).filter(User.user_type == "student")
    if current_user.user_type == "teacher":
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
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.userNotFound"),
        )

    authorize_user_access(
        target_user=user,
        current_user=current_user,
        db=db,
        forbidden_detail=get_text(
            user=current_user, key="errors.auth.unauthorizedUserView"
        ),
    )

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

    accept_language = request.headers.get("accept-language")

    # If it's the user themselves
    if current_user.username == payload.username:
        if not verify_password(payload.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=401,
                detail=get_text(
                    user=current_user,
                    accept_language=accept_language,
                    key="errors.auth.currentPasswordIncorrect",
                ),
            )
    else:
        # This endpoint changes only the authenticated user's password. Admins
        # and teachers use the separately authorized reset-password route.
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user,
                accept_language=accept_language,
                key="errors.auth.cannotChangeOtherUserPassword",
            ),
        )

    # Validate new password strength using shared validation function
    validate_password_strength(
        payload.new_password,
        accept_language=accept_language,
        user=current_user,
    )

    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user,
                accept_language=accept_language,
                key="errors.auth.passwordsDoNotMatch",
            ),
        )

    # Use the authenticated identity rather than re-querying by client input.
    user = current_user
    user.password_hash = get_password_hash(payload.new_password)
    mark_credentials_changed(user)
    db.add(user)
    db.flush()

    # Log password change in the same request transaction.
    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_password_changed(
        db=db,
        user_id=user.id,
        username=user.username,
        changed_by_admin=False,
        ip_address=client_ip
    )

    # Commit before responding so a re-login with the new password (which
    # follows this response in the UI flow) cannot read the old hash.
    db.commit()
    logger.info(f"Password changed for user '{user.username}' (id={user.id})")
    return {"ok": True}

@router.put("/users/{user_id}", response_model=schemas.UserResponse)
def update_user(
    request: Request,
    user_id: int,
    payload: dict,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Update user fields (admin only)"""
    # Note: using get_current_admin_user enforces admin check

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.userNotFound"),
        )

    # The admin edit contract accepts a raw dict, so validate the fields that
    # affect role checks and uniqueness before mutating the row. This keeps the
    # endpoint consistent with admin_create_user and update_profile, which
    # already reject invalid roles and duplicate emails.
    valid_types = ("student", "teacher", "admin")
    if "user_type" in payload and payload.get("user_type") not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=get_request_text(
                request,
                "errors.auth.invalidUserType",
                user=current_user,
                types=", ".join(valid_types),
            ),
        )

    # Never allow demoting or deactivating the last active administrator:
    # doing so would leave the application without any admin account and
    # force it back into first-run setup with no way to manage users.
    if user.user_type == "admin":
        would_leave_admin = (
            ("user_type" in payload and payload.get("user_type") != "admin")
            or ("is_active" in payload and payload.get("is_active") is False)
        )
        if would_leave_admin:
            other_active_admins = (
                db.query(User)
                .filter(
                    User.user_type == "admin",
                    User.is_active.is_(True),
                    User.id != user_id,
                )
                .count()
            )
            if other_active_admins == 0:
                raise HTTPException(
                    status_code=400,
                    detail=get_request_text(request, "errors.auth.lastAdminRequired", user=current_user),
                )

    # Mirror the profile-update contract: a blank display name is rejected so
    # admins cannot accidentally leave a user with an invisible name.
    if 'display_name' in payload:
        display_name = (payload.get('display_name') or '').strip()
        if not display_name:
            raise HTTPException(
                status_code=400,
            detail=get_request_text(request, "errors.auth.displayNameRequired", user=current_user),
            )

    new_email = payload.get('email')
    if new_email is not None and new_email != user.email:
        # An empty string from the editor means "clear the optional email".
        # Normalize it to None so the row stores NULL like an account created
        # without an email, matching update_profile's clear semantics.
        if isinstance(new_email, str):
            new_email = new_email.strip() or None
        if new_email is not None:
            validate_email_format(
                new_email,
                user=current_user,
                accept_language=request.headers.get("accept-language"),
            )
            if db.query(User).filter(User.email == new_email, User.id != user.id).first():
                raise HTTPException(
                    status_code=400,
                    detail=get_request_text(request, "errors.auth.emailTaken", user=current_user),
                )

    if 'is_active' in payload and not isinstance(payload['is_active'], bool):
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.auth.activeMustBeBoolean"),
        )

    # Allowed fields
    for key in ["display_name", "user_type", "email", "is_active"]:
        if key in payload:
            setattr(user, key, new_email if key == "email" else payload[key])
    db.add(user)
    db.flush()
    db.commit()
    db.refresh(user)
    return user

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Delete a user and all data owned by that account (admin only)."""
    if current_user.id == user_id:
        raise HTTPException(
            status_code=400,
            detail=get_request_text(request, "errors.auth.cannotDeleteOwnAccount", user=current_user),
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.userNotFound"),
        )

    # Deleting the last active administrator would strand the application in
    # first-run setup with no account able to manage users or re-create an
    # admin. Reject the operation instead of allowing a dead-end state.
    if user.user_type == "admin" and user.is_active:
        other_active_admins = (
            db.query(User)
            .filter(
                User.user_type == "admin",
                User.is_active.is_(True),
                User.id != user_id,
            )
            .count()
        )
        if other_active_admins == 0:
            raise HTTPException(
                status_code=400,
                detail=get_request_text(request, "errors.auth.lastAdminRequired", user=current_user),
            )

    # Delete dependent rows explicitly instead of relying on ORM relationship
    # synchronization. Several legacy relationships have non-null foreign
    # keys, so ``db.delete(user)`` would otherwise try to set them to NULL and
    # fail before the account is removed.
    owned_board_ids = [
        board_id
        for (board_id,) in db.query(CommunicationBoard.id)
        .filter(CommunicationBoard.user_id == user_id)
        .all()
    ]
    if owned_board_ids:
        db.execute(
            delete(BoardAssignment).where(
                BoardAssignment.board_id.in_(owned_board_ids)
            )
        )
        db.execute(
            update(BoardSymbol)
            .where(BoardSymbol.linked_board_id.in_(owned_board_ids))
            .values(linked_board_id=None)
        )
        db.execute(
            delete(BoardSymbol).where(BoardSymbol.board_id.in_(owned_board_ids))
        )
        db.execute(
            delete(CommunicationBoard).where(
                CommunicationBoard.id.in_(owned_board_ids)
            )
        )

    # Remove user relationships and clear nullable attribution fields on
    # records that remain visible to other users.
    db.execute(
        delete(BoardAssignment).where(BoardAssignment.student_id == user_id)
    )
    db.execute(
        update(BoardAssignment)
        .where(BoardAssignment.assigned_by == user_id)
        .values(assigned_by=None)
    )
    db.execute(
        delete(StudentTeacher).where(
            (StudentTeacher.student_id == user_id)
            | (StudentTeacher.teacher_id == user_id)
        )
    )

    profile_ids = [
        profile_id
        for (profile_id,) in db.query(GuardianProfile.id)
        .filter(GuardianProfile.user_id == user_id)
        .all()
    ]
    if profile_ids:
        db.execute(
            delete(GuardianProfileHistory).where(
                GuardianProfileHistory.profile_id.in_(profile_ids)
            )
        )
        db.execute(
            delete(GuardianProfile).where(GuardianProfile.id.in_(profile_ids))
        )
    db.execute(
        update(GuardianProfile)
        .where(GuardianProfile.created_by == user_id)
        .values(created_by=current_user.id)
    )
    db.execute(
        update(GuardianProfile)
        .where(GuardianProfile.updated_by == user_id)
        .values(updated_by=None)
    )
    db.execute(
        update(GuardianProfileHistory)
        .where(GuardianProfileHistory.changed_by == user_id)
        .values(changed_by=current_user.id)
    )

    learning_session_ids = [
        session_id
        for (session_id,) in db.query(LearningSession.id)
        .filter(LearningSession.user_id == user_id)
        .all()
    ]
    if learning_session_ids:
        db.execute(
            delete(SymbolUsageLog).where(
                SymbolUsageLog.session_id.in_(learning_session_ids)
            )
        )
        db.execute(
            delete(LearningSession).where(
                LearningSession.id.in_(learning_session_ids)
            )
        )
    db.execute(delete(SymbolUsageLog).where(SymbolUsageLog.user_id == user_id))

    learning_plan_ids = [
        plan_id
        for (plan_id,) in db.query(LearningPlan.id)
        .filter(LearningPlan.user_id == user_id)
        .all()
    ]
    if learning_plan_ids:
        db.execute(
            delete(LearningTask).where(LearningTask.plan_id.in_(learning_plan_ids))
        )
        db.execute(delete(LearningPlan).where(LearningPlan.id.in_(learning_plan_ids)))

    db.execute(delete(UserAchievement).where(UserAchievement.user_id == user_id))
    db.execute(delete(UserProgress).where(UserProgress.user_id == user_id))
    db.execute(delete(Notification).where(Notification.user_id == user_id))
    db.execute(delete(UserSettings).where(UserSettings.user_id == user_id))
    # A teacher's saved topics belong to their account; deleting the account
    # must not orphan them (they would linger in the admin scope=all view and
    # dangle their creator FK). Clear the nullable creator reference first so
    # topics another author saved through this user are never attributed to a
    # deleted account.
    db.execute(
        update(SavedTopic)
        .where(SavedTopic.created_by_user_id == user_id)
        .values(created_by_user_id=None)
    )
    db.execute(delete(SavedTopic).where(SavedTopic.user_id == user_id))

    # These records can remain useful after their author is removed, so clear
    # nullable attribution or target fields rather than deleting shared data.
    db.execute(
        update(LearningMode)
        .where(LearningMode.created_by == user_id)
        .values(created_by=None)
    )
    db.execute(
        update(Achievement)
        .where(Achievement.created_by == user_id)
        .values(created_by=None)
    )
    db.execute(
        update(Achievement)
        .where(Achievement.target_user_id == user_id)
        .values(target_user_id=None)
    )
    db.execute(
        update(AppSettings)
        .where(AppSettings.updated_by == user_id)
        .values(updated_by=None)
    )
    db.execute(
        delete(CollaborationSession).where(
            CollaborationSession.host_user_id == user_id
        )
    )

    # Remove lockout rows before deleting the account. Otherwise a later
    # account with the same username could inherit stale failed-login attempts
    # from this deleted account.
    db.execute(
        delete(FailedLoginAttempt).where(
            FailedLoginAttempt.username == user.username
        )
    )

    # Use a Core DELETE after dependents are handled so SQLAlchemy does not
    # synchronize already-loaded relationship collections by nulling required
    # foreign keys.
    db.execute(delete(User).where(User.id == user_id))
    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_admin_action(
        db=db,
        admin_id=current_user.id,
        admin_username=current_user.username,
        action="delete_user",
        description=f"Deleted {user.user_type} account '{user.username}' (id={user_id})",
        ip_address=client_ip,
        endpoint=f"/api/auth/users/{user_id}",
    )
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
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.userNotFound"),
        )

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
    return {
        "ok": True,
        "message": get_text(
            user=current_user,
            key="errors.auth.accountUnlocked",
            username=username,
        ),
    }

@router.put("/profile", response_model=schemas.UserResponse)
def update_profile(
    profile: schemas.UserProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile (display name, email)"""
    if profile.display_name is not None:
        display_name = profile.display_name.strip()
        if not display_name:
            raise HTTPException(
                status_code=400,
                detail=get_text(user=current_user, key="errors.auth.displayNameRequired"),
            )
        current_user.display_name = display_name

    # Pydantic keeps explicit null in model_fields_set. That distinction is
    # required here: null means "clear my optional email", while an omitted
    # field means "leave the existing email unchanged".
    if "email" in profile.model_fields_set:
        if profile.email is not None:
            existing = (
                db.query(User)
                .filter(User.email == profile.email, User.id != current_user.id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=get_text(user=current_user, key="errors.auth.emailInUse"),
                )
        current_user.email = profile.email

    db.flush()
    db.commit()
    db.refresh(current_user)
    logger.info(f"Updated profile for user {current_user.username}")
    return current_user
