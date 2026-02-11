import sys
import os
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.append(str(PROJECT_ROOT))

def prepare_db(target_dir):
    """Initialize a test database in the target directory"""
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)
    
    db_path = target_path / "aac_assistant.db"
    
    logger.info(f"Preparing test database at {db_path}")
    
    # Remove existing database to ensure clean slate
    if db_path.exists():
        logger.info("Removing existing database")
        try:
            db_path.unlink()
        except PermissionError:
            logger.error(f"Cannot delete {db_path}. Is it in use?")
            return

    # Import and configure
    try:
        import src.config
        
        # Override config values to point to the new location
        src.config.DATA_DIR = target_path
        src.config.DATABASE_PATH = db_path
        
        # Import database module (after config is patched)
        from src.aac_app.models import database
        
        # Monkey patch get_database_path just in case
        original_get_db_path = database.get_database_path
        database.get_database_path = lambda: str(db_path)
        
        # Run initialization (creates tables and seed data)
        database.init_database()
        
        # Verify creation
        if db_path.exists():
            size = db_path.stat().st_size
            logger.info(f"Test database created successfully ({size} bytes)")
        else:
            logger.error("Failed to create database file")
            sys.exit(1)
            
    except ImportError as e:
        logger.error(f"Failed to import dependencies: {e}")
        logger.error("Ensure you are running this script in an environment with project dependencies installed (sqlalchemy, loguru, etc).")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Database preparation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
    else:
        # Default to dist data dir relative to script location
        target_dir = str(PROJECT_ROOT / "dist" / "AAC_Assistant_Package" / "data")
        
    prepare_db(target_dir)
