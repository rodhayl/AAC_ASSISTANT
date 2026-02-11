from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from src import config
from src.aac_app.models.database import Base, create_engine_instance, init_database
from src.api.dependencies import get_current_admin_user, get_text

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/reset-db")
def reset_database(user=Depends(get_current_admin_user)):
    """
    Reset the database (drop all tables and recreate).
    
    SECURITY: This endpoint is disabled by default. To enable, set ALLOW_DB_RESET=true
    in env.properties. This should NEVER be enabled in production environments.
    """
    # Security check: prevent accidental production database wipe
    if not config.ALLOW_DB_RESET:
        logger.warning(
            f"Database reset attempted by user {user.username} but ALLOW_DB_RESET is disabled"
        )
        raise HTTPException(
            status_code=403,
            detail="Database reset is disabled. Set ALLOW_DB_RESET=true in env.properties to enable.",
        )
    
    # Additional production environment check
    if config.ENVIRONMENT == "production":
        logger.error(
            f"CRITICAL: Database reset attempted in PRODUCTION by user {user.username}"
        )
        raise HTTPException(
            status_code=403,
            detail="Database reset is blocked in production environments.",
        )
    
    try:
        logger.warning(f"Database reset initiated by admin user: {user.username}")
        engine = create_engine_instance()
        logger.warning("Dropping all tables for database reset...")
        Base.metadata.drop_all(engine)
        logger.info("Creating tables...")
        Base.metadata.create_all(engine)
        logger.info("Seeding database initial data...")
        init_database()
        logger.info(f"Database reset completed successfully by {user.username}")
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to reset database: {e}")
        error_msg = get_text(
            user=user, key="errors.admin.databaseResetFailed", error=str(e)
        )
        return {"ok": False, "error": error_msg}
