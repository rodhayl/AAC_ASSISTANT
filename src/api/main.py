import os
import sys
import warnings
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.aac_app.models.database import init_database
from src.aac_app.models.migrate_add_order_index import migrate_add_order_index
from src.aac_app.models.migrate_add_ui_language import migrate_add_ui_language
from src.aac_app.services.collaboration_service import collaboration_service
from src.aac_app.services.vector_utils import index_all_symbols
from src.api.limiter import limiter
from src.api.dependencies import get_startup_state, warmup_providers
from src.api.logging_config import LOG_FILE
from src import config
from src.api.routers import (
    achievements,
    admin,
    analytics,
    arasaac,
    auth,
    boards,
    collab,
)
from src.api.routers import config as config_router
from src.api.routers import (
    export_import,
    guardian_profiles,
    learning,
    learning_modes,
    notifications,
    providers,
    settings,
    users,
)

# Suppress deprecated pkg_resources warning from webrtcvad
warnings.filterwarnings("ignore", category=UserWarning, module="webrtcvad")
# Also suppress the specific message just in case module name varies or is imported indirectly
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup"""
    logger.info("=" * 60)
    logger.info("Starting AAC Assistant API...")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info("=" * 60)

    # Initialize database
    try:
        init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        logger.exception("Database initialization traceback:")

    # Ensure migrations that add required columns are applied (idempotent)
    try:
        migrate_add_order_index()
        migrate_add_ui_language()
    except Exception as e:
        logger.error(f"Failed to apply migrations: {e}")
        logger.exception("Migration traceback:")

    # Eagerly initialize all providers at startup
    # This prevents slow first requests and potential deadlocks
    try:
        warmup_providers(timeout_seconds=30.0)
    except Exception as e:
        logger.error(f"Provider warmup failed: {e}")
        logger.exception("Warmup traceback:")

    # Index symbols for semantic search
    try:
        index_all_symbols()
    except Exception as e:
        logger.error(f"Symbol indexing failed: {e}")

    logger.info("Server ready to accept requests")

    yield

    logger.info("Shutting down AAC Assistant API...")


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

# Mount Socket.IO app
app.mount("/socket.io", collaboration_service.app)

# Static files
# Use frozen-aware paths from config module
from src.config import PROJECT_ROOT, BUNDLE_DIR, IS_FROZEN

BASE_DIR = str(PROJECT_ROOT)
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")

# Create uploads directory if it doesn't exist
os.makedirs(UPLOADS_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Serve built frontend static files (for production package)
# In frozen mode, check BUNDLE_DIR for frontend; otherwise check PROJECT_ROOT
if IS_FROZEN:
    # Frozen mode: frontend is bundled at BUNDLE_DIR/frontend
    FRONTEND_DIR = os.path.join(str(BUNDLE_DIR), "frontend")
else:
    # Development mode: check for built frontend
    FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
    if not os.path.exists(FRONTEND_DIR):
        FRONTEND_DIR = os.path.join(BASE_DIR, "src", "frontend", "dist")

if os.path.exists(FRONTEND_DIR):
    from fastapi.responses import FileResponse
    
    # Mount static assets (JS, CSS, images)
    assets_dir = os.path.join(FRONTEND_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    
    # Serve index.html for SPA routes
    # Serve index.html for SPA routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA frontend for all non-API routes"""
        # Skip API routes
        if full_path.startswith("api/") or full_path.startswith("socket.io"):
            return JSONResponse(content={"detail": "Not Found"}, status_code=404)
        
        # Try to serve static file first
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        
        # Fall back to index.html for SPA routing
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        
        return JSONResponse(content={"detail": "Not Found"}, status_code=404)

    # Explicitly handle root for SPA
    @app.get("/")
    async def serve_spa_root():
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return JSONResponse(content={"detail": "Frontend not found"}, status_code=404)

# Configure CORS
# Split comma-separated string into list
origins = [origin.strip() for origin in config.ALLOWED_ORIGINS.split(",") if origin.strip()]

if not origins:
    # Safety net: if env.properties or env vars misconfigure ALLOWED_ORIGINS,
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
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8086, reload=True)
