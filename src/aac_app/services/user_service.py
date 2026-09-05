from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from src.aac_app.models import StudentTeacher, User
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.services.credential_service import mark_credentials_changed

if TYPE_CHECKING:
    # Annotation-only: importing src.api at runtime would couple the service
    # layer to the API package (whose __init__ loads all routers).
    from src.api import schemas


class UserService:
    def get_all_students(self, db: Session, skip: int = 0, limit: int = 500):
        return (
            db.query(User)
            .filter(User.user_type == "student")
            .order_by(User.id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_assigned_students(
        self, db: Session, teacher_id: int, skip: int = 0, limit: int = 500
    ):
        # Keep the roster scoped to actual students: an admin can promote a
        # user out of the student role (update_user), leaving a stale roster
        # row. Filtering by user_type here matches get_student_summaries and
        # /auth/users so promoted users never resurface in teacher lists.
        return (
            db.query(User)
            .join(StudentTeacher, User.id == StudentTeacher.student_id)
            .filter(StudentTeacher.teacher_id == teacher_id)
            .filter(User.user_type == "student")
            .order_by(User.id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create_user(self, db: Session, user: schemas.UserCreate):
        hashed_password = get_password_hash(user.password)
        db_user = User(
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            user_type=user.user_type,
            password_hash=hashed_password
        )
        # Keep account creation and the optional roster assignment in the
        # caller's transaction.  Committing the user first could leave a
        # partially-created account if assignment validation or persistence
        # failed; the route commits once after this returns.
        db.add(db_user)
        db.flush()

        if user.created_by_teacher_id:
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
                raise ValueError("created_by_teacher_id must identify an active teacher")

            assignment = StudentTeacher(
                student_id=db_user.id,
                teacher_id=teacher.id,
            )
            db.add(assignment)
            db.flush()

        return db_user

    def reset_password(self, db: Session, user_id: int, new_password: str):
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.password_hash = get_password_hash(new_password)
            mark_credentials_changed(user)
            db.flush()
