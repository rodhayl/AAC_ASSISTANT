from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.aac_app.models.database import StudentTeacher, User
from src.aac_app.services.user_service import UserService
from src.api.dependencies import get_current_active_user, get_db
from src.api.schemas import ResetPasswordRequest, StudentAssignRequest, UserCreate, UserResponse, UserUpdate

router = APIRouter()
user_service = UserService()


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user info"""
    return current_user


@router.put("/me", response_model=UserResponse)
def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update current user profile/settings"""
    return user_service.update_user(db, current_user.id, user_update)


@router.get("/students", response_model=List[UserResponse])
def get_students(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """Get all students (or assigned students for teachers)"""
    if current_user.user_type == "admin":
        return user_service.get_all_students(db)
    elif current_user.user_type == "teacher":
        return user_service.get_assigned_students(db, current_user.id)
    else:
        # Students can only see themselves? Or no access?
        # For now, return self if student
        if current_user.user_type == "student":
            return [current_user]
        return []


@router.post("/students", response_model=UserResponse)
def create_student(
    user: UserCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a new student"""
    if current_user.user_type not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Not authorized to create students")

    # Force user_type to student
    user.user_type = "student"

    # If teacher, automatically assign
    if current_user.user_type == "teacher":
        user.created_by_teacher_id = current_user.id

    return user_service.create_user(db, user)


@router.post("/assign-student")
def assign_student(
    data: StudentAssignRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Assign a student to a teacher (Admin/Teacher only)"""
    if current_user.user_type not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # If teacher, can only assign to self
    target_teacher_id = data.teacher_id

    if current_user.user_type == "teacher" and target_teacher_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Teachers can only assign students to themselves"
        )

    # Check if student exists
    student = db.query(User).filter_by(id=data.student_id, user_type="student").first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Check if teacher exists
    teacher = db.query(User).filter_by(id=target_teacher_id, user_type="teacher").first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # Check if assignment exists
    exists = (
        db.query(StudentTeacher)
        .filter_by(student_id=data.student_id, teacher_id=target_teacher_id)
        .first()
    )
    if exists:
        return {"message": "Already assigned", "status": "exists"}

    # Create assignment
    assignment = StudentTeacher(student_id=data.student_id, teacher_id=target_teacher_id)
    db.add(assignment)
    db.commit()
    return JSONResponse(
        status_code=201,
        content={"message": "Student assigned successfully", "status": "created"}
    )


@router.delete("/assign-student/{student_id}/{teacher_id}")
def unassign_student(
    student_id: int,
    teacher_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Unassign a student from a teacher (Admin/Teacher only)"""
    if current_user.user_type not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    if current_user.user_type == "teacher" and teacher_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Teachers can only unassign students from themselves"
        )

    # Check if assignment exists
    assignment = (
        db.query(StudentTeacher)
        .filter_by(student_id=student_id, teacher_id=teacher_id)
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()
    return {"message": "Assignment removed successfully"}


@router.post("/reset-password")
def reset_user_password(
    data: ResetPasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Reset user password (Admin can reset any, Teacher can reset assigned students)"""
    if current_user.user_type not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Determine user_id from payload (support both user_id and legacy student_id)
    target_user_id = data.user_id if data.user_id is not None else data.student_id

    if target_user_id is None:
        raise HTTPException(status_code=400, detail="user_id or student_id is required")

    # Fetch user
    user = db.query(User).filter(User.id == target_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Permission check
    if current_user.user_type == "admin":
        # Admin can reset anyone
        pass
    elif current_user.user_type == "teacher":
        # Teacher can only reset assigned students
        if user.user_type != "student":
            raise HTTPException(
                status_code=403, detail="Teachers can only reset student passwords"
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
                status_code=403, detail="Student is not assigned to this teacher"
            )

    # Reset password
    user_service.reset_password(db, target_user_id, data.new_password)
    return {"message": "Password reset successfully"}
