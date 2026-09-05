# Backend Change Validation Matrix (Forensic Review)

This document provides a line-by-line forensic validation of every modification introduced during the backend implementation phase, evaluating each against real runtime contracts, security boundaries, and API compatibility.

---

## Change-by-Change Forensic Ledger

| Change ID | File / Symbol | Intended Problem | Actual Diff | Behavioral Change | API Impact | Security Impact | Tests | Evidence For | Evidence Against | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CHG-01** | `src/api/deps/access.py`<br>`get_learning_session_or_404` | Teacher 403 on student learning session inspection | Added `verify_student_access` branch for teacher role | Allowed teachers to access session object for assigned students across all callers | Extends session access to teachers | **Too Broad for Mutations**: Allows teachers to access session in mutation endpoints (`/ask`, `/answer`, `/end`) | `tests/test_learning_routes_coverage.py` | Allows teachers to inspect student progress in `GET /{session_id}/progress` | Teachers should not mutate student session state or submit answers on student's behalf | **REDUCE_SCOPE** (Restricted to read endpoints via `allow_teacher=True`) |
| **CHG-02** | `src/api/routers/learning.py`<br>`start_session` | Teacher unable to start student session | Added `verify_student_access` to `/start` | Allowed teachers to start sessions on behalf of assigned students | Path and schema unchanged | **Overly Broad**: Student learning sessions should be student-owned | `tests/test_learning_routes_coverage.py` | Teachers might initiate guided practice | Starting sessions for students generates student analytics for teacher actions; frontend starts sessions using current user | **REVERT_OWN_CHANGE** (Restore self/admin only on `/start`) |
| **CHG-03** | `src/api/routers/learning.py`<br>`get_history` | Teacher unable to view assigned student learning history | Added `verify_student_access` to `GET /history/{user_id}` | Allowed assigned teachers to view student past sessions; unassigned teachers get 403 | None (query and response schema unchanged) | **Intended RBAC Read**: Resolves teacher dashboard 403 | `tests/test_learning_routes_coverage.py` | Directly consumed by `src/frontend/src/store/dashboardStore.ts:46` | None. Explicitly assigned via `StudentTeacher` table | **KEEP** |
| **CHG-04** | `src/api/routers/providers.py`<br>`GET /ai/models/lmstudio` | Remove duplicate LM Studio model listing | Deleted endpoint `GET /api/providers/ai/models/lmstudio` | Endpoint returns 404 instead of model list | **Breaking Change**: Deletes registered public route | None | `tests/test_providers_routes.py` (deleted tests) | Canonical route lives at `/api/settings/ai/models/lmstudio` | Older scripts, external clients, or legacy builds calling `/api/providers/ai/models/lmstudio` break | **REVERT_OWN_CHANGE** (Restore compatibility endpoint) |
| **CHG-05** | `src/api/routers/analytics.py`<br>`POST /api/analytics/log` | Remove legacy analytics log endpoint | Deleted route `POST /api/analytics/log` | Endpoint returns 404 instead of logging usage | **Breaking Change**: Deletes compatibility alias | None | `tests/test_analytics_api.py` (deleted test) | Modern frontend calls `/api/analytics/usage` | External clients or legacy builds calling `/log` break | **REVERT_OWN_CHANGE** (Restore compatibility endpoint) |
| **CHG-06** | `src/aac_app/providers/base_provider.py`<br>`BaseLLMProvider.close()` | Inconsistent `.close()` signatures across subclasses | Added `async def close()` to `BaseLLMProvider`, removed subclass overrides | Standardizes `await provider.close()` across all 4 LLM providers | None (internal Python interface) | None | `tests/test_groq_provider.py` | Eliminates divergent sync/async method signatures | None | **KEEP** |
| **CHG-07** | `src/aac_app/services/template_manager.py`<br>`_get_hardcoded_default` | Dead unreferenced fallback method | Deleted `_get_hardcoded_default()` | Removed dead method | None | None | `tests/test_guardian_profiles.py` | 0 references across entire codebase; `default.yaml` is validated at startup | None | **KEEP** |
| **CHG-08** | `src/api/routers/achievements.py`<br>`nullcontext(db)` | Incomplete refactor artifact | Replaced `with nullcontext(db) as session:` with `session = db` | Simplifies code; zero transaction change | None | None | `tests/test_achievements_query_regressions.py` | Removes unnecessary indentation and unused import | None | **KEEP** |
| **CHG-09** | `src/aac_app/services/board_generation_service.py`<br>`BaseLLMProvider` typing | Incomplete union type omitting Groq | Changed `llm_provider` annotation to `BaseLLMProvider` | Improves type accuracy | None | None | `tests/test_board_generation_service_unit.py` | Groq is the production provider and inherits from `BaseLLMProvider` | None | **KEEP** |
| **CHG-10** | `src/api/file_uploads.py`<br>`remove_owned_upload` docstring | Clarify parameter semantics | Updated docstring to state `target upload subdirectory` | Clarifies documentation | None | None | `tests/test_file_uploads.py` | Documents actual production usage without changing runtime code | None | **KEEP** |

---

## Summary of Actionable Corrections for Stage A

1. **CHG-01 & CHG-02 (Teacher RBAC Scope Reduction)**:
   - Scope reduction: Only allow teachers read access (`GET /api/learning/history/{user_id}` and `GET /api/learning/{session_id}/progress` with `allow_teacher=True`).
   - Restrict `POST /api/learning/start`, `/ask`, `/answer`, and `/end` strictly to session owner or admin to prevent teachers from impersonating student actions or altering session state.
2. **CHG-04 (Restore LM Studio Compatibility Route)**:
   - Re-add `GET /api/providers/ai/models/lmstudio` in `src/api/routers/providers.py` to ensure 100% external API backward compatibility.
3. **CHG-05 (Restore Analytics Compatibility Route)**:
   - Re-add `POST /api/analytics/log` in `src/api/routers/analytics.py` as a lightweight compatibility alias delegating to `_log_usage_request`.
