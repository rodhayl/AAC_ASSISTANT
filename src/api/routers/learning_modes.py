from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.aac_app.models import LearningMode, User
from src.aac_app.services.guardian_profile_service import get_guardian_profile_service
from src.aac_app.services.learning_companion_service import LearningCompanionService
from src.api.deps import (
    get_current_active_user,
    get_db,
    get_learning_service,
    verify_student_access,
)
from src.api.schemas import (
    LearningModeCreate,
    LearningModePreviewRequest,
    LearningModePreviewResponse,
    LearningModeResponse,
    LearningModeUpdate,
)

router = APIRouter(tags=["learning-modes"])

@router.get("/", response_model=list[LearningModeResponse])
async def get_learning_modes(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get all available learning modes.
    Returns default system modes (created_by=None) + user's custom modes.
    Admins can see everything? For now, let's say Admins see all,
    Teachers see defaults + their own + maybe global defaults.
    """
    # One query preserves the existing visibility rule (system defaults plus
    # the current user's modes) without loading two collections and merging
    # them in Python. The predicates are mutually exclusive for valid rows;
    # the deterministic ID order also makes the response stable.
    return (
        db.query(LearningMode)
        .filter(
            or_(
                LearningMode.created_by.is_(None),
                LearningMode.created_by == current_user.id,
            )
        )
        .order_by(LearningMode.id)
        .all()
    )

@router.post("/preview", response_model=LearningModePreviewResponse)
async def preview_learning_mode_system_prompt(
    payload: LearningModePreviewRequest,
    current_user: User = Depends(get_current_active_user),
    service: LearningCompanionService = Depends(get_learning_service),
    db: Session = Depends(get_db),
):
    """
    Preview the exact system prompt that will be sent to the LLM.

    The prompt is the user's guardian profile (or the default AAC prompt when
    no profile is configured) plus the learning mode's prompt_instruction.
    Teachers/admins can preview against a specific student to see the final
    prompt that student's sessions will use.
    """
    if current_user.user_type not in ("admin", "teacher"):
        raise HTTPException(
            status_code=403,
            detail="Only admins and teachers can preview modes",
        )

    # Preview against a specific student's guardian profile when selected,
    # otherwise against the current user (default template when no profile).
    target_user_id = current_user.id
    if payload.student_id is not None:
        verify_student_access(payload.student_id, current_user, db)
        target_user_id = payload.student_id

    prompt = service.preview_system_prompt(
        user_id=target_user_id,
        mode_key=payload.mode_key,
        mode_instruction=payload.prompt_instruction,
        db=db,
    )

    # Optional: render the exact user message the LLM would receive for a
    # real student question (the conversational path), plus the model params.
    user_message = None
    messages = None
    temperature = None
    max_tokens = None
    if payload.sample_question and payload.sample_question.strip():
        user_lang = service._get_user_language(target_user_id, db)
        user_message = service.build_conversation_user_prompt(
            student_message=payload.sample_question.strip(),
            topic=payload.topic or "general conversation",
            lang=user_lang,
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message},
        ]
        temperature = service.default_temperature
        max_tokens = service.default_max_tokens

    # Metadata for the Settings UI (template + whether a guardian profile is
    # actually being used).
    guardian_service = get_guardian_profile_service()
    profile = guardian_service.get_profile(target_user_id, db=db)
    template_name = profile.get("template_name", "default") if profile else "default"

    logger.info(
        "User {} previewed a system prompt (student_id={}, mode_key={}, sample={})",
        current_user.username,
        payload.student_id,
        payload.mode_key,
        bool(payload.sample_question),
    )
    return LearningModePreviewResponse(
        prompt=prompt,
        template_name=template_name,
        has_guardian_profile=bool(profile),
        mode_instruction=payload.prompt_instruction,
        user_message=user_message,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )


@router.post("/", response_model=LearningModeResponse)
async def create_learning_mode(
    mode: LearningModeCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a custom learning mode"""
    if current_user.user_type not in ["admin", "teacher"]:
        raise HTTPException(status_code=403, detail="Only admins and teachers can create modes")

    # Check for duplicate key for this user
    existing = db.query(LearningMode).filter(
        LearningMode.key == mode.key,
        (LearningMode.created_by == current_user.id) | (LearningMode.created_by.is_(None))
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail=f"Mode with key '{mode.key}' already exists")

    db_mode = LearningMode(
        name=mode.name,
        key=mode.key,
        description=mode.description,
        prompt_instruction=mode.prompt_instruction,
        auto_ask_enabled=mode.auto_ask_enabled,
        is_custom=True,
        created_by=current_user.id
    )
    db.add(db_mode)
    db.commit()
    db.refresh(db_mode)
    return db_mode

@router.put("/{mode_id}", response_model=LearningModeResponse)
async def update_learning_mode(
    mode_id: int,
    mode_update: LearningModeUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update a learning mode"""
    db_mode = db.get(LearningMode, mode_id)
    if not db_mode:
        raise HTTPException(status_code=404, detail="Mode not found")

    # Permission check
    if db_mode.created_by != current_user.id:
        # If it's a system mode (created_by=None), only admin can edit
        if db_mode.created_by is None:
            if current_user.user_type != "admin":
                raise HTTPException(status_code=403, detail="Only admins can edit system modes")
        else:
            raise HTTPException(status_code=403, detail="Not authorized to edit this mode")

    if mode_update.name is not None:
        db_mode.name = mode_update.name
    if mode_update.description is not None:
        db_mode.description = mode_update.description
    if mode_update.prompt_instruction is not None:
        db_mode.prompt_instruction = mode_update.prompt_instruction
    if mode_update.auto_ask_enabled is not None:
        db_mode.auto_ask_enabled = mode_update.auto_ask_enabled

    db.commit()
    db.refresh(db_mode)
    return db_mode

@router.delete("/{mode_id}")
async def delete_learning_mode(
    mode_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete a learning mode"""
    db_mode = db.get(LearningMode, mode_id)
    if not db_mode:
        raise HTTPException(status_code=404, detail="Mode not found")

    if db_mode.created_by != current_user.id:
        if db_mode.created_by is None:
            if current_user.user_type != "admin":
                 raise HTTPException(status_code=403, detail="Only admins can delete system modes")
        else:
            raise HTTPException(status_code=403, detail="Not authorized to delete this mode")

    db.delete(db_mode)
    db.commit()
    return {"success": True}
