import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib import request

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src import config
from src.aac_app import schema
from src.aac_app.seed import init_database
from src.aac_app.services.vector_utils import index_all_symbols
from src.api.deps import get_startup_state, warmup_providers
from src.api.limiter import limiter
from src.api.logging_config import LOG_FILE
from src.api.routers import (
    achievements,
    admin,
    analytics,
    arasaac,
    auth,
    board_ai,
    board_assignments,
    boards,
    collab,
    export_import,
    guardian_profiles,
    learning,
    learning_modes,
    notifications,
    providers,
    settings,
    symbols,
    users,
)
from src.api.routers import config as config_router
from src.api.spa import SPAStaticFiles, resolve_frontend_directory


# #region debug-point A:lifespan-helper
def _debug_report(hypothesis_id: str, location: str, msg: str, data: dict | None = None) -> None:
    _env_path = Path(".dbg/server-shutdown-hang.env")
    _url = "http://127.0.0.1:7777/event"
    _session_id = "server-shutdown-hang"
    try:
        if _env_path.is_file():
            for line in _env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("DEBUG_SERVER_URL="):
                    _url = line.split("=", 1)[1].strip() or _url
                elif line.startswith("DEBUG_SESSION_ID="):
                    _session_id = line.split("=", 1)[1].strip() or _session_id
        payload = json.dumps(
            {
                "sessionId": _session_id,
                "runId": "pre-fix",
                "hypothesisId": hypothesis_id,
                "location": location,
                "msg": f"[DEBUG] {msg}",
                "data": data or {},
                "ts": int(time.time() * 1000),
            }
        ).encode()
        request.urlopen(
            request.Request(_url, data=payload, headers={"Content-Type": "application/json"}),
            timeout=1,
        ).read()
    except Exception:
        pass


# #endregion


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup"""
    startup_started = time.perf_counter()
    logger.info("=" * 60)
    logger.info("Starting AAC Assistant API...")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info("=" * 60)

    # Create/update schema once, then seed data.
    try:
        schema.ensure()
        init_database(ensure_schema=False)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        logger.exception("Database initialization traceback:")

    # Warm up providers in the background so the port binds immediately.
    # /ready returns 503 warming_up until warmup completes (its designed
    # purpose); /api/health and the SPA are available right away.  All
    # provider consumers use lazy Depends singletons, so requests that
    # need a provider will construct it on demand if warmup hasn't yet.
    async def warmup_in_background() -> None:
        try:
            # #region debug-point A:warmup-start
            _debug_report("A", "src/api/main.py:warmup_in_background:start", "Warmup background task started")
            # #endregion
            await asyncio.to_thread(warmup_providers, 30.0)
            # #region debug-point A:warmup-finish
            _debug_report("A", "src/api/main.py:warmup_in_background:finish", "Warmup background task finished")
            # #endregion
        except asyncio.CancelledError:
            # #region debug-point A:warmup-cancelled
            _debug_report("A", "src/api/main.py:warmup_in_background:cancelled", "Warmup background task cancelled")
            # #endregion
            raise
        except Exception as e:
            logger.error(f"Provider warmup failed: {e}")
            logger.exception("Warmup traceback:")
            # #region debug-point A:warmup-error
            _debug_report("A", "src/api/main.py:warmup_in_background:error", "Warmup background task failed", {"error": str(e)})
            # #endregion

    warmup_task = asyncio.create_task(warmup_in_background(), name="provider-warmup")

    # Index symbols in the background.  The embedding model may need a
    # network download on first run, so it must not block health or keyword
    # search when the machine is offline.
    async def index_symbols_in_background() -> None:
        try:
            # #region debug-point A:index-start
            _debug_report("A", "src/api/main.py:index_symbols_in_background:start", "Index background task started")
            # #endregion
            await asyncio.to_thread(index_all_symbols)
            # #region debug-point A:index-finish
            _debug_report("A", "src/api/main.py:index_symbols_in_background:finish", "Index background task finished")
            # #endregion
        except asyncio.CancelledError:
            # #region debug-point A:index-cancelled
            _debug_report("A", "src/api/main.py:index_symbols_in_background:cancelled", "Index background task cancelled")
            # #endregion
            raise
        except Exception as e:
            logger.error(f"Symbol indexing failed: {e}")
            # #region debug-point A:index-error
            _debug_report("A", "src/api/main.py:index_symbols_in_background:error", "Index background task failed", {"error": str(e)})
            # #endregion

    index_task = asyncio.create_task(index_symbols_in_background(), name="symbol-indexing")

    # #region debug-point A:task-created
    _debug_report(
        "A",
        "src/api/main.py:lifespan:tasks-created",
        "Background startup tasks created",
        {"tasks": [warmup_task.get_name(), index_task.get_name()]},
    )
    # #endregion

    for task in (warmup_task, index_task):
        task.add_done_callback(
            lambda finished_task: _debug_report(
                "A",
                "src/api/main.py:lifespan:task-done",
                "Background task completed",
                {
                    "task": finished_task.get_name(),
                    "cancelled": finished_task.cancelled(),
                    "exception": str(finished_task.exception()) if not finished_task.cancelled() and finished_task.exception() else None,
                },
            )
        )

    startup_time_ms = (time.perf_counter() - startup_started) * 1000
    logger.info(f"Startup timing: initialization completed in {startup_time_ms:.0f}ms")
    display_host = (
        "127.0.0.1" if config.BACKEND_HOST in {"0.0.0.0", "::"} else config.BACKEND_HOST
    )
    logger.info(
        f"Serving URL: http://{display_host}:{config.BACKEND_PORT}"
    )
    logger.info("Server ready to accept requests")
    # #region debug-point A:lifespan-ready
    _debug_report("A", "src/api/main.py:lifespan:ready", "Lifespan startup reached yield")
    # #endregion

    yield

    logger.info("Shutting down AAC Assistant API...")
    # #region debug-point C:lifespan-shutdown
    _debug_report("C", "src/api/main.py:lifespan:shutdown", "Lifespan shutdown entered")
    # #endregion


# Initialize FastAPI app
logger.debug(f"Loading main.py from {__file__}")

app = FastAPI(
    title="AAC Assistant API",
    description="Backend API for the AAC Assistant application",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter to app state (exemptions handled per-route)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/api/health")
async def root():
    """Health check endpoint"""
    return {"status": "online", "app": "AAC Assistant API", "version": "1.0.0"}


@app.get("/ready")
async def readiness_check():
    """
    Readiness check endpoint.

    Returns 200 if all providers are initialized and ready.
    Returns 503 if still warming up or if there were initialization errors.

    This endpoint can be used by load balancers or the frontend to know
    when the server is fully ready to handle requests.
    """
    startup_state = get_startup_state()

    if not startup_state["initialized"]:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "status": "warming_up",
                "message": "Server is still initializing providers",
                "providers": startup_state["providers_ready"],
            },
        )

    # Check if all providers are ready
    all_ready = all(startup_state["providers_ready"].values())

    if not all_ready:
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "status": "degraded",
                "message": "Some providers failed to initialize",
                "providers": startup_state["providers_ready"],
                "errors": startup_state["errors"],
                "startup_time_ms": startup_state["startup_time_ms"],
            },
        )

    return {
        "ready": True,
        "status": "healthy",
        "message": "All providers initialized and ready",
        "providers": startup_state["providers_ready"],
        "startup_time_ms": startup_state["startup_time_ms"],
    }


app.include_router(config_router.router)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(symbols.router, prefix="/api/boards", tags=["boards"])
app.include_router(board_ai.router, prefix="/api/boards", tags=["boards"])
app.include_router(board_assignments.router, prefix="/api/boards", tags=["boards"])
app.include_router(boards.router, prefix="/api/boards", tags=["boards"])
app.include_router(arasaac.router, prefix="/api/arasaac", tags=["arasaac"])
app.include_router(learning.router, prefix="/api/learning", tags=["learning"])
app.include_router(learning_modes.router, prefix="/api/learning-modes", tags=["learning-modes"])
app.include_router(
    achievements.router, prefix="/api/achievements", tags=["achievements"]
)
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(guardian_profiles.router)  # Guardian profiles for Learning Companion
app.include_router(settings.router)
app.include_router(collab.router)
app.include_router(providers.router)
app.include_router(admin.router)
app.include_router(export_import.router)
app.include_router(notifications.router)
app.include_router(users.router, prefix="/api/users", tags=["users"])

# Static files are mounted after all API routers so /api/* keeps API semantics.
# In frozen builds PyInstaller exposes bundled resources through sys._MEIPASS,
# which is represented by config.BUNDLE_DIR.
from src.config import BUNDLE_DIR, IS_FROZEN, PROJECT_ROOT

UPLOADS_DIR = config.UPLOADS_DIR
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

FRONTEND_PATH = resolve_frontend_directory(
    project_root=PROJECT_ROOT,
    bundle_dir=BUNDLE_DIR,
    is_frozen=IS_FROZEN,
)
if FRONTEND_PATH is not None:
    app.mount(
        "/",
        SPAStaticFiles(directory=FRONTEND_PATH, html=True),
        name="frontend",
    )
else:
    logger.warning(
        "Built frontend not found; production SPA serving is unavailable. "
        "Expected src/frontend/dist or a bundled frontend directory."
    )

# Configure CORS
# Split comma-separated string into list
origins = [origin.strip() for origin in config.ALLOWED_ORIGINS.split(",") if origin.strip()]

if not origins:
    # Safety net: if .env, legacy env.properties, or env vars misconfigure ALLOWED_ORIGINS,
    # fall back to common dev origins so the frontend can still connect.
    logger.warning(
        "ALLOWED_ORIGINS is empty; falling back to development defaults"
    )
    origins = [
        f"http://localhost:{config.FRONTEND_PORT}",
        f"http://127.0.0.1:{config.FRONTEND_PORT}",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host=config.BACKEND_HOST,
        port=config.BACKEND_PORT,
        timeout_graceful_shutdown=config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS,
    )
