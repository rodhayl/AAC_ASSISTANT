# Backend Audit Evidence Ledger

This document serves as the canonical evidence ledger for all findings investigated during the comprehensive red-team re-audit of the AAC Assistant backend. Every claim is subjected to rigorous falsification against real code paths, frontend consumers, and test suites.

---

## Finding Classification Summary

| ID | Title / Target | Category | V1 Status | V2 Red-Team Verdict | Severity | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **EV-01** | `remove_owned_upload` Path Contract | File Safety | Critical Bug | **Falsified / Non-Issue in Production** | Low | Very High |
| **EV-02** | AI Board Item Count Strict Equality | AI Generation | Critical Bug | **Refined / Contract Invariant** | Low | High |
| **EV-03** | Startup Schema Deduplication Queries | Performance | High Priority | **Rejected (Overengineering)** | Low | High |
| **EV-04** | `UserService` & `users.py` Duplication | Architecture | Dead Code Deletion | **Falsified (Critical Frontend Dependency)** | N/A | Very High |
| **EV-05** | Board Create Route Placement | Code Cleanliness | Move Route | **Rejected (Coupling Risk)** | N/A | High |
| **EV-06** | Duplicate LM Studio Model Listing | API Redundancy | Dead Code | **Confirmed Dead Route** | Low | High |
| **EV-07** | `nullcontext(db)` in `achievements.py` | Refactoring Artifact | Code Polish | **Confirmed Code Smell** | Low | Very High |
| **EV-08** | `_get_hardcoded_default` in `template_manager.py` | Dead Code | Dead Code | **Confirmed Dead Method** | Low | Very High |
| **EV-09** | Legacy Usage Endpoint `POST /api/analytics/log` | API Redundancy | Deprecated | **Confirmed Dead Shim** | Low | Very High |
| **EV-10** | Provider Synchronous `close()` Aliases | Dead Code | Cleanup | **Confirmed Dead Aliases** | Low | Very High |
| **EV-11** | Smartbar Intent Closure Allocation | Performance | Refactor Closures | **Rejected (Micro-optimization)** | N/A | High |
| **EV-12** | Groq Provider Union Type Annotations | Typing | Type Fix | **Confirmed / Minor Type Polish** | Trivial | High |
| **EV-13** | **Teacher RBAC Bypass in Learning Sessions** | Authorization / RBAC | *Missed in V1* | **New Confirmed Defect** | Medium | Very High |

---

## Detailed Evidence Records

### EV-01: `remove_owned_upload` Path Deletion Contract
* **File Target**: [`src/api/file_uploads.py:L177-196`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/file_uploads.py#L177-L196)
* **V1 Claim**: "Passing `uploads_dir = config.UPLOADS_DIR` causes `parts[0] != uploads_dir.name` (`'symbols' != 'uploads'`) to abort silently without deleting files."
* **Evidence FOR (Hypothesis)**:
  - In `file_uploads.py:183`: `if len(parts) < 2 or parts[0] != uploads_dir.name: return`.
  - If a developer passes `config.UPLOADS_DIR` (whose `.name` is `"uploads"`), the check evaluates `"symbols" != "uploads"` and returns early.
* **Evidence AGAINST (Falsification)**:
  - An exhaustive call-site trace across the entire repository revealed 5 production invocations (all in [`src/api/routers/symbols.py`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/routers/symbols.py#L80)):
    - `symbols.py:80`: `remove_owned_upload(f"/uploads/symbols/{name}", uploads_dir)` where `uploads_dir = config.UPLOADS_DIR / "symbols"`.
    - `symbols.py:338`: `remove_owned_upload(public_path, uploads_dir)` where `uploads_dir = config.UPLOADS_DIR / "symbols"`.
    - `symbols.py:396`: `remove_owned_upload(public_path, uploads_dir)` where `uploads_dir = config.UPLOADS_DIR / "symbols"`.
    - `symbols.py:402`: `remove_owned_upload(old_image_path, uploads_dir)` where `uploads_dir = config.UPLOADS_DIR / "symbols"`.
    - `symbols.py:429`: `remove_owned_upload(image_path, config.UPLOADS_DIR / "symbols")`.
  - In all 5 call sites, `uploads_dir.name` is `"symbols"`, matching `parts[0]`.
  - Unit tests in `tests/test_file_uploads.py:112-125` explicitly pass `uploads = tmp_path / "uploads" / "symbols"`, verifying that the function deletes files inside that subdirectory and blocks traversal.
* **Frontend Impact**: Zero. No files are leaked in production.
* **Verdict**: **Falsified as a live defect**. The parameter name `uploads_dir: Path` is slightly ambiguous (it represents `target_subdir: Path`), but the runtime behavior is working as designed.
* **Minimal Remediation**: Update docstring/parameter typing to clarify `target_subdir: Path` without altering production semantics.

---

### EV-02: AI Board Item Count Strict Equality
* **File Target**: [`src/aac_app/services/board_generation_service.py:L167-171`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/aac_app/services/board_generation_service.py#L167-L171)
* **V1 Claim**: "`len(valid_items) != item_count` causes hard 502 errors when an LLM returns 11 items instead of 12."
* **Evidence FOR (Hypothesis)**:
  - LLM outputs can occasionally be non-deterministic, returning 11 items for a 12-item request.
* **Evidence AGAINST (Falsification)**:
  - AAC communication boards rely on fixed grid dimensions (e.g. $3 \times 4 = 12$ or $4 \times 5 = 20$).
  - Downstream placement in [`src/api/routers/board_ai.py:L232`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/routers/board_ai.py#L232) calls `validate_board_position(db_board, idx % cols, idx // cols)`, expecting exact grid capacity.
  - In [`tests/test_board_generation_service_unit.py:L74-82`](file:///home/wishmaster/Github/AAC_ASSISTANT/tests/test_board_generation_service_unit.py#L74-L82), `test_generate_board_items_rejects_incomplete_item_count` explicitly asserts that returning fewer items than requested raises `ValueError("AI returned X valid items; expected Y")`.
  - Repository instruction in `AGENTS.md` mandates: "Invalid provider output is an explicit failure; never invent a deterministic question/board in production."
* **Frontend Impact**: The frontend catches 502/400 errors and presents an explicit retry toast to the user rather than rendering a corrupted, half-empty grid.
* **Verdict**: **Refined**. The strict lower-bound failure is an intentional architectural invariant. Truncating excess items (`valid_items[:item_count]`) when `len(valid_items) > item_count` is safe, but relaxing the lower bound would violate existing regression tests.

---

### EV-03: Startup Schema Deduplication Scans
* **File Target**: [`src/aac_app/schema.py:L360-432`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/aac_app/schema.py#L360-L432)
* **V1 Claim**: "Unconditional deduplication scans slow down every server startup and should be replaced with a schema migration version table."
* **Evidence FOR (Hypothesis)**:
  - Lines 360-432 execute SQL `SELECT` queries across the `symbols` table on every invocation of `schema.ensure()`.
* **Evidence AGAINST (Falsification)**:
  - Live benchmark on the production database containing 10,000+ ARASAAC symbols: `schema.ensure()` completed in **173.65 ms**.
  - `schema.ensure()` executes **once** during server bootstrap (in FastAPI `lifespan`), completely outside the request-response cycle.
  - Adding a schema version tracking table introduces version state management, upgrade/downgrade logic, rollback risks, and risks skipping self-healing checks on portable USB installs.
* **Verdict**: **Rejected as overengineering**. 173ms one-time bootstrap overhead is negligible and provides valuable self-healing capabilities for portable SQLite databases.

---

### EV-04: `UserService` & `users.py` Duplication
* **File Target**: [`src/api/routers/users.py`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/routers/users.py) & [`src/aac_app/services/user_service.py`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/aac_app/services/user_service.py)
* **V1 Claim**: "`UserService` and `/api/users` are 100% dead / redundant copies of `auth_users.py`. Delete both files."
* **Evidence FOR (Hypothesis)**:
  - `GET /api/users/me` duplicates `GET /api/auth/me`.
  - `PUT /api/users/me` duplicates `PUT /api/auth/profile`.
* **Evidence AGAINST (Falsification)**:
  - Live inspection of frontend React components revealed critical active dependencies:
    - [`src/frontend/src/pages/Achievements.tsx:L97`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/frontend/src/pages/Achievements.tsx#L97): `api.get('/users/students')` loads student lists for teacher badge awarding.
    - [`src/frontend/src/pages/Students.tsx:L222`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/frontend/src/pages/Students.tsx#L222): `api.post('/users/students', ...)` allows teachers to create and automatically bind student accounts.
    - [`src/frontend/src/pages/Students.tsx:L253`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/frontend/src/pages/Students.tsx#L253) & [`UserManagement.tsx:L170`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/frontend/src/pages/UserManagement.tsx#L170): `api.post('/users/reset-password', ...)` allows teachers to reset passwords for their assigned students without knowing the student's old password.
  - The authorization contracts differ fundamentally:
    - `POST /api/auth/admin/create-user` is restricted to `admin` only (`get_current_admin_user`).
    - `POST /api/users/students` allows `teacher` users to roster new students directly.
    - `POST /api/auth/change-password` requires the user's existing password; `POST /api/users/reset-password` allows a teacher/admin to override a forgotten password.
  - Deleting `users.py` and `user_service.py` would cause immediate breakage in student rostering and password reset across the frontend.
* **Verdict**: **Falsified**. V1 recommendation to delete `users.py` was dangerous and incorrect. `users.py` serves teacher/student roster domain workflows.

---

### EV-05: Board Create Route Placement
* **File Target**: [`src/api/routers/board_ai.py:L107-170`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/routers/board_ai.py#L107-L170)
* **V1 Claim**: "Move `POST /api/boards` from `board_ai.py` to `boards.py` for REST consistency."
* **Evidence FOR (Hypothesis)**:
  - `boards.py` handles `GET /api/boards`, `GET /api/boards/{id}`, `PUT /api/boards/{id}`, `DELETE /api/boards/{id}`.
* **Evidence AGAINST (Falsification)**:
  - `POST /api/boards` in `board_ai.py` supports `generate_with_ai=True`, directly invoking `BoardGenerationService`, `get_llm_provider`, and AI suggestion generators.
  - Moving `create_board` into `boards.py` would force `boards.py` to import and depend on AI provider dependencies, violating single-responsibility boundaries and increasing module coupling.
  - Both routers are included at `prefix="/api/boards"` in `main.py`, so the public HTTP REST contract is already unified and seamless for frontend clients.
* **Verdict**: **Rejected**. Moving the function provides zero user value while increasing coupling between basic CRUD and AI generation subsystems.

---

### EV-06: Duplicate LM Studio Model Listing Endpoint
* **File Target**: [`src/api/routers/providers.py:L518-544`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/routers/providers.py#L518-L544) vs [`src/api/routers/settings.py:L449-470`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/routers/settings.py#L449-L470)
* **Evidence FOR (Hypothesis)**:
  - Both define endpoints to list available LM Studio models.
  - `src/frontend/src/store/settingsStore.ts:L131` explicitly calls `fetchModelList('/settings/ai/models/lmstudio', ...)` alongside `/settings/ai/models/ollama`, `/settings/ai/models/openrouter`, `/settings/ai/models/groq`.
  - `GET /api/providers/ai/models/lmstudio` has 0 references in `src/frontend/src/` and is referenced only in test assertions targeting that redundant endpoint.
* **Evidence AGAINST (Falsification)**:
  - None. It is an unconsumed duplicate endpoint.
* **Verdict**: **Confirmed Redundant**. Safe to remove in future cleanup with test updates.

---

### EV-07: `nullcontext(db)` Refactoring Artifact in `achievements.py`
* **File Target**: [`src/api/routers/achievements.py:L103, 161, 222, 386`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/routers/achievements.py#L103)
* **Evidence FOR (Hypothesis)**:
  - Git history (`git log -S "nullcontext(db)" -p`) proves that `with get_session() as session:` was converted to `with nullcontext(db) as session:` to avoid re-indenting blocks when `db: Session = Depends(get_db)` was introduced.
  - `nullcontext(db)` performs no transaction management or resource closing.
* **Evidence AGAINST (Falsification)**:
  - It does no active harm at runtime, but introduces unnecessary indentation and confusion regarding session lifecycle.
* **Verdict**: **Confirmed Code Smell**. Direct usage of `db` simplifies the module.

---

### EV-08: Dead Legacy Method `_get_hardcoded_default`
* **File Target**: [`src/aac_app/services/template_manager.py:L58-85`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/aac_app/services/template_manager.py#L58-L85)
* **Evidence FOR (Hypothesis)**:
  - Grep search confirms 0 callers across `src/`, `tests/`, `scripts/`.
  - Default companion template is loaded from `src/aac_app/config/companion_templates/default.yaml`.
* **Evidence AGAINST (Falsification)**:
  - None.
* **Verdict**: **Confirmed Dead Code**.

---

### EV-09: Legacy Usage Log Endpoint `POST /api/analytics/log`
* **File Target**: [`src/api/routers/analytics.py:L313-345`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/routers/analytics.py#L313-L345)
* **Evidence FOR (Hypothesis)**:
  - All frontend components call `POST /api/analytics/usage` (`DraggableSymbol.tsx`, `Communication.tsx`, `useSymbolHunt.ts`).
  - `/api/analytics/log` was a legacy compatibility alias.
* **Evidence AGAINST (Falsification)**:
  - None for internal web client.
* **Verdict**: **Confirmed Deprecated Shim**.

---

### EV-10: Provider `close()` Aliases
* **File Target**: [`src/aac_app/providers/ollama_provider.py:L190`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/aac_app/providers/ollama_provider.py#L190), [`openrouter_provider.py:L178`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/aac_app/providers/openrouter_provider.py#L178)
* **Evidence FOR (Hypothesis)**:
  - `BaseLLMProvider` standardizes on `close_sync()` and `close_async()`.
  - 0 internal callers call `.close()`.
* **Evidence AGAINST (Falsification)**:
  - None.
* **Verdict**: **Confirmed Dead Aliases**.

---

### EV-11: Smartbar Intent Closures in `analytics.py`
* **File Target**: [`src/api/routers/analytics.py:L175-265`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/routers/analytics.py#L175-L265)
* **V1 Claim**: "Refactor Smartbar intent closures (`build_query`, `apply_language_filter`, `format_results`) to eliminate heap allocation overhead."
* **Evidence FOR (Hypothesis)**:
  - Helper functions are declared inside the request handler.
* **Evidence AGAINST (Falsification)**:
  - Python function definition overhead is $<1 \mu\text{s}$.
  - The dominant latency comes from SQLite queries and translation lookups ($5\text{--}50\text{ ms}$, i.e., $50,000 \mu\text{s}$).
  - Refactoring purely for closure allocation is a classic micro-optimization with zero user impact.
* **Verdict**: **Rejected**. Not justified by measurable performance.

---

### EV-12: Groq Provider Union Type Annotations
* **File Target**: [`src/aac_app/services/board_generation_service.py:L61`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/aac_app/services/board_generation_service.py#L61)
* **V1 Claim**: "Add `GroqProvider` to the `__init__` union type annotation."
* **Evidence FOR (Hypothesis)**:
  - `llm_provider: OllamaProvider | OpenRouterProvider | LMStudioProvider` omits `GroqProvider`, even though line 64 tests `if isinstance(llm_provider, GroqProvider)`.
  - All 4 providers inherit from `BaseLLMProvider`.
* **Evidence AGAINST (Falsification)**:
  - Python does not enforce typing at runtime, so execution succeeds regardless.
* **Verdict**: **Confirmed Minor Typing Polish**. Type annotation can be broadened to `BaseLLMProvider`.

---

### EV-13: NEW DISCOVERY — Teacher RBAC Inconsistency in Learning Sessions
* **File Target**: [`src/api/routers/learning.py:L41, L322`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/routers/learning.py#L41) & [`src/api/deps/access.py:L38`](file:///home/wishmaster/Github/AAC_ASSISTANT/src/api/deps/access.py#L38)
* **Discovery Description**:
  - In `src/api/routers/learning.py:L41` (`start_session`):
    ```python
    if user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail=get_text(current_user, "errors.unauthorizedUser"))
    ```
  - In `src/api/routers/learning.py:L322` (`get_history`):
    ```python
    if user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail=get_text(current_user, "errors.unauthorized"))
    ```
  - In `src/api/deps/access.py:L38` (`get_learning_session_or_404`):
    ```python
    if session.user_id != current_user.id and current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail=message("errors.unauthorized"))
    ```
* **Evidence of Defect**:
  - Throughout all other routers (`achievements.py`, `boards.py`, `guardian_profiles.py`, `auth_users.py`), teachers have legitimate authorization to manage and inspect their assigned roster students via `verify_student_access(student_id, current_user, db)`.
  - In `src/frontend/src/store/dashboardStore.ts:L46`, the dashboard attempts to load a student's learning history: `api.get('/learning/history/${userId}')`.
  - When a logged-in `teacher` views an assigned student's learning progress, the endpoint unconditionally raises `403 Forbidden` because `current_user.user_type != "admin"` and `user_id != current_user.id`.
* **Frontend Impact**: Teachers are unable to view learning session histories or launch guided sessions for their rostered students from the teacher dashboard.
* **Minimal Remediation**:
  - In `src/api/deps/access.py:get_learning_session_or_404`: Use `verify_student_access(session.user_id, current_user, db)`.
  - In `src/api/routers/learning.py:start_session` and `get_history`: Replace inline check with `verify_student_access(user_id, current_user, db)`.
* **Severity**: **Medium** (Correctness / Functional RBAC Defect).
* **Confidence**: **Very High**.
