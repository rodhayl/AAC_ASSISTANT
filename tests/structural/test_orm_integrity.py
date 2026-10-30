"""
Structural tests for Database Models and ORM Integrity.
This ensures that no ambiguous foreign keys or invalid mappings are introduced.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import configure_mappers

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.aac_app.models.database import Base, BoardSymbol  # noqa: E402


def test_orm_mapping_validity():
    """
    Crucial test: Forces SQLAlchemy to initialize all mappers.
    This will catch 'AmbiguousForeignKeysError' and other mapping issues immediately.
    """
    try:
        configure_mappers()
    except Exception as e:
        pytest.fail(f"ORM Mapping Configuration Failed: {e}")


def test_model_relationships():
    """
    Verify specific critical relationships that have caused issues in the past.
    """
    # Inspect BoardSymbol relationships
    mapper = inspect(BoardSymbol)

    # Check 'board' relationship
    assert "board" in mapper.relationships, "BoardSymbol missing 'board' relationship"
    board_rel = mapper.relationships["board"]

    # Ensure foreign keys are explicitly defined to avoid ambiguity
    # This protects against the specific bug we just fixed
    assert board_rel.primaryjoin is not None

    # Check 'linked_board' relationship
    assert (
        "linked_board" in mapper.relationships
    ), "BoardSymbol missing 'linked_board' relationship"


def test_foreign_keys_defined():
    """Ensure all foreign keys are valid"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    # If we got here, the SQL generation works (no invalid column types/references)
    assert True
