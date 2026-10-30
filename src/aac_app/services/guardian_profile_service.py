"""
Guardian Profile Service

Manages hidden student profiles for Learning Companion personalization.
These profiles are only visible to teachers and admins, never to students.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from ..models.database import (
    GuardianProfile,
    GuardianProfileHistory,
    StudentTeacher,
    User,
    get_session,
)
from .template_manager import get_template_manager


class GuardianProfileService:
    """
    Service for managing guardian profiles.

    Guardian profiles allow teachers and admins to configure the Learning
    Companion's personality and behavior for individual students without
    the student seeing these configurations.

    Features:
    - Template-based defaults with per-student overrides
    - Full audit trail of changes
    - Safety constraints and content filtering
    - Medical/accessibility context (never sent to LLM)
    """

    def __init__(self):
        self.template_manager = get_template_manager()

    def get_profile(
        self, student_id: int, db: Optional[Session] = None
    ) -> Optional[Dict]:
        """
        Get a student's guardian profile.

        Args:
            student_id: The student's user ID
            db: Optional database session (creates one if not provided)

        Returns:
            Profile dict or None if not found
        """

        def _get(session: Session) -> Optional[Dict]:
            profile = (
                session.query(GuardianProfile)
                .filter_by(user_id=student_id, is_active=True)
                .first()
            )

            if not profile:
                return None

            return self._profile_to_dict(profile)

        if db:
            return _get(db)

        with get_session() as session:
            return _get(session)

    def get_or_create_profile(
        self, student_id: int, created_by: int, db: Optional[Session] = None
    ) -> Dict:
        """
        Get a student's profile, creating a default one if it doesn't exist.

        Args:
            student_id: The student's user ID
            created_by: ID of the teacher/admin creating the profile
            db: Optional database session

        Returns:
            Profile dict
        """

        def _get_or_create(session: Session) -> Dict:
            profile = (
                session.query(GuardianProfile).filter_by(user_id=student_id).first()
            )

            if not profile:
                profile = GuardianProfile(
                    user_id=student_id,
                    template_name="default",
                    created_by=created_by,
                )
                session.add(profile)
                session.flush()
                logger.info(f"Created guardian profile for student {student_id}")

            return self._profile_to_dict(profile)

        if db:
            return _get_or_create(db)

        with get_session() as session:
            return _get_or_create(session)

    def update_profile(
        self,
        student_id: int,
        updated_by: int,
        changes: Dict[str, Any],
        change_reason: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict:
        """
        Update a student's guardian profile.

        Args:
            student_id: The student's user ID
            updated_by: ID of the teacher/admin making changes
            changes: Dict of fields to update
            change_reason: Optional reason for the change (for audit)
            db: Optional database session

        Returns:
            Updated profile dict
        """

        def _update(session: Session) -> Dict:
            profile = (
                session.query(GuardianProfile).filter_by(user_id=student_id).first()
            )

            if not profile:
                # Create new profile with the changes
                profile = GuardianProfile(
                    user_id=student_id,
                    created_by=updated_by,
                )
                session.add(profile)
                session.flush()

            # Track changes for audit
            for field, new_value in changes.items():
                if not hasattr(profile, field):
                    continue

                old_value = getattr(profile, field)

                # Skip if value hasn't changed
                if old_value == new_value:
                    continue

                # Record history
                history_entry = GuardianProfileHistory(
                    profile_id=profile.id,
                    field_name=field,
                    old_value=json.dumps(old_value) if old_value is not None else None,
                    new_value=json.dumps(new_value) if new_value is not None else None,
                    changed_by=updated_by,
                    change_reason=change_reason,
                )
                session.add(history_entry)

                # Apply change
                setattr(profile, field, new_value)

            profile.updated_by = updated_by
            profile.updated_at = datetime.now()

            session.flush()
            logger.info(f"Updated guardian profile for student {student_id}")

            return self._profile_to_dict(profile)

        if db:
            return _update(db)

        with get_session() as session:
            return _update(session)

    def delete_profile(
        self, student_id: int, deleted_by: int, db: Optional[Session] = None
    ) -> bool:
        """
        Soft-delete a student's guardian profile.

        Args:
            student_id: The student's user ID
            deleted_by: ID of the admin deleting the profile
            db: Optional database session

        Returns:
            True if deleted, False if not found
        """

        def _delete(session: Session) -> bool:
            profile = (
                session.query(GuardianProfile).filter_by(user_id=student_id).first()
            )

            if not profile:
                return False

            # Soft delete
            profile.is_active = False
            profile.updated_by = deleted_by
            profile.updated_at = datetime.now()

            # Record deletion in history
            history_entry = GuardianProfileHistory(
                profile_id=profile.id,
                field_name="is_active",
                old_value="true",
                new_value="false",
                changed_by=deleted_by,
                change_reason="Profile deleted",
            )
            session.add(history_entry)
            session.flush()

            logger.info(f"Deleted guardian profile for student {student_id}")
            return True

        if db:
            return _delete(db)

        with get_session() as session:
            return _delete(session)

    def get_profile_history(
        self, student_id: int, limit: int = 50, db: Optional[Session] = None
    ) -> List[Dict]:
        """
        Get the change history for a student's profile.

        Args:
            student_id: The student's user ID
            limit: Maximum number of history entries to return
            db: Optional database session

        Returns:
            List of history entries
        """

        def _get_history(session: Session) -> List[Dict]:
            profile = (
                session.query(GuardianProfile).filter_by(user_id=student_id).first()
            )

            if not profile:
                return []

            entries = (
                session.query(GuardianProfileHistory)
                .filter_by(profile_id=profile.id)
                .order_by(GuardianProfileHistory.changed_at.desc())
                .limit(limit)
                .all()
            )

            result = []
            for entry in entries:
                changer = session.get(User, entry.changed_by)
                result.append(
                    {
                        "id": entry.id,
                        "field_name": entry.field_name,
                        "old_value": (
                            json.loads(entry.old_value) if entry.old_value else None
                        ),
                        "new_value": (
                            json.loads(entry.new_value) if entry.new_value else None
                        ),
                        "changed_by": {
                            "id": changer.id if changer else None,
                            "display_name": (
                                changer.display_name if changer else "Unknown"
                            ),
                        },
                        "changed_at": (
                            entry.changed_at.isoformat() if entry.changed_at else None
                        ),
                        "change_reason": entry.change_reason,
                    }
                )

            return result

        if db:
            return _get_history(db)

        with get_session() as session:
            return _get_history(session)

    def resolve_effective_profile(
        self, student_id: int, db: Optional[Session] = None
    ) -> Dict:
        """
        Resolve the complete effective profile for a student.

        This merges the selected template with all student-specific overrides
        to create the final profile that will be used for LLM interactions.

        Args:
            student_id: The student's user ID
            db: Optional database session

        Returns:
            Complete resolved profile dict
        """

        def _resolve(session: Session) -> Dict:
            profile = (
                session.query(GuardianProfile)
                .filter_by(user_id=student_id, is_active=True)
                .first()
            )

            if not profile:
                # No profile - return default template
                return self.template_manager.get_template("default")

            # Build demographics from profile
            demographics = {}
            if profile.age:
                demographics["age"] = profile.age
            if profile.gender:
                demographics["gender"] = profile.gender

            # Resolve profile using template manager
            resolved = self.template_manager.resolve_profile(
                template_name=profile.template_name or "default",
                demographics=demographics if demographics else None,
                medical_context=profile.medical_context,
                communication_style=profile.communication_style,
                safety_constraints=profile.safety_constraints,
                companion_persona=profile.companion_persona,
                custom_instructions=profile.custom_instructions,
            )

            return resolved

        if db:
            return _resolve(db)

        with get_session() as session:
            return _resolve(session)

    def build_system_prompt(self, student_id: int, db: Optional[Session] = None) -> str:
        """
        Build the complete LLM system prompt for a student.

        This is the main method called by the LearningCompanionService
        to get the personalized system prompt for a student.

        Args:
            student_id: The student's user ID
            db: Optional database session

        Returns:
            Complete system prompt string
        """
        profile = self.resolve_effective_profile(student_id, db)
        return self.template_manager.build_system_prompt(profile)

    def list_students_with_profiles(
        self, teacher_id: Optional[int] = None, db: Optional[Session] = None
    ) -> List[Dict]:
        """
        List all students that have guardian profiles.

        Args:
            teacher_id: Optional filter for teacher's students (future: via assignments)
            db: Optional database session

        Returns:
            List of student info with profile status
        """

        def _list(session: Session) -> List[Dict]:
            # Get students
            query = session.query(User).filter_by(user_type="student", is_active=True)

            if teacher_id:
                assignment_count = (
                    session.query(StudentTeacher)
                    .filter(StudentTeacher.teacher_id == teacher_id)
                    .count()
                )
                if assignment_count > 0:
                    # Filter students assigned to this teacher
                    query = query.join(
                        StudentTeacher, User.id == StudentTeacher.student_id
                    ).filter(StudentTeacher.teacher_id == teacher_id)

            students = query.all()

            result = []
            for student in students:
                profile = (
                    session.query(GuardianProfile)
                    .filter_by(user_id=student.id, is_active=True)
                    .first()
                )

                result.append(
                    {
                        "id": student.id,
                        "username": student.username,
                        "display_name": student.display_name,
                        "has_profile": profile is not None,
                        "template_name": profile.template_name if profile else None,
                        "profile_created_at": (
                            profile.created_at.isoformat() if profile else None
                        ),
                    }
                )

            return result

        if db:
            return _list(db)

        with get_session() as session:
            return _list(session)

    def _profile_to_dict(self, profile: GuardianProfile) -> Dict:
        """Convert a GuardianProfile model to a dictionary."""
        return {
            "id": profile.id,
            "user_id": profile.user_id,
            "template_name": profile.template_name,
            "age": profile.age,
            "gender": profile.gender,
            "medical_context": profile.medical_context or {},
            "communication_style": profile.communication_style or {},
            "safety_constraints": profile.safety_constraints or {},
            "companion_persona": profile.companion_persona or {},
            "custom_instructions": profile.custom_instructions,
            "private_notes": profile.private_notes,
            "is_active": profile.is_active,
            "created_by": profile.created_by,
            "updated_by": profile.updated_by,
            "created_at": (
                profile.created_at.isoformat() if profile.created_at else None
            ),
            "updated_at": (
                profile.updated_at.isoformat() if profile.updated_at else None
            ),
        }

    def preview_system_prompt(
        self,
        template_name: str,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Preview what a system prompt would look like with given settings.

        Useful for teachers to see the effect of their configuration
        before saving it.

        Args:
            template_name: Template to use
            overrides: Optional overrides to preview

        Returns:
            Preview system prompt string
        """
        profile = self.template_manager.resolve_profile(
            template_name=template_name,
            overrides=overrides,
        )
        return self.template_manager.build_system_prompt(profile)


# Singleton instance
_guardian_service: Optional[GuardianProfileService] = None


def get_guardian_profile_service() -> GuardianProfileService:
    """Get the singleton GuardianProfileService instance."""
    global _guardian_service
    if _guardian_service is None:
        _guardian_service = GuardianProfileService()
    return _guardian_service
