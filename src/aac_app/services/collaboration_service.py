from typing import Any, Dict, List, Optional

import socketio
from loguru import logger

from src import config


def _get_cors_origins() -> List[str]:
    """
    Get CORS allowed origins from config.
    In production, never allows '*' wildcard.
    """
    origins_str = config.ALLOWED_ORIGINS
    if not origins_str:
        # Default development origins
        return [
            f"http://localhost:{config.FRONTEND_PORT}",
            "http://localhost:3000",
            "http://localhost:5173",
        ]
    
    origins = [origin.strip() for origin in origins_str.split(",") if origin.strip()]
    
    # Security: In production, reject wildcard
    if config.ENVIRONMENT == "production":
        origins = [o for o in origins if o != "*"]
        if not origins:
            logger.warning("No valid CORS origins configured for production Socket.IO")
            # Fall back to same-origin only
            return []
    
    return origins


class CollaborationService:
    """
    Service for real-time collaboration using Socket.IO.
    Handles multi-teacher sessions, plan sharing, and live feedback.
    """

    def __init__(self, cors_origins: Optional[List[str]] = None):
        # Use provided origins for testing, or get from config
        allowed_origins = cors_origins if cors_origins is not None else _get_cors_origins()
        self.sio = socketio.AsyncServer(
            async_mode="asgi",
            cors_allowed_origins=allowed_origins if allowed_origins else []
        )
        self.app = socketio.ASGIApp(self.sio)
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self._setup_events()

    def _setup_events(self):
        @self.sio.event
        async def connect(sid, environ):
            logger.info(f"Client connected: {sid}")
            await self.sio.emit("connection_response", {"data": "Connected"}, room=sid)

        @self.sio.event
        async def disconnect(sid):
            logger.info(f"Client disconnected: {sid}")
            # Cleanup user from sessions
            for session_id, session in self.active_sessions.items():
                if sid in session.get("participants", []):
                    session["participants"].remove(sid)
                    await self.sio.emit(
                        "participant_left", {"sid": sid}, room=session_id
                    )

        @self.sio.event
        async def join_session(sid, data):
            session_id = data.get("session_id")
            user_info = data.get("user_info", {})
            if not session_id:
                return

            self.sio.enter_room(sid, session_id)

            if session_id not in self.active_sessions:
                self.active_sessions[session_id] = {"participants": [], "data": {}}

            self.active_sessions[session_id]["participants"].append(sid)

            logger.info(f"User {sid} joined session {session_id}")
            await self.sio.emit(
                "user_joined", {"sid": sid, "user": user_info}, room=session_id
            )

        @self.sio.event
        async def send_message(sid, data):
            session_id = data.get("session_id")
            message = data.get("message")
            if session_id:
                await self.sio.emit(
                    "new_message", {"sender": sid, "message": message}, room=session_id
                )

        @self.sio.event
        async def update_board(sid, data):
            """Real-time board editing"""
            session_id = data.get("session_id")
            changes = data.get("changes")
            if session_id:
                await self.sio.emit(
                    "board_updated",
                    {"sender": sid, "changes": changes},
                    room=session_id,
                    skip_sid=sid,
                )

    async def broadcast_notification(self, title: str, message: str):
        """Broadcast a system-wide notification"""
        await self.sio.emit("system_notification", {"title": title, "message": message})


# Global instance
collaboration_service = CollaborationService()
