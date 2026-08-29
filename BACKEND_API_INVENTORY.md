# Backend API Inventory

This document provides a comprehensive, endpoint-by-endpoint inventory of all routes registered in the AAC Assistant FastAPI backend.

---

## Summary Statistics
- **Total Unique Paths**: 67
- **Total Operations (Method + Path)**: 126
- **Authentication Levels**:
  - **Public (No Auth)**: 8 routes (`/ready`, `/api/health`, `/api/config`, `/api/auth/token`, `/api/auth/refresh`, `/api/auth/register`, `/api/auth/setup`, `/api/auth/setup-status`)
  - **Active User (`get_current_active_user`)**: 38 routes
  - **Staff User (Teacher/Admin - `get_current_staff_user` or role check)**: 12 routes
  - **Admin Only (`get_current_admin_user`)**: 9 routes

---

## Detailed Route Ledger

### 1. System & Health (`src/api/main.py`, `src/api/routers/config.py`)

| Method | Path | Handler | Auth / RBAC | Dependencies | Response Model | Frontend Consumers | Test Files | Redundancy Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/ready` | `src.api.main.readiness_check` | Public | None | JSON | Polled on boot / reverse proxy | `tests/test_ready_endpoint.py` | **Canonical**: Live provider & DB readiness check. |
| `GET` | `/api/health` | `src.api.main.root` | Public | None | JSON | Liveness probes | `tests/test_api_comprehensive.py` | **Canonical**: Basic HTTP liveness. |
| `GET` | `/api/config` | `src.api.routers.config.get_config` | Public | None | `ConfigResponse` | `src/frontend/src/config.ts` | `tests/test_config_pydantic.py` | **Canonical**: Public client version & locale metadata. |

---

### 2. Authentication & Session Management (`src/api/routers/auth.py`, `src/api/routers/auth_preferences.py`)

| Method | Path | Handler | Auth / RBAC | Dependencies | Response Model | Frontend Consumers | Test Files | Redundancy Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/token` | `src.api.routers.auth.login_for_access_token` | Public | `OAuth2PasswordRequestForm`, `get_db` | `Token` | `src/frontend/src/store/authStore.ts` | `tests/test_auth_routes.py` | **Canonical**: OAuth2 form-data login endpoint. |
| `POST` | `/api/auth/refresh` | `src.api.routers.auth.refresh_access_token` | Public | `RefreshTokenRequest`, `get_db` | `Token` | `src/frontend/src/lib/api.ts` | `tests/test_auth_routes.py` | **Canonical**: Silent JWT token rotation. |
| `POST` | `/api/auth/register` | `src.api.routers.auth.register` | Public | `UserCreate`, `get_db` | `UserResponse` | `src/frontend/src/pages/Login.tsx` | `tests/test_auth_routes.py` | **Canonical**: Self-registration endpoint. |
| `POST` | `/api/auth/setup` | `src.api.routers.auth.initial_admin_setup` | Public | `InitialAdminSetupRequest`, `get_db` | `UserResponse` | `src/frontend/src/pages/Setup.tsx` | `tests/integration/test_first_run_security.py` | **Canonical**: First-run bootstrap setup. |
| `GET` | `/api/auth/setup-status` | `src.api.routers.auth.get_setup_status` | Public | `get_db` | `SetupStatusResponse` | `src/frontend/src/pages/Login.tsx` | `tests/test_auth_routes.py` | **Canonical**: Checks if initial setup is needed. |
| `POST` | `/api/auth/change-password` | `src.api.routers.auth.change_password` | Active User | `ChangePasswordRequest`, `get_db` | `StatusResponse` | `src/frontend/src/pages/Settings/SecurityTab.tsx` | `tests/test_auth_routes.py` | **Canonical**: User self-service password update. |
| `POST` | `/api/auth/logout` | `src.api.routers.auth.logout` | Active User | `get_db` | `StatusResponse` | `src/frontend/src/store/authStore.ts` | `tests/test_auth_routes.py` | **Canonical**: Session termination & invalidation. |
| `GET` | `/api/auth/me` | `src.api.routers.auth_users.get_current_user_info` | Active User | `get_current_active_user` | `UserResponse` | `src/frontend/src/store/authStore.ts` | `tests/test_auth_routes.py` | **Canonical**: Session profile inspection. |
| `PUT` | `/api/auth/profile` | `src.api.routers.auth_preferences.update_profile` | Active User | `ProfileUpdateRequest`, `get_db` | `UserResponse` | `src/frontend/src/pages/Settings/ProfileTab.tsx` | `tests/test_auth_routes.py` | **Canonical**: Self profile display name & email update. |
| `GET` | `/api/auth/preferences` | `src.api.routers.auth_preferences.get_preferences` | Active User | `get_db` | `UserSettingsResponse` | `src/frontend/src/pages/Settings/usePreferences.ts` | `tests/test_auth_routes.py` | **Canonical**: User UI preferences. |
| `PUT` | `/api/auth/preferences` | `src.api.routers.auth_preferences.update_preferences` | Active User | `UserSettingsUpdate`, `get_db` | `UserSettingsResponse` | `src/frontend/src/pages/Settings/usePreferences.ts` | `tests/test_auth_routes.py` | **Canonical**: User UI preferences update. |

---

### 3. User & Student Management (`src/api/routers/auth_users.py`, `src/api/routers/users.py`)

| Method | Path | Handler | Auth / RBAC | Dependencies | Response Model | Frontend Consumers | Test Files | Redundancy Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/admin/create-user` | `src.api.routers.auth_users.admin_create_user` | Admin Only | `UserCreate`, `get_db` | `UserResponse` | `src/frontend/src/pages/UserManagement.tsx` | `tests/test_admin_user_management.py` | **Canonical**: Admin creation of Teacher/Admin accounts with password confirmation. |
| `GET` | `/api/auth/users` | `src.api.routers.auth_users.get_users` | Staff User | `get_db`, `skip`, `limit` | `list[UserResponse]` | `src/frontend/src/pages/UserManagement.tsx`, `Boards.tsx` | `tests/test_auth_users_routes.py` | **Canonical**: User roster list. |
| `GET` | `/api/auth/users/student-summaries` | `src.api.routers.auth_users.get_student_summaries` | Staff User | `get_db`, `skip`, `limit` | `list[StudentBoardSummaryResponse]` | `src/frontend/src/pages/Students.tsx` | `tests/test_auth_users_routes.py` | **Canonical**: Aggregated student list with assigned board counts. |
| `GET` | `/api/auth/users/{user_id}` | `src.api.routers.auth_users.get_user` | Staff / Self | `get_db` | `UserResponse` | `src/frontend/src/store/authStore.ts` | `tests/test_auth_users_routes.py` | **Canonical**: User record lookup. |
| `PUT` | `/api/auth/users/{user_id}` | `src.api.routers.auth_users.update_user` | Staff / Self | `UserAdminUpdate`, `get_db` | `UserResponse` | `src/frontend/src/pages/UserManagement.tsx`, `Students.tsx` | `tests/test_auth_users_routes.py` | **Canonical**: Administrative user update. |
| `DELETE` | `/api/auth/users/{user_id}` | `src.api.routers.auth_users.delete_user` | Admin Only | `get_db` | `StatusResponse` | `src/frontend/src/pages/UserManagement.tsx`, `Students.tsx` | `tests/test_auth_users_routes.py` | **Canonical**: User deletion with full relational cascades. |
| `GET` | `/api/auth/users/{user_id}/preferences` | `src.api.routers.auth_users.get_user_preferences` | Staff / Self | `get_db` | `UserSettingsResponse` | `src/frontend/src/pages/Students.tsx` | `tests/test_auth_users_routes.py` | **Canonical**: Teacher inspection of student preferences. |
| `PUT` | `/api/auth/users/{user_id}/preferences` | `src.api.routers.auth_users.update_user_preferences` | Staff / Self | `UserSettingsUpdate`, `get_db` | `UserSettingsResponse` | `src/frontend/src/pages/Students.tsx` | `tests/test_auth_users_routes.py` | **Canonical**: Teacher customization of student preferences. |
| `GET` | `/api/users/students` | `src.api.routers.users.get_students` | Staff User | `get_db`, `skip`, `limit` | `list[UserResponse]` | `src/frontend/src/pages/Achievements.tsx:97` | `tests/test_users_routes.py` | **Active**: Student selection list for teachers. |
| `POST` | `/api/users/students` | `src.api.routers.users.create_student` | Staff User | `UserCreate`, `get_db` | `UserResponse` | `src/frontend/src/pages/Students.tsx:222` | `tests/test_users_routes.py` | **Active**: Teacher creation of assigned student without admin role. |
| `POST` | `/api/users/reset-password` | `src.api.routers.users.reset_user_password` | Staff User | `ResetPasswordRequest`, `get_db` | `StatusResponse` | `src/frontend/src/pages/Students.tsx:253`, `UserManagement.tsx:170` | `tests/test_users_routes.py` | **Active**: Direct password reset by teacher for student (without knowing old password). |
| `POST` | `/api/users/assign-student` | `src.api.routers.users.assign_student` | Staff User | `StudentAssignRequest`, `get_db` | JSON | Tests / Custom integrations | `tests/test_users_routes.py` | **Active**: Roster association creation. |
| `DELETE` | `/api/users/assign-student/{student_id}/{teacher_id}` | `src.api.routers.users.unassign_student` | Staff User | `get_db` | JSON | Tests / Custom integrations | `tests/test_users_routes.py` | **Active**: Roster association removal. |
| `GET` | `/api/users/me` | `src.api.routers.users.get_current_user_info` | Active User | `get_current_active_user` | `UserResponse` | None (Calls `/api/auth/me`) | `tests/test_users_routes.py` | **Redundant**: Duplicate of `GET /api/auth/me`. |
| `PUT` | `/api/users/me` | `src.api.routers.users.update_current_user` | Active User | `UserUpdate`, `get_db` | `UserResponse` | None (Calls `/api/auth/profile`) | `tests/test_users_routes.py` | **Redundant**: Overlaps with `PUT /api/auth/profile`. |

---

### 4. Communication Boards & Symbols (`src/api/routers/boards.py`, `src/api/routers/board_ai.py`, `src/api/routers/symbols.py`, `src/api/routers/board_assignments.py`)

| Method | Path | Handler | Auth / RBAC | Dependencies | Response Model | Frontend Consumers | Test Files | Redundancy Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/boards` | `src.api.routers.boards.get_boards` | Active User | `get_db`, `skip`, `limit` | `list[BoardResponse]` | `src/frontend/src/store/boardStore.ts`, `useSymbolHunt.ts` | `tests/test_boards_routes.py` | **Canonical**: List accessible boards. |
| `POST` | `/api/boards` | `src.api.routers.board_ai.create_board` | Active User | `BoardCreate`, `get_db` | `BoardResponse` | `src/frontend/src/store/boardStore.ts` | `tests/test_board_ai_routes.py` | **Canonical**: Create board (supports AI layout generation). |
| `GET` | `/api/boards/{board_id}` | `src.api.routers.boards.get_board` | Active User | `get_db` | `BoardResponse` | `src/frontend/src/pages/BoardEditor.tsx`, `useSymbolHunt.ts` | `tests/test_boards_routes.py` | **Canonical**: Load board by ID. |
| `PUT` | `/api/boards/{board_id}` | `src.api.routers.boards.update_board` | Staff / Owner | `BoardUpdate`, `get_db` | `BoardResponse` | `src/frontend/src/pages/BoardEditor.tsx` | `tests/test_boards_routes.py` | **Canonical**: Update board metadata & layout. |
| `DELETE` | `/api/boards/{board_id}` | `src.api.routers.boards.delete_board` | Staff / Owner | `get_db` | `StatusResponse` | `src/frontend/src/pages/Boards.tsx` | `tests/test_boards_routes.py` | **Canonical**: Delete board with cascaded symbols. |
| `POST` | `/api/boards/{board_id}/symbols` | `src.api.routers.symbols.add_symbol_to_board` | Staff / Owner | `BoardSymbolCreate`, `get_db` | `BoardSymbolResponse` | `src/frontend/src/pages/BoardEditor.tsx` | `tests/test_symbols_routes_coverage.py` | **Canonical**: Attach symbol to grid cell. |
| `PUT` | `/api/boards/{board_id}/symbols/{symbol_id}` | `src.api.routers.symbols.update_board_symbol` | Staff / Owner | `BoardSymbolUpdate`, `get_db` | `BoardSymbolResponse` | `src/frontend/src/pages/BoardEditor.tsx` | `tests/test_symbols_routes_coverage.py` | **Canonical**: Move or configure board symbol cell. |
| `DELETE` | `/api/boards/{board_id}/symbols/{symbol_id}` | `src.api.routers.symbols.remove_symbol_from_board` | Staff / Owner | `get_db` | `StatusResponse` | `src/frontend/src/pages/BoardEditor.tsx` | `tests/test_symbols_routes_coverage.py` | **Canonical**: Detach symbol from board grid. |
| `PUT` | `/api/boards/{board_id}/symbols/batch` | `src.api.routers.boards.batch_update_symbols` | Staff / Owner | `BatchSymbolUpdate`, `get_db` | `list[BoardSymbolResponse]` | `src/frontend/src/pages/BoardEditor.tsx` | `tests/test_boards_routes.py` | **Canonical**: Atomic reorder / layout of multiple grid cells. |
| `GET` | `/api/boards/assigned` | `src.api.routers.board_assignments.get_assigned_boards` | Active User | `get_db` | `list[BoardResponse]` | `src/frontend/src/pages/Boards.tsx`, `useSymbolHunt.ts` | `tests/test_board_assignment.py` | **Canonical**: Boards assigned to current student. |
| `POST` | `/api/boards/{board_id}/assign` | `src.api.routers.board_assignments.assign_board` | Staff User | `BoardAssignRequest`, `get_db` | `StatusResponse` | `src/frontend/src/pages/Boards.tsx` | `tests/test_board_assignment.py` | **Canonical**: Assign board to student. |
| `DELETE` | `/api/boards/{board_id}/assign/{student_id}` | `src.api.routers.board_assignments.unassign_board` | Staff User | `get_db` | `StatusResponse` | `src/frontend/src/pages/Boards.tsx` | `tests/test_board_assignment.py` | **Canonical**: Remove board assignment. |
| `POST` | `/api/boards/{board_id}/ai/suggestions` | `src.api.routers.board_ai.generate_ai_suggestions` | Staff / Owner | `AISuggestionsRequest`, `get_db` | `AISuggestionsResponse` | `src/frontend/src/hooks/useBoardAISuggestions.ts` | `tests/test_board_ai_routes.py` | **Canonical**: AI board symbol recommendations. |
| `POST` | `/api/boards/{board_id}/ai/suggestions/apply` | `src.api.routers.board_ai.apply_ai_suggestion` | Staff / Owner | `ApplySuggestionRequest`, `get_db` | `BoardSymbolResponse` | `src/frontend/src/hooks/useBoardAISuggestions.ts` | `tests/test_board_ai_routes.py` | **Canonical**: Add AI suggested symbol to board. |
| `GET` | `/api/boards/symbols` | `src.api.routers.symbols.get_symbols` | Active User | `get_db`, `query`, `category` | `list[SymbolResponse]` | `src/frontend/src/components/board/SymbolPicker.tsx`, `Learning.tsx` | `tests/test_symbols_routes_coverage.py` | **Canonical**: Multi-lingual symbol search. |
| `GET` | `/api/boards/symbols/categories` | `src.api.routers.symbols.get_symbol_categories` | Active User | `get_db` | `list[str]` | `src/frontend/src/components/board/SymbolPicker.tsx` | `tests/test_symbols_routes_coverage.py` | **Canonical**: Distinct symbol categories. |
| `POST` | `/api/boards/symbols` | `src.api.routers.symbols.create_symbol` | Staff User | `SymbolCreate`, `get_db` | `SymbolResponse` | `src/frontend/src/pages/Symbols.tsx` | `tests/test_symbols_routes_coverage.py` | **Canonical**: Create custom symbol. |
| `POST` | `/api/boards/symbols/upload` | `src.api.routers.symbols.upload_symbol_image` | Staff User | `UploadFile`, `get_db` | `SymbolResponse` | `src/frontend/src/components/board/SymbolPicker.tsx` | `tests/test_symbols_routes_coverage.py` | **Canonical**: Upload custom pictogram image. |
| `PUT` | `/api/boards/symbols/{symbol_id}` | `src.api.routers.symbols.update_symbol` | Staff User | `SymbolUpdate`, `get_db` | `SymbolResponse` | `src/frontend/src/pages/Symbols.tsx` | `tests/test_symbols_routes_coverage.py` | **Canonical**: Edit symbol label/category. |
| `POST` | `/api/boards/symbols/{symbol_id}/image` | `src.api.routers.symbols.update_symbol_image` | Staff User | `UploadFile`, `get_db` | `SymbolResponse` | `src/frontend/src/pages/Symbols.tsx` | `tests/test_symbols_routes_coverage.py` | **Canonical**: Replace symbol image. |
| `DELETE` | `/api/boards/symbols/{symbol_id}` | `src.api.routers.symbols.delete_symbol` | Staff User | `get_db`, `force` | `StatusResponse` | `src/frontend/src/pages/Symbols.tsx` | `tests/test_symbols_routes_coverage.py` | **Canonical**: Delete custom symbol & embedding. |

---

### 5. Learning Companion & Guardian Profiles (`src/api/routers/learning.py`, `src/api/routers/learning_modes.py`, `src/api/routers/guardian_profiles.py`)

| Method | Path | Handler | Auth / RBAC | Dependencies | Response Model | Frontend Consumers | Test Files | Redundancy Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/learning/start` | `src.api.routers.learning.start_session` | Active User (Defect: Omits Teacher) | `LearningSessionStart`, `get_db` | `LearningSessionResponse` | `src/frontend/src/store/learningStore.ts` | `tests/test_learning_service_modular.py` | **Actionable Defect**: Must allow assigned teachers via `verify_student_access`. |
| `POST` | `/api/learning/{session_id}/ask` | `src.api.routers.learning.ask_question` | Active User | `get_learning_service`, `get_db` | `QuestionResponse` | `src/frontend/src/store/learningStore.ts` | `tests/test_learning_service_modular.py` | **Canonical**: Generate next companion question. |
| `POST` | `/api/learning/{session_id}/answer` | `src.api.routers.learning.submit_answer` | Active User | `AnswerSubmit`, `get_db` | `AnswerResponse` | `src/frontend/src/store/learningStore.ts` | `tests/test_learning_service_modular.py` | **Canonical**: Submit text answer. |
| `POST` | `/api/learning/{session_id}/answer/symbols` | `src.api.routers.learning.submit_symbol_answer` | Active User | `SymbolAnswerSubmit`, `get_db` | `AnswerResponse` | `src/frontend/src/store/learningStore.ts` | `tests/test_learning_service_modular.py` | **Canonical**: Submit ordered symbol sequence. |
| `POST` | `/api/learning/{session_id}/answer/voice` | `src.api.routers.learning.submit_voice_answer` | Active User | `UploadFile`, `get_db` | `AnswerResponse` | `src/frontend/src/store/learningStore.ts` | `tests/test_learning_service_modular.py` | **Canonical**: Submit audio recording for transcription & response. |
| `POST` | `/api/learning/{session_id}/end` | `src.api.routers.learning.end_session` | Active User | `get_learning_service`, `get_db` | `LearningSessionResponse` | `src/frontend/src/store/learningStore.ts` | `tests/test_learning_service_modular.py` | **Canonical**: Terminate session & generate summary. |
| `GET` | `/api/learning/{session_id}/progress` | `src.api.routers.learning.get_progress` | Active User | `get_db` | JSON | `src/frontend/src/store/learningStore.ts` | `tests/test_learning_service_modular.py` | **Canonical**: Live session progress metrics. |
| `GET` | `/api/learning/history/{user_id}` | `src.api.routers.learning.get_history` | Active User (Defect: Omits Teacher) | `get_db`, `limit` | JSON | `src/frontend/src/store/dashboardStore.ts:46` | `tests/test_learning_service_modular.py` | **Actionable Defect**: Must allow assigned teachers via `verify_student_access`. |
| `GET` | `/api/learning-modes/` | `src.api.routers.learning_modes.get_learning_modes` | Active User | `get_db` | `list[LearningModeResponse]` | `src/frontend/src/pages/Learning.tsx:145` | `tests/test_learning_modes_routes.py` | **Canonical**: List available learning modes. |
| `POST` | `/api/learning-modes/` | `src.api.routers.learning_modes.create_learning_mode` | Staff User | `LearningModeCreate`, `get_db` | `LearningModeResponse` | `src/frontend/src/pages/Settings/LearningModesTab.tsx` | `tests/test_learning_modes_routes.py` | **Canonical**: Create custom learning mode. |
| `POST` | `/api/learning-modes/preview` | `src.api.routers.learning_modes.preview_learning_mode` | Staff User | `LearningModePreviewRequest`, `get_db` | `LearningModePreviewResponse` | `src/frontend/src/pages/Settings/LearningModesTab.tsx` | `tests/test_learning_modes_routes.py` | **Canonical**: Preview mode prompt rendering. |
| `PUT` | `/api/learning-modes/{mode_id}` | `src.api.routers.learning_modes.update_learning_mode` | Staff User | `LearningModeUpdate`, `get_db` | `LearningModeResponse` | `src/frontend/src/pages/Settings/LearningModesTab.tsx` | `tests/test_learning_modes_routes.py` | **Canonical**: Update learning mode. |
| `DELETE` | `/api/learning-modes/{mode_id}` | `src.api.routers.learning_modes.delete_learning_mode` | Staff User | `get_db` | `StatusResponse` | `src/frontend/src/pages/Settings/LearningModesTab.tsx` | `tests/test_learning_modes_routes.py` | **Canonical**: Delete custom learning mode. |
| `GET` | `/api/guardian-profiles/students` | `src.api.routers.guardian_profiles.list_students_with_profiles` | Staff User | `get_db` | `list[StudentWithProfileResponse]` | `src/frontend/src/pages/Settings/LearningModesTab.tsx` | `tests/test_guardian_profiles.py` | **Canonical**: List student guardian profiles. |
| `GET` | `/api/guardian-profiles/students/{student_id}` | `src.api.routers.guardian_profiles.get_student_profile` | Staff User | `get_db` | `GuardianProfileResponse` | `src/frontend/src/components/students/GuardianProfileModal.tsx` | `tests/test_guardian_profiles.py` | **Canonical**: Load student companion configuration. |
| `POST` | `/api/guardian-profiles/students/{student_id}` | `src.api.routers.guardian_profiles.create_student_profile` | Staff User | `GuardianProfileCreate`, `get_db` | `GuardianProfileResponse` | `src/frontend/src/components/students/GuardianProfileModal.tsx` | `tests/test_guardian_profiles.py` | **Canonical**: Create student guardian profile. |
| `PUT` | `/api/guardian-profiles/students/{student_id}` | `src.api.routers.guardian_profiles.update_student_profile` | Staff User | `GuardianProfileUpdate`, `get_db` | `GuardianProfileResponse` | `src/frontend/src/components/students/GuardianProfileModal.tsx` | `tests/test_guardian_profiles.py` | **Canonical**: Update student guardian profile. |
| `DELETE` | `/api/guardian-profiles/students/{student_id}` | `src.api.routers.guardian_profiles.delete_student_profile` | Staff User | `get_db` | `StatusResponse` | Tests / Admin | `tests/test_guardian_profiles.py` | **Canonical**: Reset guardian profile to default. |
| `GET` | `/api/guardian-profiles/templates` | `src.api.routers.guardian_profiles.list_templates` | Staff User | None | `list[TemplateMetadata]` | `src/frontend/src/components/students/GuardianProfileModal.tsx` | `tests/test_guardian_profiles.py` | **Canonical**: List persona templates. |

---

### 6. Analytics, Smartbar & Achievements (`src/api/routers/analytics.py`, `src/api/routers/achievements.py`)

| Method | Path | Handler | Auth / RBAC | Dependencies | Response Model | Frontend Consumers | Test Files | Redundancy Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/analytics/next-symbol` | `src.api.routers.analytics.predict_next_symbol` | Active User | `NextSymbolRequest`, `get_db` | `list[NextSymbolPrediction]` | `src/frontend/src/components/board/Smartbar.tsx` | `tests/test_analytics_api.py` | **Canonical**: Next-symbol Smartbar predictions. |
| `POST` | `/api/analytics/usage` | `src.api.routers.analytics.log_symbol_usage` | Active User | `SymbolUsageRequest`, `get_db` | JSON | `src/frontend/src/components/board/DraggableSymbol.tsx`, `Communication.tsx` | `tests/test_analytics_api.py` | **Canonical**: Record symbol activation analytics. |
| `POST` | `/api/analytics/log` | `src.api.routers.analytics.log_symbol_usage_legacy` | Active User | `SymbolUsageRequest`, `get_db` | JSON | None (0 frontend references) | `tests/test_analytics_api.py` | **Redundant**: Legacy compatibility shim for `/usage`. |
| `GET` | `/api/achievements/` | `src.api.routers.achievements.list_all_achievements` | Staff User | `get_db` | `list[AchievementFullResponse]` | `src/frontend/src/pages/Achievements.tsx` | `tests/test_achievements_query_regressions.py` | **Canonical**: List system and custom achievements. |
| `POST` | `/api/achievements/` | `src.api.routers.achievements.create_achievement` | Staff User | `AchievementCreate`, `get_db` | `AchievementFullResponse` | `src/frontend/src/pages/Achievements.tsx` | `tests/test_achievements_query_regressions.py` | **Canonical**: Create custom badge. |
| `PUT` | `/api/achievements/{achievement_id}` | `src.api.routers.achievements.update_achievement` | Staff User | `AchievementUpdate`, `get_db` | `AchievementFullResponse` | `src/frontend/src/pages/Achievements.tsx` | `tests/test_achievements_query_regressions.py` | **Canonical**: Update badge definition. |
| `DELETE` | `/api/achievements/{achievement_id}` | `src.api.routers.achievements.delete_achievement` | Staff User | `get_db` | None | `src/frontend/src/pages/Achievements.tsx` | `tests/test_achievements_query_regressions.py` | **Canonical**: Delete badge definition. |
| `POST` | `/api/achievements/{achievement_id}/award` | `src.api.routers.achievements.award_achievement` | Staff User | `AchievementAward`, `get_db` | `AchievementResponse` | `src/frontend/src/pages/Achievements.tsx` | `tests/test_achievements_query_regressions.py` | **Canonical**: Manually award badge to student. |
| `GET` | `/api/achievements/user/{user_id}` | `src.api.routers.achievements.get_user_achievements` | Staff / Self | `get_db` | `list[AchievementResponse]` | `src/frontend/src/pages/Achievements.tsx` | `tests/test_achievements_query_regressions.py` | **Canonical**: List earned badges for student. |
| `POST` | `/api/achievements/user/{user_id}/check` | `src.api.routers.achievements.check_achievements` | Staff / Self | `get_db` | `list[AchievementResponse]` | `src/frontend/src/pages/Achievements.tsx` | `tests/test_achievements_query_regressions.py` | **Canonical**: Evaluate and award pending badges. |
| `GET` | `/api/achievements/user/{user_id}/points` | `src.api.routers.achievements.get_user_points` | Staff / Self | `get_db` | `int` | `src/frontend/src/pages/Achievements.tsx` | `tests/test_achievements_query_regressions.py` | **Canonical**: Total user points. |
| `GET` | `/api/achievements/leaderboard` | `src.api.routers.achievements.get_leaderboard` | Active User | `get_db`, `limit` | `list[LeaderboardEntry]` | `src/frontend/src/pages/Achievements.tsx` | `tests/test_achievements_query_regressions.py` | **Canonical**: Gamification leaderboard ranking. |

---

### 7. AI Providers & Settings (`src/api/routers/settings.py`, `src/api/routers/providers.py`)

| Method | Path | Handler | Auth / RBAC | Dependencies | Response Model | Frontend Consumers | Test Files | Redundancy Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/settings/ai` | `src.api.routers.settings.get_ai_settings` | Active User | `get_db` | `AISettingsResponse` | `src/frontend/src/pages/Settings/AiProviderTab.tsx` | `tests/test_settings_routes.py` | **Canonical**: Active AI provider and configured models. |
| `PUT` | `/api/settings/ai` | `src.api.routers.settings.update_ai_settings` | Admin Only | `AISettingsUpdate`, `get_db` | `AISettingsResponse` | `src/frontend/src/pages/Settings/AiProviderTab.tsx` | `tests/test_settings_routes.py` | **Canonical**: Admin update of AI provider configuration. |
| `GET` | `/api/settings/ai/models/groq` | `src.api.routers.settings.get_groq_models` | Admin Only | `X-Groq-API-Key`, `get_db` | `list[str]` | `src/frontend/src/store/settingsStore.ts:139` | `tests/test_settings_routes.py` | **Canonical**: List available Groq models with request/persisted key. |
| `GET` | `/api/settings/ai/models/ollama` | `src.api.routers.settings.get_ollama_models` | Admin Only | `get_db` | `list[str]` | `src/frontend/src/store/settingsStore.ts:115` | `tests/test_settings_routes.py` | **Canonical**: List local Ollama models. |
| `GET` | `/api/settings/ai/models/openrouter` | `src.api.routers.settings.get_openrouter_models` | Admin Only | `X-OpenRouter-API-Key`, `get_db` | `list[str]` | `src/frontend/src/store/settingsStore.ts:123` | `tests/test_settings_routes.py` | **Canonical**: List OpenRouter models. |
| `GET` | `/api/settings/ai/models/lmstudio` | `src.api.routers.settings.get_lmstudio_models` | Admin Only | `get_db` | `list[str]` | `src/frontend/src/store/settingsStore.ts:131` | `tests/test_settings_routes.py` | **Canonical**: List local LM Studio models. |
| `GET` | `/api/providers/ai/models/lmstudio` | `src.api.routers.providers.get_lmstudio_models` | Active User | None | JSON | None (0 frontend references) | `tests/test_providers_routes.py` | **Redundant**: Orphaned duplicate of `/settings/ai/models/lmstudio`. |
| `GET` | `/api/providers/health` | `src.api.routers.providers.providers_health` | Active User | `get_db` | JSON | `src/frontend/src/pages/Settings/AiProviderTab.tsx` | `tests/test_providers_routes.py` | **Canonical**: Provider reachability check. |
| `GET` | `/api/providers/voice-status` | `src.api.routers.providers.voice_status` | Active User | `get_db` | JSON | `src/frontend/src/pages/Settings/VoiceTab.tsx` | `tests/test_providers_routes.py` | **Canonical**: Status of local Whisper STT runtime. |
| `GET` | `/api/settings/ui` | `src.api.routers.settings.get_ui_language` | Active User | `get_db` | `UILanguageResponse` | `src/frontend/src/components/LanguageSwitcher.tsx` | `tests/test_settings_routes.py` | **Canonical**: UI language preference. |
| `PUT` | `/api/settings/ui` | `src.api.routers.settings.update_ui_language` | Active User | `UILanguageUpdate`, `get_db` | `UILanguageResponse` | `src/frontend/src/components/LanguageSwitcher.tsx` | `tests/test_settings_routes.py` | **Canonical**: Update UI language preference. |

---

### 8. Real-Time, Collaboration & Data Transfer (`src/api/routers/collab.py`, `src/api/routers/notifications.py`, `src/api/routers/export_import.py`)

| Method | Path | Handler | Auth / RBAC | Dependencies | Response Model | Frontend Consumers | Test Files | Redundancy Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `WEBSOCKET` | `/api/collab/boards/{board_id}` | `src.api.routers.collab.board_channel` | Active User (`aac-auth` subprotocol) | `get_db` | WebSocket stream | `src/frontend/src/pages/BoardEditor.tsx` | `tests/test_collab_ws.py` | **Canonical**: Real-time multi-user board collaboration. |
| `GET` | `/api/notifications/stream` | `src.api.routers.notifications.notifications_stream` | Active User (Bearer Header) | None (Short-lived DB) | `text/event-stream` | `src/frontend/src/components/NotificationsPanel.tsx` | `tests/test_notifications.py` | **Canonical**: SSE notification event stream. |
| `GET` | `/api/notifications` | `src.api.routers.notifications.get_notifications` | Staff / Self | `get_db`, `skip`, `limit` | JSON | `src/frontend/src/components/NotificationsPanel.tsx` | `tests/test_notifications.py` | **Canonical**: Paginated user notifications. |
| `PUT` | `/api/notifications/{notification_id}/read` | `src.api.routers.notifications.mark_notification_read` | Staff / Self | `get_db` | `StatusResponse` | `src/frontend/src/components/NotificationsPanel.tsx` | `tests/test_notifications.py` | **Canonical**: Mark notification as read. |
| `PUT` | `/api/notifications/read-all` | `src.api.routers.notifications.mark_all_notifications_read` | Active User | `get_db` | JSON | `src/frontend/src/components/NotificationsPanel.tsx` | `tests/test_notifications.py` | **Canonical**: Mark all notifications as read. |
| `GET` | `/api/data/export` | `src.api.routers.export_import.export_data` | Staff / Self | `get_db`, `username` | `ExportPayload` | `src/frontend/src/pages/Settings/DataManagementTab.tsx` | `tests/test_export_import_v2.py` | **Canonical**: HMAC-signed user data export. |
| `POST` | `/api/data/import` | `src.api.routers.export_import.import_data` | Active User | `get_db` (10MB bounded body) | `ImportResponse` | `src/frontend/src/pages/Settings/DataManagementTab.tsx` | `tests/test_export_import_v2.py` | **Canonical**: Authenticated HMAC import with schema validation. |
