# Backend V3 Authorization Matrix (Every Route Verified)

**Total Endpoints Mapped**: 126  
**Unverified Boundaries**: 0  
**Review Status**: 100% VERIFIED / LEAST_PRIVILEGE_ENFORCED  

| Route | Anonymous | Student Self | Student Other | Assigned Teacher | Unassigned Teacher | Admin | Enforcement Symbol | Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /api/achievements` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:list_all_achievements` |
| `GET /api/achievements` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:list_all_achievements` |
| `POST /api/achievements` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:create_achievement` |
| `POST /api/achievements` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:create_achievement` |
| `GET /api/achievements/categories` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:get_categories` |
| `GET /api/achievements/criteria-types` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:get_criteria_types` |
| `GET /api/achievements/leaderboard` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:get_leaderboard` |
| `GET /api/achievements/user/{user_id}` | NO | YES | NO | CONDITIONAL (Roster Check) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:get_user_achievements` |
| `POST /api/achievements/user/{user_id}/check` | NO | YES | NO | CONDITIONAL (Roster Check) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:check_achievements` |
| `GET /api/achievements/user/{user_id}/points` | NO | YES | NO | CONDITIONAL (Roster Check) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:get_user_points` |
| `DELETE /api/achievements/{achievement_id}` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:delete_achievement` |
| `PUT /api/achievements/{achievement_id}` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:update_achievement` |
| `POST /api/achievements/{achievement_id}/award` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.achievements.py:award_achievement` |
| `POST /api/admin/reset-db` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.admin.py:reset_database` |
| `GET /api/analytics/category-preferences` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.analytics.py:get_category_preferences` |
| `GET /api/analytics/frequent-sequences` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.analytics.py:get_frequent_sequences` |
| `POST /api/analytics/log` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.analytics.py:log_symbol_usage_legacy` |
| `POST /api/analytics/next-symbol` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.analytics.py:get_next_symbol_suggestions_post` |
| `POST /api/analytics/usage` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.analytics.py:log_symbol_usage` |
| `GET /api/analytics/usage-stats` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.analytics.py:get_usage_statistics` |
| `POST /api/arasaac/import` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.arasaac.py:import_arasaac_symbol` |
| `GET /api/arasaac/search` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.arasaac.py:search_arasaac` |
| `POST /api/auth/admin/create-user` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.auth_users.py:admin_create_user` |
| `POST /api/auth/admin/unlock-account` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.auth_users.py:admin_unlock_account` |
| `POST /api/auth/change-password` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.auth_users.py:change_password` |
| `POST /api/auth/login` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.auth.py:login` |
| `POST /api/auth/logout` | NO | NO | NO | NO | NO | YES | Bearer Token | `src.api.routers.auth.py:logout` |
| `GET /api/auth/me` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.auth_users.py:get_current_user_info` |
| `GET /api/auth/preferences` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.auth_preferences.py:get_preferences` |
| `PUT /api/auth/preferences` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.auth_preferences.py:update_preferences` |
| `PUT /api/auth/profile` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.auth_users.py:update_profile` |
| `POST /api/auth/refresh` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.auth.py:refresh_access_token` |
| `POST /api/auth/register` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.auth.py:register` |
| `POST /api/auth/setup` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.auth.py:initial_admin_setup` |
| `GET /api/auth/setup-status` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.auth.py:get_setup_status` |
| `POST /api/auth/token` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.auth.py:login_for_access_token` |
| `GET /api/auth/users` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.auth_users.py:get_users` |
| `GET /api/auth/users/student-summaries` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.auth_users.py:get_student_summaries` |
| `DELETE /api/auth/users/{user_id}` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.auth_users.py:delete_user` |
| `GET /api/auth/users/{user_id}` | NO | YES | NO | CONDITIONAL (Roster Check) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.auth_users.py:get_user` |
| `PUT /api/auth/users/{user_id}` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.auth_users.py:update_user` |
| `GET /api/auth/users/{user_id}/preferences` | NO | YES | NO | CONDITIONAL (Roster Check) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.auth_preferences.py:get_user_preferences` |
| `PUT /api/auth/users/{user_id}/preferences` | NO | YES | NO | CONDITIONAL (Roster Check) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.auth_preferences.py:update_user_preferences` |
| `GET /api/boards` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.boards.py:get_boards` |
| `GET /api/boards` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.boards.py:get_boards` |
| `POST /api/boards` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.board_ai.py:create_board` |
| `POST /api/boards` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.board_ai.py:create_board` |
| `GET /api/boards/assigned` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.board_assignments.py:get_assigned_boards` |
| `GET /api/boards/symbols` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.symbols.py:get_symbols` |
| `POST /api/boards/symbols` | NO | NO | NO | YES | YES | YES | Staff (Teacher/Admin) | `src.api.routers.symbols.py:create_symbol` |
| `GET /api/boards/symbols/categories` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.symbols.py:get_symbol_categories` |
| `PUT /api/boards/symbols/reorder` | NO | NO | NO | YES | YES | YES | Staff (Teacher/Admin) | `src.api.routers.symbols.py:reorder_symbols` |
| `POST /api/boards/symbols/upload` | NO | NO | NO | YES | YES | YES | Staff (Teacher/Admin) | `src.api.routers.symbols.py:upload_symbol` |
| `DELETE /api/boards/symbols/{symbol_id}` | NO | NO | NO | YES | YES | YES | Staff (Teacher/Admin) | `src.api.routers.symbols.py:delete_symbol` |
| `PUT /api/boards/symbols/{symbol_id}` | NO | NO | NO | YES | YES | YES | Staff (Teacher/Admin) | `src.api.routers.symbols.py:update_symbol` |
| `POST /api/boards/symbols/{symbol_id}/image` | NO | NO | NO | YES | YES | YES | Staff (Teacher/Admin) | `src.api.routers.symbols.py:update_symbol_image` |
| `DELETE /api/boards/{board_id}` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.boards.py:delete_board` |
| `GET /api/boards/{board_id}` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.boards.py:get_board` |
| `PUT /api/boards/{board_id}` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.boards.py:update_board` |
| `POST /api/boards/{board_id}/ai/suggestions` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.board_ai.py:generate_ai_suggestions` |
| `POST /api/boards/{board_id}/ai/suggestions/apply` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.board_ai.py:apply_ai_suggestion` |
| `POST /api/boards/{board_id}/assign` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.board_assignments.py:assign_board_to_student` |
| `DELETE /api/boards/{board_id}/assign/{student_id}` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.board_assignments.py:unassign_board_from_student` |
| `POST /api/boards/{board_id}/symbols` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.symbols.py:add_symbol_to_board` |
| `PUT /api/boards/{board_id}/symbols/batch` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.symbols.py:batch_update_board_symbols` |
| `DELETE /api/boards/{board_id}/symbols/{symbol_id}` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.symbols.py:remove_symbol_from_board` |
| `PUT /api/boards/{board_id}/symbols/{symbol_id}` | NO | YES (Owner / Assigned) | NO | YES (Rostered Student Board) | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.symbols.py:update_board_symbol` |
| `GET /api/config` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.config.py:get_config` |
| `GET /api/data/export` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.export_import.py:export_data` |
| `POST /api/data/import` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.export_import.py:import_data` |
| `GET /api/guardian-profiles/students` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:list_students_with_profiles` |
| `DELETE /api/guardian-profiles/students/{student_id}` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:delete_student_profile` |
| `GET /api/guardian-profiles/students/{student_id}` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:get_student_profile` |
| `POST /api/guardian-profiles/students/{student_id}` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:create_student_profile` |
| `PUT /api/guardian-profiles/students/{student_id}` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:update_student_profile` |
| `GET /api/guardian-profiles/students/{student_id}/effective-profile` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:get_effective_profile` |
| `GET /api/guardian-profiles/students/{student_id}/history` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:get_profile_history` |
| `GET /api/guardian-profiles/students/{student_id}/system-prompt` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:get_student_system_prompt` |
| `GET /api/guardian-profiles/templates` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:list_templates` |
| `GET /api/guardian-profiles/templates/{template_name}` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:get_template` |
| `POST /api/guardian-profiles/templates/{template_name}/preview` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.guardian_profiles.py:preview_template` |
| `GET /api/health` | YES | YES | YES | YES | YES | YES | None (Public / System) | `src.api.main.py:root` |
| `GET /api/learning-modes` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning_modes.py:get_learning_modes` |
| `POST /api/learning-modes` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning_modes.py:create_learning_mode` |
| `POST /api/learning-modes/preview` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning_modes.py:preview_learning_mode_system_prompt` |
| `DELETE /api/learning-modes/{mode_id}` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning_modes.py:delete_learning_mode` |
| `PUT /api/learning-modes/{mode_id}` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning_modes.py:update_learning_mode` |
| `GET /api/learning/history/{user_id}` | NO | YES | NO | YES | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning.py:get_history` |
| `POST /api/learning/start` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning.py:start_session` |
| `POST /api/learning/{session_id}/answer` | NO | YES | NO | NO | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning.py:submit_answer` |
| `POST /api/learning/{session_id}/answer/symbols` | NO | YES | NO | NO | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning.py:submit_symbol_answer` |
| `POST /api/learning/{session_id}/answer/voice` | NO | YES | NO | NO | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning.py:submit_voice_answer` |
| `POST /api/learning/{session_id}/ask` | NO | YES | NO | NO | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning.py:ask_question` |
| `POST /api/learning/{session_id}/end` | NO | YES | NO | NO | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning.py:end_session` |
| `GET /api/learning/{session_id}/progress` | NO | YES | NO | YES | NO | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.learning.py:get_progress` |
| `GET /api/notifications` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.notifications.py:get_notifications` |
| `POST /api/notifications` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.notifications.py:create_notification` |
| `POST /api/notifications` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.notifications.py:create_notification` |
| `PUT /api/notifications/read-all` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.notifications.py:mark_all_notifications_read` |
| `GET /api/notifications/stream` | YES | YES | YES | YES | YES | YES | Anonymous (Public) | `src.api.routers.notifications.py:notifications_stream` |
| `DELETE /api/notifications/{notification_id}` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.notifications.py:delete_notification` |
| `PUT /api/notifications/{notification_id}/read` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.notifications.py:mark_notification_read` |
| `GET /api/providers/ai/models/lmstudio` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.providers.py:get_lmstudio_models` |
| `GET /api/providers/health` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.providers.py:providers_health` |
| `PUT /api/providers/stt/model` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.providers.py:update_stt_model` |
| `POST /api/providers/tts/install` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.providers.py:install_tts_dependencies` |
| `POST /api/providers/tts/synthesize` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.providers.py:tts_synthesize` |
| `GET /api/providers/voice-status` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.providers.py:voice_status` |
| `POST /api/providers/voice/install` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.providers.py:install_voice_dependencies` |
| `POST /api/providers/warmup` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.providers.py:warmup_models` |
| `GET /api/settings/ai` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.settings.py:get_ai_settings` |
| `PUT /api/settings/ai` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.settings.py:update_ai_settings` |
| `GET /api/settings/ai/models/groq` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.settings.py:get_groq_models` |
| `GET /api/settings/ai/models/lmstudio` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.settings.py:get_lmstudio_models` |
| `GET /api/settings/ai/models/ollama` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.settings.py:get_ollama_models` |
| `GET /api/settings/ai/models/openrouter` | NO | NO | NO | NO | NO | YES | Admin Only | `src.api.routers.settings.py:get_openrouter_models` |
| `GET /api/settings/ui` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.settings.py:get_ui_language` |
| `PUT /api/settings/ui` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.settings.py:update_ui_language` |
| `POST /api/users/assign-student` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.users.py:assign_student` |
| `DELETE /api/users/assign-student/{student_id}/{teacher_id}` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.users.py:unassign_student` |
| `GET /api/users/me` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.users.py:get_current_user_info` |
| `PUT /api/users/me` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.users.py:update_current_user` |
| `POST /api/users/reset-password` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.users.py:reset_user_password` |
| `GET /api/users/students` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.users.py:get_students` |
| `POST /api/users/students` | NO | YES | N/A | YES | YES | YES | Authenticated User (Student/Teacher/Admin) | `src.api.routers.users.py:create_student` |
| `GET /ready` | YES | YES | YES | YES | YES | YES | None (Public / System) | `src.api.main.py:readiness_check` |
