"""Regression: user-facing API errors are localized via Accept-Language.

Previously several account/achievement/teacher endpoints returned hardcoded
English strings even when the UI language was Spanish (the application
default). These tests lock the translated responses for unauthenticated
(login/registration) and authenticated (achievement permissions) paths.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

ADMIN_PASSWORD = "AdminStrong#2026"


@pytest.fixture
def api_client(setup_test_db):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def student_token(api_client):
    username = f"i18n_student_{uuid.uuid4().hex[:8]}"
    password = "StudentStrong#2026"
    response = api_client.post(
        "/api/auth/register",
        json={
            "username": username,
            "display_name": "I18n Student",
            "password": password,
            "confirm_password": password,
            "user_type": "student",
        },
    )
    assert response.status_code == 200, response.text
    login = api_client.post(
        "/api/auth/token", data={"username": username, "password": password}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def test_login_error_is_spanish_with_accept_language(api_client):
    """Wrong-password login answered in Spanish when the client asks for it."""
    response = api_client.post(
        "/api/auth/token",
        data={"username": "admin1", "password": "wrong-password"},
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Nombre de usuario o contraseña incorrectos"


def test_login_error_stays_english_by_default(api_client):
    """Without a language header the API keeps its English default."""
    response = api_client.post(
        "/api/auth/token",
        data={"username": "admin1", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"


def test_registration_password_error_is_spanish(api_client):
    """Weak-password registration answered in Spanish."""
    response = api_client.post(
        "/api/auth/register",
        json={
            "username": "weak_pass_user",
            "display_name": "Weak Pass",
            "password": "short",
            "confirm_password": "short",
            "user_type": "student",
        },
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == (
        "La contraseña debe tener al menos 8 caracteres"
    )


def test_achievement_permission_error_is_spanish(api_client, student_token):
    """Student hitting a teacher-only achievement route gets a Spanish denial."""
    response = api_client.get(
        "/api/achievements/categories",
        headers={"Authorization": f"Bearer {student_token}", "Accept-Language": "es"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Solo profesores y administradores pueden ver categorías"
    )


def test_achievement_permission_error_english_default(api_client, student_token):
    """Without a language header the achievement denial is English."""
    response = api_client.get(
        "/api/achievements/categories",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only teachers and admins can view categories"


def test_refresh_token_error_is_spanish(api_client):
    """An invalid refresh token is answered in the request language."""
    response = api_client.post(
        "/api/auth/refresh",
        params={"refresh_token": "not-a-valid-token"},
        headers={"Accept-Language": "es"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Token de actualización inválido o expirado"


def test_preference_validation_error_is_spanish(api_client, student_token):
    """Negative timing preferences are rejected in the request language."""
    response = api_client.put(
        "/api/auth/preferences",
        json={"dwell_time": -1},
        headers={"Authorization": f"Bearer {student_token}", "Accept-Language": "es"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "dwell_time debe ser >= 0"
