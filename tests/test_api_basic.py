import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


def test_read_main():
    """Test the API health check endpoint"""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "online",
        "app": "AAC Assistant API",
        "version": "1.0.0",
    }


def test_create_user():
    response = client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "TestPassword123",
            "display_name": "Test User",
            "user_type": "student",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert "id" in data


def test_login():
    # First create user (if not exists from previous test order)
    client.post(
        "/api/auth/register",
        json={
            "username": "loginuser",
            "password": "LoginPassword123",
            "display_name": "Login User",
            "user_type": "student",
        },
    )

    response = client.post(
        "/api/auth/login",
        json={"username": "loginuser", "password": "LoginPassword123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "loginuser"


def test_create_board():
    # Register user
    reg_response = client.post(
        "/api/auth/register",
        json={
            "username": "boarduser",
            "password": "BoardPassword123",
            "display_name": "Board User",
            "user_type": "teacher",
        },
    )
    user_id = reg_response.json()["id"]
    headers = create_test_headers(user_id, "boarduser", "teacher")

    # Create board
    response = client.post(
        f"/api/boards/?user_id={user_id}",
        json={
            "name": "Test Board",
            "description": "A test board",
            "category": "test",
            "is_public": False,
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Board"
    assert data["user_id"] == user_id
