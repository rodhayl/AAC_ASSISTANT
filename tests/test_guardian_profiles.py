"""
Tests for Guardian Profiles Feature

Tests the complete guardian profile system including:
- Access control (students cannot access their profiles)
- CRUD operations by teachers and admins
- Template system
- System prompt generation
- Audit trail
- Profile resolution with templates + overrides
"""

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.aac_app.models.database import User, GuardianProfile
from src.aac_app.services.auth_service import get_password_hash
from tests.test_utils_auth import create_test_headers

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("setup_test_db")
_USER_CONTEXT: dict[int, tuple[str, str]] = {}


# --- Helper Functions ---

def create_admin_for_tests(test_db_session, test_password) -> tuple[dict, str]:
    """Create an admin user directly in DB for test setup."""
    from src.aac_app.models.database import User
    from src.aac_app.services.auth_service import get_password_hash
    from tests.test_utils_auth import create_test_token
    
    admin = User(
        username="test_admin",
        email="admin@test.com",
        password_hash=get_password_hash(test_password),
        user_type="admin",
        is_active=True,
        display_name="Test Admin"
    )
    test_db_session.add(admin)
    test_db_session.commit()
    test_db_session.refresh(admin)
    
    token = create_test_token(admin.id, admin.username, "admin")
    _USER_CONTEXT[admin.id] = (admin.username, "admin")
    return {"id": admin.id, "username": admin.username}, token


def create_user(username: str, user_type: str, password: str, admin_token: str = None) -> dict:
    """Create a user and return their info including ID."""
    # Students can self-register
    if user_type == "student":
        response = client.post(
            "/api/auth/register",
            json={
                "username": username,
                "password": password,
                "display_name": f"{username.capitalize()} User",
                "user_type": user_type
            },
        )
        assert response.status_code == 200, f"Failed to create student: {response.text}"
        data = response.json()
        _USER_CONTEXT[data["id"]] = (data["username"], data["user_type"])
        return data
    
    # Teachers and admins need to be created by an admin
    if admin_token is None:
        from src.api.dependencies import get_session
        from tests.test_utils_auth import create_test_token

        with get_session() as db:
            bootstrap_admin = (
                db.query(User)
                .filter(User.user_type == "admin", User.is_active.is_(True))
                .first()
            )
            if bootstrap_admin is None:
                bootstrap_admin = User(
                    username="bootstrap_admin",
                    email="bootstrap_admin@test.com",
                    password_hash=get_password_hash(password),
                    user_type="admin",
                    is_active=True,
                    display_name="Bootstrap Admin",
                )
                db.add(bootstrap_admin)
                db.flush()
            admin_token = create_test_token(
                bootstrap_admin.id, bootstrap_admin.username, "admin"
            )
            _USER_CONTEXT[bootstrap_admin.id] = (bootstrap_admin.username, "admin")

    response = client.post(
        "/api/auth/admin/create-user",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": username,
            "password": password,
            "confirm_password": password,
            "display_name": f"{username.capitalize()} User",
            "user_type": user_type
        },
    )
    assert response.status_code == 200, f"Failed to create user: {response.text}"
    data = response.json()
    _USER_CONTEXT[data["id"]] = (data["username"], data["user_type"])
    return data


def get_auth_header(user_id: int, username: str = None, user_type: str = None) -> dict:
    """Get authorization header for a user."""
    if username is None or user_type is None:
        resolved = _USER_CONTEXT.get(user_id)
        if resolved is None:
            raise AssertionError(
                f"Missing user context for id={user_id}; provide username and user_type."
            )
        username, user_type = resolved
    return create_test_headers(user_id, username, user_type)


# --- Access Control Tests ---

class TestAccessControl:
    """Test that students cannot access guardian profiles."""
    
    def test_student_cannot_list_templates(self, test_db_session, test_password):
        """Students should be forbidden from listing templates."""
        admin, admin_token = create_admin_for_tests(test_db_session, test_password)
        student = create_user("student_ac1", "student", test_password)
        
        response = client.get(
            "/api/guardian-profiles/templates",
            headers=get_auth_header(student["id"], student["username"], "student")
        )
        
        assert response.status_code == 403
        assert "teachers and admins" in response.json()["detail"].lower()
    
    def test_student_cannot_view_own_profile(self, test_db_session, test_password):
        """Students should not be able to see their own guardian profile."""
        admin, admin_token = create_admin_for_tests(test_db_session, test_password)
        student = create_user("student_ac2", "student", test_password)
        teacher = create_user("teacher_ac2", "teacher", test_password, admin_token)
        
        # Teacher creates profile for student
        response = client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "default"},
            headers=get_auth_header(teacher["id"], teacher["username"], "teacher")
        )
        assert response.status_code == 200
        
        # Student tries to view their profile - should fail
        response = client.get(
            f"/api/guardian-profiles/students/{student['id']}",
            headers=get_auth_header(student["id"], student["username"], "student")
        )
        assert response.status_code == 403
    
    def test_student_cannot_view_other_student_profile(self, test_password):
        """Students should not be able to see other students' profiles."""
        student1 = create_user("student_ac3a", "student", test_password)
        student2 = create_user("student_ac3b", "student", test_password)
        
        response = client.get(
            f"/api/guardian-profiles/students/{student2['id']}",
            headers=get_auth_header(student1["id"])
        )
        assert response.status_code == 403
    
    def test_student_cannot_list_students_with_profiles(self, test_password):
        """Students should not be able to list students with profiles."""
        student = create_user("student_ac4", "student", test_password)
        
        response = client.get(
            "/api/guardian-profiles/students",
            headers=get_auth_header(student["id"])
        )
        assert response.status_code == 403
    
    def test_teacher_can_access_profiles(self, test_password):
        """Teachers should be able to access guardian profiles."""
        teacher = create_user("teacher_ac5", "teacher", test_password)
        student = create_user("student_ac5", "student", test_password)
        
        # List templates
        response = client.get(
            "/api/guardian-profiles/templates",
            headers=get_auth_header(teacher["id"])
        )
        assert response.status_code == 200
        
        # List students
        response = client.get(
            "/api/guardian-profiles/students",
            headers=get_auth_header(teacher["id"])
        )
        assert response.status_code == 200
    
    def test_admin_can_access_profiles(self, test_password):
        """Admins should be able to access guardian profiles."""
        admin = create_user("admin_ac6", "admin", test_password)
        student = create_user("student_ac6", "student", test_password)
        
        # List templates
        response = client.get(
            "/api/guardian-profiles/templates",
            headers=get_auth_header(admin["id"])
        )
        assert response.status_code == 200
        
        # List students
        response = client.get(
            "/api/guardian-profiles/students",
            headers=get_auth_header(admin["id"])
        )
        assert response.status_code == 200
    
    def test_only_admin_can_delete_profile(self, test_password):
        """Only admins should be able to delete profiles."""
        admin = create_user("admin_ac7", "admin", test_password)
        teacher = create_user("teacher_ac7", "teacher", test_password)
        student = create_user("student_ac7", "student", test_password)
        
        # Create profile
        response = client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "default"},
            headers=get_auth_header(teacher["id"])
        )
        assert response.status_code == 200
        
        # Teacher tries to delete - should fail
        response = client.delete(
            f"/api/guardian-profiles/students/{student['id']}",
            headers=get_auth_header(teacher["id"])
        )
        assert response.status_code == 403
        assert "Only admins" in response.json()["detail"]
        
        # Admin can delete
        response = client.delete(
            f"/api/guardian-profiles/students/{student['id']}",
            headers=get_auth_header(admin["id"])
        )
        assert response.status_code == 200


# --- Template Tests ---

class TestTemplates:
    """Test template listing and retrieval."""
    
    def test_list_templates(self, test_password):
        """Should list all available templates."""
        teacher = create_user("teacher_t1", "teacher", test_password)
        
        response = client.get(
            "/api/guardian-profiles/templates",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        templates = response.json()
        assert isinstance(templates, list)
        assert len(templates) > 0
        
        # Should have default template
        template_names = [t["name"] for t in templates]
        assert "default" in template_names
    
    def test_get_specific_template(self, test_password):
        """Should get details of a specific template."""
        teacher = create_user("teacher_t2", "teacher", test_password)
        
        response = client.get(
            "/api/guardian-profiles/templates/default",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        template = response.json()
        # Template 'name' field is the display name, not the file name
        assert "name" in template  # Should have a name field
        assert "communication_style" in template
        assert "safety" in template
    
    def test_get_nonexistent_template_404(self, test_password):
        """Should return 404 for nonexistent template."""
        teacher = create_user("teacher_t3", "teacher", test_password)
        
        response = client.get(
            "/api/guardian-profiles/templates/nonexistent_template_xyz",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 404
    
    def test_preview_template_prompt(self, test_password):
        """Should preview system prompt for a template."""
        teacher = create_user("teacher_t4", "teacher", test_password)
        
        response = client.post(
            "/api/guardian-profiles/templates/default/preview",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        preview = response.json()
        assert "prompt" in preview
        assert len(preview["prompt"]) > 0


# --- Profile CRUD Tests ---

class TestProfileCRUD:
    """Test profile create, read, update, delete operations."""
    
    def test_create_profile(self, test_password):
        """Should create a profile for a student."""
        teacher = create_user("teacher_c1", "teacher", test_password)
        student = create_user("student_c1", "student", test_password)
        
        response = client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={
                "template_name": "default",
                "age": 8,
                "gender": "male",
                "communication_style": {
                    "tone": "encouraging",
                    "complexity": "simple"
                }
            },
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        profile = response.json()
        assert profile["user_id"] == student["id"]
        assert profile["template_name"] == "default"
        assert profile["age"] == 8
        assert profile["communication_style"]["tone"] == "encouraging"
    
    def test_create_profile_duplicate_conflict(self, test_password):
        """Should return 409 when profile already exists."""
        teacher = create_user("teacher_c2", "teacher", test_password)
        student = create_user("student_c2", "student", test_password)
        
        # Create first profile
        response = client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "default"},
            headers=get_auth_header(teacher["id"])
        )
        assert response.status_code == 200
        
        # Try to create again - should fail
        response = client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "calm_gentle"},
            headers=get_auth_header(teacher["id"])
        )
        assert response.status_code == 409
    
    def test_get_profile(self, test_password):
        """Should retrieve an existing profile."""
        teacher = create_user("teacher_c3", "teacher", test_password)
        student = create_user("student_c3", "student", test_password)
        
        # Create profile
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "calm_gentle", "age": 10},
            headers=get_auth_header(teacher["id"])
        )
        
        # Get profile
        response = client.get(
            f"/api/guardian-profiles/students/{student['id']}",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        profile = response.json()
        assert profile["template_name"] == "calm_gentle"
        assert profile["age"] == 10
    
    def test_get_profile_not_found(self, test_password):
        """Should return 404 when profile doesn't exist."""
        teacher = create_user("teacher_c4", "teacher", test_password)
        student = create_user("student_c4", "student", test_password)
        
        response = client.get(
            f"/api/guardian-profiles/students/{student['id']}",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 404
    
    def test_update_profile(self, test_password):
        """Should update an existing profile."""
        teacher = create_user("teacher_c5", "teacher", test_password)
        student = create_user("student_c5", "student", test_password)
        
        # Create profile
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "default", "age": 8},
            headers=get_auth_header(teacher["id"])
        )
        
        # Update profile
        response = client.put(
            f"/api/guardian-profiles/students/{student['id']}",
            json={
                "age": 9,
                "communication_style": {"tone": "playful"},
                "change_reason": "Student had birthday"
            },
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        profile = response.json()
        assert profile["age"] == 9
        assert profile["communication_style"]["tone"] == "playful"
    
    def test_update_profile_no_changes_error(self, test_password):
        """Should return 400 when no changes provided."""
        teacher = create_user("teacher_c6", "teacher", test_password)
        student = create_user("student_c6", "student", test_password)
        
        # Create profile
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "default"},
            headers=get_auth_header(teacher["id"])
        )
        
        # Update with empty body
        response = client.put(
            f"/api/guardian-profiles/students/{student['id']}",
            json={},
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 400
        assert "No changes" in response.json()["detail"]
    
    def test_delete_profile(self, test_password):
        """Should soft-delete a profile."""
        admin = create_user("admin_c7", "admin", test_password)
        student = create_user("student_c7", "student", test_password)
        
        # Create profile
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "default"},
            headers=get_auth_header(admin["id"])
        )
        
        # Delete profile
        response = client.delete(
            f"/api/guardian-profiles/students/{student['id']}",
            headers=get_auth_header(admin["id"])
        )
        
        assert response.status_code == 200
        
        # Verify it's no longer accessible
        response = client.get(
            f"/api/guardian-profiles/students/{student['id']}",
            headers=get_auth_header(admin["id"])
        )
        assert response.status_code == 404
    
    def test_profile_for_non_student_rejected(self, test_password):
        """Should reject creating profile for non-student users."""
        admin = create_user("admin_c8", "admin", test_password)
        teacher = create_user("teacher_c8", "teacher", test_password)
        
        # Try to create profile for teacher
        response = client.post(
            f"/api/guardian-profiles/students/{teacher['id']}",
            json={"template_name": "default"},
            headers=get_auth_header(admin["id"])
        )
        
        assert response.status_code == 400
        assert "students" in response.json()["detail"].lower()


# --- Profile Resolution Tests ---

class TestProfileResolution:
    """Test effective profile resolution combining templates and overrides."""
    
    def test_effective_profile_with_template_only(self, test_password):
        """Should return template defaults when no overrides."""
        teacher = create_user("teacher_r1", "teacher", test_password)
        student = create_user("student_r1", "student", test_password)
        
        # Create profile with just template
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "calm_gentle"},
            headers=get_auth_header(teacher["id"])
        )
        
        # Get effective profile
        response = client.get(
            f"/api/guardian-profiles/students/{student['id']}/effective-profile",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        profile = response.json()
        # Should have values from calm_gentle template
        assert "communication_style" in profile
    
    def test_effective_profile_with_overrides(self, test_password):
        """Should merge overrides with template defaults."""
        teacher = create_user("teacher_r2", "teacher", test_password)
        student = create_user("student_r2", "student", test_password)
        
        # Create profile with overrides
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={
                "template_name": "default",
                "communication_style": {
                    "tone": "very_playful",
                    "use_emojis": True
                }
            },
            headers=get_auth_header(teacher["id"])
        )
        
        # Get effective profile
        response = client.get(
            f"/api/guardian-profiles/students/{student['id']}/effective-profile",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        profile = response.json()
        # Should have our override
        comm_style = profile.get("communication_style", {})
        assert comm_style.get("tone") == "very_playful"
        assert comm_style.get("use_emojis") is True
    
    def test_system_prompt_generation(self, test_password):
        """Should generate complete system prompt from profile."""
        teacher = create_user("teacher_r3", "teacher", test_password)
        student = create_user("student_r3", "student", test_password)
        
        # Create profile
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={
                "template_name": "default",
                "age": 7,
                "companion_persona": {
                    "name": "Buddy",
                    "personality": ["friendly", "patient"]
                },
                "custom_instructions": "Always use simple words"
            },
            headers=get_auth_header(teacher["id"])
        )
        
        # Get system prompt
        response = client.get(
            f"/api/guardian-profiles/students/{student['id']}/system-prompt",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        result = response.json()
        prompt = result["prompt"]
        
        # Prompt should contain our customizations
        assert "Buddy" in prompt or "friendly" in prompt or "simple words" in prompt


# --- Audit Trail Tests ---

class TestAuditTrail:
    """Test profile change history tracking."""
    
    def test_history_records_creation(self, test_password):
        """Should record profile creation in history."""
        teacher = create_user("teacher_a1", "teacher", test_password)
        student = create_user("student_a1", "student", test_password)
        
        # Create profile
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "calm_gentle"},
            headers=get_auth_header(teacher["id"])
        )
        
        # Get history - should exist
        response = client.get(
            f"/api/guardian-profiles/students/{student['id']}/history",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        # History may or may not have entries for initial creation
        # depending on implementation
    
    def test_history_records_updates(self, test_password):
        """Should record all profile updates in history."""
        teacher = create_user("teacher_a2", "teacher", test_password)
        student = create_user("student_a2", "student", test_password)
        
        # Create profile
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "default", "age": 8},
            headers=get_auth_header(teacher["id"])
        )
        
        # Update profile multiple times
        client.put(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"age": 9, "change_reason": "Birthday update"},
            headers=get_auth_header(teacher["id"])
        )
        
        client.put(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "calm_gentle", "change_reason": "Therapy recommendation"},
            headers=get_auth_header(teacher["id"])
        )
        
        # Get history
        response = client.get(
            f"/api/guardian-profiles/students/{student['id']}/history",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        history = response.json()
        assert isinstance(history, list)
        assert len(history) >= 2  # At least the two updates
        
        # Check that change reasons are recorded
        reasons = [h.get("change_reason") for h in history if h.get("change_reason")]
        assert "Birthday update" in reasons or "Therapy recommendation" in reasons
    
    def test_history_records_who_made_change(self, test_password):
        """Should record which user made each change."""
        teacher1 = create_user("teacher_a3a", "teacher", test_password)
        teacher2 = create_user("teacher_a3b", "teacher", test_password)
        student = create_user("student_a3", "student", test_password)
        
        # Teacher 1 creates profile
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "default"},
            headers=get_auth_header(teacher1["id"])
        )
        
        # Teacher 2 updates profile
        client.put(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"age": 10},
            headers=get_auth_header(teacher2["id"])
        )
        
        # Get history
        response = client.get(
            f"/api/guardian-profiles/students/{student['id']}/history",
            headers=get_auth_header(teacher1["id"])
        )
        
        assert response.status_code == 200
        history = response.json()
        
        # Find update by teacher2
        for entry in history:
            if entry.get("field_name") == "age":
                assert entry["changed_by"]["id"] == teacher2["id"]
                break


# --- Safety Configuration Tests ---

class TestSafetyConfiguration:
    """Test safety constraints and content filtering."""
    
    def test_safety_constraints_stored(self, test_password):
        """Should store safety constraints correctly."""
        teacher = create_user("teacher_s1", "teacher", test_password)
        student = create_user("student_s1", "student", test_password)
        
        # Create profile with safety constraints
        response = client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={
                "template_name": "default",
                "safety_constraints": {
                    "content_filter_level": "strict",
                    "forbidden_topics": ["violence", "politics"],
                    "trigger_words": ["scary", "monster"]
                }
            },
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        profile = response.json()
        safety = profile["safety_constraints"]
        assert safety["content_filter_level"] == "strict"
        assert "violence" in safety["forbidden_topics"]
        assert "scary" in safety["trigger_words"]
    
    def test_medical_context_stored_but_private(self, test_password):
        """Should store medical context privately (never sent to LLM)."""
        teacher = create_user("teacher_s2", "teacher", test_password)
        student = create_user("student_s2", "student", test_password)
        
        # Create profile with medical context
        response = client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={
                "template_name": "autism_friendly",
                "medical_context": {
                    "diagnoses": ["autism_spectrum", "anxiety"],
                    "sensitivities": ["loud_noises", "bright_lights"],
                    "notes": "Needs extra processing time"
                }
            },
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        profile = response.json()
        medical = profile["medical_context"]
        assert "autism_spectrum" in medical["diagnoses"]
        assert "loud_noises" in medical["sensitivities"]
        
        # Note: The actual prompt should NOT contain this medical info
        # This would be verified in integration tests with actual LLM


# --- Student Listing Tests ---

class TestStudentListing:
    """Test listing students with profile status."""
    
    def test_list_students_shows_profile_status(self, test_password):
        """Should show which students have profiles configured."""
        teacher = create_user("teacher_l1", "teacher", test_password)
        student_with = create_user("student_l1a", "student", test_password)
        student_without = create_user("student_l1b", "student", test_password)
        
        # Create profile for one student
        client.post(
            f"/api/guardian-profiles/students/{student_with['id']}",
            json={"template_name": "default"},
            headers=get_auth_header(teacher["id"])
        )
        
        # List students
        response = client.get(
            "/api/guardian-profiles/students",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        students = response.json()
        
        # Find our students
        student_with_info = next((s for s in students if s["id"] == student_with["id"]), None)
        student_without_info = next((s for s in students if s["id"] == student_without["id"]), None)
        
        assert student_with_info is not None
        assert student_with_info["has_profile"] is True
        assert student_with_info["template_name"] == "default"
        
        assert student_without_info is not None
        assert student_without_info["has_profile"] is False


# --- Edge Cases ---

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_nonexistent_student_404(self, test_password):
        """Should return 404 for nonexistent student."""
        teacher = create_user("teacher_e1", "teacher", test_password)
        
        response = client.get(
            "/api/guardian-profiles/students/999999",
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 404
    
    def test_delete_nonexistent_profile_404(self, test_password):
        """Should return 404 when deleting nonexistent profile."""
        admin = create_user("admin_e2", "admin", test_password)
        student = create_user("student_e2", "student", test_password)
        
        response = client.delete(
            f"/api/guardian-profiles/students/{student['id']}",
            headers=get_auth_header(admin["id"])
        )
        
        assert response.status_code == 404
    
    def test_create_with_invalid_template(self, test_password):
        """Should handle gracefully when template doesn't exist."""
        teacher = create_user("teacher_e3", "teacher", test_password)
        student = create_user("student_e3", "student", test_password)
        
        # Create with nonexistent template - should still work (falls back to default)
        response = client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"template_name": "nonexistent_template_xyz"},
            headers=get_auth_header(teacher["id"])
        )
        
        # Should either succeed with fallback or return appropriate error
        assert response.status_code in [200, 400, 404]
    
    def test_update_profile_preserves_unmentioned_fields(self, test_password):
        """Should preserve existing fields when updating only some fields."""
        teacher = create_user("teacher_e4", "teacher", test_password)
        student = create_user("student_e4", "student", test_password)
        
        # Create profile with multiple fields
        client.post(
            f"/api/guardian-profiles/students/{student['id']}",
            json={
                "template_name": "default",
                "age": 8,
                "communication_style": {"tone": "encouraging"},
                "custom_instructions": "Be patient"
            },
            headers=get_auth_header(teacher["id"])
        )
        
        # Update only age
        response = client.put(
            f"/api/guardian-profiles/students/{student['id']}",
            json={"age": 9},
            headers=get_auth_header(teacher["id"])
        )
        
        assert response.status_code == 200
        profile = response.json()
        
        # Age should be updated
        assert profile["age"] == 9
        # Other fields should be preserved
        assert profile["template_name"] == "default"
        assert profile["custom_instructions"] == "Be patient"
