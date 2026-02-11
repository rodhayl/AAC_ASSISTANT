from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models.database import LearningMode, User, get_session
from src.api.dependencies import get_current_active_user, get_db
from src.api.schemas import (
    LearningModeCreate,
    LearningModeResponse,
    LearningModeUpdate,
)

router = APIRouter(tags=["learning-modes"])

@router.get("/", response_model=List[LearningModeResponse])
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
    # Base query: System defaults
    query = db.query(LearningMode).filter(LearningMode.created_by == None)
    
    # If user is admin/teacher, they might have their own custom modes
    # If student, they should see defaults + their teacher's modes? 
    # For now, let's keep it simple: Everyone sees defaults.
    # Users see their own custom modes.
    
    custom_modes = db.query(LearningMode).filter(LearningMode.created_by == current_user.id)
    
    # Union?
    modes = query.all() + custom_modes.all()
    
    # Deduplicate by ID just in case (shouldn't happen with this logic)
    return modes

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
        (LearningMode.created_by == current_user.id) | (LearningMode.created_by == None)
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"Mode with key '{mode.key}' already exists")

    db_mode = LearningMode(
        name=mode.name,
        key=mode.key,
        description=mode.description,
        prompt_instruction=mode.prompt_instruction,
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
