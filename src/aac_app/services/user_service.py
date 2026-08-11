from sqlalchemy.orm import Session

from src.aac_app.models import StudentTeacher, User, UserSettings
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.services.credential_service import mark_credentials_changed
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
        return (
            db.query(User)
            .join(StudentTeacher, User.id == StudentTeacher.student_id)
            .filter(StudentTeacher.teacher_id == teacher_id)
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

    def update_user(self, db: Session, user_id: int, update_data: schemas.UserUpdate):
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        if update_data.display_name:
            user.display_name = update_data.display_name
        if update_data.email:
            user.email = update_data.email

        if update_data.settings:
            if not user.settings:
                user.settings = UserSettings(user_id=user_id)
                db.add(user.settings)

            # Update settings fields
            settings_dict = update_data.settings.model_dump(exclude_unset=True)
            for key, value in settings_dict.items():
                setattr(user.settings, key, value)

        # The calling route owns the final commit. Flush here so callers
        # receive database-generated values without splitting the update into
        # a second transaction.
        db.flush()
        db.refresh(user)
        return user
