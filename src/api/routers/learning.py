from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from src.aac_app.models.database import LearningSession, User
from src.aac_app.services.learning_companion_service import LearningCompanionService
from src.aac_app.services.translation_service import get_translation_service
from src.api import schemas
from src.api.dependencies import get_current_active_user, get_db, get_learning_service

router = APIRouter()


def get_text(user: User, key: str, **kwargs) -> str:
    lang = "en"
    if user.settings and user.settings.ui_language:
        lang = user.settings.ui_language

    return get_translation_service().get(lang, "pages/learning", key, **kwargs)


@router.post("/start", response_model=schemas.LearningSessionResponse)
async def start_session(
    session_data: schemas.LearningSessionStart,
    user_id: int,
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
):
    """Start a new learning session"""
    if user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403, detail=get_text(current_user, "errors.unauthorizedUser")
        )

    result = await service.start_learning_session(
        user_id=user_id,
        topic=session_data.topic,
        purpose=session_data.purpose,
        difficulty=session_data.difficulty,
        board_id=session_data.board_id,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", get_text(current_user, "errors.unknownError")),
        )

    return result


@router.post("/{session_id}/ask", response_model=schemas.QuestionResponse)
async def ask_question(
    session_id: int,
    difficulty: Optional[str] = None,
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Generate a question for the session"""
    session = db.query(LearningSession).filter(LearningSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=404, detail=get_text(current_user, "errors.sessionNotFound")
        )
    if session.user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403, detail=get_text(current_user, "errors.unauthorized")
        )

    result = await service.ask_question(session_id=session_id, difficulty=difficulty)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", get_text(current_user, "errors.unknownError")),
        )

    return result


@router.post("/{session_id}/answer", response_model=schemas.AnswerResponse)
async def submit_answer(
    session_id: int,
    answer_data: schemas.AnswerSubmit,
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Submit an answer (text)"""
    session = db.query(LearningSession).filter(LearningSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=404, detail=get_text(current_user, "errors.sessionNotFound")
        )
    if session.user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403, detail=get_text(current_user, "errors.unauthorized")
        )

    result = await service.process_response(
        session_id=session_id, student_response=answer_data.answer, is_voice=False
    )

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", get_text(current_user, "errors.unknownError")),
        )

    return result


@router.post("/{session_id}/answer/voice", response_model=schemas.AnswerResponse)
async def submit_voice_answer(
    session_id: int,
    file: UploadFile = File(...),
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Submit an answer (voice audio file)"""
    session = db.query(LearningSession).filter(LearningSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=404, detail=get_text(current_user, "errors.sessionNotFound")
        )
    if session.user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403, detail=get_text(current_user, "errors.unauthorized")
        )

    audio_data = await file.read()

    result = await service.process_response(
        session_id=session_id,
        student_response="",  # Will be transcribed
        is_voice=True,
        audio_data=audio_data,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", get_text(current_user, "errors.unknownError")),
        )

    return result


@router.post("/{session_id}/answer/symbols", response_model=schemas.AnswerResponse)
async def submit_symbol_answer(
    session_id: int,
    payload: schemas.SymbolAnswerSubmit,
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Submit an answer composed of AAC symbols (ordered list)."""
    session = db.query(LearningSession).filter(LearningSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=404, detail=get_text(current_user, "errors.sessionNotFound")
        )
    if session.user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403, detail=get_text(current_user, "errors.unauthorized")
        )

    if not payload.symbols or len(payload.symbols) == 0:
        raise HTTPException(
            status_code=400, detail=get_text(current_user, "errors.noSymbolsProvided")
        )

    # Use enriched gloss if available, otherwise fall back to raw_gloss or simple join
    text = (
        payload.enriched_gloss
        or payload.raw_gloss
        or payload.text
        or " ".join([s.label for s in payload.symbols if s.label])
    )

    result = await service.process_response(
        session_id=session_id,
        student_response=text,
        is_voice=False,
        audio_data=None,
        symbols=[s.model_dump() for s in payload.symbols],
    )

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", get_text(current_user, "errors.unknownError")),
        )

    return result


@router.post(
    "/{session_id}/end", response_model=schemas.LearningSessionResponse
)  # Reusing response model for summary
async def end_session(
    session_id: int,
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """End the learning session"""
    session = db.query(LearningSession).filter(LearningSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=404, detail=get_text(current_user, "errors.sessionNotFound")
        )
    if session.user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403, detail=get_text(current_user, "errors.unauthorized")
        )

    result = await service.end_learning_session(session_id)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", get_text(current_user, "errors.unknownError")),
        )

    # Map result to schema (summary is not in LearningSessionResponse, but we can return a dict)
    return result


@router.get("/{session_id}/progress")
def get_progress(
    session_id: int,
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get session progress"""
    session = db.query(LearningSession).filter(LearningSession.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=404, detail=get_text(current_user, "errors.sessionNotFound")
        )
    if session.user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403, detail=get_text(current_user, "errors.unauthorized")
        )

    result = service.get_session_progress(session_id)

    if not result["success"]:
        raise HTTPException(
            status_code=404,
            detail=result.get("error", get_text(current_user, "errors.unknownError")),
        )

    return result


@router.get("/history/{user_id}")
def get_history(
    user_id: int,
    limit: int = 10,
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
):
    """Get user learning history"""
    if user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403, detail=get_text(current_user, "errors.unauthorized")
        )

    result = service.get_user_history(user_id, limit)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", get_text(current_user, "errors.unknownError")),
        )

    return {"sessions": result["sessions"]}
