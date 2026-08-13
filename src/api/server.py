"""Uvicorn integration for application-aware graceful shutdown."""

from __future__ import annotations

from typing import Any

import uvicorn


class ShutdownAwareServer(uvicorn.Server):
    """Signal long-lived app connections before Uvicorn waits for them."""

    def __init__(self, config: uvicorn.Config, *, app: Any) -> None:
        self._aac_app = app
        super().__init__(config)

    async def shutdown(self, *args: Any, **kwargs: Any) -> None:
        shutdown_event = getattr(self._aac_app.state, "shutdown_event", None)
        if shutdown_event is not None:
            shutdown_event.set()
        await super().shutdown(*args, **kwargs)
