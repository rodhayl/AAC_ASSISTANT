
import contextlib
import os

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from src.aac_app.models import LearningMode, User
from src.aac_app.services.learning.service import LearningCompanionService
from src.api import schemas
from src.api.deps import (
    get_board_or_404,
    get_current_active_user,
    get_db,
    get_learning_service,
    get_learning_session_or_404,
    require_board_view_access,
    verify_student_access,
)
from src.api.deps import (
    get_text as get_shared_text,
)
from src.api.file_uploads import DEFAULT_MAX_AUDIO_BYTES, save_audio_upload

router = APIRouter()


def get_text(user: User, key: str, **kwargs) -> str:
    """Translate a learning-namespace message for the current user."""
    return get_shared_text(user, key, namespace="pages/learning", **kwargs)


@router.post("/start", response_model=schemas.LearningSessionResponse)
def start_session(
    session_data: schemas.LearningSessionStart,
    user_id: int,
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Start a new learning session"""
    if user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403, detail=get_text(current_user, "errors.unauthorizedUser")
        )

    if session_data.board_id is not None:
        board = get_board_or_404(db, session_data.board_id, current_user)
        require_board_view_access(board, current_user, db)

    if session_data.mode_key:
        mode_query = db.query(LearningMode).filter(LearningMode.key == session_data.mode_key)
        if current_user.user_type != "admin":
            mode_query = mode_query.filter(
                (LearningMode.created_by.is_(None))
                | (LearningMode.created_by == current_user.id)
            )
        mode = mode_query.order_by(LearningMode.id).first()
        mode_visible = mode is not None
        if not mode_visible:
            raise HTTPException(
                status_code=404,
                # The learningModes keys live in the shared common namespace.
                detail=get_shared_text(
                    current_user, "errors.learningModes.notFound"
                ),
            )

    result = service.start_learning_session(
        user_id=user_id,
        topic=session_data.topic,
        purpose=session_data.purpose,
        difficulty=session_data.difficulty,
        board_id=session_data.board_id,
        mode_key=session_data.mode_key,
        db=db,
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
    difficulty: str | None = None,
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Generate a question for the session"""
    get_learning_session_or_404(
        db,
        session_id,
        current_user,
        message=lambda key: get_text(current_user, key),
        require_active=True,
    )

    result = await service.ask_question(
        session_id=session_id, difficulty=difficulty, db=db
    )

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
    get_learning_session_or_404(
        db,
        session_id,
        current_user,
        message=lambda key: get_text(current_user, key),
        require_active=True,
    )

    result = await service.process_response(
        session_id=session_id,
        student_response=answer_data.answer,
        is_voice=False,
        db=db,
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
    get_learning_session_or_404(
        db,
        session_id,
        current_user,
        message=lambda key: get_text(current_user, key),
        require_active=True,
    )

    temp_path = None
    try:
        temp_path = await save_audio_upload(
            file,
            max_bytes=DEFAULT_MAX_AUDIO_BYTES,
            too_large_detail=get_shared_text(
                user=current_user,
                key="errors.boards.audioFileTooLarge",
                namespace="common",
            ),
            invalid_type_detail=get_shared_text(
                user=current_user,
                key="errors.boards.invalidAudioType",
                namespace="common",
            ),
            empty_detail=get_shared_text(
                user=current_user,
                key="errors.boards.invalidAudioType",
                namespace="common",
            ),
        )
        result = await service.process_response(
            session_id=session_id,
            student_response="",  # Will be transcribed
            is_voice=True,
            audio_path=temp_path,
            db=db,
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            with contextlib.suppress(OSError):
                os.remove(temp_path)

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
    get_learning_session_or_404(
        db,
        session_id,
        current_user,
        message=lambda key: get_text(current_user, key),
        require_active=True,
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
        db=db,
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
    get_learning_session_or_404(
        db,
        session_id,
        current_user,
        message=lambda key: get_text(current_user, key),
        require_active=True,
    )

    result = await service.end_learning_session(session_id, db=db)

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
    get_learning_session_or_404(
        db,
        session_id,
        current_user,
        message=lambda key: get_text(current_user, key),
        allow_teacher=True,
    )

    result = service.get_session_progress(session_id, db=db)

    if not result["success"]:
        raise HTTPException(
            status_code=404,
            detail=result.get("error", get_text(current_user, "errors.unknownError")),
        )

    return result


@router.get("/history/{user_id}")
def get_history(
    user_id: int,
    limit: int = Query(10, ge=1, le=1000),
    service: LearningCompanionService = Depends(get_learning_service),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get user learning history"""
    if user_id != current_user.id and current_user.user_type != "admin":
        if current_user.user_type == "teacher":
            verify_student_access(user_id, current_user, db)
        else:
            raise HTTPException(
                status_code=403, detail=get_text(current_user, "errors.unauthorized")
            )

    result = service.get_user_history(user_id, limit, db=db)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", get_text(current_user, "errors.unknownError")),
        )

    return {"sessions": result["sessions"]}
