import asyncio
import os
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src import config
from src.aac_app import schema
from src.aac_app.seed import init_database
from src.aac_app.services.arasaac_library_import import import_arasaac_library_if_needed
from src.aac_app.services.ngram_builder import rebuild_ngram_models
from src.aac_app.services.symbol_image_backfill import backfill_missing_symbol_images
from src.aac_app.services.vector_utils import index_all_symbols
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
from src.api.spa import ImmutableStaticFiles, SPAStaticFiles, resolve_frontend_directory


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    startup_started = time.perf_counter()
    app.state.database_ready = False
    app.state.database_startup_error = False
    app.state.lifespan_active = False
    # Long-lived SSE/WebSocket handlers use this signal to leave their receive
    # loops before Uvicorn's graceful-shutdown deadline expires.
    app.state.shutdown_event = asyncio.Event()
    logger.info("=" * 60)
    logger.info("Starting AAC Assistant API...")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info("=" * 60)

    # Create/update schema once, then seed data.
    try:
        schema.ensure()
        init_database(ensure_schema=False)
        app.state.database_ready = True
        logger.info("Database initialized successfully")
    except Exception as e:
        app.state.database_startup_error = True
        logger.error(f"Failed to initialize database: {e}")
        logger.exception("Database initialization traceback:")

    # Warm up providers in the background so the port binds immediately.
    # /ready returns 503 warming_up until warmup completes (its designed
    # purpose); /api/health and the SPA are available right away.  All
    # provider consumers use lazy Depends singletons, so requests that
    # need a provider will construct it on demand if warmup hasn't yet.
    async def warmup_in_background() -> None:
        try:
            await asyncio.to_thread(warmup_providers, 30.0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Provider warmup failed: {e}")
            logger.exception("Warmup traceback:")

    warmup_task = asyncio.create_task(warmup_in_background(), name="provider-warmup")

    # Index symbols in the background. The embedding model may need a network
    # download on first run, so it must not block health or keyword search when
    # the machine is offline. Track the real worker separately: cancelling an
    # asyncio.to_thread wrapper does not cancel its underlying thread.
    index_finished = threading.Event()
    index_started = threading.Event()
    shutdown_started = threading.Event()

    def run_index() -> None:
        index_started.set()
        if shutdown_started.is_set() or not app.state.database_ready:
            if not app.state.database_ready:
                logger.warning("Skipping symbol indexing because database initialization failed")
            index_finished.set()
            return
        try:
            index_all_symbols()
        finally:
            index_finished.set()

    async def index_symbols_in_background() -> None:
        try:
            await asyncio.to_thread(run_index)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Symbol indexing failed: {e}")

    index_task = asyncio.create_task(index_symbols_in_background(), name="symbol-indexing")

    async def backfill_symbol_images_in_background() -> None:
        try:
            if not app.state.database_ready:
                logger.warning(
                    "Skipping symbol image backfill because database initialization failed"
                )
                return
            if os.environ.get("TESTING") == "1":
                logger.info("Skipping symbol image backfill during tests")
                return
            if not config.get_bool("AAC_ENABLE_SYMBOL_IMAGE_BACKFILL", False):
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

    async def import_arasaac_library_in_background() -> None:
        try:
            if not app.state.database_ready:
                logger.warning(
                    "Skipping ARASAAC library import because database initialization failed"
                )
                return
            if os.environ.get("TESTING") == "1":
                logger.info("Skipping ARASAAC library import during tests")
                return
            if not config.get_bool("AAC_ENABLE_ARASAAC_LIBRARY_IMPORT", False):
                logger.info("ARASAAC library import disabled by configuration")
                return
            locales = [
                locale.strip()
                for locale in str(
                    config.get("AAC_ARASAAC_LIBRARY_LOCALES", "es")
                ).split(",")
                if locale.strip()
            ] or ["es"]
            for locale in locales:
                await import_arasaac_library_if_needed(locale=locale)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"ARASAAC library import failed: {e}")

    arasaac_import_task = asyncio.create_task(
        import_arasaac_library_in_background(),
        name="arasaac-library-import",
    )

    async def rebuild_ngrams_in_background() -> None:
        try:
            if not app.state.database_ready:
                logger.warning(
                    "Skipping n-gram rebuild because database initialization failed"
                )
                return
            if os.environ.get("TESTING") == "1":
                logger.info("Skipping n-gram rebuild during tests")
                return
            if not config.get_bool("AAC_ENABLE_NGRAM_REBUILD", False):
                logger.info("N-gram rebuild disabled by configuration")
                return
            locales = tuple(
                locale.strip()
                for locale in str(
                    config.get("AAC_ARASAAC_LIBRARY_LOCALES", "es")
                ).split(",")
                if locale.strip()
            ) or ("es",)
            await asyncio.to_thread(rebuild_ngram_models, None, locales)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"N-gram rebuild failed: {e}")

    ngram_rebuild_task = asyncio.create_task(
        rebuild_ngrams_in_background(),
        name="ngram-model-rebuild",
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
    app.state.lifespan_active = True
    try:
        yield
    finally:
        logger.info("Shutting down AAC Assistant API...")
        app.state.shutdown_event.set()
        shutdown_started.set()
        # Uvicorn applies the same value as a hard lifespan timeout. Reserve a
        # strictly positive handoff buffer so application cleanup finishes
        # before Uvicorn force-cancels the lifespan task (especially on
        # Windows signal exit), including low configured timeout values.
        graceful_timeout = max(
            float(config.BACKEND_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS), 1.0
        )
        handoff_buffer = min(2.0, graceful_timeout * 0.25)
        shutdown_budget = graceful_timeout - handoff_buffer
        shutdown_deadline = asyncio.get_running_loop().time() + shutdown_budget
        startup_tasks = (
            warmup_task,
            index_task,
            image_backfill_task,
            arasaac_import_task,
            ngram_rebuild_task,
        )
        pending_tasks = [task for task in startup_tasks if not task.done()]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            # Await task cancellation so no asyncio task survives the ASGI
            # lifespan. asyncio.to_thread workers may continue independently,
            # but their wrapper tasks are now fully drained and cannot emit
            # unhandled exceptions during server shutdown. Share one deadline
            # across every shutdown phase.
            remaining = shutdown_deadline - asyncio.get_running_loop().time()
            if remaining > 0:
                try:
                    task_results = await asyncio.wait_for(
                        asyncio.gather(*pending_tasks, return_exceptions=True),
                        timeout=remaining,
                    )
                    for task, result in zip(pending_tasks, task_results, strict=True):
                        if isinstance(result, BaseException) and not isinstance(
                            result, asyncio.CancelledError
                        ):
                            logger.error(
                                "Startup task failed during shutdown ({}): {}",
                                task.get_name(),
                                result,
                            )
                except TimeoutError:
                    logger.warning(
                        "Timed out waiting for startup tasks to shut down: {}",
                        ", ".join(task.get_name() for task in pending_tasks if not task.done()),
                    )

        # If cancellation happened before the executor started the indexing
        # callable, no worker can ever set its completion event. Mark it
        # finished only after the wrapper has been drained; a late callable
        # observes shutdown_started and exits without touching the store.
        if not index_started.is_set():
            index_finished.set()

        # A cancelled to_thread wrapper can return while its synchronous index
        # worker is still running. Wait within the same shutdown budget before
        # closing the shared vector store; otherwise reset could close it under
        # an active worker. If the worker does not stop in time, reset leaves
        # that store alive until process exit instead of using it after close.
        while not index_finished.is_set():
            remaining = shutdown_deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.warning(
                    "Symbol indexing worker still running; deferring vector-store close"
                )
                break
            await asyncio.sleep(min(remaining, 0.05))

        # Provider singletons own HTTP/model resources and must be released
        # after background tasks stop using them. Cleanup is idempotent and
        # deliberately outside the task wait so shutdown remains bounded.
        remaining = max(
            shutdown_deadline - asyncio.get_running_loop().time(),
            0.01,
        )
        await reset_providers_async(
            close_vector_store=index_finished.is_set(),
            timeout_seconds=remaining,
        )
        app.state.lifespan_active = False


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


@app.middleware("http")
async def add_api_cache_control(request: Request, call_next):
    """Prevent browsers from caching API responses.

    API payloads are dynamic (lists, profiles, settings) and can change
    between requests, e.g. immediately after a create/update. Without an
    explicit Cache-Control policy Chromium may serve a stale response for a
    repeated GET from its in-memory cache, hiding newly created data. Static
    assets and /uploads are deliberately not covered.
    """
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/api/health")
async def root():
    """Health check endpoint"""
    return {"status": "online", "app": "AAC Assistant API", "version": config.APP_VERSION}


@app.get("/ready")
async def readiness_check():
    """
    Readiness check endpoint.

    Returns 200 only after database and provider initialization succeed.
    Returns 503 while warming up, when the database is unavailable, or when
    one or more providers failed to initialize.

    This endpoint can be used by load balancers or the frontend to know
    when the server is fully ready to handle requests.
    """
    startup_state = get_startup_state()

    if getattr(app.state, "database_startup_error", False):
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "status": "database_unavailable",
                "message": "Database initialization failed; server is not ready",
            },
        )

    if not getattr(app.state, "database_ready", False):
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "status": "database_initializing",
                "message": "Database is still initializing",
            },
        )

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
# Uploads are content-addressed by UUID filename (see _save_symbol_image and
# the ARASAAC backfill), so immutable caching is safe and avoids re-fetching
# the pictogram library on every board render.
app.mount("/uploads", ImmutableStaticFiles(directory=UPLOADS_DIR), name="uploads")

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
