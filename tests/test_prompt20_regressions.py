"""PROMPT_20 regressions: D1-D8, D10-D12 (the collab WS item D9 lives in
test_collab_ws.py; the symbols unicode-recall route test D7 lives here).

- D1: the unauthenticated login path bounds the password (PASSWORD_MAX_LENGTH)
  BEFORE hashing — an overlong passphrase is a fast 401 and never reaches
  verify_password_and_update nor writes lockout/audit rows.
- D2: every email write path bounds the address at the User column (100) —
  register/setup/profile with a 102-char valid email are a clean 422.
- D3: the admin raw-dict edit bounds display_name/email (after strip/normalize)
  with the same 400 keys the route already uses.
- D4: unified deactivation policy — admins may READ deactivated accounts
  (user row + guardian profile), but NEW links (board assignment, roster link,
  password reset) to inactive accounts are 404 for everyone.
- D5: the failed-login-attempt table is capped like the audit log.
- D6: the audit purge is count-based, so id gaps can neither over-delete the
  newest rows nor leave the table over cap.
- D7: symbol search supplements the ASCII-only SQL LIKE with the canonical
  Python casefold hit (stored "straße" is found by searching "STRASSE").
- D8: preference validation rejects floats/numeric strings instead of
  coercing them toward int.
- D10: saved-topic search keeps literal %/_ semantics through the canonical
  escaping home (refactor; behavior identical to the inlined version).
- D11: contains_like_pattern strips, mirroring normalize_symbol_label.
- D12: board-gen dedupe keeps a stripped label on the surviving item.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.aac_app.models import (
    AuditLog,
    BoardAssignment,
    CommunicationBoard,
    FailedLoginAttempt,
    GuardianProfile,
    SavedTopic,
    StudentTeacher,
    Symbol,
    User,
)
from src.aac_app.services.audit_service import AuditLogService
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.services.lockout_service import (
    LOCKOUT_MAX_ROWS,
    AccountLockoutService,
)
from src.aac_app.services.runtime_translation import contains_like_pattern
from src.api.main import app
from src.api.routers.auth_helpers import validate_preference_updates
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")

_PASSWORD = "TestPassword123"
_EMAIL_HOST = "example.com"


def _long_email(extra_chars: int = 2) -> str:
    # Base 102-char valid email: 'a'*90 + '@example.com'. extra_chars adds
    # more 'a's so callers can exceed the bound by any margin.
    return "a" * (90 + extra_chars) + f"@{_EMAIL_HOST}"


def _register(username, password=_PASSWORD, **overrides):
    payload = {
        "username": username,
        "password": password,
        "display_name": username.capitalize(),
        "user_type": "student",
        **overrides,
    }
    return client.post("/api/auth/register", json=payload)


def _login_token(username, password=_PASSWORD):
    login = client.post(
        "/api/auth/token", data={"username": username, "password": password}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


# --- D1: login password bound (fast 401, never hashed) ---------------------


def test_login_with_overlong_password_is_fast_401_without_hashing(
    monkeypatch, test_db_session
):
    _register("d1_overlong_pw_user")

    called = {"count": 0}

    def _boom(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("verify_password_and_update must not run")

    monkeypatch.setattr(
        "src.api.routers.auth.verify_password_and_update", _boom
    )
    huge_password = "x" * 10_000
    response = client.post(
        "/api/auth/token",
        data={"username": "d1_overlong_pw_user", "password": huge_password},
    )
    assert response.status_code == 401
    assert called["count"] == 0

    # No lockout/audit rows are minted by the rejected attempt.
    assert (
        test_db_session.query(FailedLoginAttempt)
        .filter(FailedLoginAttempt.username == "d1_overlong_pw_user")
        .count()
        == 0
    )
    assert (
        test_db_session.query(AuditLog)
        .filter(AuditLog.username == "d1_overlong_pw_user")
        .count()
        == 0
    )


def test_login_normal_password_still_succeeds():
    _register("d1_normal_login_user")
    token = _login_token("d1_normal_login_user")
    assert token


def test_login_wrong_normal_password_still_401():
    _register("d1_wrong_pw_user")
    response = client.post(
        "/api/auth/token",
        data={"username": "d1_wrong_pw_user", "password": "WrongPass999"},
    )
    assert response.status_code == 401


# --- D2: email bound (String(100)) on every write path ---------------------


def test_register_rejects_overlong_email():
    response = _register("d2_long_email_reg", email=_long_email())
    assert response.status_code == 422, response.text


def test_setup_rejects_overlong_email():
    payload = {
        "username": "setupadmin",
        "display_name": "Setup Admin",
        "email": _long_email(),
        "password": _PASSWORD,
        "confirm_password": _PASSWORD,
    }
    response = client.post("/api/auth/setup", json=payload)
    # 422 from pydantic validation (the schema bound), regardless of whether
    # an admin already exists in this test DB.
    assert response.status_code == 422, response.text


def test_profile_update_rejects_overlong_email(user_token):
    response = client.put(
        "/api/auth/profile",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"email": _long_email()},
    )
    assert response.status_code == 422, response.text


def test_register_normal_email_still_200_and_duplicate_still_400():
    first = _register("d2_email_ok_a", email="user@example.com")
    assert first.status_code == 200, first.text
    duplicate = _register("d2_email_ok_b", email="USER@example.com")
    assert duplicate.status_code == 400, duplicate.text


# --- D3: admin raw-dict edit bounds after strip/normalize ------------------


def _create_target_user(username):
    response = _register(username)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_admin_edit_rejects_overlong_display_name(admin_token):
    target_id = _create_target_user("d3_long_name_user")
    response = client.put(
        f"/api/auth/users/{target_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"display_name": "x" * 500},
    )
    assert response.status_code == 400, response.text


def test_admin_edit_rejects_overlong_email(admin_token, test_db_session):
    target_id = _create_target_user("d3_long_email_user")
    response = client.put(
        f"/api/auth/users/{target_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": _long_email()},
    )
    assert response.status_code == 400, response.text
    # The overlong value must never be stored on SQLite (where the VARCHAR
    # bound is not enforced by the engine).
    test_db_session.expire_all()
    stored = test_db_session.query(User).filter(User.id == target_id).first()
    assert stored.email is None


def test_admin_edit_valid_change_still_200(admin_token, test_db_session):
    target_id = _create_target_user("d3_valid_edit_user")
    response = client.put(
        f"/api/auth/users/{target_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"display_name": "Valid Name", "email": "valid@example.com"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "Valid Name"
    assert response.json()["email"] == "valid@example.com"


# --- D4: unified deactivation policy ----------------------------------------


def _seed_inactive_roster(test_db_session, admin_user):
    """Teacher + inactive rostered student (+ guardian profile) and return
    the (teacher, student) rows."""
    teacher = User(
        username="d4_teacher",
        display_name="D4 Teacher",
        user_type="teacher",
        password_hash=get_password_hash(_PASSWORD),
        is_active=True,
    )
    student = User(
        username="d4_inactive_student",
        display_name="D4 Inactive Student",
        user_type="student",
        password_hash=get_password_hash(_PASSWORD),
        is_active=False,
    )
    test_db_session.add_all([teacher, student])
    test_db_session.flush()
    test_db_session.add(
        StudentTeacher(teacher_id=teacher.id, student_id=student.id)
    )
    test_db_session.add(
        GuardianProfile(
            user_id=student.id,
            template_name="default",
            is_active=True,
            created_by=admin_user.id,
        )
    )
    board = CommunicationBoard(
        user_id=teacher.id, name="D4 Teacher Board", is_public=False
    )
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(teacher)
    test_db_session.refresh(student)
    test_db_session.refresh(board)
    return teacher, student, board


def test_admin_can_read_inactive_student_row_and_guardian_profile(
    admin_token, admin_user, test_db_session
):
    _, student, _ = _seed_inactive_roster(test_db_session, admin_user)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin GET /auth/users/{id} already returned 200 (authorize_user_access
    # early-returns for admins); the guardian read must agree now.
    row = client.get(f"/api/auth/users/{student.id}", headers=headers)
    assert row.status_code == 200, row.text
    profile = client.get(
        f"/api/guardian-profiles/students/{student.id}", headers=headers
    )
    assert profile.status_code == 200, profile.text


def test_teacher_guardian_read_of_inactive_student_still_404(
    test_db_session, admin_user
):
    teacher, student, _ = _seed_inactive_roster(test_db_session, admin_user)
    headers = create_test_headers(teacher.id, teacher.username, "teacher")
    response = client.get(
        f"/api/guardian-profiles/students/{student.id}", headers=headers
    )
    assert response.status_code == 404, response.text


def test_teacher_learning_history_of_inactive_student_still_404(
    test_db_session, admin_user
):
    # Kept from R11: the rostered teacher's learning-history read of a
    # deactivated student is 404 (pinned separately in
    # test_prompt19_regressions.py too).
    teacher, student, _ = _seed_inactive_roster(test_db_session, admin_user)
    headers = create_test_headers(teacher.id, teacher.username, "teacher")
    response = client.get(
        f"/api/learning/history/{student.id}", headers=headers
    )
    assert response.status_code == 404, response.text


def test_admin_board_assign_to_inactive_student_404(
    admin_token, admin_user, test_db_session
):
    _, student, board = _seed_inactive_roster(test_db_session, admin_user)
    response = client.post(
        f"/api/boards/{board.id}/assign",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"student_id": student.id},
    )
    assert response.status_code == 404, response.text
    assert (
        test_db_session.query(BoardAssignment)
        .filter_by(board_id=board.id, student_id=student.id)
        .count()
        == 0
    )


def test_assign_student_link_to_inactive_student_404(
    admin_token, admin_user, test_db_session
):
    teacher, student, _ = _seed_inactive_roster(test_db_session, admin_user)
    response = client.post(
        "/api/users/assign-student",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"student_id": student.id, "teacher_id": teacher.id},
    )
    assert response.status_code == 404, response.text


def test_reset_password_for_inactive_student_404(
    admin_token, admin_user, test_db_session
):
    _, student, _ = _seed_inactive_roster(test_db_session, admin_user)
    response = client.post(
        "/api/users/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"student_id": student.id, "new_password": "NewPass1234!"},
    )
    assert response.status_code == 404, response.text


def test_teacher_assign_student_and_reset_inactive_still_404(
    test_db_session, admin_user
):
    teacher, student, _ = _seed_inactive_roster(test_db_session, admin_user)
    headers = create_test_headers(teacher.id, teacher.username, "teacher")

    roster = client.post(
        "/api/users/assign-student",
        headers=headers,
        json={"student_id": student.id, "teacher_id": teacher.id},
    )
    assert roster.status_code == 404, roster.text

    reset = client.post(
        "/api/users/reset-password",
        headers=headers,
        json={"student_id": student.id, "new_password": "NewPass1234!"},
    )
    assert reset.status_code == 404, reset.text


def test_active_student_paths_still_work(test_db_session, admin_user):
    teacher = User(
        username="d4_active_teacher",
        display_name="D4 Active Teacher",
        user_type="teacher",
        password_hash=get_password_hash(_PASSWORD),
        is_active=True,
    )
    student = User(
        username="d4_active_student",
        display_name="D4 Active Student",
        user_type="student",
        password_hash=get_password_hash(_PASSWORD),
        is_active=True,
    )
    test_db_session.add_all([teacher, student])
    test_db_session.flush()
    test_db_session.add(
        StudentTeacher(teacher_id=teacher.id, student_id=student.id)
    )
    board = CommunicationBoard(
        user_id=teacher.id, name="D4 Active Board", is_public=False
    )
    test_db_session.add(board)
    test_db_session.commit()
    test_db_session.refresh(teacher)
    test_db_session.refresh(student)
    test_db_session.refresh(board)

    admin_token = create_test_headers(admin_user.id, admin_user.username, "admin")
    teacher_headers = create_test_headers(teacher.id, teacher.username, "teacher")

    # Teacher assigns an active rostered student their board.
    assign_board = client.post(
        f"/api/boards/{board.id}/assign",
        headers=teacher_headers,
        json={"student_id": student.id},
    )
    assert assign_board.status_code == 200, assign_board.text

    # Admin links the (already-linked) active student; 201 for a fresh link.
    fresh_student = User(
        username="d4_active_fresh",
        display_name="D4 Active Fresh",
        user_type="student",
        password_hash=get_password_hash(_PASSWORD),
        is_active=True,
    )
    test_db_session.add(fresh_student)
    test_db_session.commit()
    test_db_session.refresh(fresh_student)
    roster = client.post(
        "/api/users/assign-student",
        headers=admin_token,
        json={"student_id": fresh_student.id, "teacher_id": teacher.id},
    )
    assert roster.status_code == 201, roster.text

    # Admin resets an active student's password.
    reset = client.post(
        "/api/users/reset-password",
        headers=admin_token,
        json={"student_id": fresh_student.id, "new_password": "NewPass1234!"},
    )
    assert reset.status_code == 200, reset.text


# --- D5: failed-login-attempt table cap -------------------------------------


def test_failed_login_trims_lockout_rows_beyond_cap(test_db_session):
    rows = [
        FailedLoginAttempt(
            username=f"ghost-lockout-{i}",
            ip_address="10.0.0.1",
            attempt_count=1,
            locked_until=None,
        )
        for i in range(LOCKOUT_MAX_ROWS + 300)
    ]
    test_db_session.add_all(rows)
    test_db_session.commit()
    pre_count = test_db_session.query(FailedLoginAttempt).count()
    assert pre_count == LOCKOUT_MAX_ROWS + 300

    response = client.post(
        "/api/auth/token",
        data={"username": "no_such_lockout_user_d5", "password": _PASSWORD},
    )
    assert response.status_code == 401
    test_db_session.expire_all()
    post_count = test_db_session.query(FailedLoginAttempt).count()
    assert post_count <= LOCKOUT_MAX_ROWS
    # The just-recorded attempt survives (it is the newest row).
    assert (
        test_db_session.query(FailedLoginAttempt)
        .filter(FailedLoginAttempt.username == "no_such_lockout_user_d5")
        .count()
        == 1
    )


def test_lockout_success_reset_still_deletes_user_rows(test_db_session):
    username = "d5_reset_user"
    for _ in range(2):
        AccountLockoutService.record_failed_attempt(test_db_session, username)
    assert (
        test_db_session.query(FailedLoginAttempt)
        .filter(FailedLoginAttempt.username == username)
        .count()
        == 1
    )
    AccountLockoutService.reset_attempts(test_db_session, username)
    assert (
        test_db_session.query(FailedLoginAttempt)
        .filter(FailedLoginAttempt.username == username)
        .count()
        == 0
    )


# --- D6: count-based audit purge (gap-safe) ---------------------------------


def _audit_row(row_id: int) -> AuditLog:
    return AuditLog(
        id=row_id,
        event_type="login_failed",
        severity="warning",
        username=f"gap-{row_id}",
        description=f"gap seed {row_id}",
        success=False,
    )


def test_purge_old_entries_is_count_based_with_gapped_ids(
    setup_test_db, test_db_session
):
    """5200 live rows with ids up to 9200 (ids 9001-9200 only; 5001-9000 are
    gaps). id-arithmetic (newest - max) would compute cutoff 4200 and delete
    4200 rows, leaving 1000; the count-based purge deletes exactly the 200
    excess, keeping 5000 with the newest row intact."""
    test_db_session.add_all(
        [_audit_row(i) for i in range(1, 5001)]
        + [_audit_row(i) for i in range(9001, 9201)]
    )
    test_db_session.commit()
    assert test_db_session.query(AuditLog).count() == 5200
    assert test_db_session.query(AuditLog).filter(AuditLog.id == 9200).count() == 1

    deleted = AuditLogService.purge_old_entries(
        test_db_session, max_rows=5000, batch_limit=10_000
    )
    assert deleted == 200
    assert test_db_session.query(AuditLog).count() == 5000
    # The newest row survives; the oldest 200 were removed.
    assert test_db_session.query(AuditLog).filter(AuditLog.id == 9200).count() == 1
    assert test_db_session.query(AuditLog).filter(AuditLog.id == 1).count() == 0


# --- D7: symbol search unicode recall supplement ----------------------------


class _EmptyVectorStore:
    """Deterministic stand-in for the process-global vector store: the symbol
    route tests only exercise the SQL LIKE + canonical-casefold supplement, so
    the semantic branch must never contribute stale rows from another test's
    database (the real store is a process-global singleton)."""

    def search(self, query, k=20):
        return []


def _symbol_search(token, term):
    response = client.get(
        "/api/boards/symbols",
        params={"search": term},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return {item["label"] for item in response.json()}


def test_symbol_search_finds_casefold_equivalent_stored_label(
    admin_token, test_db_session, monkeypatch
):
    monkeypatch.setattr("src.api.deps.get_vector_store", lambda: _EmptyVectorStore())
    # Stored lowercase-with-ß row, searched by its all-caps casefold
    # equivalent: the ASCII-only SQL LIKE cannot match (lower('straße')
    # keeps the ß), so the canonical Python-side hit must supplement it.
    # Red before the D7 fix: the search returned nothing for this row.
    test_db_session.add_all(
        [
            Symbol(
                label="straße",
                category="noun",
                language="de",
                is_builtin=True,
            ),
            Symbol(
                label="casa",
                category="noun",
                language="es",
                is_builtin=True,
            ),
        ]
    )
    test_db_session.commit()

    assert "straße" in _symbol_search(admin_token, "STRASSE")
    assert "straße" in _symbol_search(admin_token, "straße")
    # ASCII search behavior is unchanged.
    assert _symbol_search(admin_token, "casa") == {"casa"}


def test_symbol_search_reverse_casefold_direction(
    admin_token, test_db_session, monkeypatch
):
    monkeypatch.setattr("src.api.deps.get_vector_store", lambda: _EmptyVectorStore())
    # Stored all-caps ASCII row, searched by its casefold-equivalent ß query:
    # SQL LIKE already matches this direction (strasse), but the ß-query must
    # also not miss it once the canonical supplement runs.
    test_db_session.add(
        Symbol(label="STRASSE", category="noun", language="de", is_builtin=True)
    )
    test_db_session.commit()

    assert "STRASSE" in _symbol_search(admin_token, "straße")


def test_symbol_search_does_not_leak_unicode_equiv_to_wrong_label(
    admin_token, test_db_session
):
    test_db_session.add(
        Symbol(label="casa", category="noun", language="es", is_builtin=True)
    )
    test_db_session.commit()
    # A ß query must NOT match the ASCII 'casa' (no false positive from the
    # supplement path).
    assert _symbol_search(admin_token, "casa") == {"casa"}
    assert _symbol_search(admin_token, "casax") == set()


# --- D8: strict-int preference validation -----------------------------------


def test_validate_preference_updates_rejects_coercible_values():
    # Red before the fix: int(3.7) == 3 and int("100") == 100 passed.
    for bad in (3.7, "100", [1], True, "abc"):
        with pytest.raises(HTTPException) as exc:
            validate_preference_updates({"dwell_time": bad})
        assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        validate_preference_updates({"hover_speak_delay_ms": -5})
    assert exc.value.status_code == 400
    # True ints pass.
    validate_preference_updates(
        {"dwell_time": 0, "ignore_repeats": 100, "hover_speak_delay_ms": 1000}
    )


def test_preferences_route_accepts_valid_int(test_db_session, user_token):
    response = client.put(
        "/api/auth/preferences",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"dwell_time": 100},
    )
    assert response.status_code == 200, response.text


# --- D10: saved-topic search stays literal through the canonical helper -----


def test_saved_topic_search_literal_wildcards(test_db_session):
    teacher = User(
        username="d10_topic_teacher",
        display_name="D10 Topic Teacher",
        user_type="teacher",
        password_hash=get_password_hash(_PASSWORD),
        is_active=True,
    )
    test_db_session.add(teacher)
    test_db_session.flush()
    test_db_session.add_all(
        [
            SavedTopic(
                user_id=teacher.id,
                board="Board A",
                topic="100% ready",
                created_by="D10 Topic Teacher",
            ),
            SavedTopic(
                user_id=teacher.id,
                board="Board B",
                topic="a_b literal",
                created_by="D10 Topic Teacher",
            ),
            SavedTopic(
                user_id=teacher.id,
                board="Board C",
                topic="axb no underscore",
                created_by="D10 Topic Teacher",
            ),
            SavedTopic(
                user_id=teacher.id,
                board="Board D",
                topic="plain topic",
                created_by="D10 Topic Teacher",
            ),
        ]
    )
    test_db_session.commit()
    headers = create_test_headers(teacher.id, teacher.username, "teacher")

    def _list(search):
        response = client.get(
            "/api/learning/topics/saved",
            params={"search": search},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        return {entry["topic"] for entry in response.json()}

    # "%" must not act as a wildcard (only the literal "100%" topic matches).
    assert _list("100%") == {"100% ready"}
    # "_" must not match "axb" through the any-char wildcard.
    assert _list("a_b") == {"a_b literal"}
    assert _list("axb") == {"axb no underscore"}


# --- D11: contains_like_pattern strips ---------------------------------------


def test_contains_like_pattern_strips():
    assert contains_like_pattern("  casa  ") == "%casa%"
    assert contains_like_pattern("Straße") == "%strasse%"
    # Empty-after-strip yields the degenerate "%%" the falsy-search guards
    # already keep away from SQL.
    assert contains_like_pattern("   ") == "%%"


def test_symbol_search_with_padded_term_finds_label(
    admin_token, test_db_session, monkeypatch
):
    monkeypatch.setattr("src.api.deps.get_vector_store", lambda: _EmptyVectorStore())
    test_db_session.add(
        Symbol(label="casa", category="noun", language="es", is_builtin=True)
    )
    test_db_session.commit()
    assert "casa" in _symbol_search(admin_token, "  casa  ")


# --- D12: board-gen dedupe keeps the stripped label -------------------------


def test_board_gen_dedupe_keeps_stripped_label():
    from src.aac_app.services.board_generation_service import (
        _dedupe_items_by_label,
    )

    deduped = _dedupe_items_by_label(
        [{"label": "  casa "}, {"label": "casa", "color": "#fff"}]
    )
    assert len(deduped) == 1
    # The surviving item's label is stripped, matching what the catalog
    # stores; the first (padded) item wins on key order and keeps its extras.
    assert deduped[0]["label"] == "casa"
