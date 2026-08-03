from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from src.aac_app.models import BoardAssignment, BoardSymbol, CommunicationBoard, User
from src.api import schemas
from src.api.deps import get_current_active_user, get_db, get_text
from src.api.routers.board_helpers import get_playable_count

router = APIRouter()


@router.get("/assigned", response_model=list[schemas.BoardResponse])
def get_assigned_boards(
    student_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    # Only allow if admin, teacher, or the student themselves
    if (
        current_user.user_type != "admin"
        and current_user.user_type != "teacher"
        and current_user.id != student_id
    ):
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedAssignments"
            ),
        )

    assignments = (
        db.query(BoardAssignment).filter(BoardAssignment.student_id == student_id).all()
    )
    board_ids = [a.board_id for a in assignments]
    boards = (
        db.query(CommunicationBoard)
        .filter(CommunicationBoard.id.in_(board_ids))
        .options(joinedload(CommunicationBoard.symbols).joinedload(BoardSymbol.symbol))
        .all()
        if board_ids
        else []
    )

    for b in boards:
        with suppress(Exception):
            b.playable_symbols_count = get_playable_count(b)

    return boards


@router.post("/{board_id}/assign")
def assign_board_to_student(
    board_id: int,
    payload: schemas.BoardAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Only Admin, Teacher, or Board Owner can assign
    board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    if (
        current_user.user_type != "admin"
        and current_user.user_type != "teacher"
        and board.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.boards.unauthorizedAssign"),
        )

    student = db.query(User).filter(User.id == payload.student_id).first()
    if not student or student.user_type != "student":
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.invalidStudent"),
        )
    existing = (
        db.query(BoardAssignment)
        .filter(
            BoardAssignment.board_id == board_id,
            BoardAssignment.student_id == payload.student_id,
        )
        .first()
    )
    if existing:
        return {"ok": True}

    assigned_by_id = payload.assigned_by if payload.assigned_by else current_user.id
    assignment = BoardAssignment(
        board_id=board_id, student_id=payload.student_id, assigned_by=assigned_by_id
    )
    db.add(assignment)
    db.commit()
    return {"ok": True}


@router.delete("/{board_id}/assign/{student_id}")
def unassign_board_from_student(
    board_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Only Admin, Teacher, or Board Owner can unassign
    board = (
        db.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
    )
    if not board:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )

    if (
        current_user.user_type != "admin"
        and current_user.user_type != "teacher"
        and board.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedUnassign"
            ),
        )

    assignment = (
        db.query(BoardAssignment)
        .filter(
            BoardAssignment.board_id == board_id,
            BoardAssignment.student_id == student_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.assignmentNotFound"),
        )
    db.delete(assignment)
    db.commit()
    return {"ok": True}
