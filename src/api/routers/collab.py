from typing import Dict, Optional, Set

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models.database import BoardAssignment, CommunicationBoard
from src.api.dependencies import get_db, get_text, validate_token

router = APIRouter(prefix="/api/collab", tags=["collab"])


class ConnectionManager:
    def __init__(self):
        self.rooms: Dict[int, Set[WebSocket]] = {}

    async def connect(self, board_id: int, websocket: WebSocket):
        await websocket.accept()
        self.rooms.setdefault(board_id, set()).add(websocket)
        logger.info(f"WS connected to board {board_id}")

    def disconnect(self, board_id: int, websocket: WebSocket):
        try:
            self.rooms.get(board_id, set()).discard(websocket)
        except Exception:
            pass
        logger.info(f"WS disconnected from board {board_id}")

    async def broadcast(
        self, board_id: int, message: dict, sender: WebSocket | None = None
    ):
        for ws in list(self.rooms.get(board_id, set())):
            if ws is sender:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(board_id, ws)


manager = ConnectionManager()


@router.websocket("/boards/{board_id}")
async def board_channel(
    websocket: WebSocket,
    board_id: int,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        logger.info(
            f"WS Connection attempt for board {board_id}. Token present: {bool(token)}"
        )

        # Authenticate user
        user = validate_token(token, db)

        # Get language preference from headers
        accept_language = websocket.headers.get("accept-language")

        if not user:
            logger.warning(
                f"WebSocket authentication failed for board {board_id}. Token provided: {bool(token)}"
            )
            # Must accept to send a custom close code/reason in some cases,
            # but standard practice for rejection is just close.
            # However, to be polite and give a reason, we can accept then close.
            # But for security, maybe just close.
            # Let's try accepting first to ensure the client gets the message.
            await websocket.accept()
            reason = get_text(
                accept_language=accept_language, key="errors.collab.policyViolation"
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)
            return

        logger.info(
            f"WebSocket user authenticated: {user.username} (id={user.id}, type={user.user_type}) connecting to board {board_id}"
        )

        # Check board permissions
        board = (
            db.query(CommunicationBoard)
            .filter(CommunicationBoard.id == board_id)
            .first()
        )
        if not board:
            logger.warning(f"Board {board_id} not found")
            await websocket.accept()
            reason = get_text(
                user=user,
                accept_language=accept_language,
                key="errors.collab.accessDenied",
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)
            return

        # Access rules...
        has_access = False
        if user.user_type == "admin":
            has_access = True
        elif user.user_type == "teacher":
            has_access = True
        elif board.user_id == user.id:
            has_access = True
        else:
            # Check if assigned
            assignment = (
                db.query(BoardAssignment)
                .filter(
                    BoardAssignment.board_id == board_id,
                    BoardAssignment.student_id == user.id,
                )
                .first()
            )
            if assignment:
                has_access = True

        if not has_access:
            logger.warning(f"User {user.username} denied access to board {board_id}")
            if board.is_public:
                # Allow read-only for public boards?
                pass
            else:
                await websocket.accept()
                reason = get_text(
                    user=user,
                    accept_language=accept_language,
                    key="errors.collab.accessDenied",
                )
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION, reason=reason
                )
                return

        await manager.connect(board_id, websocket)
        try:
            while True:
                data = await websocket.receive_json()

                if not has_access and board.is_public:
                    continue

                message = {
                    "type": "board_change",
                    "board_id": board_id,
                    "payload": data,
                    "user_id": user.id,
                    "username": user.username,
                }
                await manager.broadcast(board_id, message, sender=websocket)
        except WebSocketDisconnect:
            manager.disconnect(board_id, websocket)
        except Exception as e:
            logger.error(f"WebSocket error in loop: {e}")
            manager.disconnect(board_id, websocket)

    except Exception as e:
        logger.error(f"Unexpected WebSocket error: {e}")
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
