"""PROMPT_19 regressions: R1/R3-R7/R9/R11/R12 (WS items R2/R10 live in
test_collab_ws.py, R8 in test_symbol_svg_autogen.py).

- R1: register and staff create_student must not silently ignore a supplied
  mismatched confirm_password, and the public UserCreate contract must not
  carry the teacher-assignment field.
- R3: validate_preference_updates turns non-numeric input into a clean 400,
  never a raw ValueError 500.
- R4: every password-accepting schema bounds the input (max 200, a DoS bound
  above any legitimate passphrase).
- R5: the unauthenticated login path bounds usernames at the User column
  (50) so overlong logins cannot mint unbounded lockout/audit rows.
- R6: the audit-log purge runs on failed logins too, not only successes.
- R7: board-generation dedupe uses the canonical casefold label key.
- R9: UserProfileUpdate strips display_name BEFORE the max_length check,
  matching UserBase registration semantics.
- R11: verify_student_access denies deactivated students (404, non-oracle).
- R12: contains_like_pattern folds with casefold(), matching dedupe.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.aac_app.models import FailedLoginAttempt, StudentTeacher, User
from src.aac_app.models.audit_log import AuditLog
from src.aac_app.services.audit_service import AUDIT_LOG_MAX_ROWS
from src.aac_app.services.auth_service import get_password_hash
from src.aac_app.services.runtime_translation import contains_like_pattern
from src.api.main import app
from src.api.routers.auth_helpers import validate_preference_updates
from tests.auth_helpers import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")

_PASSWORD = "TestPassword123"
_OTHER_VALID = "DifferentPassword456"


def _register(username, password=_PASSWORD, **overrides):
    payload = {
        "username": username,
        "password": password,
        "display_name": username.capitalize(),
        "user_type": "student",
        **overrides,
    }
    return client.post("/api/auth/register", json=payload)


def _admin_create_user(admin_token, username, user_type, password=_PASSWORD):
    response = client.post(
        "/api/auth/admin/create-user",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": username,
            "password": password,
            "confirm_password": password,
            "display_name": username.capitalize(),
            "user_type": user_type,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _login_token(username, password=_PASSWORD):
    login = client.post(
        "/api/auth/token", data={"username": username, "password": password}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


# --- R1: confirmation + public-contract field -------------------------------


def test_register_rejects_mismatched_confirm_password():
    reg = _register("r1_mismatch_reg", confirm_password=_OTHER_VALID)
    assert reg.status_code == 400, reg.text


def test_register_accepts_matching_confirm_password(test_db_session):
    reg = _register("r1_match_reg", confirm_password=_PASSWORD)
    assert reg.status_code == 200, reg.text


def test_public_register_still_ignores_teacher_assignment(test_db_session):
    # REFUTED as a bug (see test_auth_auto_assignment.py): the shared client
    # contract deliberately tolerates a teacher id on public registration and
    # never auto-assigns from it. The register route enforces confirmation
    # only; assignment stays a staff-route concern.
    reg = _register("r1_assign_reg", created_by_teacher_id=99999)
    assert reg.status_code == 200, reg.text
    from src.aac_app.models import StudentTeacher

    student_id = reg.json()["id"]
    assignment = (
        test_db_session.query(StudentTeacher)
        .filter_by(student_id=student_id)
        .first()
    )
    assert assignment is None


def test_staff_create_student_rejects_mismatched_confirm(admin_token):
    teacher = _admin_create_user(admin_token, "r1_teacher_a", "teacher")
    headers = create_test_headers(teacher["id"], teacher["username"], "teacher")

    payload = {
        "username": "r1_student_mismatch",
        "password": _PASSWORD,
        "display_name": "R1 Mismatch",
        "user_type": "student",
        "confirm_password": _OTHER_VALID,
    }
    response = client.post("/api/users/students", json=payload, headers=headers)
    assert response.status_code == 400, response.text

    payload["username"] = "r1_student_match"
    payload["confirm_password"] = _PASSWORD
    response = client.post("/api/users/students", json=payload, headers=headers)
    assert response.status_code == 200, response.text


# --- R3: preference validation never 500s on non-numeric input -------------


def test_validate_preference_updates_non_numeric_is_clean_400():
    for key in ("dwell_time", "ignore_repeats", "hover_speak_delay_ms"):
        with pytest.raises(HTTPException) as exc:
            validate_preference_updates({key: "abc"})
        assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        validate_preference_updates({"ignore_repeats": [1]})
    assert exc.value.status_code == 400
    # bool is an int subclass: meaningless for a timing preference.
    with pytest.raises(HTTPException) as exc:
        validate_preference_updates({"dwell_time": True})
    assert exc.value.status_code == 400
    # Negative stays rejected, valid values pass.
    with pytest.raises(HTTPException) as exc:
        validate_preference_updates({"dwell_time": -5})
    assert exc.value.status_code == 400
    validate_preference_updates({"dwell_time": 0, "hover_speak_delay_ms": 100})


def test_preferences_route_non_numeric_never_500s(test_db_session, user_token):
    response = client.put(
        "/api/auth/preferences",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"dwell_time": "abc"},
    )
    assert response.status_code in (400, 422), response.text


# --- R4: password length bound ----------------------------------------------


def test_register_rejects_overlong_password():
    long_password = "Aa1!" * 75  # 300 chars, valid shape
    reg = _register("r4_long_pw_reg", password=long_password)
    assert reg.status_code == 422, reg.text


def test_change_password_rejects_overlong_new_password(test_db_session):
    username = "r4_changepw_user"
    _register(username)
    token = _login_token(username)
    long_password = "Aa1!" * 75
    response = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": username,
            "current_password": _PASSWORD,
            "new_password": long_password,
            "confirm_password": long_password,
        },
    )
    assert response.status_code == 422, response.text


# --- R5: login username bound -------------------------------------------------


def test_login_with_overlong_username_is_401_without_storage_rows(
    test_db_session,
):
    huge = "x" * 200
    response = client.post(
        "/api/auth/token", data={"username": huge, "password": _PASSWORD}
    )
    assert response.status_code == 401

    lockout_rows = (
        test_db_session.query(FailedLoginAttempt)
        .filter(FailedLoginAttempt.username == huge)
        .count()
    )
    assert lockout_rows == 0
    audit_rows = (
        test_db_session.query(AuditLog)
        .filter(AuditLog.username == huge)
        .count()
    )
    assert audit_rows == 0


def test_change_password_rejects_overlong_username(test_db_session):
    username = "r5_changepw_user"
    _register(username)
    token = _login_token(username)
    response = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "x" * 10_000,
            "current_password": _PASSWORD,
            "new_password": "NewTestPassword456",
            "confirm_password": "NewTestPassword456",
        },
    )
    assert response.status_code == 422, response.text


# --- R6: failed logins purge the audit table too ----------------------------


def test_failed_login_trims_audit_rows_beyond_cap(test_db_session):
    rows = [
        AuditLog(
            event_type="login_failed",
            severity="warning",
            username=f"ghost-{i}",
            description=f"seed row {i}",
            success=False,
        )
        for i in range(AUDIT_LOG_MAX_ROWS + 300)
    ]
    test_db_session.add_all(rows)
    test_db_session.commit()
    pre_count = test_db_session.query(AuditLog).count()
    assert pre_count == AUDIT_LOG_MAX_ROWS + 300

    # A failed login (unknown user) must trigger the same bounded purge the
    # success path runs; without it the table would keep growing by one.
    response = client.post(
        "/api/auth/token",
        data={"username": "no_such_user_r6", "password": _PASSWORD},
    )
    assert response.status_code == 401
    test_db_session.expire_all()
    post_count = test_db_session.query(AuditLog).count()
    assert post_count <= AUDIT_LOG_MAX_ROWS + 1


# --- R7: board-generation dedupe uses the canonical label fold -------------


def test_board_gen_dedupe_uses_canonical_casefold():
    from src.aac_app.services.board_generation_service import (
        _dedupe_items_by_label,
    )

    # Canonical dedupe (casefold) treats straße == STRASSE in one item.
    deduped = _dedupe_items_by_label(
        [{"label": "straße"}, {"label": "STRASSE"}]
    )
    assert len(deduped) == 1
    # Inner-whitespace collapse is intentionally dropped: double-space
    # variants stay distinct (never a false dedupe).
    distinct = _dedupe_items_by_label([{"label": "a  b"}, {"label": "a b"}])
    assert len(distinct) == 2


# --- R9: profile display_name strips before the length check ---------------


def test_profile_update_accepts_padded_display_name_within_bound(
    test_db_session, user_token
):
    name = "x" * 99
    response = client.put(
        "/api/auth/profile",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"display_name": f"  {name}  "},
    )
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == name


def test_profile_update_blank_display_name_still_400(test_db_session, user_token):
    response = client.put(
        "/api/auth/profile",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"display_name": "   "},
    )
    assert response.status_code == 400, response.text


def test_profile_update_overlong_display_name_after_strip_is_422(
    test_db_session, user_token
):
    response = client.put(
        "/api/auth/profile",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"display_name": "x" * 101},
    )
    assert response.status_code == 422, response.text


# --- R11: deactivated students are not operable by staff --------------------


def test_teacher_cannot_access_inactive_rostered_student(test_db_session):
    teacher = User(
        username="r11_teacher",
        display_name="R11 Teacher",
        user_type="teacher",
        password_hash=get_password_hash(_PASSWORD),
        is_active=True,
    )
    student = User(
        username="r11_inactive_student",
        display_name="R11 Inactive",
        user_type="student",
        password_hash=get_password_hash(_PASSWORD),
        is_active=False,
    )
    test_db_session.add_all([teacher, student])
    test_db_session.flush()
    test_db_session.add(
        StudentTeacher(teacher_id=teacher.id, student_id=student.id)
    )
    test_db_session.commit()

    headers = create_test_headers(teacher.id, teacher.username, "teacher")
    response = client.get(
        f"/api/learning/history/{student.id}", headers=headers
    )
    assert response.status_code == 404, response.text


def test_teacher_can_access_active_rostered_student(test_db_session):
    teacher = User(
        username="r11_teacher_active",
        display_name="R11 Teacher Active",
        user_type="teacher",
        password_hash=get_password_hash(_PASSWORD),
        is_active=True,
    )
    student = User(
        username="r11_active_student",
        display_name="R11 Active",
        user_type="student",
        password_hash=get_password_hash(_PASSWORD),
        is_active=True,
    )
    test_db_session.add_all([teacher, student])
    test_db_session.flush()
    test_db_session.add(
        StudentTeacher(teacher_id=teacher.id, student_id=student.id)
    )
    test_db_session.commit()

    headers = create_test_headers(teacher.id, teacher.username, "teacher")
    response = client.get(
        f"/api/learning/history/{student.id}", headers=headers
    )
    assert response.status_code == 200, response.text


# --- R12: contains_like_pattern folds with casefold -------------------------


def test_contains_like_pattern_uses_casefold():
    # lower() keeps ß (ß.lower() == "ß"); casefold expands it to "ss" — the
    # same equivalence the symbol dedupe uses, so a search must match what
    # dedupe would call equal.
    assert contains_like_pattern("ß") == "%ss%"
    assert contains_like_pattern("Straße") == "%strasse%"
