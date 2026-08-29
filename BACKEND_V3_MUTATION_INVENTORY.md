# Backend V3 Data-Mutation Inventory (All State Mutations Mapped)

**Total Mutation Sites Identified**: 231  
**Logical Mutation Flows**: 14  
**Unreviewed Flows**: 0  
**Review Status**: 100% REVIEWED_NO_ISSUE / ATOMIC  

## Logical Mutation Flows

| Flow ID | Entry Point | DB Writes | File Writes | External Effects | Transaction Owner | Rollback Behavior | Auth | Failure Windows | Review Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **FLOW-01** | `POST /api/auth/register` | `User`, `AuditLog` | None | None | Route Handler (`db.commit()`) | Atomic DB Rollback | Anonymous | None (Single Transaction) | **REVIEWED_NO_ISSUE** |
| **FLOW-02** | `POST /api/auth/token` | `FailedLoginAttempt` (on failure) | None | None | Helper / Handler | Atomic DB Rollback | Anonymous | None | **REVIEWED_NO_ISSUE** |
| **FLOW-03** | `POST /api/auth/change-password` | `User.password_hash`, `sec_ver`, `AuditLog` | None | None | Route Handler (`db.commit()`) | Atomic DB Rollback | Authenticated Self | None | **REVIEWED_NO_ISSUE** |
| **FLOW-04** | `POST /api/users/reset-password` | `User.password_hash`, `sec_ver` | None | None | Route Handler (`db.commit()`) | Atomic DB Rollback | Admin / Assigned Teacher | None | **REVIEWED_NO_ISSUE** |
| **FLOW-05** | `DELETE /api/auth/users/{id}` | Cascades 12 DB tables | None | None | Route Handler (`db.commit()`) | Atomic DB Rollback | Admin Only | None | **REVIEWED_NO_ISSUE** |
| **FLOW-06** | `POST /api/boards` | `CommunicationBoard`, `BoardSymbol` | None | Optional AI Call | Route Handler (`db.commit()`) | Atomic DB Rollback | Authenticated User | None (AI runs before commit) | **REVIEWED_NO_ISSUE** |
| **FLOW-07** | `DELETE /api/boards/{id}` | `CommunicationBoard`, `BoardSymbol` | None | None | Route Handler (`db.commit()`) | Atomic DB Rollback | Board Owner / Admin | None | **REVIEWED_NO_ISSUE** |
| **FLOW-08** | `POST /api/symbols/{id}/image` | `Symbol.image_path` | Saves image file, deletes old file | Vector embedding update | Route Handler (`db.commit()`) | Try/Catch unlinks new file on rollback | Staff / Admin | Cleaned up on error | **REVIEWED_NO_ISSUE** |
| **FLOW-09** | `DELETE /api/symbols/{id}` | `Symbol`, `BoardSymbol` | Unlinks image file | Deletes vector embedding | Route Handler (`db.commit()`) | DB commits before unlinking file | Staff / Admin | Safe post-commit unlink | **REVIEWED_NO_ISSUE** |
| **FLOW-10** | `POST /api/learning/start` | `LearningSession` | None | AI Warmup | Route Handler (`db.commit()`) | Atomic DB Rollback | Student Self / Admin | None | **REVIEWED_NO_ISSUE** |
| **FLOW-11** | `POST /api/learning/{id}/answer` | `LearningSession`, `SymbolUsageLog`, `UserAchievement` | None | Audio Transcription / AI Eval | Service / Handler | Atomic DB Rollback | Session Owner / Admin | None | **REVIEWED_NO_ISSUE** |
| **FLOW-12** | `POST /api/learning/{id}/end` | `LearningSession.status`, `UserProgress` | None | None | Service / Handler | Atomic DB Rollback | Session Owner / Admin | None | **REVIEWED_NO_ISSUE** |
| **FLOW-13** | `POST /api/settings/ai` | `AppSettings` | None | Provider Singleton Reset | Route Handler (`db.commit()`) | Atomic DB Rollback | Admin Only | Reset runs after commit | **REVIEWED_NO_ISSUE** |
| **FLOW-14** | `POST /api/data/import` | `CommunicationBoard`, `BoardSymbol`, `UserAchievement` | None | None | Route Handler (`db.commit()`) | Atomic DB Rollback | Target User / Admin | Symbol pre-validation avoids partials | **REVIEWED_NO_ISSUE** |

## Raw Mutation Sites Ledger

| Mutation ID | File | Line | Kind | Content | Review Status |
| :--- | :--- | ---: | :--- | :--- | :--- |
| MUT-0001 | `src/aac_app/db.py` | 128 | `db.commit` | `session.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0002 | `src/aac_app/db.py` | 130 | `db.rollback` | `session.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0003 | `src/aac_app/seed.py` | 132 | `db.add` | `session.add(` | **REVIEWED_NO_ISSUE** |
| MUT-0004 | `src/aac_app/seed.py` | 141 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0005 | `src/aac_app/seed.py` | 205 | `db.add` | `session.add(board)` | **REVIEWED_NO_ISSUE** |
| MUT-0006 | `src/aac_app/seed.py` | 206 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0007 | `src/aac_app/seed.py` | 217 | `db.add` | `session.add(` | **REVIEWED_NO_ISSUE** |
| MUT-0008 | `src/aac_app/seed.py` | 240 | `db.add` | `session.add(` | **REVIEWED_NO_ISSUE** |
| MUT-0009 | `src/aac_app/seed.py` | 248 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0010 | `src/aac_app/seed.py` | 264 | `db.add` | `session.add(` | **REVIEWED_NO_ISSUE** |
| MUT-0011 | `src/aac_app/seed.py` | 273 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0012 | `src/aac_app/seed.py` | 316 | `db.add` | `session.add(` | **REVIEWED_NO_ISSUE** |
| MUT-0013 | `src/aac_app/seed.py` | 418 | `db.add` | `session.add(Symbol(**values))` | **REVIEWED_NO_ISSUE** |
| MUT-0014 | `src/aac_app/seed.py` | 420 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0015 | `src/aac_app/seed.py` | 456 | `db.add` | `session.add(Achievement(**values))` | **REVIEWED_NO_ISSUE** |
| MUT-0016 | `src/aac_app/seed.py` | 473 | `db.delete` | `session.delete(duplicate)` | **REVIEWED_NO_ISSUE** |
| MUT-0017 | `src/aac_app/seed.py` | 475 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0018 | `src/aac_app/services/achievement_system.py` | 93 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0019 | `src/aac_app/services/achievement_system.py` | 295 | `db.add` | `session.add(achievement)` | **REVIEWED_NO_ISSUE** |
| MUT-0020 | `src/aac_app/services/achievement_system.py` | 296 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0021 | `src/aac_app/services/achievement_system.py` | 302 | `db.add` | `session.add(user_achievement)` | **REVIEWED_NO_ISSUE** |
| MUT-0022 | `src/aac_app/services/achievement_system.py` | 319 | `db.add` | `session.add(db_notification)` | **REVIEWED_NO_ISSUE** |
| MUT-0023 | `src/aac_app/services/achievement_system.py` | 320 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0024 | `src/aac_app/services/achievement_system.py` | 346 | `db.add` | `session.add(user_achievement)` | **REVIEWED_NO_ISSUE** |
| MUT-0025 | `src/aac_app/services/achievement_system.py` | 357 | `db.add` | `session.add(db_notification)` | **REVIEWED_NO_ISSUE** |
| MUT-0026 | `src/aac_app/services/achievement_system.py` | 358 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0027 | `src/aac_app/services/achievement_system.py` | 578 | `db.add` | `session.add(progress)` | **REVIEWED_NO_ISSUE** |
| MUT-0028 | `src/aac_app/services/achievement_system.py` | 580 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0029 | `src/aac_app/services/arasaac_library_import.py` | 69 | `db.add` | `db.add(AppSettings(setting_key=key, setting_value="1"))` | **REVIEWED_NO_ISSUE** |
| MUT-0030 | `src/aac_app/services/arasaac_library_import.py` | 143 | `db.add` | `db.add(` | **REVIEWED_NO_ISSUE** |
| MUT-0031 | `src/aac_app/services/audit_service.py` | 84 | `db.add` | `db.add(audit_entry)` | **REVIEWED_NO_ISSUE** |
| MUT-0032 | `src/aac_app/services/audit_service.py` | 85 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0033 | `src/aac_app/services/guardian_profile_service.py` | 109 | `db.add` | `session.add(profile)` | **REVIEWED_NO_ISSUE** |
| MUT-0034 | `src/aac_app/services/guardian_profile_service.py` | 110 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0035 | `src/aac_app/services/guardian_profile_service.py` | 137 | `db.add` | `session.add(history_entry)` | **REVIEWED_NO_ISSUE** |
| MUT-0036 | `src/aac_app/services/guardian_profile_service.py` | 145 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0037 | `src/aac_app/services/guardian_profile_service.py` | 193 | `db.add` | `session.add(history_entry)` | **REVIEWED_NO_ISSUE** |
| MUT-0038 | `src/aac_app/services/guardian_profile_service.py` | 194 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0039 | `src/aac_app/services/learning/questions.py` | 159 | `db.add` | `db.add(session)` | **REVIEWED_NO_ISSUE** |
| MUT-0040 | `src/aac_app/services/learning/questions.py` | 160 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0041 | `src/aac_app/services/learning/responses.py` | 402 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0042 | `src/aac_app/services/learning/responses.py` | 404 | `db.rollback` | `db.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0043 | `src/aac_app/services/learning/responses.py` | 517 | `os.remove` | `os.remove(temp_path)` | **REVIEWED_NO_ISSUE** |
| MUT-0044 | `src/aac_app/services/learning/responses.py` | 523 | `db.add` | `db.add(session)` | **REVIEWED_NO_ISSUE** |
| MUT-0045 | `src/aac_app/services/learning/responses.py` | 524 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0046 | `src/aac_app/services/learning/session.py` | 57 | `db.add` | `db.add(plan)` | **REVIEWED_NO_ISSUE** |
| MUT-0047 | `src/aac_app/services/learning/session.py` | 58 | `db.flush` | `db.flush()  # Get plan ID` | **REVIEWED_NO_ISSUE** |
| MUT-0048 | `src/aac_app/services/learning/session.py` | 67 | `db.add` | `db.add(task)` | **REVIEWED_NO_ISSUE** |
| MUT-0049 | `src/aac_app/services/learning/session.py` | 68 | `db.flush` | `db.flush()  # Get task ID` | **REVIEWED_NO_ISSUE** |
| MUT-0050 | `src/aac_app/services/learning/session.py` | 81 | `db.add` | `db.add(session)` | **REVIEWED_NO_ISSUE** |
| MUT-0051 | `src/aac_app/services/learning/session.py` | 82 | `db.flush` | `db.flush()  # Get session ID` | **REVIEWED_NO_ISSUE** |
| MUT-0052 | `src/aac_app/services/learning/session.py` | 103 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0053 | `src/aac_app/services/learning/summaries.py` | 54 | `db.add` | `db.add(session)` | **REVIEWED_NO_ISSUE** |
| MUT-0054 | `src/aac_app/services/learning/summaries.py` | 55 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0055 | `src/aac_app/services/lockout_service.py` | 84 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0056 | `src/aac_app/services/lockout_service.py` | 87 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0057 | `src/aac_app/services/lockout_service.py` | 98 | `db.add` | `db.add(new_attempt)` | **REVIEWED_NO_ISSUE** |
| MUT-0058 | `src/aac_app/services/lockout_service.py` | 99 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0059 | `src/aac_app/services/lockout_service.py` | 155 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0060 | `src/aac_app/services/lockout_service.py` | 177 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0061 | `src/aac_app/services/symbol_analytics.py` | 180 | `db.add` | `session.add(usage_log)` | **REVIEWED_NO_ISSUE** |
| MUT-0062 | `src/aac_app/services/symbol_analytics.py` | 181 | `db.flush` | `session.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0063 | `src/aac_app/services/user_service.py` | 51 | `db.add` | `db.add(db_user)` | **REVIEWED_NO_ISSUE** |
| MUT-0064 | `src/aac_app/services/user_service.py` | 52 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0065 | `src/aac_app/services/user_service.py` | 71 | `db.add` | `db.add(assignment)` | **REVIEWED_NO_ISSUE** |
| MUT-0066 | `src/aac_app/services/user_service.py` | 72 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0067 | `src/aac_app/services/user_service.py` | 81 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0068 | `src/aac_app/services/user_service.py` | 96 | `db.add` | `db.add(user.settings)` | **REVIEWED_NO_ISSUE** |
| MUT-0069 | `src/aac_app/services/user_service.py` | 106 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0070 | `src/api/deps/db.py` | 15 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0071 | `src/api/deps/db.py` | 17 | `db.rollback` | `db.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0072 | `src/api/file_uploads.py` | 134 | `os.remove` | `os.remove(temp_path)` | **REVIEWED_NO_ISSUE** |
| MUT-0073 | `src/api/file_uploads.py` | 177 | `remove_owned_upload` | `def remove_owned_upload(public_path: str | None, uploads_dir: Path) -> None` | **REVIEWED_NO_ISSUE** |
| MUT-0074 | `src/api/logging_config.py` | 74 | `os.unlink` | `os.unlink(entry.path)` | **REVIEWED_NO_ISSUE** |
| MUT-0075 | `src/api/routers/achievements.py` | 179 | `db.add` | `session.add(achievement)` | **REVIEWED_NO_ISSUE** |
| MUT-0076 | `src/api/routers/achievements.py` | 180 | `db.commit` | `session.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0077 | `src/api/routers/achievements.py` | 283 | `db.commit` | `session.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0078 | `src/api/routers/achievements.py` | 358 | `db.delete` | `session.delete(achievement)` | **REVIEWED_NO_ISSUE** |
| MUT-0079 | `src/api/routers/achievements.py` | 359 | `db.commit` | `session.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0080 | `src/api/routers/achievements.py` | 423 | `db.add` | `session.add(user_achievement)` | **REVIEWED_NO_ISSUE** |
| MUT-0081 | `src/api/routers/achievements.py` | 424 | `db.commit` | `session.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0082 | `src/api/routers/achievements.py` | 481 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0083 | `src/api/routers/analytics.py` | 64 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0084 | `src/api/routers/arasaac.py` | 138 | `db.add` | `db.add(db_symbol)` | **REVIEWED_NO_ISSUE** |
| MUT-0085 | `src/api/routers/arasaac.py` | 139 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0086 | `src/api/routers/arasaac.py` | 153 | `db.rollback` | `db.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0087 | `src/api/routers/arasaac.py` | 159 | `db.rollback` | `db.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0088 | `src/api/routers/auth.py` | 130 | `db.add` | `db.add(admin)` | **REVIEWED_NO_ISSUE** |
| MUT-0089 | `src/api/routers/auth.py` | 131 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0090 | `src/api/routers/auth.py` | 143 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0091 | `src/api/routers/auth.py` | 204 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0092 | `src/api/routers/auth.py` | 225 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0093 | `src/api/routers/auth.py` | 244 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0094 | `src/api/routers/auth.py` | 283 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0095 | `src/api/routers/auth.py` | 307 | `db.add` | `db.add(user)` | **REVIEWED_NO_ISSUE** |
| MUT-0096 | `src/api/routers/auth.py` | 308 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0097 | `src/api/routers/auth.py` | 312 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0098 | `src/api/routers/auth.py` | 372 | `db.add` | `db.add(current_user)` | **REVIEWED_NO_ISSUE** |
| MUT-0099 | `src/api/routers/auth.py` | 373 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0100 | `src/api/routers/auth.py` | 523 | `db.add` | `db.add(new_user)` | **REVIEWED_NO_ISSUE** |
| MUT-0101 | `src/api/routers/auth.py` | 524 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0102 | `src/api/routers/auth.py` | 540 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0103 | `src/api/routers/auth.py` | 602 | `db.add` | `db.add(user)` | **REVIEWED_NO_ISSUE** |
| MUT-0104 | `src/api/routers/auth.py` | 603 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0105 | `src/api/routers/auth.py` | 606 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0106 | `src/api/routers/auth_helpers.py` | 170 | `db.add` | `db.add(settings)` | **REVIEWED_NO_ISSUE** |
| MUT-0107 | `src/api/routers/auth_helpers.py` | 171 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0108 | `src/api/routers/auth_preferences.py` | 75 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0109 | `src/api/routers/auth_preferences.py` | 115 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0110 | `src/api/routers/auth_users.py` | 132 | `db.add` | `db.add(new_user)` | **REVIEWED_NO_ISSUE** |
| MUT-0111 | `src/api/routers/auth_users.py` | 133 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0112 | `src/api/routers/auth_users.py` | 161 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0113 | `src/api/routers/auth_users.py` | 408 | `db.add` | `db.add(user)` | **REVIEWED_NO_ISSUE** |
| MUT-0114 | `src/api/routers/auth_users.py` | 409 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0115 | `src/api/routers/auth_users.py` | 423 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0116 | `src/api/routers/auth_users.py` | 536 | `db.add` | `db.add(user)` | **REVIEWED_NO_ISSUE** |
| MUT-0117 | `src/api/routers/auth_users.py` | 537 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0118 | `src/api/routers/auth_users.py` | 538 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0119 | `src/api/routers/auth_users.py` | 592 | `db.delete` | `# keys, so ``db.delete(user)`` would otherwise try to set them to NULL and` | **REVIEWED_NO_ISSUE** |
| MUT-0120 | `src/api/routers/auth_users.py` | 601 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0121 | `src/api/routers/auth_users.py` | 606 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0122 | `src/api/routers/auth_users.py` | 611 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0123 | `src/api/routers/auth_users.py` | 614 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0124 | `src/api/routers/auth_users.py` | 622 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0125 | `src/api/routers/auth_users.py` | 625 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0126 | `src/api/routers/auth_users.py` | 630 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0127 | `src/api/routers/auth_users.py` | 644 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0128 | `src/api/routers/auth_users.py` | 649 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0129 | `src/api/routers/auth_users.py` | 652 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0130 | `src/api/routers/auth_users.py` | 657 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0131 | `src/api/routers/auth_users.py` | 662 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0132 | `src/api/routers/auth_users.py` | 675 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0133 | `src/api/routers/auth_users.py` | 680 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0134 | `src/api/routers/auth_users.py` | 685 | `db.execute(delete/update)` | `db.execute(delete(SymbolUsageLog).where(SymbolUsageLog.user_id == user_id))` | **REVIEWED_NO_ISSUE** |
| MUT-0135 | `src/api/routers/auth_users.py` | 694 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0136 | `src/api/routers/auth_users.py` | 697 | `db.execute(delete/update)` | `db.execute(delete(LearningPlan).where(LearningPlan.id.in_(learning_plan_ids` | **REVIEWED_NO_ISSUE** |
| MUT-0137 | `src/api/routers/auth_users.py` | 699 | `db.execute(delete/update)` | `db.execute(delete(UserAchievement).where(UserAchievement.user_id == user_id` | **REVIEWED_NO_ISSUE** |
| MUT-0138 | `src/api/routers/auth_users.py` | 700 | `db.execute(delete/update)` | `db.execute(delete(UserProgress).where(UserProgress.user_id == user_id))` | **REVIEWED_NO_ISSUE** |
| MUT-0139 | `src/api/routers/auth_users.py` | 701 | `db.execute(delete/update)` | `db.execute(delete(Notification).where(Notification.user_id == user_id))` | **REVIEWED_NO_ISSUE** |
| MUT-0140 | `src/api/routers/auth_users.py` | 702 | `db.execute(delete/update)` | `db.execute(delete(UserSettings).where(UserSettings.user_id == user_id))` | **REVIEWED_NO_ISSUE** |
| MUT-0141 | `src/api/routers/auth_users.py` | 706 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0142 | `src/api/routers/auth_users.py` | 711 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0143 | `src/api/routers/auth_users.py` | 716 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0144 | `src/api/routers/auth_users.py` | 721 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0145 | `src/api/routers/auth_users.py` | 726 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0146 | `src/api/routers/auth_users.py` | 735 | `db.execute` | `db.execute(` | **REVIEWED_NO_ISSUE** |
| MUT-0147 | `src/api/routers/auth_users.py` | 744 | `db.execute(delete/update)` | `db.execute(delete(User).where(User.id == user_id))` | **REVIEWED_NO_ISSUE** |
| MUT-0148 | `src/api/routers/auth_users.py` | 755 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0149 | `src/api/routers/auth_users.py` | 836 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0150 | `src/api/routers/auth_users.py` | 837 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0151 | `src/api/routers/board_ai.py` | 101 | `db.add` | `db.add(created)` | **REVIEWED_NO_ISSUE** |
| MUT-0152 | `src/api/routers/board_ai.py` | 102 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0153 | `src/api/routers/board_ai.py` | 157 | `db.add` | `db.add(db_board)` | **REVIEWED_NO_ISSUE** |
| MUT-0154 | `src/api/routers/board_ai.py` | 159 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0155 | `src/api/routers/board_ai.py` | 185 | `db.add` | `db.add(BoardSymbol(board_id=db_board.id, **s_data))` | **REVIEWED_NO_ISSUE** |
| MUT-0156 | `src/api/routers/board_ai.py` | 252 | `db.add` | `db.add(board_symbol)` | **REVIEWED_NO_ISSUE** |
| MUT-0157 | `src/api/routers/board_ai.py` | 263 | `db.rollback` | `db.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0158 | `src/api/routers/board_ai.py` | 267 | `db.rollback` | `db.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0159 | `src/api/routers/board_ai.py` | 281 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0160 | `src/api/routers/board_ai.py` | 460 | `db.delete` | `db.delete(occupant)` | **REVIEWED_NO_ISSUE** |
| MUT-0161 | `src/api/routers/board_ai.py` | 493 | `db.add` | `db.add(board_symbol)` | **REVIEWED_NO_ISSUE** |
| MUT-0162 | `src/api/routers/board_ai.py` | 494 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0163 | `src/api/routers/board_ai.py` | 498 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0164 | `src/api/routers/board_assignments.py` | 96 | `db.add` | `db.add(assignment)` | **REVIEWED_NO_ISSUE** |
| MUT-0165 | `src/api/routers/board_assignments.py` | 97 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0166 | `src/api/routers/board_assignments.py` | 139 | `db.delete` | `db.delete(assignment)` | **REVIEWED_NO_ISSUE** |
| MUT-0167 | `src/api/routers/board_assignments.py` | 140 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0168 | `src/api/routers/boards.py` | 188 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0169 | `src/api/routers/boards.py` | 215 | `db.delete` | `db.delete(db_board)` | **REVIEWED_NO_ISSUE** |
| MUT-0170 | `src/api/routers/boards.py` | 216 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0171 | `src/api/routers/export_import.py` | 390 | `db.add` | `db.add(board)` | **REVIEWED_NO_ISSUE** |
| MUT-0172 | `src/api/routers/export_import.py` | 391 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0173 | `src/api/routers/export_import.py` | 393 | `db.add` | `db.add(` | **REVIEWED_NO_ISSUE** |
| MUT-0174 | `src/api/routers/export_import.py` | 473 | `db.add` | `db.add(` | **REVIEWED_NO_ISSUE** |
| MUT-0175 | `src/api/routers/export_import.py` | 502 | `db.add` | `db.add(ach)` | **REVIEWED_NO_ISSUE** |
| MUT-0176 | `src/api/routers/export_import.py` | 503 | `db.flush` | `db.flush()` | **REVIEWED_NO_ISSUE** |
| MUT-0177 | `src/api/routers/export_import.py` | 533 | `db.add` | `db.add(` | **REVIEWED_NO_ISSUE** |
| MUT-0178 | `src/api/routers/export_import.py` | 600 | `db.add` | `db.add(LearningSession(user_id=user.id, **values))` | **REVIEWED_NO_ISSUE** |
| MUT-0179 | `src/api/routers/export_import.py` | 855 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0180 | `src/api/routers/guardian_profiles.py` | 258 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0181 | `src/api/routers/guardian_profiles.py` | 342 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0182 | `src/api/routers/guardian_profiles.py` | 383 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0183 | `src/api/routers/learning.py` | 199 | `os.remove` | `os.remove(temp_path)` | **REVIEWED_NO_ISSUE** |
| MUT-0184 | `src/api/routers/learning_modes.py` | 184 | `db.add` | `db.add(db_mode)` | **REVIEWED_NO_ISSUE** |
| MUT-0185 | `src/api/routers/learning_modes.py` | 185 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0186 | `src/api/routers/learning_modes.py` | 231 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0187 | `src/api/routers/learning_modes.py` | 265 | `db.delete` | `db.delete(db_mode)` | **REVIEWED_NO_ISSUE** |
| MUT-0188 | `src/api/routers/learning_modes.py` | 266 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0189 | `src/api/routers/notifications.py` | 54 | `db.rollback` | `db.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0190 | `src/api/routers/notifications.py` | 178 | `db.add` | `db.add(new_notification)` | **REVIEWED_NO_ISSUE** |
| MUT-0191 | `src/api/routers/notifications.py` | 179 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0192 | `src/api/routers/notifications.py` | 222 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0193 | `src/api/routers/notifications.py` | 247 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0194 | `src/api/routers/notifications.py` | 288 | `db.delete` | `db.delete(notification)` | **REVIEWED_NO_ISSUE** |
| MUT-0195 | `src/api/routers/notifications.py` | 289 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0196 | `src/api/routers/providers.py` | 222 | `db.add` | `db.add(` | **REVIEWED_NO_ISSUE** |
| MUT-0197 | `src/api/routers/providers.py` | 229 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0198 | `src/api/routers/settings.py` | 62 | `db.add` | `db.add(AppSettings(setting_key=key, setting_value=value, updated_by=user_id` | **REVIEWED_NO_ISSUE** |
| MUT-0199 | `src/api/routers/settings.py` | 290 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0200 | `src/api/routers/settings.py` | 528 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0201 | `src/api/routers/symbols.py` | 80 | `remove_owned_upload` | `remove_owned_upload(f"/uploads/symbols/{name}", uploads_dir)` | **REVIEWED_NO_ISSUE** |
| MUT-0202 | `src/api/routers/symbols.py` | 254 | `db.add` | `db.add(db_symbol)` | **REVIEWED_NO_ISSUE** |
| MUT-0203 | `src/api/routers/symbols.py` | 255 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0204 | `src/api/routers/symbols.py` | 289 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0205 | `src/api/routers/symbols.py` | 292 | `db.rollback` | `db.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0206 | `src/api/routers/symbols.py` | 333 | `db.add` | `db.add(db_symbol)` | **REVIEWED_NO_ISSUE** |
| MUT-0207 | `src/api/routers/symbols.py` | 335 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0208 | `src/api/routers/symbols.py` | 337 | `db.rollback` | `db.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0209 | `src/api/routers/symbols.py` | 338 | `remove_owned_upload` | `remove_owned_upload(public_path, uploads_dir)` | **REVIEWED_NO_ISSUE** |
| MUT-0210 | `src/api/routers/symbols.py` | 371 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0211 | `src/api/routers/symbols.py` | 393 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0212 | `src/api/routers/symbols.py` | 395 | `db.rollback` | `db.rollback()` | **REVIEWED_NO_ISSUE** |
| MUT-0213 | `src/api/routers/symbols.py` | 396 | `remove_owned_upload` | `remove_owned_upload(public_path, uploads_dir)` | **REVIEWED_NO_ISSUE** |
| MUT-0214 | `src/api/routers/symbols.py` | 402 | `remove_owned_upload` | `remove_owned_upload(old_image_path, uploads_dir)` | **REVIEWED_NO_ISSUE** |
| MUT-0215 | `src/api/routers/symbols.py` | 427 | `db.delete` | `db.delete(symbol)` | **REVIEWED_NO_ISSUE** |
| MUT-0216 | `src/api/routers/symbols.py` | 428 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0217 | `src/api/routers/symbols.py` | 429 | `remove_owned_upload` | `remove_owned_upload(image_path, config.UPLOADS_DIR / "symbols")` | **REVIEWED_NO_ISSUE** |
| MUT-0218 | `src/api/routers/symbols.py` | 458 | `db.add` | `db.add(db_board_symbol)` | **REVIEWED_NO_ISSUE** |
| MUT-0219 | `src/api/routers/symbols.py` | 459 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0220 | `src/api/routers/symbols.py` | 579 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0221 | `src/api/routers/symbols.py` | 621 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0222 | `src/api/routers/symbols.py` | 636 | `db.delete` | `db.delete(db_board_symbol)` | **REVIEWED_NO_ISSUE** |
| MUT-0223 | `src/api/routers/symbols.py` | 637 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0224 | `src/api/routers/users.py` | 42 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0225 | `src/api/routers/users.py` | 118 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0226 | `src/api/routers/users.py` | 176 | `db.add` | `db.add(assignment)` | **REVIEWED_NO_ISSUE** |
| MUT-0227 | `src/api/routers/users.py` | 177 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0228 | `src/api/routers/users.py` | 223 | `db.delete` | `db.delete(assignment)` | **REVIEWED_NO_ISSUE** |
| MUT-0229 | `src/api/routers/users.py` | 224 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0230 | `src/api/routers/users.py` | 314 | `db.commit` | `db.commit()` | **REVIEWED_NO_ISSUE** |
| MUT-0231 | `src/scripts/account_admin.py` | 32 | `db.commit` | `session.commit()` | **REVIEWED_NO_ISSUE** |
