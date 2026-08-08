import asyncio
import os
import time
from contextlib import asynccontextmanager

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
from src.aac_app.services.symbol_image_backfill import backfill_missing_symbol_images
from src.aac_app.services.vector_utils import index_all_symbols
from src.api.debug_reporting import report_debug
from src.api.deps import (
    get_startup_state,
    reset_providers_async,
    warmup_providers,
)
from src.api.limiter import limiter
from src.api.logging_config import LOG_FILE
from src.api.routers import (
    achievements,
    admin,
    analytics,
    arasaac,
    auth,
    auth_preferences,
    auth_users,
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
            report_debug("A", "src/api/main.py:warmup_in_background:start", "Warmup background task started")
            # #endregion
            await asyncio.to_thread(warmup_providers, 30.0)
            # #region debug-point A:warmup-finish
            report_debug("A", "src/api/main.py:warmup_in_background:finish", "Warmup background task finished")
            # #endregion
        except asyncio.CancelledError:
            # #region debug-point A:warmup-cancelled
            report_debug("A", "src/api/main.py:warmup_in_background:cancelled", "Warmup background task cancelled")
            # #endregion
            raise
        except Exception as e:
            logger.error(f"Provider warmup failed: {e}")
            logger.exception("Warmup traceback:")
            # #region debug-point A:warmup-error
            report_debug("A", "src/api/main.py:warmup_in_background:error", "Warmup background task failed", {"error": str(e)})
            # #endregion

    warmup_task = asyncio.create_task(warmup_in_background(), name="provider-warmup")

    # Index symbols in the background.  The embedding model may need a
    # network download on first run, so it must not block health or keyword
    # search when the machine is offline.
    async def index_symbols_in_background() -> None:
        try:
            # #region debug-point A:index-start
            report_debug("A", "src/api/main.py:index_symbols_in_background:start", "Index background task started")
            # #endregion
            await asyncio.to_thread(index_all_symbols)
            # #region debug-point A:index-finish
            report_debug("A", "src/api/main.py:index_symbols_in_background:finish", "Index background task finished")
            # #endregion
        except asyncio.CancelledError:
            # #region debug-point A:index-cancelled
            report_debug("A", "src/api/main.py:index_symbols_in_background:cancelled", "Index background task cancelled")
            # #endregion
            raise
        except Exception as e:
            logger.error(f"Symbol indexing failed: {e}")
            # #region debug-point A:index-error
            report_debug("A", "src/api/main.py:index_symbols_in_background:error", "Index background task failed", {"error": str(e)})
            # #endregion

    index_task = asyncio.create_task(index_symbols_in_background(), name="symbol-indexing")

    async def backfill_symbol_images_in_background() -> None:
        try:
            if os.environ.get("TESTING") == "1":
                logger.info("Skipping symbol image backfill during tests")
                return
            if not config.get_bool("AAC_ENABLE_SYMBOL_IMAGE_BACKFILL", True):
                logger.info("Symbol image backfill disabled by configuration")
                return

            limit = max(config.get_int("AAC_SYMBOL_IMAGE_BACKFILL_LIMIT", 100), 0)
            if limit == 0:
                logger.info("Symbol image backfill skipped because the limit is 0")
                return

            await backfill_missing_symbol_images(limit=limit)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Symbol image backfill failed: {e}")

    image_backfill_task = asyncio.create_task(
        backfill_symbol_images_in_background(),
        name="symbol-image-backfill",
    )

    # #region debug-point A:task-created
    report_debug(
        "A",
        "src/api/main.py:lifespan:tasks-created",
        "Background startup tasks created",
        {
            "tasks": [
                warmup_task.get_name(),
                index_task.get_name(),
                image_backfill_task.get_name(),
            ]
        },
    )
    # #endregion

    def report_background_task_done(finished_task: asyncio.Task) -> None:
        """Report completion without raising from a done callback."""
        exception = None
        if not finished_task.cancelled():
            try:
                task_exception = finished_task.exception()
            except asyncio.CancelledError:
                task_exception = None
            exception = str(task_exception) if task_exception else None
        report_debug(
            "A",
            "src/api/main.py:lifespan:task-done",
            "Background task completed",
            {
                "task": finished_task.get_name(),
                "cancelled": finished_task.cancelled(),
                "exception": exception,
            },
        )

    for task in (warmup_task, index_task, image_backfill_task):
        task.add_done_callback(report_background_task_done)

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
    report_debug("A", "src/api/main.py:lifespan:ready", "Lifespan startup reached yield")
    # #endregion

    try:
        yield
    finally:
        logger.info("Shutting down AAC Assistant API...")
        # #region debug-point C:lifespan-shutdown
        report_debug("C", "src/api/main.py:lifespan:shutdown", "Lifespan shutdown entered")
        # #endregion

        startup_tasks = (warmup_task, index_task, image_backfill_task)
        pending_tasks = [task for task in startup_tasks if not task.done()]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            # Await task cancellation so no asyncio task survives the ASGI
            # lifespan. asyncio.to_thread workers may continue independently,
            # but their wrapper tasks are now fully drained and cannot emit
            # unhandled exceptions during server shutdown. The timeout also
            # keeps a non-cooperative optional task from blocking shutdown.
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending_tasks, return_exceptions=True),
                    timeout=max(config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS, 1),
                )
            except TimeoutError:
                logger.warning(
                    "Timed out waiting for startup tasks to shut down: {}",
                    ", ".join(task.get_name() for task in pending_tasks if not task.done()),
                )

        # Provider singletons own HTTP/model resources and must be released
        # after background tasks stop using them. Cleanup is idempotent and
        # deliberately outside the task wait so shutdown remains bounded.
        await reset_providers_async()


# Initialize FastAPI app
logger.debug(f"Loading main.py from {__file__}")

app = FastAPI(
    title="AAC Assistant API",
    description="Backend API for the AAC Assistant application",
    version=config.APP_VERSION,
    lifespan=lifespan,
)

# Add rate limiter to app state (exemptions handled per-route)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/api/health")
async def root():
    """Health check endpoint"""
    return {"status": "online", "app": "AAC Assistant API", "version": config.APP_VERSION}


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
                "provider_metrics": startup_state.get("provider_metrics", {}),
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
                "provider_metrics": startup_state.get("provider_metrics", {}),
            },
        )

    return {
        "ready": True,
        "status": "healthy",
        "message": "All providers initialized and ready",
        "providers": startup_state["providers_ready"],
        "startup_time_ms": startup_state["startup_time_ms"],
        "provider_metrics": startup_state.get("provider_metrics", {}),
    }


app.include_router(config_router.router)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(auth_users.router, prefix="/api/auth", tags=["auth"])
app.include_router(auth_preferences.router, prefix="/api/auth", tags=["auth"])
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

def resolve_allowed_origins(
    configured_origins: str,
    environment: str,
    frontend_port: int,
) -> list[str]:
    """Resolve CORS origins without silently weakening production isolation."""
    origins = [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
    if "*" in origins:
        raise RuntimeError(
            "ALLOWED_ORIGINS must not contain '*' when credentialed CORS is enabled"
        )
    if origins:
        return origins
    if environment.strip().casefold() != "development":
        raise RuntimeError(
            "ALLOWED_ORIGINS must contain explicit origins outside development"
        )

    # Development fallback keeps local setup convenient, but is never used in
    # production where silently allowing localhost would weaken deployment
    # isolation.
    logger.warning("ALLOWED_ORIGINS is empty; falling back to development defaults")
    return [
        f"http://localhost:{frontend_port}",
        f"http://127.0.0.1:{frontend_port}",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


origins = resolve_allowed_origins(
    config.ALLOWED_ORIGINS,
    config.ENVIRONMENT,
    config.FRONTEND_PORT,
)

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
