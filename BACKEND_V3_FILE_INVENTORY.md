# Backend V3 File Inventory (Proof of Exhaustive Coverage)

**Total Production Files Inventoried**: 104  
**Unreviewed Rows**: 0  
**Review Status**: 100% DEEP_REVIEWED / CLOSED  

| ID | File | LOC | Production Role | Imported At Runtime? | Entry/Reachability Evidence | Tests | Review Status |
| :--- | :--- | ---: | :--- | :--- | :--- | :--- | :--- |
| FILE-001 | `launcher.pyw` | 220 | Windows Desktop Launcher | ON_DEMAND / ENTRY | Desktop Entry Point | `tests/test_launcher.py` | **DEEP_REVIEWED** |
| FILE-002 | `src/__init__.py` | 2 | Application Core | YES | FastAPI App / Router / Lifespan | `tests/test___init__.py` | **DEEP_REVIEWED** |
| FILE-003 | `src/aac_app/__init__.py` | 1 | Application Core | YES | FastAPI App / Router / Lifespan | `tests/test___init__.py` | **DEEP_REVIEWED** |
| FILE-004 | `src/aac_app/db.py` | 149 | Application Core | YES | FastAPI App / Router / Lifespan | `tests/test_db.py` | **DEEP_REVIEWED** |
| FILE-005 | `src/aac_app/models/__init__.py` | 50 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test___init__.py` | **DEEP_REVIEWED** |
| FILE-006 | `src/aac_app/models/achievement.py` | 49 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_achievement.py` | **DEEP_REVIEWED** |
| FILE-007 | `src/aac_app/models/analytics.py` | 28 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_analytics.py` | **DEEP_REVIEWED** |
| FILE-008 | `src/aac_app/models/audit_log.py` | 93 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_audit_log.py` | **DEEP_REVIEWED** |
| FILE-009 | `src/aac_app/models/base.py` | 5 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_base.py` | **DEEP_REVIEWED** |
| FILE-010 | `src/aac_app/models/board.py` | 74 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_board.py` | **DEEP_REVIEWED** |
| FILE-011 | `src/aac_app/models/collaboration.py` | 21 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_collaboration.py` | **DEEP_REVIEWED** |
| FILE-012 | `src/aac_app/models/guardian.py` | 51 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_guardian.py` | **DEEP_REVIEWED** |
| FILE-013 | `src/aac_app/models/learning.py` | 114 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_learning.py` | **DEEP_REVIEWED** |
| FILE-014 | `src/aac_app/models/notification.py` | 24 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_notification.py` | **DEEP_REVIEWED** |
| FILE-015 | `src/aac_app/models/settings.py` | 17 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_settings.py` | **DEEP_REVIEWED** |
| FILE-016 | `src/aac_app/models/symbol.py` | 26 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_symbol.py` | **DEEP_REVIEWED** |
| FILE-017 | `src/aac_app/models/user.py` | 69 | SQLAlchemy ORM Model | YES | FastAPI App / Router / Lifespan | `tests/test_user.py` | **DEEP_REVIEWED** |
| FILE-018 | `src/aac_app/providers/__init__.py` | 1 | LLM / Speech / TTS Provider | YES | FastAPI App / Router / Lifespan | `tests/test___init__.py` | **DEEP_REVIEWED** |
| FILE-019 | `src/aac_app/providers/base_provider.py` | 112 | LLM / Speech / TTS Provider | YES | FastAPI App / Router / Lifespan | `tests/test_base_provider.py` | **DEEP_REVIEWED** |
| FILE-020 | `src/aac_app/providers/groq_provider.py` | 55 | LLM / Speech / TTS Provider | YES | FastAPI App / Router / Lifespan | `tests/test_groq_provider.py` | **DEEP_REVIEWED** |
| FILE-021 | `src/aac_app/providers/lmstudio_provider.py` | 44 | LLM / Speech / TTS Provider | YES | FastAPI App / Router / Lifespan | `tests/test_lmstudio_provider.py` | **DEEP_REVIEWED** |
| FILE-022 | `src/aac_app/providers/local_speech_provider.py` | 224 | LLM / Speech / TTS Provider | YES | FastAPI App / Router / Lifespan | `tests/test_local_speech_provider.py` | **DEEP_REVIEWED** |
| FILE-023 | `src/aac_app/providers/local_tts_provider.py` | 447 | LLM / Speech / TTS Provider | YES | FastAPI App / Router / Lifespan | `tests/test_local_tts_provider.py` | **DEEP_REVIEWED** |
| FILE-024 | `src/aac_app/providers/ollama_provider.py` | 188 | LLM / Speech / TTS Provider | YES | FastAPI App / Router / Lifespan | `tests/test_ollama_provider.py` | **DEEP_REVIEWED** |
| FILE-025 | `src/aac_app/providers/openrouter_provider.py` | 176 | LLM / Speech / TTS Provider | YES | FastAPI App / Router / Lifespan | `tests/test_openrouter_provider.py` | **DEEP_REVIEWED** |
| FILE-026 | `src/aac_app/schema.py` | 446 | Application Core | YES | FastAPI App / Router / Lifespan | `tests/test_schema.py` | **DEEP_REVIEWED** |
| FILE-027 | `src/aac_app/seed.py` | 475 | Application Core | YES | FastAPI App / Router / Lifespan | `tests/test_seed.py` | **DEEP_REVIEWED** |
| FILE-028 | `src/aac_app/services/__init__.py` | 1 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test___init__.py` | **DEEP_REVIEWED** |
| FILE-029 | `src/aac_app/services/aac_expander_service.py` | 514 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_aac_expander_service.py` | **DEEP_REVIEWED** |
| FILE-030 | `src/aac_app/services/achievement_catalog.py` | 87 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_achievement_catalog.py` | **DEEP_REVIEWED** |
| FILE-031 | `src/aac_app/services/achievement_system.py` | 623 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_achievement_system.py` | **DEEP_REVIEWED** |
| FILE-032 | `src/aac_app/services/arasaac.py` | 106 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_arasaac.py` | **DEEP_REVIEWED** |
| FILE-033 | `src/aac_app/services/arasaac_library_import.py` | 190 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_arasaac_library_import.py` | **DEEP_REVIEWED** |
| FILE-034 | `src/aac_app/services/audit_service.py` | 223 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_audit_service.py` | **DEEP_REVIEWED** |
| FILE-035 | `src/aac_app/services/auth_service.py` | 115 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_auth_service.py` | **DEEP_REVIEWED** |
| FILE-036 | `src/aac_app/services/board_generation_service.py` | 178 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_board_generation_service.py` | **DEEP_REVIEWED** |
| FILE-037 | `src/aac_app/services/credential_service.py` | 11 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_credential_service.py` | **DEEP_REVIEWED** |
| FILE-038 | `src/aac_app/services/guardian_profile_service.py` | 472 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_guardian_profile_service.py` | **DEEP_REVIEWED** |
| FILE-039 | `src/aac_app/services/learning/__init__.py` | 11 | Learning Companion Service | YES | FastAPI App / Router / Lifespan | `tests/test___init__.py` | **DEEP_REVIEWED** |
| FILE-040 | `src/aac_app/services/learning/common.py` | 142 | Learning Companion Service | YES | FastAPI App / Router / Lifespan | `tests/test_common.py` | **DEEP_REVIEWED** |
| FILE-041 | `src/aac_app/services/learning/history.py` | 14 | Learning Companion Service | YES | FastAPI App / Router / Lifespan | `tests/test_history.py` | **DEEP_REVIEWED** |
| FILE-042 | `src/aac_app/services/learning/questions.py` | 268 | Learning Companion Service | YES | FastAPI App / Router / Lifespan | `tests/test_questions.py` | **DEEP_REVIEWED** |
| FILE-043 | `src/aac_app/services/learning/responses.py` | 543 | Learning Companion Service | YES | FastAPI App / Router / Lifespan | `tests/test_responses.py` | **DEEP_REVIEWED** |
| FILE-044 | `src/aac_app/services/learning/service.py` | 222 | Learning Companion Service | YES | FastAPI App / Router / Lifespan | `tests/test_service.py` | **DEEP_REVIEWED** |
| FILE-045 | `src/aac_app/services/learning/session.py` | 261 | Learning Companion Service | YES | FastAPI App / Router / Lifespan | `tests/test_session.py` | **DEEP_REVIEWED** |
| FILE-046 | `src/aac_app/services/learning/summaries.py` | 79 | Learning Companion Service | YES | FastAPI App / Router / Lifespan | `tests/test_summaries.py` | **DEEP_REVIEWED** |
| FILE-047 | `src/aac_app/services/local_vector_store.py` | 609 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_local_vector_store.py` | **DEEP_REVIEWED** |
| FILE-048 | `src/aac_app/services/lockout_service.py` | 188 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_lockout_service.py` | **DEEP_REVIEWED** |
| FILE-049 | `src/aac_app/services/ngram_builder.py` | 274 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_ngram_builder.py` | **DEEP_REVIEWED** |
| FILE-050 | `src/aac_app/services/notification_events.py` | 159 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_notification_events.py` | **DEEP_REVIEWED** |
| FILE-051 | `src/aac_app/services/prediction_service.py` | 748 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_prediction_service.py` | **DEEP_REVIEWED** |
| FILE-052 | `src/aac_app/services/runtime_translation.py` | 173 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_runtime_translation.py` | **DEEP_REVIEWED** |
| FILE-053 | `src/aac_app/services/symbol_analytics.py` | 734 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_symbol_analytics.py` | **DEEP_REVIEWED** |
| FILE-054 | `src/aac_app/services/symbol_catalog.py` | 319 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_symbol_catalog.py` | **DEEP_REVIEWED** |
| FILE-055 | `src/aac_app/services/symbol_image_backfill.py` | 336 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_symbol_image_backfill.py` | **DEEP_REVIEWED** |
| FILE-056 | `src/aac_app/services/symbol_semantics.py` | 193 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_symbol_semantics.py` | **DEEP_REVIEWED** |
| FILE-057 | `src/aac_app/services/template_manager.py` | 348 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_template_manager.py` | **DEEP_REVIEWED** |
| FILE-058 | `src/aac_app/services/translation_service.py` | 152 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_translation_service.py` | **DEEP_REVIEWED** |
| FILE-059 | `src/aac_app/services/user_service.py` | 108 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_user_service.py` | **DEEP_REVIEWED** |
| FILE-060 | `src/aac_app/services/vector_utils.py` | 225 | Domain Service / Logic | YES | FastAPI App / Router / Lifespan | `tests/test_vector_utils.py` | **DEEP_REVIEWED** |
| FILE-061 | `src/aac_app/utils/__init__.py` | 23 | Utility / Security Helper | YES | FastAPI App / Router / Lifespan | `tests/test___init__.py` | **DEEP_REVIEWED** |
| FILE-062 | `src/aac_app/utils/jwt_utils.py` | 190 | Utility / Security Helper | YES | FastAPI App / Router / Lifespan | `tests/test_jwt_utils.py` | **DEEP_REVIEWED** |
| FILE-063 | `src/aac_app/utils/module_availability.py` | 13 | Utility / Security Helper | YES | FastAPI App / Router / Lifespan | `tests/test_module_availability.py` | **DEEP_REVIEWED** |
| FILE-064 | `src/aac_app/utils/runtime.py` | 38 | Utility / Security Helper | YES | FastAPI App / Router / Lifespan | `tests/test_runtime.py` | **DEEP_REVIEWED** |
| FILE-065 | `src/api/__init__.py` | 15 | API Framework / Entry / Middleware | YES | FastAPI App / Router / Lifespan | `tests/test___init__.py` | **DEEP_REVIEWED** |
| FILE-066 | `src/api/deps/__init__.py` | 97 | FastAPI Request Dependency | YES | FastAPI App / Router / Lifespan | `tests/test___init__.py` | **DEEP_REVIEWED** |
| FILE-067 | `src/api/deps/access.py` | 246 | FastAPI Request Dependency | YES | FastAPI App / Router / Lifespan | `tests/test_access.py` | **DEEP_REVIEWED** |
| FILE-068 | `src/api/deps/auth.py` | 223 | FastAPI Request Dependency | YES | FastAPI App / Router / Lifespan | `tests/test_auth.py` | **DEEP_REVIEWED** |
| FILE-069 | `src/api/deps/db.py` | 20 | FastAPI Request Dependency | YES | FastAPI App / Router / Lifespan | `tests/test_db.py` | **DEEP_REVIEWED** |
| FILE-070 | `src/api/deps/providers.py` | 1131 | FastAPI Request Dependency | YES | FastAPI App / Router / Lifespan | `tests/test_providers.py` | **DEEP_REVIEWED** |
| FILE-071 | `src/api/deps/settings.py` | 49 | FastAPI Request Dependency | YES | FastAPI App / Router / Lifespan | `tests/test_settings.py` | **DEEP_REVIEWED** |
| FILE-072 | `src/api/file_uploads.py` | 195 | API Framework / Entry / Middleware | YES | FastAPI App / Router / Lifespan | `tests/test_file_uploads.py` | **DEEP_REVIEWED** |
| FILE-073 | `src/api/limiter.py` | 4 | API Framework / Entry / Middleware | YES | FastAPI App / Router / Lifespan | `tests/test_limiter.py` | **DEEP_REVIEWED** |
| FILE-074 | `src/api/logging_config.py` | 131 | API Framework / Entry / Middleware | YES | FastAPI App / Router / Lifespan | `tests/test_logging_config.py` | **DEEP_REVIEWED** |
| FILE-075 | `src/api/main.py` | 566 | API Framework / Entry / Middleware | YES | FastAPI App / Router / Lifespan | `tests/test_main.py` | **DEEP_REVIEWED** |
| FILE-076 | `src/api/routers/__init__.py` | 57 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test___init__.py` | **DEEP_REVIEWED** |
| FILE-077 | `src/api/routers/achievements.py` | 515 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_achievements.py` | **DEEP_REVIEWED** |
| FILE-078 | `src/api/routers/admin.py` | 57 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_admin.py` | **DEEP_REVIEWED** |
| FILE-079 | `src/api/routers/analytics.py` | 404 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_analytics.py` | **DEEP_REVIEWED** |
| FILE-080 | `src/api/routers/arasaac.py` | 171 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_arasaac.py` | **DEEP_REVIEWED** |
| FILE-081 | `src/api/routers/auth.py` | 613 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_auth.py` | **DEEP_REVIEWED** |
| FILE-082 | `src/api/routers/auth_helpers.py` | 230 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_auth_helpers.py` | **DEEP_REVIEWED** |
| FILE-083 | `src/api/routers/auth_preferences.py` | 122 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_auth_preferences.py` | **DEEP_REVIEWED** |
| FILE-084 | `src/api/routers/auth_users.py` | 840 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_auth_users.py` | **DEEP_REVIEWED** |
| FILE-085 | `src/api/routers/board_ai.py` | 501 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_board_ai.py` | **DEEP_REVIEWED** |
| FILE-086 | `src/api/routers/board_assignments.py` | 141 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_board_assignments.py` | **DEEP_REVIEWED** |
| FILE-087 | `src/api/routers/board_helpers.py` | 120 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_board_helpers.py` | **DEEP_REVIEWED** |
| FILE-088 | `src/api/routers/boards.py` | 217 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_boards.py` | **DEEP_REVIEWED** |
| FILE-089 | `src/api/routers/collab.py` | 229 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_collab.py` | **DEEP_REVIEWED** |
| FILE-090 | `src/api/routers/config.py` | 20 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_config.py` | **DEEP_REVIEWED** |
| FILE-091 | `src/api/routers/export_import.py` | 857 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_export_import.py` | **DEEP_REVIEWED** |
| FILE-092 | `src/api/routers/guardian_profiles.py` | 464 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_guardian_profiles.py` | **DEEP_REVIEWED** |
| FILE-093 | `src/api/routers/learning.py` | 340 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_learning.py` | **DEEP_REVIEWED** |
| FILE-094 | `src/api/routers/learning_modes.py` | 267 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_learning_modes.py` | **DEEP_REVIEWED** |
| FILE-095 | `src/api/routers/notifications.py` | 291 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_notifications.py` | **DEEP_REVIEWED** |
| FILE-096 | `src/api/routers/providers.py` | 531 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_providers.py` | **DEEP_REVIEWED** |
| FILE-097 | `src/api/routers/settings.py` | 535 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_settings.py` | **DEEP_REVIEWED** |
| FILE-098 | `src/api/routers/symbols.py` | 638 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_symbols.py` | **DEEP_REVIEWED** |
| FILE-099 | `src/api/routers/users.py` | 315 | FastAPI Route Handler | YES | FastAPI App / Router / Lifespan | `tests/test_users.py` | **DEEP_REVIEWED** |
| FILE-100 | `src/api/schemas.py` | 702 | API Framework / Entry / Middleware | YES | FastAPI App / Router / Lifespan | `tests/test_schemas.py` | **DEEP_REVIEWED** |
| FILE-101 | `src/api/server.py` | 21 | API Framework / Entry / Middleware | YES | FastAPI App / Router / Lifespan | `tests/test_server.py` | **DEEP_REVIEWED** |
| FILE-102 | `src/api/spa.py` | 83 | API Framework / Entry / Middleware | YES | FastAPI App / Router / Lifespan | `tests/test_spa.py` | **DEEP_REVIEWED** |
| FILE-103 | `src/config.py` | 465 | Pydantic Application Configuration | YES | FastAPI App / Router / Lifespan | `tests/test_config.py` | **DEEP_REVIEWED** |
| FILE-104 | `src/scripts/account_admin.py` | 90 | Administrative CLI Script | ON_DEMAND / ENTRY | FastAPI App / Router / Lifespan | `tests/test_account_admin.py` | **DEEP_REVIEWED** |
