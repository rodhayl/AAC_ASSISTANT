from sqlalchemy.orm import Session
from src.aac_app.models.database import User, StudentTeacher, UserSettings
from src.aac_app.services.auth_service import get_password_hash
from src.api import schemas


class UserService:
    def get_all_students(self, db: Session):
        return db.query(User).filter(User.user_type == "student").all()

    def get_assigned_students(self, db: Session, teacher_id: int):
        return (
            db.query(User)
            .join(StudentTeacher, User.id == StudentTeacher.student_id)
            .filter(StudentTeacher.teacher_id == teacher_id)
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
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        if user.created_by_teacher_id:
            assignment = StudentTeacher(
                student_id=db_user.id,
                teacher_id=user.created_by_teacher_id
            )
            db.add(assignment)
            db.commit()

        return db_user

    def reset_password(self, db: Session, user_id: int, new_password: str):
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.password_hash = get_password_hash(new_password)
            db.commit()

    def reset_password_for_username(self, db: Session, username: str, new_password: str):
        user = db.query(User).filter(User.username == username).first()
        if user:
            user.password_hash = get_password_hash(new_password)
            db.commit()
            return True
        return False

    def update_user(self, db: Session, user_id: int, update_data: schemas.UserUpdate):
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
            
        if update_data.display_name:
            user.display_name = update_data.display_name
        if update_data.email:
            user.email = update_data.email
            
        if update_data.settings:
            # Check if settings exist, if not create
            if not user.settings:
                # Assuming UserSettings model requires user_id
                settings = UserSettings(user_id=user_id)
                db.add(settings)
                # Flush to associate?
                db.flush() 
                # SQLAlchemy should handle relationship update if user.settings is set?
                # user.settings = settings
                # Actually, if we add it, we might need to refresh user?
                # Or just assign to relationship.
                # If we used db.add(settings), user.settings might not update immediately in memory unless back_populates triggers.
                # Safe way:
                # user.settings = settings # This might fail if settings is not committed?
                # Let's rely on relationship loading or explicit assignment.
                pass
            
            # If settings was None, we created it. But user.settings might still be None in this session context?
            # Let's reload settings or ensure it's attached.
            if not user.settings:
                 user.settings = UserSettings(user_id=user_id)
                 db.add(user.settings)
            
            # Update settings fields
            settings_dict = update_data.settings.model_dump(exclude_unset=True)
            for key, value in settings_dict.items():
                setattr(user.settings, key, value)
                
        db.commit()
        db.refresh(user)
        return user
