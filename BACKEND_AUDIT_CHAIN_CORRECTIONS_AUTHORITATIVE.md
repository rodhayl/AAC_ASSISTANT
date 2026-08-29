# Authoritative Audit-Chain Corrections (Consolidated)

**Purpose**: Single authoritative document consolidating every correction made to the previous backend audit chain during the evidence challenge and its follow-up verification passes. This document supersedes the incorrect rows/figures in the original audit artifacts and is the reference a reviewer should trust.

**Provenance**: Consolidates the four corrected artifacts:
- `BACKEND_EVIDENCE_CHALLENGE_AUTH_MATRIX_CORRECTED.md`
- `BACKEND_EVIDENCE_CHALLENGE_DESTRUCTIVE_INVENTORY.md`
- `BACKEND_EVIDENCE_CHALLENGE_TEST_MAPPING_CORRECTED.md`
- `BACKEND_EVIDENCE_CHALLENGE_SYMBOL_SIDE_EFFECTS_CORRECTED.md`

plus the count/claim corrections from:
- `BACKEND_EVIDENCE_CHALLENGE_COUNTS.md`, `BACKEND_EVIDENCE_CHALLENGE_RAW_INVENTORY.md`, `BACKEND_EVIDENCE_CHALLENGE_CLAIMS.md`, `BACKEND_EVIDENCE_CHALLENGE_FINAL.md`, `BACKEND_VERIFIER_PRIOR_MUTATION_DISCLOSURE.md`

and the sub-claims / totals verifications from:
- `BACKEND_EVIDENCE_CHALLENGE_V3_SUBCLAIMS.md` (exception breakdown 84/38/20, FS 68, external 44)
- `BACKEND_EVIDENCE_CHALLENGE_V3_TOTALS.md` (module state 16, flows 14, destructive 52)

**Method**: Every correction below was independently re-derived from current source (full handler reads, AST scans, live FastAPI route introspection, import-graph analysis). The later no-log remediation is explicitly recorded below as an implementation follow-up; it modified nine backend handlers and added focused regression tests for the two highest-risk paths.

---

## 1. Master Correction Register

| # | Area | Prior claim (artifact) | Corrected fact | Verdict on prior claim |
| :--- | :--- | :--- | :--- | :--- |
| C-01 | Auth matrix | Guardian-profiles routes "Anonymous: YES" (V3 matrix) | All 11 routes require teacher/admin (`get_current_teacher_or_admin`); student-scoped routes require roster; delete is admin-only | **WRONG** |
| C-02 | Auth matrix | users.py 4 mutating routes "Student Self: YES" (V3 matrix) | Students get 403 on create-student, assign, unassign, reset-password | **WRONG** |
| C-03 | Auth matrix | Achievement write routes "Student Self: YES" (V3 matrix) | 9 of 13 rows wrong; teacher/admin-only with creator-ownership + roster constraints | **WRONG** |
| C-04 | Routes | 126 operations / 67 paths (V3 Proof §7) | 127 operations (126 HTTP + WS collab); 103 registered / 100 normalized paths | **CONTRADICTED** |
| C-05 | Routes | `GET/POST /api/learning-modes` without trailing slash (V3 route inventory) | Actual registration is `/api/learning-modes/` only | **STALE** |
| C-06 | Mutations | 231 sites / 14 flows (V3 Proof §9) | 231-site ledger **confirmed exact and set-identical**; 14-flow table **partial** — 3/14 entry points wrong (FLOW-08/09 symbols paths → `/api/boards/symbols/...`, FLOW-13 PUT not POST), ≥73 sites (31.6%) in flows absent from the table | **VERIFIED (ledger) / PARTIAL (flows)** |
| C-07 | Destructive ops | "5 operations" (Stage B) / "6 flows" (V3 Proof) / "16+1" (final ledger) / "52 sites" | Authoritative: **16 API operations + 1 startup repair flow** (member-listed); site-level accounting = **58 ledger sites** (delete_user cascade = 30 alone; corrects the earlier ≈46 estimate); "52 sites" not reproducible | **INCONSISTENT → CORRECTED** |
| C-08 | Test mappings | `tests/test_<basename>.py` for all 104 files (V3 file inventory) | Fabricated; only 1/104 coincidentally exists. Real mapping: 98 test modules cover all 104 files | **FALSE** |
| C-09 | Symbol side-effects | `import_data`, `log_symbol_usage_legacy` "Pure / Read"; `remove_owned_upload` "DB Mutation" (V3 symbol inventory) | All three mislabeled; systemic: 31 false-pure + 22 false-DB-mutation rows (53/777, 6.8%) | **WRONG** |
| C-10 | Module state | 16 module mutable-state sites (V3 Proof §19) | **16 = exactly the 15 threading locks + 1 semaphore** (reproducible under that rule); but V3's text claims "events, provider singletons" which are NOT in the 16 — full mutable universe is 38–46 sites (+9 containers, +14 singletons/engines, +8 scalars) | **MATCHES (narrow rule) / MISDESCRIBED (text)** |
| C-11 | Exceptions | 142 broad handlers (V3 Proof §17) | **Confirmed exact** (AST scan) | **VERIFIED** |
| C-12 | Files/symbols | 104 files / 777 symbols (V3 Proof §5-6) | **Confirmed exact** | **VERIFIED** |
| C-13 | Prior verifier | "Zero Production Code Changes" + "Fixed missing logSymbolFailed" (final verification) | Unauthorized production change to `analytics.py:332-337`; key existed at HEAD and the reference resolved fine — **but** concurrent locale cleanup removed `logFailed`, orphaning the reference; the fix migrated it to the surviving `logSymbolFailed`. Dispositions (2026-08-28): `analytics.py` **KEEP** (revert re-breaks error detail); `test_analytics_api.py` comment removal **REVERTED** (gratuitous removal of an accurate comment — file restored to HEAD, 15 tests still pass); `test_learning_routes_coverage.py` RBAC test **KEPT** (correct, passes, only regression lock for assigned/unassigned teacher boundary). See `BACKEND_VERIFIER_PRIOR_MUTATION_DISCLOSURE.md` §3-4 | **CONTRADICTED (as worded) / CORRECT REPAIR (as executed)** |
| C-14 | Exception breakdown | "84 route-level error boundaries" (V3 Proof §17) | Only **17** of 142 broad handlers raise `HTTPException`; 84 = residual (142−38−20) mislabeled. "38 provider/transcription" ≈ 40 by strict rule; "20 rollback/cleanup" matches. The original "logging on all error paths" claim was contradicted by 24 no-log handlers; all 9 handlers identified as genuine silent-swallow risks were subsequently instrumented and regression-tested (see `BACKEND_NO_LOG_HANDLERS_AUDIT.md` §5). | **COUNT NOT REPRODUCIBLE / REMEDIATION COMPLETE** |
| C-15 | Filesystem I/O | "68 Sites" (V3 Proof §1, §38) | Curated universe = **96 sites** (41 write/delete, 55 read/metadata), full member list; no V3 member list and no clean exclusion rule reproduces 68 | **NOT REPRODUCIBLE** |
| C-16 | External I/O | "44 Sites" (V3 Proof §1, §38) | Curated universe = **25 core / 38 extended** sites, full member list; 44 only reachable via undocumented inherited-sites counting (Groq/LMStudio subclass OpenRouter and perform zero own calls) | **NOT REPRODUCIBLE** |

---

## 2. Corrected Authorization Matrix (31 rows re-traced)

**Scope**: `guardian_profiles.py` (11), `users.py` (7), `achievements.py` (13 incl. 2 trailing-slash dups). All other routers were verified correct in the challenge (learning, boards, symbols, notifications, providers, settings, learning_modes, auth, auth_users, auth_preferences, admin, arasaac, export_import, config).

Legend: StSelf = authenticated student (own resource); AsgT = teacher with roster link; UnasgT = teacher without; Admin = administrator. "NO" = 403/404.

### 2.1 Guardian Profiles — 11/11 V3 rows WRONG

All routes use `get_current_teacher_or_admin` (`guardian_profiles.py:34-43`); student-scoped routes add `verify_student_access` (`auth.py:155-200`); delete is admin-only.

| Route | Anon | StSelf | AsgT | UnasgT | Admin | Enforcement (file:line) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| GET `/templates` | NO | NO | YES | YES | YES | dep @52 |
| GET `/templates/{name}` | NO | NO | YES | YES | YES | dep @66 |
| POST `/templates/{name}/preview` | NO | NO | YES | YES | YES | dep @96 |
| GET `/students` | NO | NO | YES (assigned only @136-139) | NO | YES | dep @128 |
| GET `/students/{id}` | NO | NO | YES | NO | YES | dep @155 + verify @164 |
| POST `/students/{id}` | NO | NO | YES | NO | YES | dep @184 + verify @192 |
| PUT `/students/{id}` | NO | NO | YES | NO | YES | dep @270 + verify @279 |
| DELETE `/students/{id}` | NO | NO | **NO** (403 even for assigned teachers) | NO | YES | dep @353 + admin-only @362 + verify @368 |
| GET `/students/{id}/history` | NO | NO | YES | NO | YES | dep @403 + verify @411 |
| GET `/students/{id}/effective-profile` | NO | NO | YES | NO | YES | dep @424 + verify @433 |
| GET `/students/{id}/system-prompt` | NO | NO | YES | NO | YES | dep @446 + verify @455 |

### 2.2 Users — 4/7 V3 rows WRONG

| Route | Anon | StSelf | AsgT | UnasgT | Admin | Enforcement (file:line) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| GET `/me` | NO | YES | YES | YES | YES | dep @27 |
| PUT `/me` | NO | YES | YES | YES | YES | dep @35 |
| GET `/students` | NO | YES (returns `[self]` @63-65) | YES (assigned only) | NO | YES | dep @50 + branches @54-66 |
| POST `/students` | NO | **NO** (403 @76-84) | YES (auto-assigns self @96-101) | YES | YES | dep @72 + 403 @76 |
| POST `/assign-student` | NO | **NO** (403 @130-134) | YES (self only @139-146) | YES | YES | dep @126 + 403 @130 |
| DELETE `/assign-student/{sid}/{tid}` | NO | **NO** (403 @193-197) | YES (own tid @199-206) | YES | YES | dep @189 + 403 @193 |
| POST `/reset-password` | NO | **NO** (403 @236-240) | YES (rostered @277-289) | NO | YES (except self @264-269) | dep @232 + 403 @236 |

### 2.3 Achievements — 9/13 V3 rows WRONG

| Route | Anon | StSelf | AsgT | UnasgT | Admin | Enforcement (file:line) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| GET `/` (+ `/` dup) | NO | **NO** (403 @92-95) | YES | YES | YES | dep @88 + 403 @92 |
| POST `/` (+ `/` dup) | NO | **NO** (403 @137-140) | YES (target rostered @154) | YES | YES | dep @133 + 403 @137 |
| GET `/categories` | NO | **NO** (403 @44-47) | YES | YES | YES | dep @41 + 403 @44 |
| GET `/criteria-types` | NO | **NO** (403 @62-65) | YES | YES | YES | dep @59 + 403 @62 |
| GET `/leaderboard` | NO | YES | YES | YES | YES | dep @509; no role restriction |
| GET `/user/{uid}` | NO | YES (self @452) | YES | NO | YES | dep @447 + self-or-verify @452 |
| POST `/user/{uid}/check` | NO | YES (self @470) | YES | NO | YES | dep @465 + self-or-verify @470 |
| GET `/user/{uid}/points` | NO | YES (self @496) | YES | NO | YES | dep @491 + self-or-verify @496 |
| PUT `/{aid}` | NO | **NO** (403 @211-214) | YES (own creations @232) | YES | YES (incl. system) | dep @207 + 403 @211 + owner @232 |
| DELETE `/{aid}` | NO | **NO** (403 @313-316) | YES (own creations @343) | YES | YES (except system @334) | dep @309 + 403 @313 + system-block @334 |
| POST `/{aid}/award` | NO | **NO** (403 @375-378) | YES (rostered @395) | NO | YES | dep @371 + 403 @375 + verify @395 |

**Totals: 24 of 31 rows corrected; V3 wrong on 24 of 126 overall** (all other routers verified correct).

---

## 3. Authoritative Destructive-Operation Inventory (16 + 1)

Reconciles the chain's inconsistent **5 / 6 / 16+1** figures. They are nested subsets with undocumented inclusion rules; the authoritative unit is the operation.

### Category A — DELETE endpoints (10)
| # | Route | Handler | What is destroyed | Auth |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `DELETE /api/auth/users/{user_id}` | `auth_users.delete_user` (543-756) | User + 12 dependent tables; commit @755 | Admin; last-admin guard @567 |
| 2 | `DELETE /api/boards/{board_id}` | `boards.delete_board` (194-217) | Board + cascades; commit @216 | Owner/admin |
| 3 | `DELETE /api/boards/symbols/{symbol_id}` | `symbols.delete_symbol` (409-429) | Symbol + joins + image file (post-commit @429) | Staff |
| 4 | `DELETE /api/boards/{bid}/symbols/{sid}` | `symbols.remove_symbol_from_board` (627-638) | BoardSymbol placement; commit @637 | Owner/admin/rostered teacher |
| 5 | `DELETE /api/boards/{bid}/assign/{sid}` | `board_assignments.unassign_board_from_student` (102-141) | BoardAssignment; commit @140 | Owner/admin/rostered teacher |
| 6 | `DELETE /api/users/assign-student/{sid}/{tid}` | `users.unassign_student` (185-225) | StudentTeacher row; commit @224 | Admin; teacher own tid only |
| 7 | `DELETE /api/achievements/{aid}` | `achievements.delete_achievement` (306-362) | Achievement + UserAchievement bulk; commit @359 | Teacher (own)/admin; system undeletable |
| 8 | `DELETE /api/learning-modes/{mode_id}` | `learning_modes.delete_learning_mode` (236-267) | LearningMode; commit @266 | System: admin; custom: creator |
| 9 | `DELETE /api/notifications/{nid}` | `notifications.delete_notification` (253-290) | Notification; commit @289 | Owner/admin |
| 10 | `DELETE /api/guardian-profiles/students/{sid}` | `guardian_profiles.delete_student_profile` (350-390) | **Soft-delete** (audit retained) | **Admin only** @362 |

### Category B — Replace / overwrite / reset (6)
| # | Route | Handler | What is replaced/reset | Auth |
| :--- | :--- | :--- | :--- | :--- |
| 11 | `POST /api/boards/symbols/{sid}/image` | `symbols.update_symbol_image` (381-402) | Image file; commit-fail unlink @396; old unlink @402 | Staff |
| 12 | `POST /api/users/reset-password` | `users.reset_user_password` (229-315) | Password + `security_version` (revokes sessions) | Admin (not self); teacher rostered |
| 13 | `POST /api/auth/change-password` | `auth_users.change_password` (350-~420) | Password + `security_version` | Authenticated self |
| 14 | `POST /api/data/import` | `export_import.import_data` (767-857) | Bulk replace/upsert (boards, symbols, achievements, sessions); atomic commit @855 | Owner/admin |
| 15 | `POST /api/admin/reset-db` | `admin.reset_database` (14-57) | **Entire DB** (drop_all + create_all + reseed) | Admin + `ALLOW_DB_RESET` + production block |
| 16 | `POST /api/auth/logout` | `auth.logout` (353-378) | Session invalidation (all tokens) | Bearer (best-effort) |

### Category C — Startup repair flow (1)
| # | Flow | Location | What it does |
| :--- | :--- | :--- | :--- |
| 17 | `schema.ensure()` repair | `schema.py:434`; FK rebuilds @210-330; label dedup; `seed.py:473` | Destructive table rebuilds + data cleanup per boot; idempotent |

**Key corrections**: V3's "6" omits **reset-db** (the most destructive endpoint); "5" omits import too; the "52 sites" figure is not reproducible (its composition was never documented; schema.py rebuilds are absent from V3's 231-site ledger).

---

## 4. Corrected Test-File Mapping (104 files → 98 real test modules)

**V3's `tests/test_<basename>.py` names are fabricated** — they match reality for exactly 1 of 104 files (`test_guardian_profiles.py` by coincidence). The real repository has 98 test modules (101 files minus `conftest.py`, `auth_helpers.py`, `__init__.py`).

### Coverage classes
| Class | Files | Evidence |
| :--- | ---: | :--- |
| Direct module import | 55 | `(import\|from) <module>` in ≥1 test |
| Package import (models) | 13 | `from src.aac_app.models import ...` in 64 tests |
| App-level + dedicated domain tests | 36 | exercised via `src.api.main`; dedicated files exist for every router |
| **Total covered** | **104** | **no production file uncovered** |

### Representative corrected mappings (full table in `BACKEND_EVIDENCE_CHALLENGE_TEST_MAPPING_CORRECTED.md`)
| Production file | V3 claimed | Real test file(s) |
| :--- | :--- | :--- |
| `learning/common.py` | `test_common.py` (doesn't exist) | `test_learning_common_helpers.py`, `test_response_processing_helpers.py` |
| `learning/history.py` | `test_history.py` (doesn't exist) | `test_learning_persistence.py` |
| `scripts/account_admin.py` | `test_account_admin.py` (doesn't exist) | `test_operator_credential_revocation.py` |
| `routers/analytics.py` | `test_analytics.py` (doesn't exist) | `test_analytics_api.py` |
| `routers/boards.py` | `test_boards.py` (doesn't exist) | `test_boards_router_split.py`, `test_board_ai_routes.py`, `test_boards_list_symbols_and_achievement_routes.py` |
| `routers/auth_users.py` | `test_auth_users.py` (doesn't exist) | `test_users_routes_coverage.py`, `test_rbac.py`, `test_admin_user_management.py` |
| `services/board_generation_service.py` | `test_board_generation_service.py` (doesn't exist) | `test_board_generation_service_unit.py` |
| `providers/groq_provider.py` | `test_groq_provider.py` — **exists** | `test_groq_provider.py`, `test_production_groq_selection.py` |

Weakest links (still genuinely tested): `openrouter_provider.py` → `test_llm_behavior_settings.py`; `vector_utils.py` → `test_e2e_gui_coverage.py`.

---

## 5. Corrected Symbol Side-Effect Classifications (53+ of 777 rows)

The V3 "Side Effects" column was **canned boilerplate assigned by symbol kind**, not derived from symbol bodies. A scan of all 777 rows against the 231-site mutation ledger found:

### 5.1 The three named symbols
| Symbol | V3 label | Correct label | Evidence |
| :--- | :--- | :--- | :--- |
| `import_data` (SYM-0586) | Pure / Read | **DB WRITE (multi-table) + atomic commit** | export_import.py:390-393,473,502-503,600,855 |
| `log_symbol_usage_legacy` (SYM-0508) | Pure / Read | **DB WRITE (SymbolUsageLog) + commit** | analytics.py:36-65, commit @64; symbol_analytics.py:180-181 |
| `remove_owned_upload` (SYM-0483) | Route Handler / DB Mutation | **FILESYSTEM DELETE (best-effort)** | file_uploads.py:177-195, unlink @192 |

### 5.2 Systemic: 31 false-"Pure" rows (mutation site inside own body)
Key examples: `get_session` (db.py:128-130 — transaction boundary), `get_db` (deps/db.py:15,17), `register`, `logout`, `initial_admin_setup`, `change_password`, `award_achievement`, `check_achievements`, `_log_usage_request`, `import_arasaac_symbol`, `apply_ai_suggestion`, `assign_board_to_student`, `unassign_board_from_student`, `_import_assigned_boards`, `_import_achievements`, `_import_learning_history`, `import_data`, `submit_voice_answer` (os.remove), `notifications_stream`, `mark_notification_read`, `mark_all_notifications_read`, `set_settings`, `reorder_symbols`, `add_symbol_to_board`, `remove_symbol_from_board`, `assign_student`, `unassign_student`, `_cleanup_old_logs` (os.unlink), `_mark_imported`, `import_arasaac_library`, `_ensure_bootstrap_admin`.

### 5.3 Systemic: 22 false-"DB Mutation" rows (no DB call)
| Category | Symbols |
| :--- | :--- |
| Pure token generation | `create_access_token`, `create_refresh_token` |
| Pure file read/validation | `read_upload_bytes`, `read_image_upload` |
| Module-state resets (no DB) | `reset_providers`, `reset_providers_async`, `reset_llm_providers`, `reset_speech_provider`, `reset_local_tts_provider`, `_detach_vector_store_for_reset`, `_defer_vector_store_for_reset`, `_start_deferred_vector_store_close`, `_new_startup_state`, `get_startup_state` |
| Pure hash verification | `verify_password_and_update` |
| Vector-store delete (not DB) | `vector_utils.delete_symbol`, `vector_utils._delete_symbol` |
| Pure validation | `validate_preference_updates` |
| Launcher/other | `_startup_log_directories`, `_write_startup_error`, `_start_shutdown_watcher`, `create_session_factory`, `remove_owned_upload` |

### 5.4 Correct despite no regex match (5)
`reset_database` (DDL drop_all/create_all), `create_tables` (DDL), `start_session` (delegates to service commit), `_update_single_symbol` (ORM dirty-tracking write), `create_engine_instance` (borderline — DB infrastructure).

**Net: at least 53/777 rows (6.8%) mislabeled.**

---

## 6. Sub-Claims Verification (exception breakdown, FS I/O, external I/O, module state, flows, destructive sites)

Consolidates `BACKEND_EVIDENCE_CHALLENGE_V3_SUBCLAIMS.md` and `BACKEND_EVIDENCE_CHALLENGE_V3_TOTALS.md`. V3 provided **no member lists** for any of these claims; every independent count below is member-listed in the source artifacts.

### 6.1 Exception classification 84/38/20 → **17 / 40 / 20 (+65 residual)**

Total broad handlers **142 — exact** (AST scan). The "84" bucket is an arithmetic residual (142 − 38 − 20), not an independently classified set:

| Bucket | V3 | Independent | Members |
| :--- | ---: | ---: | :--- |
| Route-level boundaries raising `HTTPException` | 84 | **17** | analytics.py:81,117,300,332,361,397; symbols.py:291; arasaac.py:158; settings.py:329,381,433,478; admin.py:52; board_ai.py:265,380; boards.py:81; providers.py:421 |
| Provider/transcription fallbacks | 38 | **40** (strict rule) | 12 provider handlers + arasaac 3 + backfill 3 + questions 2 + responses 3 + board_gen 1 + runtime_translation 2 + vector store 14 (see artifact §1.4) |
| Rollback / cleanup | 20 | **20** | 8 rollback + 11 provider/store cleanup + 1 temp-file (artifact §1.5) |
| Residual (log-and-fallback, startup, WS, re-raise) | — | **65** | main.py 7, deps/providers.py 6, collab.py 3, achievement_system 9, learning services 11, etc. (artifact §1.6) |

**Original logging claim contradicted; remediation recorded**: the challenge identified 24 of 142 handlers (17%) with no logger call, including 9 genuine silent-swallow risks. Those 9 sites were instrumented without changing fallback/re-raise behavior, and the P1 achievement and P2 vector-store paths now have focused log-emission regression tests. The full remediation record and test evidence are in `BACKEND_NO_LOG_HANDLERS_AUDIT.md` §5.

### 6.2 Filesystem I/O 68 → **96 curated sites (41 write/delete + 55 read/metadata)**

Raw AST scan: 133 candidates → **37 false positives** curated out (13 `.absolute()` pure path math, 12 `str/datetime.replace` — **zero `Path.replace` exist in the codebase** — 4 dict `.copy()`, 2 list `.remove()`, 1 `logger.remove()`, 1 `webbrowser.open`, 1 `Image.open(BytesIO)`, 3 `Path.home()`). No V3 member list and no clean exclusion rule reproduces 68. Full 96-site member list in artifact §2.3.

### 6.3 External I/O 44 → **25 core / 38 extended sites**

| Universe | Count | Members |
| :--- | ---: | :--- |
| Core (outbound calls + clients + subprocess + engines) | **25** | 14 outbound HTTP calls (launcher 1, tts download 1, ollama 3, openrouter 3, arasaac 5, runtime_translation 1) + 7 client instantiations + 2 `subprocess.run` (providers.py:398,492) + 2 engine inferences (Whisper transcribe, Kokoro synthesize) |
| Extended (+cleanup/resolution/endpoints) | **38** | +5 client closes (base_provider 4, arasaac 1) +5 `shutil.which` +1 `webbrowser.open` +1 WS endpoint +1 SSE endpoint |

44 is reachable **only** by counting Groq/LMStudio's inherited OpenRouter call sites per subclass (+6) — both subclass `OpenRouterProvider` and perform **zero** own network calls (`groq_provider.py`, `lmstudio_provider.py` have no client code). Undocumented convention.

### 6.4 Module mutable state 16 → **16 sync primitives (exact) / 38–46 full universe**

- **16 = exactly the 15 threading locks + 1 semaphore** (member-listed: db.py:27, tts 192/418, vector_store 47/51, notification_events 80, prediction 59, runtime_translation 22/30, symbol_analytics 54, deps/providers 61/68/74, deps/settings 11, routers/providers 43/44). **Reproducible under that rule only.**
- V3's text claims "locks, **events**, **provider singletons**" — **zero** module-level `Event` objects exist, and the 7 provider singletons + `_local_tts_provider` + `faster_whisper` + `_template_manager` + `_guardian_service` + `_engine_instance`/`_session_factory` are **not** in the 16. **The description is wrong.**
- Full mutable universe: +9 containers (`_subscribers`, `_catalog_cache`, `_history_transition_cache`, `_scheduled_tasks`, `_deferred_vector_store_events`, `_speech_release_workers`, `_pending_llm_close_tasks`, `_settings_cache`, `_translation_client_factory`) + 14 singletons/engines + 8 scalars mutated via `global` (`_startup_generation`, `_consecutive_failures`, `_circuit_open_until`, `_available`/`_import_error`/`_import_attempted`, `FASTER_WHISPER_AVAILABLE`/`faster_whisper`, `FASTEMBED_AVAILABLE`).

### 6.5 Logical mutation flows 14 → **count OK; 3/14 entry points wrong; coverage partial**

Live route-table check of FLOW-01…14: **11 exact + 1 slash-variant (FLOW-06 `/api/boards`)** + **3 errors**:

| Flow | V3 entry point | Actual |
| :--- | :--- | :--- |
| FLOW-08 | `POST /api/symbols/{symbol_id}/image` | **`POST /api/boards/symbols/{symbol_id}/image`** (symbols router moved under boards) |
| FLOW-09 | `DELETE /api/symbols/{symbol_id}` | **`DELETE /api/boards/symbols/{symbol_id}`** |
| FLOW-13 | `POST /api/settings/ai` | **`PUT /api/settings/ai`** |

**Completeness**: ≥73 of 231 sites (31.6%) belong to mutation entry points absent from the flow table — seed (15), board_ai (13), achievements CRUD (8), notifications (7), guardian profiles (9), learning_modes (5), board_assignments (4), arasaac (6), preferences/providers (4). "Unreviewed Flows: 0" holds only for the 14 rows.

### 6.6 Destructive sites 52 → **58 ledger sites (16 ops)**

Precise ledger-range count for the 16 destructive operations: **58 sites** — dominated by the **30-site 12-table cascade** inside `delete_user` (auth_users.py:543-756; V3's "Cascades 12 DB tables" compressed it to one row). The 6-flow subset = 41 sites; neither 41 nor 58 equals 52 under any clean rule. **Corrects the earlier ≈46 estimate** in §3 (it undercounted the cascade). Plus schema.py rebuild internals, entirely absent from the 231-site ledger. Full per-op table in `BACKEND_EVIDENCE_CHALLENGE_V3_TOTALS.md` §3.2.

---

## 7. Count Reconciliation Summary

| Metric | V3 claimed | Corrected | Status |
| ------ | ---------: | ---------: | :--- |
| Production files | 104 | 104 | ✅ exact |
| Symbols | 777 | 777 | ✅ exact (labels ✗) |
| FastAPI operations | 126 | **127** (126 HTTP + WS collab) | ✗ corrected |
| Unique paths | 67 | **103 registered / 100 normalized** | ✗ corrected |
| Auth matrix rows | 126 | 127; **24 rows corrected** | ✗ corrected |
| DB mutation sites | 231 | 231 (set-identical) | ✅ exact |
| Logical mutation flows | 14 | 14 (3/14 entry points wrong; ≥73 sites outside table) | ⚠️ partial |
| Destructive ops | 5 / 6 / 16+1 / 52 sites | **16 + 1 (member-listed); 58 ledger sites** | ✗ corrected |
| Broad exception handlers | 142 | 142 | ✅ exact |
| Exception breakdown | 84 / 38 / 20 | **17 / 40 / 20 (+65 residual)**; original logging claim contradicted (24 no-log), **9 at-risk handlers remediated** | ✗ count corrected / remediation recorded |
| Filesystem I/O | 68 | **96 curated** (41 write/delete) | ✗ corrected |
| External I/O | 44 | **25 core / 38 extended** | ✗ corrected |
| Module mutable state | 16 | 16 sync primitives (exact) / 38–46 full universe; text misdescribes | ⚠️ partial |
| Test mappings | 104 (fabricated) | 98 real modules, all 104 covered | ✗ corrected |
| Symbol side-effect labels | boilerplate | 53+ corrected | ✗ corrected |

---

## 8. Impact on Prior Verdicts

| Prior verdict | Status after corrections |
| :--- | :--- |
| V3 denominators (files, symbols, mutations, exceptions) | **STAND** — exactly reproducible |
| All 11 implementation claims (teacher RBAC, provider close, dead-code removals, compatibility routes, typing) | **STAND** — verified in current code |
| Clean-subsystem claims (JWT, SQLite, uploads, providers, packaging, startup) | **STAND** — supported by code |
| V3 auth matrix "100% least-privilege verified" | **CORRECTED** — 24/126 rows wrong; code itself is secure |
| V3 route inventory "126 ops / 67 paths" | **CORRECTED** — 127 ops / 103 paths |
| V3 file inventory test column | **CORRECTED** — fabricated |
| V3 symbol inventory side-effect column | **CORRECTED** — 53+ rows wrong |
| V3 proof "52 destructive sites" | **CORRECTED** — not reproducible; 58 ledger sites for 16 ops |
| V3 exception breakdown "84/38/20" | **CORRECTED** — 17/40/20 + 65 residual; original "logging on all error paths" false (24 no-log). The 9 at-risk handlers were subsequently instrumented and the P1/P2 emissions regression-tested. Targeted RBAC, mutation/destructive, provider, logging, and i18n tests pass. |
| Latent translation default | `get_learning_session_or_404` defaulted `errors.sessionNotFound` to the `common` namespace | Default now uses `pages/learning`; all statically checked backend defaults resolve in both locales, with a namespace regression test | **REMEDIATED / VERIFIED** |
| V3 "68 FS sites" / "44 external I/O sites" | **CORRECTED** — 96 curated FS / 25–38 external; both totals-only, no member lists |
| V3 "16 module mutable objects" description | **CORRECTED** — 16 = locks only; text's "events/provider singletons" wrong; true universe 38–46 |
| V3 14-flow table | **PARTIAL** — 3/14 entry points stale; ≥73 sites in flows absent from table |
| Final verification "Zero Production Code Changes" | **CORRECTED** — unauthorized `analytics.py` change exists |
| Overall evidence reliability | **PRIOR_AUDIT_EVIDENCE_HAS_MATERIAL_GAPS** as a historical assessment. The corrected artifacts supersede the stale claims; functional remediations are separately backed by targeted tests, while documentation-only corrections do not constitute application fixes. |

---

## 9. Verification Evidence (commands used across the consolidation)

- Live route introspection: `uv run python` walking `app.routes` incl. `_IncludedRouter` recursion → 127 ops / 103 paths
- AST scans: classes/functions/methods (777 exact), exception handlers (142 exact), module state (9–21)
- Mutation scan: regex `db|session.(add|commit|flush|delete|execute|rollback)` + file deletes → 231 sites, **set-identical** to V3 ledger (0/0 diffs)
- Import-graph scan: `(^|\s)(import|from)\s+<module>` over 98 test modules → 55 direct + 13 package + 36 app-level
- Symbol scan: 231-site ledger intersected with every symbol row's line range → 31 false-pure / 27 false-DB-mutation (5 correct via delegation/DDL)
- Full handler reads: `guardian_profiles.py`, `users.py`, `achievements.py`, `admin.py`, `auth.py` logout, `learning_modes.py`, `export_import.py:760-857`, `analytics.py:300-359`, `file_uploads.py:175-195`, `jwt_utils.py:60-89`, `providers.py:992-1023`, `auth_service.py:67-96`, `vector_utils.py:205-225`, `auth_helpers.py:109-147`, `symbols.py:488-544`
- Git: `git diff`, `git show HEAD:` for the `logSymbolFailed` attribution
- Sub-claims (V3_SUBCLAIMS/V3_TOTALS): AST scans of 104 files for except clauses (142 broad / 232 any-type, per-handler body classification), FS ops (133 raw → 96 curated), network/subprocess calls (25 core / 38 extended); live route-table walk of `_IncludedRouter.original_router` (+`include_context.prefix`) for FLOW-01…14; ledger-range counting for the 16 destructive handlers (58 sites); threading-primitive AST scan (16 locks/semaphore) + `global`-statement scan (8 scalars)
- No-log remediation: nine identified at-risk handlers instrumented with narrow logging; focused P1/P2 regression tests assert warning/error emission. See `BACKEND_NO_LOG_HANDLERS_AUDIT.md` §5 and the affected tests in `tests/test_response_processing_helpers.py` and `tests/test_local_vector_store_sqlite_vec.py`.
- Translation-default scan: backend helper defaults and statically resolvable calls were checked against both locale trees; the only apparent learning mismatches were false positives caused by the local `pages/learning` wrapper. `get_learning_session_or_404` now defaults to `pages/learning`, with focused regression tests asserting the namespace and required keys. See `BACKEND_TRANSLATION_DEFAULT_SCAN.md`, `tests/test_teacher_student_access.py::test_learning_session_lookup_default_uses_learning_namespace`, and `tests/test_backend_translation_contract.py`.
- Follow-up validation: targeted RBAC/access, mutation/destructive-flow, provider/lifecycle, logging, and i18n tests all passed. These tests verify current behavior; corrected V3 counts, mappings, and classifications remain documentation/evidence corrections rather than code changes.

---

## 10. Post-Audit GUI/E2E Validation & Production Robustness Fix (2026-08-29)

After the audit chain was consolidated, a GUI/E2E validation pass exercised the
production build against a live server and surfaced one genuine production
robustness defect, which was remediated and regression-tested.

### 10.1 Production defect: login/ARASAAC-import SQLite write-lock contention

**Discovery**: during the first authenticated E2E run, the admin login timed out
(20s) while the startup ARASAAC import held the SQLite write lock; a controlled
reproduction on a fresh DB with the import enabled showed 1 of 4 successful
logins stalling the full 30s `busy_timeout` and the import dying with
`sqlite3.OperationalError: database is locked`. The failed-login path committed
inline and never stalled — only the success path did.

**Root cause**: the login success path flushed its writes (lockout reset + audit
INSERT) but deferred the commit to `get_db` teardown, which runs *after* token
generation. The request session therefore held the SQLite RESERVED lock across
token generation; the import's next batch blocked holding SHARED, and the
login's COMMIT needed EXCLUSIVE — a circular wait that only broke when one
side's 30s timeout fired. Empirically proven with a minimal two-connection
SQLAlchemy test.

**Remediation**:
- `src/api/routers/auth.py`: the success path now commits its writes inline
  before issuing tokens (mirroring the failed path), closing the write
  transaction promptly.
- `src/aac_app/services/arasaac_library_import.py`: a transient
  `OperationalError("database is locked")` on a batch commit is retried instead
  of aborting the whole ~17k-row import (no double-counting: the retry re-flushes
  the same batch).

**Regression tests**: `tests/test_login_write_lock_contention.py` (4 tests):
durability of the success-path writes independent of `get_db` teardown, and
import-batch retry without duplication. **Stress verification**: with the import
enabled (`es,en`), 10/10 successful logins completed in ≤0.37s (previously one
took 30.44s) and the import finished 9093/9093 with zero failures.

### 10.2 Full E2E suite (real browser, production build, seeded backend)

Final result: **243 passed** (run twice for stability). Five spec-level defects
were root-caused and fixed (details in `MANUAL_GUI_SMOKE_RESULTS.md`):

1. `AppToaster` sonner `containerAriaLabel="Alerts"` — removed the live-region
   label collision with the Navbar bell (production a11y fix).
2. `SentenceStrip` chips: stable `data-testid="sentence-chip"` (production test
   affordance).
3. `contrast-interactive` symbol-search step made conditional on fully-populated
   boards (spec fix).
4. `llm-integration` Ask AI mock now returns `board_id: 1` (mock fidelity).
5. `voice-mode` persistence clicks the visible `[role="switch"]` instead of the
   hidden mirror input (spec fix).

### 10.3 Complete validation state at consolidation

| Suite | Result |
| :--- | :--- |
| Backend pytest (full, first complete run) | **924 passed** (3m13s) |
| Frontend Vitest (full) | **649 passed** (80 files) |
| Frontend Playwright E2E (full, ×2) | **243 passed** each run |
| TypeScript / ESLint / Vite build | pass; bundles within budget |
| Ruff (`src tests scripts`) / `git diff --check` | pass / clean |

---

## 11. Repository Modification Confirmation

`Production backend modified by the no-log remediation: YES — 9 narrowly scoped logging additions`
`Backend tests modified by the no-log remediation: YES — focused P1/P2 log-emission regression tests`
`Frontend modified by the no-log remediation: NONE`
`Concurrent work reverted/overwritten: NONE`

The i18n remediation modified `src/api/deps/access.py` and added focused regression tests in `tests/test_teacher_student_access.py` and `tests/test_backend_translation_contract.py`; the scan record `BACKEND_TRANSLATION_DEFAULT_SCAN.md` documents that no additional mismatch was confirmed.

Historical disposition remains unchanged: the prior verifier's gratuitous 2-line comment removal in `tests/test_analytics_api.py` was **reverted** (`git checkout -- tests/test_analytics_api.py`), while the pre-existing unauthorized `analytics.py` repair remains disclosed and **KEPT**. The later no-log remediation modified only the nine documented handlers and added tests in `tests/test_response_processing_helpers.py` and `tests/test_local_vector_store_sqlite_vec.py`.

---

## 12. Artifact Index

| Artifact | Content |
| :--- | :--- |
| **THIS DOCUMENT** | Authoritative consolidated corrections (reference) |
| `BACKEND_EVIDENCE_CHALLENGE_AUTH_MATRIX_CORRECTED.md` | Full 31-row corrected matrix with file:line evidence |
| `BACKEND_EVIDENCE_CHALLENGE_DESTRUCTIVE_INVENTORY.md` | Full 16+1 destructive inventory + 5/6/16+1 reconciliation |
| `BACKEND_EVIDENCE_CHALLENGE_TEST_MAPPING_CORRECTED.md` | Full 104-file → real-test mapping |
| `BACKEND_EVIDENCE_CHALLENGE_SYMBOL_SIDE_EFFECTS_CORRECTED.md` | Full 53-row corrected side-effect tables |
| `BACKEND_EVIDENCE_CHALLENGE_COUNTS.md` | V3 vs independent counts + set differences |
| `BACKEND_EVIDENCE_CHALLENGE_V3_SUBCLAIMS.md` | Exception breakdown 84/38/20, FS 68, external 44 — full member lists |
| `BACKEND_EVIDENCE_CHALLENGE_V3_TOTALS.md` | Module state 16, flows 14, destructive 52 — full member lists |
| `BACKEND_NO_LOG_HANDLERS_AUDIT.md` | 24-handler swallow-risk audit and completed 9-site logging remediation; P1/P2 regression evidence |
| `BACKEND_TRANSLATION_DEFAULT_SCAN.md` | Backend translation-helper namespace scan and latent-default disposition |
| `tests/test_teacher_student_access.py` | Regression test for the learning-session default translation namespace |
| `tests/test_backend_translation_contract.py` | Backend translation namespace/key contract tests |
| `tests/test_response_processing_helpers.py` | P1 achievement-update warning regression test |
| `tests/test_local_vector_store_sqlite_vec.py` | P2 vector metadata-load error regression test |
| `BACKEND_EVIDENCE_CHALLENGE_RAW_INVENTORY.md` | Raw members behind every count |
| `BACKEND_EVIDENCE_CHALLENGE_CLAIMS.md` | 28 claim verdicts (16 verified, 6 qualified, 3 partial, 1 contradicted, 1 false) |
| `BACKEND_EVIDENCE_CHALLENGE_FINAL.md` | Final verdict: PRIOR_AUDIT_EVIDENCE_HAS_MATERIAL_GAPS |
| `BACKEND_VERIFIER_PRIOR_MUTATION_DISCLOSURE.md` | Unauthorized `analytics.py` modification disclosure |
| `BACKEND_REMAINING_WORK_CLOSURE.md` | Closed-item register, targeted validation evidence, and scope qualifications |
| `MANUAL_GUI_SMOKE_RESULTS.md` | GUI/E2E validation results: 243 E2E + 649 Vitest passing, spec-fix root causes, backend smoke evidence |
| `tests/test_login_write_lock_contention.py` | Regression tests for the login inline-commit fix and ARASAAC import batch retry |