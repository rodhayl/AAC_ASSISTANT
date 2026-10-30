"""
Guardian Profiles API Router

Provides endpoints for managing student learning companion profiles.
These profiles are ONLY visible to teachers and admins, never to students.

The guardian profile system allows teachers/admins to:
- Configure personalized AI companion behavior per student
- Set safety constraints and content filters
- Add medical/accessibility context
- Choose from pre-built templates or customize fully
- View audit history of profile changes
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models.database import StudentTeacher, User
from src.aac_app.services.guardian_profile_service import get_guardian_profile_service
from src.aac_app.services.template_manager import get_template_manager
from src.api import schemas
from src.api.dependencies import get_current_active_user, get_db, get_text

router = APIRouter(prefix="/api/guardian-profiles", tags=["guardian-profiles"])


def get_current_teacher_or_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Dependency that requires teacher or admin role."""
    if current_user.user_type not in ("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=get_text(
                user=current_user, key="errors.guardian.onlyTeachersAdmins"
            ),
        )
    return current_user


def verify_student_access(student_id: int, current_user: User, db: Session) -> User:
    """Verify the student exists and current user can access their profile."""
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

    # Verify teacher has access to this specific student
    assignment_count = (
        db.query(StudentTeacher)
        .filter(StudentTeacher.teacher_id == current_user.id)
        .count()
    )
    if assignment_count == 0:
        # Backward-compatible mode: if the teacher has no explicit roster yet,
        # allow access to students so profile setup can start.
        return student

    is_assigned = (
        db.query(StudentTeacher)
        .filter(
            StudentTeacher.teacher_id == current_user.id,
            StudentTeacher.student_id == student_id,
        )
        .first()
    )

    if not is_assigned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=get_text(
                user=current_user, key="errors.guardian.studentNotAssigned"
            ),
        )

    return student


# --- Template Endpoints ---


@router.get("/templates", response_model=List[schemas.TemplateInfo])
async def list_templates(current_user: User = Depends(get_current_teacher_or_admin)):
    """
    List all available personality templates.

    Templates are pre-configured personality profiles that can be used
    as a starting point for student configuration.
    """
    template_manager = get_template_manager()
    templates = template_manager.list_templates()
    return templates


@router.get("/templates/{template_name}")
async def get_template(
    template_name: str, current_user: User = Depends(get_current_teacher_or_admin)
):
    """
    Get full details of a specific template.

    Returns the complete template configuration including all
    communication style settings, safety constraints, etc.
    """
    template_manager = get_template_manager()

    if not template_manager.template_exists(template_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=get_text(
                user=current_user,
                key="errors.guardian.templateNotFound",
                name=template_name,
            ),
        )

    template = template_manager.get_template(template_name)
    return template


@router.post(
    "/templates/{template_name}/preview", response_model=schemas.SystemPromptPreview
)
async def preview_template(
    template_name: str,
    overrides: Optional[dict] = None,
    current_user: User = Depends(get_current_teacher_or_admin),
):
    """
    Preview what the system prompt would look like with this template.

    Optionally include overrides to see how customizations would affect
    the final prompt.
    """
    guardian_service = get_guardian_profile_service()

    prompt = guardian_service.preview_system_prompt(
        template_name=template_name, overrides=overrides
    )

    return schemas.SystemPromptPreview(template_name=template_name, prompt=prompt)


# --- Student List Endpoints ---


@router.get("/students", response_model=List[schemas.StudentWithProfileInfo])
async def list_students_with_profiles(
    current_user: User = Depends(get_current_teacher_or_admin),
    db: Session = Depends(get_db),
):
    """
    List all students with their profile status.

    Shows whether each student has a guardian profile configured
    and which template they're using.
    """
    guardian_service = get_guardian_profile_service()

    teacher_id = None
    if current_user.user_type == "teacher":
        teacher_id = current_user.id

    students = guardian_service.list_students_with_profiles(
        teacher_id=teacher_id, db=db
    )
    return students


# --- Profile CRUD Endpoints ---


@router.get("/students/{student_id}", response_model=schemas.GuardianProfileResponse)
async def get_student_profile(
    student_id: int,
    current_user: User = Depends(get_current_teacher_or_admin),
    db: Session = Depends(get_db),
):
    """
    Get a student's guardian profile.

    Returns the full profile configuration including template,
    customizations, and metadata.
    """
    verify_student_access(student_id, current_user, db)

    guardian_service = get_guardian_profile_service()
    profile = guardian_service.get_profile(student_id, db=db)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=get_text(
                user=current_user, key="errors.guardian.noProfileCreateFirst"
            ),
        )

    return profile


@router.post("/students/{student_id}", response_model=schemas.GuardianProfileResponse)
async def create_student_profile(
    student_id: int,
    profile_data: schemas.GuardianProfileCreate,
    current_user: User = Depends(get_current_teacher_or_admin),
    db: Session = Depends(get_db),
):
    """
    Create a guardian profile for a student.

    If a profile already exists, returns an error. Use PUT to update.
    """
    verify_student_access(student_id, current_user, db)

    guardian_service = get_guardian_profile_service()
    template_manager = get_template_manager()

    # Validate template name if provided
    if profile_data.template_name and not template_manager.template_exists(
        profile_data.template_name
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_text(
                user=current_user,
                key="errors.guardian.templateNotExist",
                name=profile_data.template_name,
            ),
        )

    # Check if profile already exists
    existing = guardian_service.get_profile(student_id, db=db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=get_text(user=current_user, key="errors.guardian.profileExists"),
        )

    # Build changes dict from the profile data
    changes = {}
    if profile_data.template_name:
        changes["template_name"] = profile_data.template_name
    if profile_data.age is not None:
        changes["age"] = profile_data.age
    if profile_data.gender:
        changes["gender"] = profile_data.gender
    if profile_data.medical_context:
        changes["medical_context"] = profile_data.medical_context.model_dump(
            exclude_none=True
        )
    if profile_data.communication_style:
        changes["communication_style"] = profile_data.communication_style.model_dump(
            exclude_none=True
        )
    if profile_data.safety_constraints:
        changes["safety_constraints"] = profile_data.safety_constraints.model_dump(
            exclude_none=True
        )
    if profile_data.companion_persona:
        changes["companion_persona"] = profile_data.companion_persona.model_dump(
            exclude_none=True
        )
    if profile_data.custom_instructions:
        changes["custom_instructions"] = profile_data.custom_instructions
    if profile_data.private_notes:
        changes["private_notes"] = profile_data.private_notes

    profile = guardian_service.update_profile(
        student_id=student_id,
        updated_by=current_user.id,
        changes=changes,
        change_reason="Initial profile creation",
        db=db,
    )

    logger.info(
        f"Guardian profile created for student {student_id} by {current_user.username}"
    )
    return profile


@router.put("/students/{student_id}", response_model=schemas.GuardianProfileResponse)
async def update_student_profile(
    student_id: int,
    profile_data: schemas.GuardianProfileUpdate,
    current_user: User = Depends(get_current_teacher_or_admin),
    db: Session = Depends(get_db),
):
    """
    Update a student's guardian profile.

    Only provided fields will be updated. Include change_reason
    for the audit trail.
    """
    verify_student_access(student_id, current_user, db)

    guardian_service = get_guardian_profile_service()
    template_manager = get_template_manager()

    # Validate template name if provided
    if profile_data.template_name is not None and not template_manager.template_exists(
        profile_data.template_name
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_text(
                user=current_user,
                key="errors.guardian.templateNotExist",
                name=profile_data.template_name,
            ),
        )

    # Build changes dict from provided fields
    changes = {}
    if profile_data.template_name is not None:
        changes["template_name"] = profile_data.template_name
    if profile_data.age is not None:
        changes["age"] = profile_data.age
    if profile_data.gender is not None:
        changes["gender"] = profile_data.gender
    if profile_data.medical_context is not None:
        changes["medical_context"] = profile_data.medical_context.model_dump(
            exclude_none=True
        )
    if profile_data.communication_style is not None:
        changes["communication_style"] = profile_data.communication_style.model_dump(
            exclude_none=True
        )
    if profile_data.safety_constraints is not None:
        changes["safety_constraints"] = profile_data.safety_constraints.model_dump(
            exclude_none=True
        )
    if profile_data.companion_persona is not None:
        changes["companion_persona"] = profile_data.companion_persona.model_dump(
            exclude_none=True
        )
    if profile_data.custom_instructions is not None:
        changes["custom_instructions"] = profile_data.custom_instructions
    if profile_data.private_notes is not None:
        changes["private_notes"] = profile_data.private_notes

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_text(user=current_user, key="errors.guardian.noChanges"),
        )

    profile = guardian_service.update_profile(
        student_id=student_id,
        updated_by=current_user.id,
        changes=changes,
        change_reason=profile_data.change_reason,
        db=db,
    )

    logger.info(
        f"Guardian profile updated for student {student_id} by {current_user.username}"
    )
    return profile


@router.delete("/students/{student_id}")
async def delete_student_profile(
    student_id: int,
    current_user: User = Depends(get_current_teacher_or_admin),
    db: Session = Depends(get_db),
):
    """
    Delete (soft-delete) a student's guardian profile.

    The profile will be deactivated but the data is retained for audit.
    Only admins can perform this action.
    """
    if current_user.user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=get_text(user=current_user, key="errors.guardian.onlyAdminsDelete"),
        )

    verify_student_access(student_id, current_user, db)

    guardian_service = get_guardian_profile_service()
    deleted = guardian_service.delete_profile(
        student_id=student_id, deleted_by=current_user.id, db=db
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=get_text(user=current_user, key="errors.guardian.noProfile"),
        )

    logger.info(
        f"Guardian profile deleted for student {student_id} by {current_user.username}"
    )
    return {"success": True, "message": "Profile deleted"}


# --- History and Preview Endpoints ---


@router.get(
    "/students/{student_id}/history", response_model=List[schemas.ProfileHistoryEntry]
)
async def get_profile_history(
    student_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_teacher_or_admin),
    db: Session = Depends(get_db),
):
    """
    Get the change history for a student's profile.

    Shows who changed what and when, for audit purposes.
    """
    verify_student_access(student_id, current_user, db)

    guardian_service = get_guardian_profile_service()
    history = guardian_service.get_profile_history(
        student_id=student_id, limit=limit, db=db
    )

    return history


@router.get("/students/{student_id}/effective-profile")
async def get_effective_profile(
    student_id: int,
    current_user: User = Depends(get_current_teacher_or_admin),
    db: Session = Depends(get_db),
):
    """
    Get the fully resolved effective profile for a student.

    This shows the final configuration after merging template
    defaults with student-specific customizations.
    """
    verify_student_access(student_id, current_user, db)

    guardian_service = get_guardian_profile_service()
    profile = guardian_service.resolve_effective_profile(student_id, db=db)

    return profile


@router.get(
    "/students/{student_id}/system-prompt", response_model=schemas.SystemPromptPreview
)
async def get_student_system_prompt(
    student_id: int,
    current_user: User = Depends(get_current_teacher_or_admin),
    db: Session = Depends(get_db),
):
    """
    Get the actual system prompt that will be sent to the LLM for this student.

    Useful for teachers to verify the final prompt before the student
    starts a learning session.
    """
    verify_student_access(student_id, current_user, db)

    guardian_service = get_guardian_profile_service()
    prompt = guardian_service.build_system_prompt(student_id, db=db)

    # Get template name for response
    profile = guardian_service.get_profile(student_id, db=db)
    template_name = profile.get("template_name", "default") if profile else "default"

    return schemas.SystemPromptPreview(template_name=template_name, prompt=prompt)
