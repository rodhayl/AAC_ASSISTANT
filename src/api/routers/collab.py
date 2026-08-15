
import asyncio
import contextlib

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import BoardAssignment, CommunicationBoard, StudentTeacher, User
from src.api.deps import get_db, get_text, validate_active_token

router = APIRouter(prefix="/api/collab", tags=["collab"])


class ConnectionManager:
    def __init__(self):
        self.rooms: dict[int, set[WebSocket]] = {}

    async def connect(
        self,
        board_id: int,
        websocket: WebSocket,
        subprotocol: str | None = None,
    ):
        await websocket.accept(subprotocol=subprotocol)
        self.rooms.setdefault(board_id, set()).add(websocket)
        logger.info(f"WS connected to board {board_id}")

    def disconnect(self, board_id: int, websocket: WebSocket):
        with contextlib.suppress(Exception):
            self.rooms.get(board_id, set()).discard(websocket)
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
    db: Session = Depends(get_db),
):
    try:
        # Browser WebSocket clients cannot set arbitrary Authorization headers.
        # Negotiate a harmless fixed subprotocol and carry the bearer token in
        # the second offered protocol so it is not exposed in the URL/logs.
        offered_protocols = [
            value.strip()
            for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
            if value.strip()
        ]
        auth_subprotocol = "aac-auth" if offered_protocols[:1] == ["aac-auth"] else None
        auth_token = offered_protocols[1] if auth_subprotocol and len(offered_protocols) > 1 else None
        logger.info(
            f"WS Connection attempt for board {board_id}. Token present: {bool(auth_token)}"
        )

        # Authenticate user
        user = validate_active_token(auth_token, db)

        # Get language preference from headers
        accept_language = websocket.headers.get("accept-language")

        if not user:
            logger.warning(
                f"WebSocket authentication failed for board {board_id}. Token provided: {bool(auth_token)}"
            )
            # Must accept to send a custom close code/reason in some cases,
            # but standard practice for rejection is just close.
            # However, to be polite and give a reason, we can accept then close.
            # But for security, maybe just close.
            # Let's try accepting first to ensure the client gets the message.
            await websocket.accept(subprotocol=auth_subprotocol)
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
            await websocket.accept(subprotocol=auth_subprotocol)
            reason = get_text(
                user=user,
                accept_language=accept_language,
                key="errors.collab.accessDenied",
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)
            return

        # Access rules: owners and admins may collaborate; students need an
        # explicit board assignment; teachers need an explicit roster
        # relationship to the student who owns the board. Public boards remain
        # available as read-only channels below.
        has_access = user.user_type == "admin" or board.user_id == user.id
        if not has_access and user.user_type == "teacher":
            owner = db.query(User).filter(User.id == board.user_id).first()
            if owner is not None and owner.user_type == "student":
                has_access = (
                    db.query(StudentTeacher)
                    .filter(
                        StudentTeacher.teacher_id == user.id,
                        StudentTeacher.student_id == owner.id,
                    )
                    .first()
                    is not None
                )

        if not has_access and user.user_type == "student":
            has_access = (
                db.query(BoardAssignment)
                .filter(
                    BoardAssignment.board_id == board_id,
                    BoardAssignment.student_id == user.id,
                )
                .first()
                is not None
            )

        if not has_access:
            logger.warning(f"User {user.username} denied access to board {board_id}")
            if board.is_public:
                # Allow read-only for public boards?
                pass
            else:
                await websocket.accept(subprotocol=auth_subprotocol)
                reason = get_text(
                    user=user,
                    accept_language=accept_language,
                    key="errors.collab.accessDenied",
                )
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION, reason=reason
                )
                return

        # Mark the room registration before awaiting accept so cancellation in
        # this tiny handoff window still triggers the outer cleanup path.
        connected = True
        await manager.connect(board_id, websocket, subprotocol=auth_subprotocol)
        shutdown_event = getattr(websocket.app.state, "shutdown_event", None)
        if not getattr(websocket.app.state, "lifespan_active", False):
            shutdown_event = None
        if shutdown_event is None:
            # Direct ASGI callers that do not run the application lifespan still
            # receive normal WebSocket behavior; production lifespan installs it.
            shutdown_event = asyncio.Event()
        try:
            while True:
                receive_task = asyncio.create_task(websocket.receive_json())
                shutdown_task = asyncio.create_task(shutdown_event.wait())
                try:
                    done, _ = await asyncio.wait(
                        (receive_task, shutdown_task),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if shutdown_task in done:
                        with contextlib.suppress(Exception):
                            await websocket.close(
                                code=status.WS_1001_GOING_AWAY,
                                reason="Server shutting down",
                            )
                        return
                    data = receive_task.result()
                finally:
                    for task in (receive_task, shutdown_task):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(
                        receive_task, shutdown_task, return_exceptions=True
                    )

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
            pass
        except asyncio.CancelledError:
            # TestClient and ASGI servers may cancel the handler while closing
            # a client connection. This is an expected lifecycle outcome, not
            # an application error; the manager cleanup below still runs.
            pass
        except Exception as e:
            logger.error(f"WebSocket error in loop: {e}")
        finally:
            manager.disconnect(board_id, websocket)

    except asyncio.CancelledError:
        # A cancellation before the connection loop starts is also a normal
        # teardown path and must not become an unhandled server exception.
        # If room registration completed (or was being attempted), remove the
        # socket even when cancellation landed before the inner finally block.
        if "connected" in locals() and connected:
            manager.disconnect(board_id, websocket)
        return
    except Exception as e:
        logger.error(f"Unexpected WebSocket error: {e}")
        with contextlib.suppress(Exception):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
