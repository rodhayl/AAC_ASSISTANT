
import asyncio
import contextlib
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.models import CommunicationBoard
from src.api.deps import get_db, get_text, validate_active_token
from src.api.deps.access import (
    require_board_collab_write_access,
    require_board_view_access,
)

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
            room = self.rooms.get(board_id)
            if room is None:
                return
            room.discard(websocket)
            if not room:
                self.rooms.pop(board_id, None)
        logger.info(f"WS disconnected from board {board_id}")

    async def broadcast(
        self, board_id: int, message: dict, sender: WebSocket | None = None
    ):
        for ws in list(self.rooms.get(board_id, set())):
            if ws is sender:
                continue
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.debug(
                    "WebSocket send failed for board {}; disconnecting client: {}",
                    board_id,
                    exc,
                )
                self.disconnect(board_id, ws)


manager = ConnectionManager()

# Cap on a single collaboration payload before it is re-broadcast to every
# member of the room (the fan-out multiplies it N-fold). Uvicorn accepts
# messages up to ~16MB by default, so without this cap an authenticated
# client with any board access could amplify 16MB x members per message.
# The rest of the repo bounds inbound bodies the same way
# (_MAX_IMPORT_BODY_BYTES = 10MB in export_import.py, batches capped at
# 1000, search queries at 200 chars); real board_change payloads are a few
# hundred bytes, so 256KB leaves a wide margin for richer edits while
# capping amplification.
MAX_COLLAB_PAYLOAD_BYTES = 256 * 1024


def _is_collab_move_payload(data: dict) -> bool:
    """True when ``data`` is the one payload the product actually speaks.

    The ONLY collab sender in the tree emits ``{op: 'move', symbol_id,
    position: {x, y}}`` and the ONLY receiver acts solely on
    ``payload.op === 'move'`` with a ``symbol_id`` and a ``position`` — see
    src/frontend/src/hooks/useBoardCollab.ts (the contract). Allow-listing
    the op and validating the exact shape the receiver dereferences means a
    junk or forged dict (e.g. an ``add``/``ping`` payload, or a move without
    a usable position) is never amplified to every peer. bool is rejected
    (it is an int subclass and a JSON ``true`` must not become symbol id 1).
    """
    if data.get("op") != "move":
        return False
    symbol_id = data.get("symbol_id")
    if isinstance(symbol_id, bool) or not isinstance(symbol_id, int):
        return False
    position = data.get("position")
    if not isinstance(position, dict):
        return False
    for axis in ("x", "y"):
        value = position.get(axis)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
    return True


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

        # View access uses the canonical board rule shared with the board
        # detail/prediction routers (admin/owner/public/assigned/rostered).
        # Broadcast access uses the sibling helper that excludes the public
        # shortcut: a public board is viewable read-only by everyone, but only
        # the owner, an admin, a rostered teacher, or an assigned student may
        # re-emit edits to the room.
        view_granted = True
        try:
            require_board_view_access(board, user, db)
        except HTTPException as exc:
            # Only the intentional 403 denial maps to "no view". Any other
            # HTTPException (e.g. a 500 surfaced by the helpers or the
            # localized-text lookup) must propagate instead of silently
            # degrading to "denied"/read-only.
            if exc.status_code != status.HTTP_403_FORBIDDEN:
                raise
            view_granted = False
        if not view_granted:
            logger.warning(f"User {user.username} denied access to board {board_id}")
            await websocket.accept(subprotocol=auth_subprotocol)
            reason = get_text(
                user=user,
                accept_language=accept_language,
                key="errors.collab.accessDenied",
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason)
            return

        write_granted = True
        try:
            require_board_collab_write_access(board, user, db)
        except HTTPException as exc:
            # Same rule as the view gate above: only the intentional 403 (a
            # public-board viewer without any write relationship — view was
            # granted above and the private-board relationships are exactly
            # the write relationships) means read-only; anything else must
            # propagate.
            if exc.status_code != status.HTTP_403_FORBIDDEN:
                raise
            write_granted = False

        # Mark the room registration before awaiting accept so cancellation in
        # this tiny handoff window still triggers the outer cleanup path.
        connected = False
        await manager.connect(board_id, websocket, subprotocol=auth_subprotocol)
        connected = True
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

                # Bound the fan-out (see MAX_COLLAB_PAYLOAD_BYTES above): a
                # message larger than the cap is refused with 1009 before any
                # peer receives it. The cap is measured in WIRE bytes (what
                # json.dumps(...).encode() actually delivers to every peer):
                # a len() over the str counts code points, so a non-ASCII
                # payload of 256K chars would pass this check and still
                # arrive as ~0.5-1MB per peer.
                payload_size = len(
                    json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode(
                        "utf-8"
                    )
                )
                if payload_size > MAX_COLLAB_PAYLOAD_BYTES:
                    logger.warning(
                        "Rejecting oversized collab payload ({} bytes > {}) from {}",
                        payload_size,
                        MAX_COLLAB_PAYLOAD_BYTES,
                        user.username,
                    )
                    with contextlib.suppress(Exception):
                        await websocket.close(
                            code=status.WS_1009_MESSAGE_TOO_BIG,
                            reason=f"Payload exceeds {MAX_COLLAB_PAYLOAD_BYTES} bytes",
                        )
                    return

                if not write_granted:
                    # Public-board read-only viewer: keep receiving, never emit.
                    continue

                # The fan-out contract is a JSON dict whose vocabulary is a
                # SINGLE op — ``move`` (the frontend collab sender/receiver in
                # src/frontend/src/hooks/useBoardCollab.ts speaks nothing
                # else). A list/str/int payload would otherwise skip the
                # label content gate below (its label_candidate lookup is
                # dict-only) and be wrapped and broadcast to every peer as
                # garbage; an op outside the allow-list (or a move with an
                # unusable shape) would do the same. Both are dropped
                # silently and the connection stays alive: a malformed client
                # must not kill the room (mirrors the fail-closed gate
                # philosophy — unshaped input is not fanned out).
                if not isinstance(data, dict):
                    logger.debug(
                        "Dropping non-dict collab payload from {} ({} bytes)",
                        user.username,
                        payload_size,
                    )
                    continue

                # Layer-1 content gate on board-change payloads that carry a
                # free-text label. This layer vets ANY label-bearing dict
                # (whatever its op) because it is the only enforcement point
                # of the guardian ``block_social_messaging`` lock and the
                # fail-closed net for text that could not be vetted; the
                # vocabulary gate below then restricts what may actually fan
                # out to the move op alone. Blocked labels are never fanned
                # out to the room; the REST admission gates
                # (get_or_create_symbol) are the authoritative DB guard, this
                # protects every connected peer from forged/malformed input.
                # (data is a dict here — the dict gate above ran first.)
                label_candidate = data.get("label")
                if isinstance(label_candidate, str) and label_candidate.strip():
                    try:
                        from src.aac_app.services.content_safety import (
                            check_text,
                            load_global_policy,
                            log_event,
                            resolve_policy_for_user,
                        )

                        # Per-student lock: a teacher/admin may disable collab
                        # messaging entirely for this student.
                        student_policy = resolve_policy_for_user(user.id, db=db)
                        if student_policy.feature_blocked("block_social_messaging"):
                            log_event(
                                user_id=user.id,
                                surface="social",
                                direction="output",
                                verdict="blocked",
                                matched=[],
                                detail="feature_lock: block_social_messaging",
                                db=db,
                            )
                            continue

                        verdict = check_text(load_global_policy(), label_candidate)
                        if verdict.blocked:
                            log_event(
                                user_id=user.id,
                                surface="social",
                                direction="output",
                                verdict="blocked",
                                matched=list(verdict.matched_terms),
                                detail=f"collab label: {label_candidate[:200]}",
                                db=db,
                            )
                            logger.info(
                                "Blocked collab label from {}: {!r}",
                                user.username,
                                label_candidate[:80],
                            )
                            continue
                    except Exception as exc:
                        # Fail CLOSED: when the gate itself errors (DB down,
                        # policy load failure, check_text throw) the message is
                        # dropped like a blocked one — a label that could not
                        # be vetted must never be fanned out to the room.
                        logger.warning(
                            "Content gate unavailable; dropping collab payload: {}",
                            exc,
                        )
                        continue

                # Layer-2 vocabulary gate (C1): only the ``move`` op with the
                # exact shape the client receiver dereferences is broadcast.
                # Anything else — ``add``/``ping``/unknown ops, malformed
                # moves — is dropped here with the connection kept alive; the
                # label content gate above already vetted any text it
                # carried, so nothing unvetted can slip past this continue.
                if not _is_collab_move_payload(data):
                    logger.debug(
                        "Dropping non-move collab payload from {} ({} bytes)",
                        user.username,
                        payload_size,
                    )
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
            # Leave the transport with an explicit server-error close code so
            # the peer does not hang on an abruptly dropped (half-open)
            # connection; mirrors the outer handler's 1011.
            with contextlib.suppress(Exception):
                await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
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
