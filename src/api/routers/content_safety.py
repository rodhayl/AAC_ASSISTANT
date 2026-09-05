"""Admin content-safety router.

Server-wide defaults (filter level, forbidden topics, trigger words, feature
locks, strict sentinel switch), the safety-event audit log, and the purge
tool for auto-generated pictograms. All endpoints are admin-only.

Teachers configure the *per-student* side through the guardian-profiles API
(``SafetyConstraintsSchema``); fields listed in the global policy's
``locked_fields`` are rejected there so admins can pin an org-wide floor.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import ContentSafetyEvent, User
from src.aac_app.services import content_safety as safety
from src.api import schemas
from src.api.deps import get_current_admin_user, get_db, get_text

router = APIRouter(prefix="/api/settings/content-safety", tags=["content-safety"])


@router.get("", response_model=schemas.ContentSafetyPolicySchema)
def get_global_policy(
    current_user: User = Depends(get_current_admin_user),
):
    """Return the current global content policy (what every student gets by
    default before teacher overrides)."""
    policy = safety.load_global_policy()
    data = safety.load_global_policy_dict()
    policy_data = {
        "level": policy.level,
        "forbidden_topics": list(policy.forbidden_topics),
        "trigger_words": list(policy.trigger_words),
        "feature_locks": dict(policy.feature_locks),
        "sentinel_moderation": policy.sentinel_moderation,
        "max_response_length": policy.max_response_length,
        "locked_fields": list(data.get("locked_fields", [])),
    }
    return schemas.ContentSafetyPolicySchema(**policy_data)


@router.put("", response_model=schemas.ContentSafetyPolicySchema)
def update_global_policy(
    payload: schemas.ContentSafetyPolicySchema,
    current_user: User = Depends(get_current_admin_user),
):
    """Replace the global content policy. This is the server-wide floor every
    student resolves from; per-student overrides (guardian profiles) can only
    loosen/stiffen fields that are not in ``locked_fields``."""
    try:
        safety.save_global_policy(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_text(user=current_user, key="errors.safety.invalidLevel"),
        ) from exc
    logger.info("Global content policy updated by {}", current_user.username)
    return get_global_policy(current_user)


@router.get("/events", response_model=list[schemas.ContentSafetyEventSchema])
def list_safety_events(
    limit: int = Query(50, ge=1, le=500),
    surface: str | None = Query(None),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Recent content-safety verdicts across all students."""
    query = db.query(ContentSafetyEvent).order_by(ContentSafetyEvent.id.desc())
    if surface:
        query = query.filter(ContentSafetyEvent.surface == surface)
    return query.limit(limit).all()


@router.delete("/events", status_code=status.HTTP_204_NO_CONTENT)
def clear_safety_events(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Clear the safety-event audit log."""
    db.query(ContentSafetyEvent).delete()
    db.commit()
    logger.info("Content-safety events cleared by {}", current_user.username)


@router.delete("/ai-symbols")
def purge_ai_symbols(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Delete every auto-generated pictogram symbol and its image file."""
    count = safety.purge_ai_symbols(db=db)
    logger.info("Purged {} auto-generated symbols by {}", count, current_user.username)
    return {"deleted": count}
