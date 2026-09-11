
import asyncio
import contextlib
import json
import math
import time as _time  # top-level: one import per socket was wasteful (D4)
from datetime import UTC as _UTC
from datetime import datetime as _DT

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from loguru import logger
from sqlalchemy.orm import Session

from src.aac_app.db import create_session_factory as _csf
from src.aac_app.models import CommunicationBoard
from src.aac_app.models import User as _User
from src.aac_app.utils.jwt_utils import decode_access_token as _decode_token
from src.api.deps import get_db, get_text, validate_active_token
from src.api.deps.access import (
    require_board_collab_write_access,
    require_board_view_access,
)

router = APIRouter(prefix="/api/collab", tags=["collab"])


class ConnectionManager:
    MAX_ROOM_SIZE = 50
    SEND_TIMEOUT = 3.0

    def __init__(self):
        self.rooms: dict[int, set[WebSocket]] = {}

    async def connect(
        self,
        board_id: int,
        websocket: WebSocket,
        subprotocol: str | None = None,
    ):
        await websocket.accept(subprotocol=subprotocol)
        room = self.rooms.setdefault(board_id, set())
        if len(room) >= self.MAX_ROOM_SIZE:
            with contextlib.suppress(Exception):
                await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER, reason="Room full")
            return False
        room.add(websocket)
        logger.info(f"WS connected to board {board_id}")
        return True

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
        coros = []
        targets = []
        for ws in list(self.rooms.get(board_id, set())):
            if ws is sender:
                continue
            targets.append(ws)
            coros.append(ws.send_json(message))
        if not coros:
            return
        results = await asyncio.gather(*[asyncio.wait_for(c, timeout=self.SEND_TIMEOUT) for c in coros], return_exceptions=True)
        for ws, res in zip(targets, results, strict=False):
            if isinstance(res, Exception):
                logger.debug("WebSocket send failed for board {}; disconnecting client: {}", board_id, res)
                self.disconnect(board_id, ws)
                with contextlib.suppress(Exception):
                    await ws.close(code=status.WS_1011_INTERNAL_ERROR)


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

    E6 tightened the shape: ``symbol_id`` must be a positive int (a forged
    negative/zero id could never name a real placement), and ``x``/``y`` must
    be FINITE numbers (a ``1e999`` float serializes to ``Infinity`` and must
    not ride to every peer). Extra keys beyond ``op``/``symbol_id``/
    ``position`` are IGNORED and broadcast as-is: the receiver dereferences
    only the three fields above, so a faithful under-cap frame must not be
    mangled or dropped for carrying inert fields — the only key with content
    semantics (``label``) is vetted by the content gate before broadcast.
    """
    if data.get("op") != "move":
        return False
    symbol_id = data.get("symbol_id")
    if isinstance(symbol_id, bool) or not isinstance(symbol_id, int):
        return False
    if symbol_id <= 0:
        return False
    position = data.get("position")
    if not isinstance(position, dict):
        return False
    for axis in ("x", "y"):
        value = position.get(axis)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if isinstance(value, float) and not math.isfinite(value):
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

        # F06: release the request-scoped DB session (and its pooled
        # connection) before entering the long-lived socket loop. The initial
        # auth/permission reads are complete; holding this connection for the
        # socket's lifetime would let idle sockets exhaust the engine pool.
        # All in-loop DB work (revalidation, policy lookup, safety events)
        # uses short-lived sessions instead. Detached ORM attributes read in
        # the loop (user.id/username) were loaded above and remain accessible
        # after close.
        db.close()

        # Mark the room registration before awaiting accept so cancellation in
        # this tiny handoff window still triggers the outer cleanup path.
        connected = False
        ok = await manager.connect(board_id, websocket, subprotocol=auth_subprotocol)
        if not ok:
            return
        connected = True
        initial_payload = _decode_token(auth_token) if auth_token else None
        token_exp = (initial_payload or {}).get("exp", 0)
        token_sec_ver = (initial_payload or {}).get("sec_ver")
        token_iat = (initial_payload or {}).get("iat", 0)
        auth_user_id = user.id
        last_revalidate = _time.monotonic()
        revalidate_failures = 0  # consecutive transient failures (D4)
        REVALIDATE_MAX_FAILURES = 3
        shutdown_event = getattr(websocket.app.state, "shutdown_event", None)
        if not getattr(websocket.app.state, "lifespan_active", False):
            shutdown_event = None
        if shutdown_event is None:
            shutdown_event = asyncio.Event()
        REVALIDATE_INTERVAL = 60.0
        try:
            while True:
                # D4: cheap expiry check every iteration (no DB), not only every 60s.
                if token_exp and _time.time() > token_exp:
                    with contextlib.suppress(Exception):
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token expired")
                    return
                now_mono = _time.monotonic()
                if now_mono - last_revalidate >= REVALIDATE_INTERVAL:
                    last_revalidate = now_mono
                    # Fresh DB revalidation with short-lived session
                    try:
                        _db2 = _csf()()
                        try:
                            fresh_user = _db2.query(_User).filter(_User.id == auth_user_id).first()
                            if not fresh_user or not fresh_user.is_active:
                                with contextlib.suppress(Exception):
                                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access revoked")
                                return
                            if token_sec_ver is not None:
                                if token_sec_ver != (fresh_user.security_version or 1):
                                    with contextlib.suppress(Exception):
                                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access revoked")
                                    return
                            elif fresh_user.credentials_changed_at is not None and (
                                not token_iat
                                or _DT.fromtimestamp(token_iat, _UTC).replace(tzinfo=None)
                                < fresh_user.credentials_changed_at
                            ):
                                with contextlib.suppress(Exception):
                                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access revoked")
                                return
                            fresh_board = _db2.query(CommunicationBoard).filter(CommunicationBoard.id == board_id).first()
                            if not fresh_board:
                                with contextlib.suppress(Exception):
                                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Board removed")
                                return
                            try:
                                require_board_view_access(fresh_board, fresh_user, _db2)
                            except HTTPException as _exc:
                                if _exc.status_code == status.HTTP_403_FORBIDDEN:
                                    with contextlib.suppress(Exception):
                                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Access revoked")
                                    return
                                # Non-403 policy error: close 1011, do not swallow.
                                logger.warning("Collab revalidation policy error: {}", _exc)
                                with contextlib.suppress(Exception):
                                    await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Policy error")
                                return
                        finally:
                            _db2.close()
                        revalidate_failures = 0
                    except HTTPException:
                        raise
                    except Exception as exc:
                        revalidate_failures += 1
                        logger.warning(
                            "Collab revalidation transient failure {}/{}: {}",
                            revalidate_failures,
                            REVALIDATE_MAX_FAILURES,
                            exc,
                        )
                        if revalidate_failures >= REVALIDATE_MAX_FAILURES:
                            with contextlib.suppress(Exception):
                                await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Revalidation failed")
                            return
                        # Keep socket alive for this attempt; next 60s cycle retries.
                timeout = max(0.5, last_revalidate + REVALIDATE_INTERVAL - now_mono)
                receive_task = asyncio.create_task(websocket.receive_json())
                shutdown_task = asyncio.create_task(shutdown_event.wait())
                revalidate_task = asyncio.create_task(asyncio.sleep(timeout))
                try:
                    done, _ = await asyncio.wait(
                        (receive_task, shutdown_task, revalidate_task),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if shutdown_task in done:
                        with contextlib.suppress(Exception):
                            await websocket.close(code=status.WS_1001_GOING_AWAY, reason="Server shutting down")
                        return
                    if revalidate_task in done and receive_task not in done:
                        continue
                    data = receive_task.result()
                finally:
                    for task in (receive_task, shutdown_task, revalidate_task):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(receive_task, shutdown_task, revalidate_task, return_exceptions=True)

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

                # Layer-2 vocabulary gate FIRST (E6/C1): only the ``move`` op
                # with the exact shape the client receiver dereferences is
                # broadcast. Anything else — ``add``/``ping``/unknown ops,
                # malformed moves — is dropped here with the connection kept
                # alive. Running this gate BEFORE any policy/DB work means a
                # junk dict (e.g. ``{"op": "ping", "label": "<blocked>"}``)
                # is dropped without paying a policy lookup or writing a
                # content-safety row for a payload that would never be
                # broadcast anyway (an attacker could otherwise fill the
                # safety log without ever reaching a peer).
                if not _is_collab_move_payload(data):
                    logger.debug(
                        "Dropping non-move collab payload from {} ({} bytes)",
                        user.username,
                        payload_size,
                    )
                    continue

                # Layer-1 content gate (R2/E6): vets ONLY the will-broadcast
                # moves that actually carry a non-blank free-text ``label``
                # — the sole enforcement point of the guardian
                # ``block_social_messaging`` lock and the fail-closed net for
                # text that could not be vetted. (A label-less move has no
                # text to vet.) Blocked labels are never fanned out to the
                # room; the REST admission gates (get_or_create_symbol) are
                # the authoritative DB guard, this protects every connected
                # peer from forged input. Extra non-label keys ride along
                # inertly (see _is_collab_move_payload).
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
                        # messaging entirely for this student. Short-lived
                        # session inside resolve_policy_for_user (request db
                        # was closed before the socket loop, F06).
                        student_policy = resolve_policy_for_user(user.id)
                        if student_policy.feature_blocked("block_social_messaging"):
                            log_event(
                                user_id=user.id,
                                surface="social",
                                direction="output",
                                verdict="blocked",
                                matched=[],
                                detail="feature_lock: block_social_messaging",
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
                                detail="collab label blocked (content policy)",
                            )
                            # F09: log the event category only — the label
                            # itself is child communication and must not be
                            # duplicated into logs.
                            logger.info(
                                "Blocked collab label from {} ({} chars) by content policy",
                                user.username,
                                len(label_candidate),
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
