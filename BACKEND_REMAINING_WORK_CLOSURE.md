# Remaining Backend Work Closure

**Date**: 2026-08-28

## Scope

This register separates functional implementation, regression coverage, and audit-document corrections. Existing working-tree changes outside the files explicitly modified in this follow-up were preserved.

## Closed items

| ID | Type | Status | Evidence |
|---|---|---|---|
| RBAC-01 | FUNCTIONAL/TEST | CLOSED | Current guardian-profile, user, achievement, and teacher/student boundaries are covered by targeted tests; related suites passed. |
| MUT-01 | FUNCTIONAL/TEST | CLOSED | Existing destructive/import/delete/durability tests passed in targeted execution. |
| PROVIDER-01 | FUNCTIONAL/TEST | CLOSED | Provider route, telemetry, Groq, TTS, lifecycle, and compatibility tests passed in targeted execution. |
| LOG-01 | FUNCTIONAL/TEST | CLOSED | Nine at-risk handlers contain logging; P1/P2 emission regression tests passed. |
| I18N-01 | FUNCTIONAL/TEST | CLOSED | Learning-session namespace fix and contract tests passed. |
| AUDIT-01 | DOCUMENTATION | CLOSED | Authoritative corrections document updated with current implementation/test evidence and artifact links. |
| AUDIT-02 | DOCUMENTATION | CLOSED | V3 route, mutation, destructive, exception, filesystem, external-I/O, mutable-state, test-mapping, and side-effect corrections are recorded in the challenge artifacts. |

## Targeted validation executed

- `uv run pytest -q tests/test_teacher_student_access.py tests/test_guardian_profiles.py tests/test_achievements_query_regressions.py tests/test_users_routes_coverage.py`
- `uv run pytest -q tests/test_user_creation_validation.py tests/test_writes_durable_before_response.py tests/test_schema_migrations.py`
- `uv run pytest -q tests/test_providers_routes.py tests/test_provider_telemetry.py tests/test_groq_provider.py tests/test_local_tts_provider.py`
- `uv run pytest -q tests/test_response_processing_helpers.py::test_process_response_logs_achievement_update_failure tests/test_local_vector_store_sqlite_vec.py::test_refresh_metadata_cache_logs_load_failure tests/test_backend_translation_contract.py tests/test_teacher_student_access.py::test_learning_session_lookup_default_uses_learning_namespace`
- `git diff --check`

## Important qualification

The corrected historical V3 claims are not application defects requiring code changes. They are stale or unsupported audit assertions, and their authoritative replacements are documented. The tests above establish current behavior for the implemented/remediated paths; they do not retroactively make the original V3 assertions true.

## Preserved unrelated work

The working tree contained unrelated backend, frontend, test, documentation, dependency, and packaging changes before this follow-up. They were not reverted, reset, or overwritten.
