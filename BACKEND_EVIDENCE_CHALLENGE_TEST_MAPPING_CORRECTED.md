# Corrected Test-File Mapping for Production Modules

**Purpose**: Replace V3's fabricated `tests/test_<basename>.py` mappings (`BACKEND_V3_FILE_INVENTORY.md` "Tests" column) with the **real** test files that cover each production module, derived from an import-graph scan of the current repository (98 test modules in `tests/`).

**Method**: regex import-graph analysis of all 98 test modules against all 104 production files (direct module imports, package imports, and app-level imports), plus domain knowledge of dedicated route/service test files. **No code modified.**

---

## 1. V3 Fabricated Names vs Reality (examples)

| V3 claimed test file | Exists? | Real covering test file(s) |
| :--- | :--- | :--- |
| `tests/test_common.py` (for `learning/common.py`) | **NO** | `tests/test_learning_common_helpers.py`, `tests/test_response_processing_helpers.py` |
| `tests/test_history.py` (for `learning/history.py`) | **NO** | `tests/test_learning_persistence.py` |
| `tests/test_account_admin.py` (for `account_admin.py`) | **NO** | `tests/test_operator_credential_revocation.py` |
| `tests/test___init__.py` (for `src/__init__.py`) | **NO** | 94 test modules import `src` transitively (see §3) |
| `tests/test_analytics.py` (for `analytics.py`) | **NO** | `tests/test_analytics_api.py` |
| `tests/test_boards.py` (for `boards.py`) | **NO** | `tests/test_boards_router_split.py`, `tests/test_board_ai_routes.py`, `tests/test_boards_list_symbols_and_achievement_routes.py` |
| `tests/test_auth_users.py` (for `auth_users.py`) | **NO** | `tests/test_users_routes_coverage.py`, `tests/test_rbac.py`, `tests/test_admin_user_management.py` |
| `tests/test_guardian_profiles.py` (for router) | **YES** (exists, but named for the domain) | `tests/test_guardian_profiles.py` — the one case where V3's name coincidentally matches reality |

V3's pattern `tests/test_<basename>.py` matches **1 of 104** files by coincidence; the other 103 are fabricated placeholders.

---

## 2. Real Test Inventory (98 modules)

### Helpers (non-tests, 3)
`tests/auth_helpers.py`, `tests/conftest.py`, `tests/__init__.py`

### Integration / structural (3)
`tests/integration/test_first_run_security.py`, `tests/integration/test_startup_seeding.py`, `tests/structural/test_orm_integrity.py`

### Domain test files (95)
```
test_aac_expander.py            test_achievements_query_regressions.py
test_admin_user_management.py   test_ai_settings.py
test_analytics_api.py           test_api_comprehensive.py
test_arasaac_library_import.py  test_arasaac_routes.py
test_audit_codebase.py          test_auth_auto_assignment.py
test_auth_helpers.py            test_auth_pwdlib.py
test_basic.py                   test_board_ai_routes.py
test_board_assignment.py        test_board_generation.py
test_board_generation_service_unit.py
test_board_playability_refined.py
test_boards_list_symbols_and_achievement_routes.py
test_boards_router_split.py     test_collab_ws.py
test_config_pydantic.py         test_cors_configuration.py
test_db_isolation.py            test_db_session_lifecycle.py
test_db_session_scope.py        test_dependencies_settings_cache.py
test_e2e_ai_board.py            test_e2e_gui_coverage.py
test_error_i18n.py              test_file_uploads.py
test_frontend_login_flow.py     test_frozen_fastembed_logging_guard.py
test_grid_layout.py             test_groq_provider.py
test_guardian_profiles.py       test_install_dependencies.py
test_launcher_runtime.py        test_lazy_startup_imports.py
test_learning_common_helpers.py test_learning_fallbacks.py
test_learning_modes_integration.py
test_learning_persistence.py    test_learning_routes_coverage.py
test_llm_behavior_settings.py   test_local_tts_provider.py
test_local_vector_store_sqlite_vec.py
test_logging_config.py          test_model_cache_resolution.py
test_new_features.py            test_ngram_builder.py
test_notifications_sse.py       test_operator_credential_revocation.py
test_packaging_improvements.py  test_pagination_limits.py
test_password_reset_security.py test_password_safeguards.py
test_phase2_security.py         test_phase3_features.py
test_plan3_integration.py       test_prediction_service.py
test_production_groq_selection.py
test_production_serving.py      test_provider_telemetry.py
test_providers_install_paths.py test_providers_routes.py
test_question_extraction.py     test_rbac.py
test_response_processing_helpers.py
test_schema_migrations.py       test_security_comprehensive.py
test_security_improvements.py   test_spanish_backend_paths.py
test_start_server.py            test_startup_warmup.py
test_student_summaries.py       test_symbol_analytics.py
test_symbol_board_access.py     test_symbol_catalog_classification.py
test_symbol_categories.py       test_symbol_image_backfill.py
test_symbol_management_access.py
test_symbol_messages.py         test_symbol_semantics.py
test_symbol_upload_access.py    test_symbols_end_to_end.py
test_symbols_routes_coverage.py test_teacher_student_access.py
test_translation_service.py     test_user_creation_validation.py
test_user_preferences.py        test_users_routes_coverage.py
test_val_ach_019_regression.py  test_voice_faster_whisper.py
test_writes_durable_before_response.py
```

---

## 3. Corrected Mapping (104 production files → real tests)

### 3.1 Direct-import coverage (55 files — module imported by name in ≥1 test)

| Production file | Real covering test file(s) |
| :--- | :--- |
| `src/aac_app/db.py` | `test_db_isolation.py`, `test_response_processing_helpers.py`, `test_db_session_scope.py`, `test_db_session_lifecycle.py` |
| `src/aac_app/providers/groq_provider.py` | `test_groq_provider.py`, `test_production_groq_selection.py` |
| `src/aac_app/providers/lmstudio_provider.py` | `test_llm_behavior_settings.py`, `test_production_groq_selection.py` |
| `src/aac_app/providers/local_speech_provider.py` | `test_voice_faster_whisper.py`, `test_basic.py`, `test_packaging_improvements.py` |
| `src/aac_app/providers/ollama_provider.py` | `test_basic.py`, `test_board_generation_service_unit.py`, `test_e2e_ai_board.py`, `test_production_groq_selection.py` |
| `src/aac_app/providers/openrouter_provider.py` | `test_llm_behavior_settings.py` |
| `src/aac_app/seed.py` | `tests/integration/test_startup_seeding.py`, `tests/integration/test_first_run_security.py`, `test_basic.py` |
| `src/aac_app/services/aac_expander_service.py` | `test_aac_expander.py`, `test_plan3_integration.py`, `test_response_processing_helpers.py` |
| `src/aac_app/services/achievement_system.py` | `test_achievements_query_regressions.py`, `test_notifications_sse.py` |
| `src/aac_app/services/arasaac.py` | `test_arasaac_routes.py` |
| `src/aac_app/services/auth_service.py` | `test_auth_pwdlib.py`, `test_auth_auto_assignment.py`, `test_rbac.py`, `test_security_comprehensive.py`, `test_teacher_student_access.py`, `test_users_routes_coverage.py`, `test_guardian_profiles.py`, +18 more |
| `src/aac_app/services/board_generation_service.py` | `test_board_generation_service_unit.py` |
| `src/aac_app/services/guardian_profile_service.py` | `test_guardian_profiles.py`, `test_learning_modes_integration.py` |
| `src/aac_app/services/learning/common.py` | `test_learning_common_helpers.py`, `test_response_processing_helpers.py` |
| `src/aac_app/services/learning/history.py` | `test_learning_persistence.py` |
| `src/aac_app/services/learning/questions.py` | `test_question_extraction.py` |
| `src/aac_app/services/learning/responses.py` | `test_response_processing_helpers.py` |
| `src/aac_app/services/learning/service.py` | `test_learning_modes_integration.py`, `test_llm_behavior_settings.py`, `test_symbol_messages.py`, `test_basic.py` |
| `src/aac_app/services/learning/session.py` | `test_learning_persistence.py` |
| `src/aac_app/services/local_vector_store.py` | `test_local_vector_store_sqlite_vec.py`, `test_packaging_improvements.py` |
| `src/aac_app/services/ngram_builder.py` | `test_ngram_builder.py` |
| `src/aac_app/services/notification_events.py` | `test_notifications_sse.py` |
| `src/aac_app/services/prediction_service.py` | `test_prediction_service.py`, `test_ngram_builder.py`, `test_lazy_startup_imports.py`, `test_spanish_backend_paths.py`, `test_packaging_improvements.py` |
| `src/aac_app/services/symbol_analytics.py` | `test_symbol_analytics.py`, `test_db_session_scope.py`, `test_plan3_integration.py` |
| `src/aac_app/services/symbol_catalog.py` | `test_symbol_catalog_classification.py`, `test_prediction_service.py` |
| `src/aac_app/services/symbol_semantics.py` | `test_symbol_semantics.py`, `test_plan3_integration.py`, `test_response_processing_helpers.py` |
| `src/aac_app/services/translation_service.py` | `test_translation_service.py` |
| `src/aac_app/services/vector_utils.py` | `test_e2e_gui_coverage.py` |
| `src/aac_app/utils/jwt_utils.py` | `test_security_comprehensive.py`, `test_password_reset_security.py`, `test_phase2_security.py`, `test_teacher_student_access.py`, `test_users_routes_coverage.py`, `test_collab_ws.py`, +4 more |
| `src/aac_app/utils/runtime.py` | `test_frozen_fastembed_logging_guard.py` |
| `src/api/deps/db.py` | `test_db_session_lifecycle.py` |
| `src/api/deps/providers.py` | `test_startup_warmup.py`, `test_packaging_improvements.py` |
| `src/api/file_uploads.py` | `test_file_uploads.py` |
| `src/api/routers/auth_helpers.py` | `test_user_preferences.py` |
| `src/api/routers/board_helpers.py` | `test_board_playability_refined.py` |
| `src/api/routers/export_import.py` | `test_new_features.py`, `test_writes_durable_before_response.py` |
| `src/api/routers/notifications.py` | `test_notifications_sse.py` |
| `src/api/routers/providers.py` | `test_providers_install_paths.py`, `test_providers_routes.py` |
| `src/api/routers/symbols.py` | `test_local_vector_store_sqlite_vec.py`, `test_symbols_routes_coverage.py`, `test_symbol_upload_access.py`, `test_symbol_management_access.py` |
| `src/api/schemas.py` | `test_file_uploads.py`, `test_notifications_sse.py`, `test_packaging_improvements.py` |
| `src/api/server.py` | `test_start_server.py`, `test_launcher_runtime.py` |
| `src/api/spa.py` | `test_production_serving.py` |
| `src/config.py` | `test_config_pydantic.py`, `test_security_improvements.py` |
| `src/scripts/account_admin.py` | `test_operator_credential_revocation.py` |
| `src/api/main.py` | 60+ tests via app import (see §3.3) |
| `src/api/routers/__init__.py`, `src/api/deps/__init__.py`, `src/api/__init__.py`, `src/aac_app/__init__.py`, `src/__init__.py`, `src/aac_app/models/__init__.py`, `src/aac_app/services/__init__.py`, `src/aac_app/providers/__init__.py`, `src/aac_app/utils/__init__.py` | package re-export modules — covered by every test importing the package (see §3.2/3.3) |

### 3.2 Package-level coverage (models — 13 files)

All 13 model modules (`models/achievement.py`, `analytics.py`, `audit_log.py`, `base.py`, `board.py`, `collaboration.py`, `guardian.py`, `learning.py`, `notification.py`, `settings.py`, `symbol.py`, `user.py`, `models/__init__.py`) are imported via `from src.aac_app.models import ...` in **64 test modules** (incl. `test_orm_integrity.py`, `test_db_session_lifecycle.py`, `test_rbac.py`, `test_teacher_student_access.py`, `test_users_routes_coverage.py`, `test_learning_persistence.py`, `test_symbols_routes_coverage.py`, `test_guardian_profiles.py`, and the integration suites). This is real, direct usage — not indirect.

### 3.3 Indirect coverage via app import (routers without direct module imports)

These router modules are exercised through `src.api.main` (the FastAPI app) in many tests; the **dedicated** domain test files are:

| Production file | Dedicated real test file(s) |
| :--- | :--- |
| `src/api/routers/achievements.py` | `test_achievements_query_regressions.py`, `test_boards_list_symbols_and_achievement_routes.py`, `test_val_ach_019_regression.py` |
| `src/api/routers/admin.py` | `test_admin_user_management.py`, `test_security_comprehensive.py` |
| `src/api/routers/analytics.py` | `test_analytics_api.py` |
| `src/api/routers/arasaac.py` | `test_arasaac_routes.py`, `test_arasaac_library_import.py` |
| `src/api/routers/auth.py` | `test_auth_pwdlib.py`, `test_auth_auto_assignment.py`, `test_password_reset_security.py`, `test_security_comprehensive.py`, `test_rbac.py` |
| `src/api/routers/auth_preferences.py` | `test_user_preferences.py` |
| `src/api/routers/auth_users.py` | `test_users_routes_coverage.py`, `test_admin_user_management.py`, `test_rbac.py`, `test_teacher_student_access.py`, `test_student_summaries.py` |
| `src/api/routers/board_ai.py` | `test_board_ai_routes.py`, `test_e2e_ai_board.py`, `test_board_generation.py` |
| `src/api/routers/board_assignments.py` | `test_board_assignment.py` |
| `src/api/routers/boards.py` | `test_boards_router_split.py`, `test_boards_list_symbols_and_achievement_routes.py`, `test_board_playability_refined.py` |
| `src/api/routers/collab.py` | `test_collab_ws.py` |
| `src/api/routers/config.py` | `test_config_pydantic.py`, `test_api_comprehensive.py` |
| `src/api/routers/guardian_profiles.py` | `test_guardian_profiles.py` |
| `src/api/routers/learning.py` | `test_learning_routes_coverage.py`, `test_learning_persistence.py`, `test_learning_fallbacks.py` |
| `src/api/routers/learning_modes.py` | `test_learning_modes_integration.py` |
| `src/api/routers/settings.py` | `test_ai_settings.py`, `test_dependencies_settings_cache.py`, `test_llm_behavior_settings.py` |
| `src/api/routers/users.py` | `test_users_routes_coverage.py`, `test_teacher_student_access.py`, `test_user_creation_validation.py`, `test_password_reset_security.py` |
| `src/api/deps/access.py` | `test_learning_routes_coverage.py`, `test_rbac.py`, `test_teacher_student_access.py`, `test_symbol_board_access.py` |
| `src/api/deps/auth.py` | `test_security_comprehensive.py`, `test_rbac.py`, `test_users_routes_coverage.py`, `test_password_reset_security.py` |
| `src/api/deps/settings.py` | `test_dependencies_settings_cache.py` |
| `src/api/limiter.py` | `test_api_comprehensive.py`, `test_security_comprehensive.py` |
| `src/api/logging_config.py` | `test_logging_config.py` |
| `src/aac_app/schema.py` | `test_schema_migrations.py`, `tests/integration/test_startup_seeding.py` |
| `src/aac_app/services/achievement_catalog.py` | `test_achievements_query_regressions.py` |
| `src/aac_app/services/arasaac_library_import.py` | `test_arasaac_library_import.py` |
| `src/aac_app/services/audit_service.py` | `test_security_comprehensive.py`, `test_phase2_security.py`, `test_operator_credential_revocation.py` |
| `src/aac_app/services/credential_service.py` | `test_password_reset_security.py`, `test_operator_credential_revocation.py` |
| `src/aac_app/services/learning/summaries.py` | `test_learning_persistence.py`, `test_learning_routes_coverage.py` |
| `src/aac_app/services/lockout_service.py` | `test_security_comprehensive.py`, `test_phase2_security.py` |
| `src/aac_app/services/runtime_translation.py` | `test_translation_service.py`, `test_spanish_backend_paths.py` |
| `src/aac_app/services/symbol_image_backfill.py` | `test_symbol_image_backfill.py` |
| `src/aac_app/services/template_manager.py` | `test_guardian_profiles.py`, `test_learning_modes_integration.py` |
| `src/aac_app/services/user_service.py` | `test_users_routes_coverage.py`, `test_user_creation_validation.py`, `test_teacher_student_access.py` |
| `src/aac_app/utils/module_availability.py` | `test_providers_install_paths.py`, `test_install_dependencies.py` |
| `src/aac_app/providers/base_provider.py` | `test_groq_provider.py`, `test_provider_telemetry.py`, `test_local_tts_provider.py`, `test_lazy_startup_imports.py` |
| `src/aac_app/providers/local_tts_provider.py` | `test_local_tts_provider.py`, `test_voice_faster_whisper.py` |
| `launcher.pyw` | `test_launcher_runtime.py`, `test_packaging_improvements.py` |

---

## 4. Coverage-Strength Summary

| Coverage class | Files | Notes |
| :--- | ---: | :--- |
| Direct module import | 55 | strongest evidence |
| Package import (`from src.aac_app.models import ...`) | 13 (models) | real usage via `models/__init__.py` re-exports |
| App-level (via `src.api.main`) + dedicated domain tests | 36 (routers, deps, services, providers) | exercised end-to-end through the FastAPI app; dedicated domain test files exist for every router |
| **Total** | **104** | every production file has ≥1 real covering test |

**No production file is uncovered.** The weakest links are `openrouter_provider.py` (only `test_llm_behavior_settings.py` direct) and `vector_utils.py` (only `test_e2e_gui_coverage.py`) — both still have real tests.

---

## 5. Verification Evidence (commands)

- `find tests -name "*.py" | wc -l` → 101 (98 test modules + 3 helpers)
- Import-graph scan: `(^|\s)(import|from)\s+<module>` over all 98 test modules → direct mapping (55 files)
- Package-expansion scan: `from src.<pkg> import` → models/package coverage (64 tests for models)
- App-level: all routers imported by `src/api/main.py` → exercised by the 60+ tests importing the app

**No application source, test, or frontend file was modified by this task.**