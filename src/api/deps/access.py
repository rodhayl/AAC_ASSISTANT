"""Shared domain lookup and authorization helpers for API routers."""

from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.aac_app.models import CommunicationBoard, LearningSession, User

from .auth import get_text, verify_student_access


def get_learning_session_or_404(
    db: Session,
    session_id: int,
    current_user: User,
    *,
    message: Callable[[str], str] | None = None,
) -> LearningSession:
    """Load a learning session and enforce its owner/admin access rule.

    ``message`` lets routers retain their domain-specific translation namespace.
    """
    message = message or (lambda key: get_text(current_user, key))
    session = db.query(LearningSession).filter(LearningSession.id == session_id).first()
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=message("errors.sessionNotFound"),
        )
    if session.user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail=message("errors.unauthorized"),
        )
    return session


def get_board_or_404(
    db: Session,
    board_id: int,
    current_user: User,
) -> CommunicationBoard:
    """Load a board or raise the localized board-not-found response."""
    board = (
        db.query(CommunicationBoard)
        .filter(CommunicationBoard.id == board_id)
        .first()
    )
    if board is None:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )
    return board


def require_board_owner_or_admin(
    board: CommunicationBoard,
    current_user: User,
    *,
    error_key: str = "errors.boards.unauthorizedModifyBoard",
) -> CommunicationBoard:
    """Require an administrator or the board owner for mutations."""
    if current_user.user_type != "admin" and board.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key=error_key),
        )
    return board


def validate_board_position(
    board: CommunicationBoard,
    position_x: int,
    position_y: int,
    current_user: User,
) -> None:
    """Reject placements outside the board's persisted grid."""
    rows = max(int(board.grid_rows or 4), 1)
    cols = max(int(board.grid_cols or 5), 1)
    if not (0 <= position_x < cols and 0 <= position_y < rows):
        raise HTTPException(
            status_code=400,
            detail=get_text(
                user=current_user,
                key="errors.boards.invalidPosition",
                x=position_x,
                y=position_y,
                rows=rows,
                cols=cols,
            ),
        )


def validate_grid_resize(
    board: CommunicationBoard,
    rows: int,
    cols: int,
    current_user: User,
) -> None:
    """Prevent a grid resize from hiding existing symbol placements."""
    for board_symbol in board.symbols or []:
        if not (
            0 <= (board_symbol.position_x or 0) < cols
            and 0 <= (board_symbol.position_y or 0) < rows
        ):
            raise HTTPException(
                status_code=400,
                detail=get_text(
                    user=current_user,
                    key="errors.boards.gridTooSmall",
                    rows=rows,
                    cols=cols,
                ),
            )


def validate_linked_board(
    db: Session,
    board_id: int,
    linked_board_id: int | None,
    current_user: User,
) -> None:
    """Validate a board link before persisting it.

    A board cannot link to itself because that creates an AAC navigation loop.
    Non-admin users may link only to their own boards or public boards, which
    matches the boards visible to them in the editor.
    """
    if linked_board_id is None:
        return
    if linked_board_id == board_id:
        raise HTTPException(
            status_code=400,
            detail=get_text(user=current_user, key="errors.boards.selfLinkedBoard"),
        )

    linked_board = (
        db.query(CommunicationBoard)
        .filter(CommunicationBoard.id == linked_board_id)
        .first()
    )
    if linked_board is None:
        raise HTTPException(
            status_code=404,
            detail=get_text(user=current_user, key="errors.boards.boardNotFound"),
        )
    if (
        current_user.user_type != "admin"
        and linked_board.user_id != current_user.id
        and not linked_board.is_public
    ):
        raise HTTPException(
            status_code=403,
            detail=get_text(user=current_user, key="errors.boards.unauthorizedViewBoard"),
        )


def require_board_staff_or_owner(
    board: CommunicationBoard,
    current_user: User,
    db: Session,
    *,
    error_key: str = "errors.boards.unauthorizedModifyBoard",
) -> CommunicationBoard:
    """Require an admin, owner, or rostered teacher for staff actions.

    Teachers may work on their own boards. For a student's board, they must
    have an explicit roster assignment; a teacher role alone is not sufficient
    to mutate another student's board or invoke its AI features.
    """
    if current_user.user_type == "admin" or board.user_id == current_user.id:
        return board

    if current_user.user_type == "teacher":
        owner = db.query(User).filter(User.id == board.user_id).first()
        if owner is not None and owner.user_type == "student":
            verify_student_access(owner.id, current_user, db)
            return board

    raise HTTPException(
        status_code=403,
        detail=get_text(user=current_user, key=error_key),
    )
