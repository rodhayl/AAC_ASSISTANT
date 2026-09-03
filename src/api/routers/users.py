
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.aac_app.models import StudentTeacher, User
from src.aac_app.services.user_service import UserService
from src.api.deps import get_current_active_user, get_db, get_request_text, get_text
from src.api.routers.auth_helpers import (
    apply_student_safety_at_creation,
    ensure_username_email_available,
    validate_email_format,
    validate_password_strength,
)
from src.api.schemas import (
    ResetPasswordRequest,
    StaffStudentCreate,
    StudentAssignRequest,
    UserResponse,
)

router = APIRouter()
user_service = UserService()


@router.get("/students", response_model=list[UserResponse])
def get_students(
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get students (or assigned students for teachers), paginated."""
    if current_user.user_type == "admin":
        return user_service.get_all_students(db, skip=skip, limit=limit)
    elif current_user.user_type == "teacher":
        return user_service.get_assigned_students(
            db, current_user.id, skip=skip, limit=limit
        )
    else:
        # Students can only see themselves? Or no access?
        # For now, return self if student
        if current_user.user_type == "student":
            return [current_user]
        return []


@router.post("/students", response_model=UserResponse)
def create_student(
    request: Request,
    user: StaffStudentCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a new student"""
    if current_user.user_type not in ["admin", "teacher"]:
        raise HTTPException(
            status_code=403,
            detail=get_request_text(request, "errors.users.unauthorizedCreateStudents", user=current_user),
        )

    # Force user_type to student
    user.user_type = "student"

    validate_password_strength(user.password, user=current_user)
    validate_email_format(user.email, user=current_user)
    ensure_username_email_available(db, user.username, user.email, user=current_user)

    # Teachers always assign students to themselves. Admins may optionally
    # provide an assignment target, but it must be an active teacher rather
    # than an arbitrary user ID.
    if current_user.user_type == "teacher":
        user.created_by_teacher_id = current_user.id
    elif user.created_by_teacher_id is not None:
        teacher = (
            db.query(User)
            .filter(
                User.id == user.created_by_teacher_id,
                User.user_type == "teacher",
                User.is_active.is_(True),
            )
            .first()
        )
        if teacher is None:
            raise HTTPException(
                status_code=404,
                detail=get_text(user=current_user, key="errors.users.teacherNotFound"),
            )

    created = user_service.create_user(db, user)
    # Optional one-step safety configuration: age, filter level, forbidden
    # topics/words and feature gates land in the guardian profile inside the
    # same transaction as the user row (teacher lock rules still apply).
    apply_student_safety_at_creation(db, created, user.safety, current_user)
    # Commit before responding: the UI re-fetches the student list right
    # after this create, and the request dependency's teardown commit runs
    # only after the response is sent.
    db.commit()
    return created


@router.post("/assign-student")
def assign_student(
    request: Request,
    data: StudentAssignRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Assign a student to a teacher (Admin/Teacher only)"""
    if current_user.user_type not in ["admin", "teacher"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.unauthorized"),
        )

    # If teacher, can only assign to self
    target_teacher_id = data.teacher_id

    if current_user.user_type == "teacher" and target_teacher_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=get_request_text(request, "errors.users.assignOnlySelf", user=current_user),
        )

    # Check if student exists
    student = db.query(User).filter_by(id=data.student_id, user_type="student").first()
    if not student:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.users.studentNotFound"),
        )

    # Check if teacher exists
    teacher = db.query(User).filter_by(id=target_teacher_id, user_type="teacher").first()
    if not teacher:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.users.teacherNotFound"),
        )

    # Check if assignment exists
    exists = (
        db.query(StudentTeacher)
        .filter_by(student_id=data.student_id, teacher_id=target_teacher_id)
        .first()
    )
    if exists:
        return {"message": get_text(user=current_user, key="assignmentAlreadyExists"), "status": "exists"}

    # Create assignment. The database uniqueness constraint closes the race
    # between the existence check above and the insert; a concurrent request
    # that loses that race is still an idempotent success for the caller.
    assignment = StudentTeacher(student_id=data.student_id, teacher_id=target_teacher_id)
    try:
        db.add(assignment)
        db.commit()
    except IntegrityError:
        db.rollback()
        if not (
            db.query(StudentTeacher)
            .filter_by(student_id=data.student_id, teacher_id=target_teacher_id)
            .first()
        ):
            raise
        return {
            "message": get_text(user=current_user, key="assignmentAlreadyExists"),
            "status": "exists",
        }

    return JSONResponse(
        status_code=201,
        content={"message": get_text(user=current_user, key="studentAssigned"), "status": "created"}
    )


@router.delete("/assign-student/{student_id}/{teacher_id}")
def unassign_student(
    request: Request,
    student_id: int,
    teacher_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Unassign a student from a teacher (Admin/Teacher only)"""
    if current_user.user_type not in ["admin", "teacher"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.unauthorized"),
        )

    if current_user.user_type == "teacher" and teacher_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=get_request_text(request, "errors.users.unassignOnlySelf", user=current_user),
        )

    # Check if assignment exists
    assignment = (
        db.query(StudentTeacher)
        .filter_by(student_id=student_id, teacher_id=teacher_id)
        .first()
    )
    if not assignment:
        raise HTTPException(
            status_code=404,
            detail=get_text(
                user=current_user, key="errors.users.assignmentNotFound"
            ),
        )

    db.delete(assignment)
    db.commit()
    return {"message": get_text(user=current_user, key="assignmentRemoved")}


@router.post("/reset-password")
def reset_user_password(
    request: Request,
    data: ResetPasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Reset user password (Admin can reset any, Teacher can reset assigned students)"""
    if current_user.user_type not in ["admin", "teacher"]:
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.unauthorized"),
        )

    # Determine user_id from payload (support both user_id and legacy student_id)
    target_user_id = data.user_id if data.user_id is not None else data.student_id

    if target_user_id is None:
        raise HTTPException(
            status_code=400,
            detail=get_request_text(request, "errors.users.studentIdRequired", user=current_user),
        )

    # Fetch user
    user = db.query(User).filter(User.id == target_user_id).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.userNotFound"),
        )

    # Permission check
    if current_user.user_type == "admin":
        # Admin can reset anyone *except themselves*: resetting your own
        # password here bypasses the current-password check that
        # /auth/change-password enforces (mirroring the self-delete guard).
        if target_user_id == current_user.id:
            raise HTTPException(
                status_code=400,
                detail=get_request_text(request, "errors.users.cannotResetOwnPassword", user=current_user),
            )
    elif current_user.user_type == "teacher":
        # Teacher can only reset assigned students
        if user.user_type != "student":
            raise HTTPException(
                status_code=403,
                detail=get_request_text(request, "errors.users.resetOnlyStudents", user=current_user),
            )

        # Check assignment
        assignment = (
            db.query(StudentTeacher)
            .filter(
                StudentTeacher.teacher_id == current_user.id,
                StudentTeacher.student_id == target_user_id,
            )
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=403,
                detail=get_request_text(request, "errors.users.notAssignedToTeacher", user=current_user),
            )

    validate_password_strength(data.new_password, user=current_user)

    # Reset password
    user_service.reset_password(db, target_user_id, data.new_password)
    # Commit before responding so a login with the new password (which
    # follows this response in the UI flow) cannot read the old hash.
    db.commit()
    return {"message": get_text(user=current_user, key="passwordResetSuccessfully")}
