from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from src.aac_app.models import BoardAssignment, BoardSymbol, CommunicationBoard, User
from src.api import schemas
from src.api.deps import (
    STAFF_USER_TYPES,
    get_board_or_404,
    get_current_active_user,
    get_db,
    get_text,
    require_board_owner_or_admin,
    verify_student_access,
)
from src.api.routers.board_helpers import serialize_board

router = APIRouter()


@router.get("/assigned", response_model=list[schemas.BoardResponse])
def get_assigned_boards(
    student_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    # Students may view only their own assignments. Teachers are limited to
    # their explicit roster.
    if current_user.user_type == "teacher":
        verify_student_access(student_id, current_user, db)
    elif current_user.user_type != "admin" and current_user.id != student_id:
        raise HTTPException(
            status_code=403,
            detail=get_text(
                user=current_user, key="errors.boards.unauthorizedAssignments"
            ),
        )

    boards = (
        db.query(CommunicationBoard)
        .join(BoardAssignment, BoardAssignment.board_id == CommunicationBoard.id)
        .filter(BoardAssignment.student_id == student_id)
        .distinct()
        .options(joinedload(CommunicationBoard.symbols).joinedload(BoardSymbol.symbol))
        .all()
    )

    return [serialize_board(board) for board in boards]


@router.post("/{board_id}/assign")
def assign_board_to_student(
    board_id: int,
    payload: schemas.BoardAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Assignment management is a staff action. Board ownership alone must not
    # let a student change another student's roster or forge distribution.
    if current_user.user_type not in STAFF_USER_TYPES:
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.boards.unauthorizedAssign"),
        )

    board = get_board_or_404(db, board_id, current_user)
    require_board_owner_or_admin(
        board,
        current_user,
        error_key="errors.boards.unauthorizedAssign",
    )

    if current_user.user_type == "teacher":
        verify_student_access(payload.student_id, current_user, db)

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

    # The authenticated actor is the only trusted assignment author; do not
    # allow a client-supplied ID to forge the audit field.
    assignment = BoardAssignment(
        board_id=board_id, student_id=payload.student_id, assigned_by=current_user.id
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
    # Assignment management is a staff action. Board ownership alone must not
    # let a student change another student's roster or forge distribution.
    if current_user.user_type not in STAFF_USER_TYPES:
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.boards.unauthorizedUnassign"),
        )

    board = get_board_or_404(db, board_id, current_user)
    require_board_owner_or_admin(
        board,
        current_user,
        error_key="errors.boards.unauthorizedUnassign",
    )

    if current_user.user_type == "teacher":
        verify_student_access(student_id, current_user, db)

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
