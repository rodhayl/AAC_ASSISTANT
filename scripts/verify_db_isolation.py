
import os
import sys
import time
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src import config

def verify_isolation():
    db_path = config.DATABASE_PATH
    print(f"Database path: {db_path}")
    
    if not db_path.exists():
        print("Database does not exist! Creating it via validate_database...")
        # Create it by running validate (which might check schema) or init
        # Actually, let's just run init_db logic if needed, but for now assume it exists
        # or that tests shouldn't create it either if it doesn't exist.
        pass

    initial_stat = None
    if db_path.exists():
        initial_stat = db_path.stat()
        print(f"Initial size: {initial_stat.st_size}, mtime: {initial_stat.st_mtime}")
    else:
        print("Database file not found initially.")

    print("\nRunning tests...")
    # Run a simple test that involves DB operations
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_api_basic.py", "-v"],
        capture_output=True,
        text=True
    )
    
    print("Test output:")
    print(result.stdout)
    if result.stderr:
        print("Test errors:")
        print(result.stderr)
        
    if result.returncode != 0:
        print("Tests failed!")
        # We continue to check isolation anyway
    
    print("\nChecking database file...")
    if not db_path.exists():
        if initial_stat:
             print("❌ ERROR: Database file was DELETED!")
             return False
        else:
             print("✓ Database file still doesn't exist (good).")
             return True

    final_stat = db_path.stat()
    print(f"Final size: {final_stat.st_size}, mtime: {final_stat.st_mtime}")

    if initial_stat:
        if final_stat.st_mtime != initial_stat.st_mtime or final_stat.st_size != initial_stat.st_size:
            print("❌ ERROR: Database file was MODIFIED during tests!")
            return False
        else:
            print("✅ Database file was NOT modified. Isolation successful.")
            return True
    else:
        print("❌ ERROR: Database file was CREATED during tests!")
        return False

if __name__ == "__main__":
    success = verify_isolation()
    sys.exit(0 if success else 1)
