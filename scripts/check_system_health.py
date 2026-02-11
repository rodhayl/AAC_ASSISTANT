"""
System Health Check Script
Run this to verify the integrity of the codebase, database, and critical configurations.
Usage: python scripts/check_system_health.py
"""

import sys
from pathlib import Path

import pytest

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_check(name, check_func):
    """Helper to run a check and print status"""
    print(f"\n[CHECK] {name}...")
    try:
        check_func()
        print(f"✅ {name}: PASS")
        return True
    except Exception as e:
        print(f"❌ {name}: FAIL")
        print(f"   Error: {e}")
        return False


def check_orm_mapping():
    """Check SQLAlchemy ORM mappings"""
    from sqlalchemy.orm import configure_mappers

    configure_mappers()
    print("   ORM Mappers configured successfully.")


def check_database_connection():
    """Check if we can connect to the database"""
    from sqlalchemy import text

    from src.aac_app.models.database import get_session

    with get_session() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1
    print("   Database connection successful.")


def check_critical_users():
    """Check if critical users exist (soft check)"""
    from src.aac_app.models.database import User, get_session

    with get_session() as session:
        users = ["student1", "teacher1", "admin1"]
        missing = []
        for u in users:
            user = session.query(User).filter(User.username == u).first()
            if not user:
                missing.append(u)

        if missing:
            raise Exception(f"Missing critical users: {', '.join(missing)}")
    print("   Critical users present.")


def run_integrity_tests():
    """Run the specific integrity pytest suite"""
    print("   Running structural tests...")
    retcode = pytest.main(
        [
            "tests/structural/test_orm_integrity.py",
            "tests/integration/test_startup_seeding.py",
            "-v",
        ]
    )
    if retcode != 0:
        raise Exception("Integrity tests failed")


def main():
    print("=" * 60)
    print("AAC ASSISTANT - SYSTEM HEALTH CHECK")
    print("=" * 60)

    checks = [
        ("ORM Integrity", check_orm_mapping),
        ("Database Connectivity", check_database_connection),
        ("Critical Data Presence", check_critical_users),
        ("Deep Integrity Tests", run_integrity_tests),
    ]

    failures = 0
    for name, func in checks:
        if not run_check(name, func):
            failures += 1

    print("\n" + "=" * 60)
    if failures == 0:
        print("✅ SYSTEM HEALTHY - READY FOR PRODUCTION")
        sys.exit(0)
    else:
        print(f"❌ SYSTEM UNHEALTHY - {failures} CHECKS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
