from datetime import datetime, timedelta
from pathlib import Path

from src.aac_app.models import LearningSession, Symbol
from src.aac_app.services.retention import (
    cleanup_orphaned_symbol_uploads,
    prune_completed_learning_sessions,
)


def test_orphan_upload_cleanup_is_dry_run_by_default(test_db_session, tmp_path: Path):
    uploads = tmp_path / "symbols"
    uploads.mkdir()
    orphan = uploads / "orphan.png"
    orphan.write_bytes(b"x")
    referenced = uploads / "referenced.png"
    referenced.write_bytes(b"x")
    test_db_session.add(Symbol(label="known", image_path="/uploads/symbols/referenced.png"))
    test_db_session.commit()

    report = cleanup_orphaned_symbol_uploads(test_db_session, uploads_dir=uploads)

    assert report.candidates == 1
    assert report.removed == 0
    assert orphan.exists()
    assert referenced.exists()

    report = cleanup_orphaned_symbol_uploads(
        test_db_session, uploads_dir=uploads, dry_run=False
    )
    assert report.removed == 1
    assert not orphan.exists()
    assert referenced.exists()


def test_completed_session_prune_never_removes_active_sessions(test_db_session, regular_user):
    old = datetime.now() - timedelta(days=40)
    test_db_session.add_all(
        [
            LearningSession(
                user_id=regular_user.id,
                topic_name="old",
                status="completed",
                ended_at=old,
                conversation_history=[],
            ),
            LearningSession(
                user_id=regular_user.id,
                topic_name="active",
                status="active",
                started_at=old,
                conversation_history=[],
            ),
        ]
    )
    test_db_session.commit()

    report = prune_completed_learning_sessions(
        test_db_session, older_than_days=30, dry_run=False
    )

    assert report.candidates == 1
    assert report.removed == 1
    assert test_db_session.query(LearningSession).filter_by(topic_name="old").count() == 0
    assert test_db_session.query(LearningSession).filter_by(topic_name="active").count() == 1
