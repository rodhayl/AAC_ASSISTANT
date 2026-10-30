"""
Comprehensive API Integration Tests

Tests all API endpoints with realistic scenarios
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from tests.test_utils_auth import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")


class TestAuthAPI:
    """Test authentication endpoints"""

    def test_register_student(self, test_password):
        """Test student registration"""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "student1",
                "password": test_password,
                "display_name": "Student One",
                "user_type": "student",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "student1"
        assert data["user_type"] == "student"
        assert "id" in data

    def test_register_teacher(self, test_password):
        """Test teacher registration - should be forced to student for security"""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "teacher1",
                "password": test_password,
                "display_name": "Teacher One",
                "user_type": "teacher",  # Will be forced to 'student' by security policy
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Security: self-registration always creates students, teachers must be upgraded by admin
        assert data["user_type"] == "student"

    def test_login_success(self, test_password):
        """Test successful login"""
        # Register first
        client.post(
            "/api/auth/register",
            json={
                "username": "logintest",
                "password": test_password,
                "display_name": "Login Test",
                "user_type": "student",
            },
        )

        # Login
        response = client.post(
            "/api/auth/login",
            json={"username": "logintest", "password": test_password},
        )
        assert response.status_code == 200
        assert response.json()["username"] == "logintest"

    def test_login_wrong_password(self, test_password):
        """Test login with wrong password"""
        response = client.post(
            "/api/auth/login",
            json={"username": "logintest", "password": "wrongpass"},
        )
        assert response.status_code == 401


class TestBoardsAPI:
    """Test board management endpoints"""

    @pytest.fixture
    def user_data(self, test_password):
        """Create a test user and return auth data"""
        response = client.post(
            "/api/auth/register",
            json={
                "username": f"boarduser_{uuid.uuid4().hex[:8]}",
                "password": test_password,
                "display_name": "Board User",
                "user_type": "teacher",
            },
        )
        user_id = response.json()["id"]
        return {
            "id": user_id,
            "headers": create_test_headers(
                user_id, response.json()["username"], "teacher"
            ),
        }

    def test_create_board(self, user_data):
        """Test board creation"""
        user_id = user_data["id"]
        headers = user_data["headers"]
        response = client.post(
            f"/api/boards/?user_id={user_id}",
            json={
                "name": "My First Board",
                "description": "A test board",
                "category": "communication",
                "is_public": False,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My First Board"
        assert data["user_id"] == user_id

    def test_list_user_boards(self, user_data):
        """Test listing user's boards"""
        user_id = user_data["id"]
        headers = user_data["headers"]
        # Create a board first
        client.post(
            f"/api/boards/?user_id={user_id}",
            json={
                "name": "Test Board",
                "description": "Test",
                "category": "test",
                "is_public": False,
            },
            headers=headers,
        )

        # List boards
        response = client.get(f"/api/boards/?user_id={user_id}", headers=headers)
        assert response.status_code == 200
        boards = response.json()
        assert isinstance(boards, list)
        assert len(boards) >= 1

    def test_get_board_by_id(self, user_data):
        """Test getting a specific board"""
        user_id = user_data["id"]
        headers = user_data["headers"]
        # Create board
        create_response = client.post(
            f"/api/boards/?user_id={user_id}",
            json={
                "name": "Specific Board",
                "description": "Test",
                "category": "test",
                "is_public": False,
            },
            headers=headers,
        )
        board_id = create_response.json()["id"]

        # Get board
        response = client.get(f"/api/boards/{board_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Specific Board"

    def test_update_board(self, user_data):
        """Test updating a board"""
        user_id = user_data["id"]
        headers = user_data["headers"]
        # Create board
        create_response = client.post(
            f"/api/boards/?user_id={user_id}",
            json={
                "name": "Original Name",
                "description": "Test",
                "category": "test",
                "is_public": False,
            },
            headers=headers,
        )
        board_id = create_response.json()["id"]

        # Update board
        response = client.put(
            f"/api/boards/{board_id}",
            json={"name": "Updated Name", "description": "Updated description"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_delete_board(self, user_data):
        """Test deleting a board"""
        user_id = user_data["id"]
        headers = user_data["headers"]
        # Create board
        create_response = client.post(
            f"/api/boards/?user_id={user_id}",
            json={
                "name": "To Delete",
                "description": "Test",
                "category": "test",
                "is_public": False,
            },
            headers=headers,
        )
        board_id = create_response.json()["id"]

        # Delete board
        response = client.delete(f"/api/boards/{board_id}", headers=headers)
        assert response.status_code == 200

        # Verify deletion
        get_response = client.get(f"/api/boards/{board_id}", headers=headers)
        assert get_response.status_code == 404


class TestAchievementsAPI:
    """Test achievements endpoints"""

    @pytest.fixture
    def student_data(self, test_password):
        """Create a test student and return auth data"""
        response = client.post(
            "/api/auth/register",
            json={
                "username": f"achievestudent_{uuid.uuid4().hex[:8]}",
                "password": test_password,
                "display_name": "Achievement Student",
                "user_type": "student",
            },
        )
        user_id = response.json()["id"]
        return {
            "id": user_id,
            "headers": create_test_headers(
                user_id, response.json()["username"], "student"
            ),
        }

    def test_get_user_achievements(self, student_data):
        """Test getting user achievements"""
        student_id = student_data["id"]
        headers = student_data["headers"]
        response = client.get(f"/api/achievements/user/{student_id}", headers=headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_user_points(self, student_data):
        """Test getting user points"""
        student_id = student_data["id"]
        headers = student_data["headers"]
        response = client.get(
            f"/api/achievements/user/{student_id}/points", headers=headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), int)

    def test_check_achievements(self, student_data):
        """Test checking for new achievements"""
        student_id = student_data["id"]
        headers = student_data["headers"]
        response = client.post(
            f"/api/achievements/user/{student_id}/check", headers=headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_leaderboard(self, student_data):
        """Test getting leaderboard"""
        # Leaderboard requires authentication
        headers = student_data["headers"]
        response = client.get("/api/achievements/leaderboard?limit=10", headers=headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestSymbolManagementAPI:
    """Test symbol management endpoints"""

    @pytest.fixture
    def test_setup(self, test_password):
        """Create test user, board, and symbols"""
        # Create user
        user_response = client.post(
            "/api/auth/register",
            json={
                "username": f"symboluser_{id(self)}",
                "password": test_password,
                "display_name": "Symbol User",
                "user_type": "student",
            },
        )
        user_id = user_response.json()["id"]
        headers = create_test_headers(
            user_id, user_response.json()["username"], "student"
        )

        # Create board
        board_response = client.post(
            f"/api/boards/?user_id={user_id}",
            json={"name": "Symbol Test Board", "category": "test"},
            headers=headers,
        )
        board_id = board_response.json()["id"]

        # Create test symbols
        symbol1 = client.post(
            "/api/boards/symbols",
            json={
                "label": "test_symbol_1",
                "category": "test",
                "description": "Test symbol 1",
            },
            headers=headers,
        ).json()

        symbol2 = client.post(
            "/api/boards/symbols",
            json={
                "label": "test_symbol_2",
                "category": "test",
                "description": "Test symbol 2",
            },
            headers=headers,
        ).json()

        symbol3 = client.post(
            "/api/boards/symbols",
            json={
                "label": "test_symbol_3",
                "category": "test",
                "description": "Test symbol 3",
            },
            headers=headers,
        ).json()

        return {
            "user_id": user_id,
            "board_id": board_id,
            "symbols": [symbol1, symbol2, symbol3],
            "headers": headers,
        }

    def test_add_symbol_to_board(self, test_setup):
        """Test adding a symbol to a board"""
        board_id = test_setup["board_id"]
        symbol_id = test_setup["symbols"][0]["id"]
        headers = test_setup["headers"]

        # Add symbol to board
        response = client.post(
            f"/api/boards/{board_id}/symbols",
            json={"symbol_id": symbol_id, "position_x": 0, "position_y": 0, "size": 1},
            headers=headers,
        )
        assert response.status_code == 200
        board_symbol = response.json()
        assert board_symbol["symbol_id"] == symbol_id

    def test_update_board_symbol(self, test_setup):
        """Test updating a symbol's position on a board"""
        board_id = test_setup["board_id"]
        symbol_id = test_setup["symbols"][0]["id"]
        headers = test_setup["headers"]

        # Add symbol to board
        add_response = client.post(
            f"/api/boards/{board_id}/symbols",
            json={"symbol_id": symbol_id, "position_x": 0, "position_y": 0},
            headers=headers,
        )
        board_symbol_id = add_response.json()["id"]

        # Update symbol position
        response = client.put(
            f"/api/boards/{board_id}/symbols/{board_symbol_id}",
            json={"symbol_id": symbol_id, "position_x": 2, "position_y": 3, "size": 2},
            headers=headers,
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["position_x"] == 2
        assert updated["position_y"] == 3
        assert updated["size"] == 2

    def test_delete_board_symbol(self, test_setup):
        """Test removing a symbol from a board"""
        board_id = test_setup["board_id"]
        symbol_id = test_setup["symbols"][0]["id"]
        headers = test_setup["headers"]

        # Add symbol to board
        add_response = client.post(
            f"/api/boards/{board_id}/symbols",
            json={"symbol_id": symbol_id, "position_x": 0, "position_y": 0},
            headers=headers,
        )
        board_symbol_id = add_response.json()["id"]

        # Delete symbol from board
        response = client.delete(
            f"/api/boards/{board_id}/symbols/{board_symbol_id}", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_batch_update_symbols(self, test_setup):
        """Test batch updating multiple symbol positions"""
        board_id = test_setup["board_id"]
        symbols = test_setup["symbols"]
        headers = test_setup["headers"]

        # Add multiple symbols to board
        board_symbol_ids = []
        for i, symbol in enumerate(symbols[:2]):
            add_response = client.post(
                f"/api/boards/{board_id}/symbols",
                json={"symbol_id": symbol["id"], "position_x": i, "position_y": 0},
                headers=headers,
            )
            board_symbol_ids.append(add_response.json()["id"])

        # Batch update
        updates = [
            {"id": board_symbol_ids[0], "position_x": 3, "position_y": 1},
            {"id": board_symbol_ids[1], "position_x": 4, "position_y": 2},
        ]

        response = client.put(
            f"/api/boards/{board_id}/symbols/batch", json=updates, headers=headers
        )
        assert response.status_code == 200
        result = response.json()
        assert result["ok"] is True
        assert result["updated"] == 2

    def test_reorder_symbols(self, test_setup):
        """Test reordering global symbols"""
        headers = test_setup["headers"]
        symbols = test_setup["symbols"]

        # Update order index
        updates = [
            {"id": symbols[0]["id"], "order_index": 10},
            {"id": symbols[1]["id"], "order_index": 5},
        ]

        response = client.put(
            "/api/boards/symbols/reorder", json=updates, headers=headers
        )
        assert response.status_code == 200
        result = response.json()
        assert result["ok"] is True
        assert result["updated"] == 2

        # Verify order
        get_response = client.get("/api/boards/symbols", headers=headers)
        assert get_response.status_code == 200
        fetched_symbols = get_response.json()

        # Filter to only our test symbols
        test_ids = [s["id"] for s in symbols]
        our_symbols = [s for s in fetched_symbols if s["id"] in test_ids]

        assert len(our_symbols) == 3
        # symbols[2] has default order 0
        # symbols[1] has order 5
        # symbols[0] has order 10
        assert our_symbols[0]["id"] == symbols[2]["id"]
        assert our_symbols[1]["id"] == symbols[1]["id"]
        assert our_symbols[2]["id"] == symbols[0]["id"]


class TestLearningAPI:
    """Test learning companion endpoints"""

    @pytest.fixture
    def student_data(self, test_password):
        """Create a test student and return data with headers"""
        username = f"learnstudent_{uuid.uuid4()}"
        password = test_password
        response = client.post(
            "/api/auth/register",
            json={
                "username": username,
                "password": password,
                "display_name": "Learning Student",
                "user_type": "student",
            },
        )
        user_id = response.json()["id"]

        # Get token
        login_res = client.post(
            "/api/auth/token",
            data={"username": username, "password": password},
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        return {"id": user_id, "headers": headers}

    def test_learning_flow_without_ollama(self, student_data):
        """Test basic learning session flow (will skip if Ollama not available)"""
        student_id = student_data["id"]
        headers = student_data["headers"]

        # Start session
        start_response = client.post(
            f"/api/learning/start?user_id={student_id}",
            json={"topic": "colors", "purpose": "practice", "difficulty": "basic"},
            headers=headers,
        )

        # If Ollama is not available, the endpoint might return an error
        # We accept either success or expected failure
        if start_response.status_code != 200:
            # Check if it was auth error - if so, fail
            if start_response.status_code == 401 or start_response.status_code == 403:
                pytest.fail(
                    f"Auth error in learning test: {start_response.status_code}"
                )
            pytest.skip("Ollama not available for learning tests")

        data = start_response.json()
        assert "session_id" in data
        session_id = data["session_id"]

        # Get session progress
        progress_response = client.get(
            f"/api/learning/{session_id}/progress", headers=headers
        )
        assert progress_response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
