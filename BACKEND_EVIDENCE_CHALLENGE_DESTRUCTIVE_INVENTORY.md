# Authoritative Destructive-Operation Inventory

**Purpose**: Reconcile the audit chain's mutually inconsistent destructive-operation counts — **5** (Stage B Second-Wave Audit §3), **6** (V3 Proof of Coverage §10), **16 + 1** (Final Verification Ledger CLM-19 / VRD-19) — into one authoritative, member-listed inventory derived independently from current source.

**Method**: full enumeration of all `DELETE` routes from the live route table + all replace/overwrite/reset endpoints from code, each verified by reading the handler. **No code modified.**

---

## 1. The Three Prior Figures — Exact Origin and Members

| Figure | Source artifact | Members listed? | Actual members |
| :--- | :--- | :--- | :--- |
| **5** | `BACKEND_SECOND_WAVE_AUDIT.md` §3 table | YES (5 rows) | Delete User, Delete Symbol, Replace Image, Delete Board, Reset Password |
| **6** | `BACKEND_AUDIT_V3_PROOF_OF_COVERAGE.md` §10 | YES (6 items) | Delete User, Delete Symbol, Replace Symbol Image, Delete Board, Reset Password, Import Data |
| **16 + 1** | `BACKEND_FINAL_VERIFICATION_CLAIM_LEDGER.md` CLM-19; `BACKEND_FINAL_VERDICT_TABLE.md` VRD-19 | **NO — asserted without a member list** | (was never enumerated in the artifact) |

The "52 sites" figure (V3 Proof §1) is a site-level aggregation whose composition is **not documented**; it is not independently reproducible as stated (see §4).

---

## 2. Authoritative Inventory — 16 API Operations + 1 Startup Repair Flow

### Category A — Data-destroying DELETE endpoints (10)

| # | Method + Path | Handler (module:line range) | What is destroyed | Auth | Commit / rollback behavior |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `DELETE /api/auth/users/{user_id}` | `auth_users.delete_user` (auth_users.py:543–756) | User + 12 dependent tables (SymbolUsageLog, LearningPlan/Task, UserAchievement, UserProgress, Notification, UserSettings, StudentTeacher links, board ownership, etc.) via `db.execute(delete(...))` @685–744; `db.delete(User)` @744; commit @755 | Admin only; last-active-admin guard @567–575 | Single transaction; full rollback on failure |
| 2 | `DELETE /api/boards/{board_id}` | `boards.delete_board` (boards.py:194–217) | CommunicationBoard + BoardSymbol/BoardAssignment cascades; `db.delete(db_board)` @215, commit @216 | Owner or admin | Atomic commit; FK cascade |
| 3 | `DELETE /api/boards/symbols/{symbol_id}` | `symbols.delete_symbol` (symbols.py:409–429) | Symbol + BoardSymbol joins; image file via `remove_owned_upload` @429 (post-commit); vector embedding | Staff (teacher/admin) | DB commit first (@428), then file unlink — no orphaned refs |
| 4 | `DELETE /api/boards/{board_id}/symbols/{symbol_id}` | `symbols.remove_symbol_from_board` (symbols.py:627–638) | Single BoardSymbol placement; `db.delete(db_board_symbol)` @636, commit @637 | Board owner/admin (or rostered teacher via `require_board_staff_or_owner`) | Atomic |
| 5 | `DELETE /api/boards/{board_id}/assign/{student_id}` | `board_assignments.unassign_board_from_student` (board_assignments.py:102–141; delete/commit @139–140) | BoardAssignment row | Owner/admin (rostered teacher) | Atomic |
| 6 | `DELETE /api/users/assign-student/{student_id}/{teacher_id}` | `users.unassign_student` (users.py:223–224) | StudentTeacher roster row | Admin; teacher only for own `teacher_id` @199 | Atomic |
| 7 | `DELETE /api/achievements/{achievement_id}` | `achievements.delete_achievement` (achievements.py:306–362) | Achievement + bulk `UserAchievement` delete @358, commit @359 | Teacher (own creations only @343) / admin; system achievements undeletable @334 | Atomic |
| 8 | `DELETE /api/learning-modes/{mode_id}` | `learning_modes.delete_learning_mode` (learning_modes.py:236–267; delete/commit @265–266) | LearningMode row | System modes: admin only; custom: creator only | Atomic |
| 9 | `DELETE /api/notifications/{notification_id}` | `notifications.delete_notification` (notifications.py:253–290; delete/commit @288–289) | Notification row | Owner or admin | Atomic |
| 10 | `DELETE /api/guardian-profiles/students/{student_id}` | `guardian_profiles.delete_student_profile` (guardian_profiles.py:350–390) | **Soft-delete** (deactivates profile; data retained for audit) | **Admin only** @362 + roster verify @368 | Commit @383 |

### Category B — Replace / overwrite / reset endpoints (6)

| # | Method + Path | Handler (module:line range) | What is replaced/reset | Auth | Commit / rollback behavior |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 11 | `POST /api/boards/symbols/{symbol_id}/image` | `symbols.update_symbol_image` (symbols.py:381–402) | Symbol image file replaced; new file unlinked on commit failure @396; old file unlinked @402 | Staff (teacher/admin) | Try/except: DB rollback + new-file unlink on failure |
| 12 | `POST /api/users/reset-password` | `users.reset_user_password` (users.py:228–315) | Password hash overwritten + `security_version` bumped (`user_service.py:80` `mark_credentials_changed`) — revokes all sessions | Admin (except self @264–269); teacher only for rostered students @277–289 | Atomic; commit @314 |
| 13 | `POST /api/auth/change-password` | `auth_users.change_password` (auth_users.py:350–~420) | Password hash overwritten + `mark_credentials_changed` @407 — revokes all sessions | Authenticated self | Atomic |
| 14 | `POST /api/data/import` | `export_import.import_data` (export_import.py:767–857) | Bulk replace/upsert of user boards, symbols, achievements, learning sessions; commit @855 | Authenticated user (own data) / admin | Single transaction; symbol pre-validation prevents partial imports |
| 15 | `POST /api/admin/reset-db` | `admin.reset_database` (admin.py:14–57) | **Entire database**: `Base.metadata.drop_all` + `create_all` + reseed | Admin only; **guarded**: 403 unless `ALLOW_DB_RESET=true`; **403 in production** | Drop/recreate is not transactional (SQLite DDL) — mitigated by guards |
| 16 | `POST /api/auth/logout` | `auth.logout` (auth.py:355–378) | Session invalidation: `mark_credentials_changed` + commit @373 (revokes all tokens for the account) | Bearer token (best-effort) | Atomic; accepts expired/undecodable tokens |

### Category C — Startup repair flow (1)

| # | Flow | Location | What it does |
| :--- | :--- | :--- | :--- |
| 17 | `schema.ensure()` migration/repair | `schema.py:434 ensure()`; FK table rebuilds @210–330 (drop + rename of `board_symbols`, `symbol_usage_logs` etc. to enforce `ON DELETE CASCADE`/`SET NULL`); label dedup cleanup; `seed.py:473` duplicate delete + flush @475 | Destructive table rebuilds and data cleanup executed once per boot; idempotent |

---

## 3. Reconciliation of the Three Figures

```
5   (Stage B)   = {1, 2, 3, 11, 12}                    — curated "highest-consequence" subset
6   (V3 Proof)  = {1, 2, 3, 11, 12, 14}                — adds Import Data; still omits:
16  (final)     = {1..16}                              — complete API enumeration
+1  (final)     = {17}                                 — startup repair flow
```

| Figure | Missing from it | Verdict |
| :--- | :--- | :--- |
| **5** | Import Data (14), Reset DB (15), Change Password (13), Logout (16), and the 5 smaller DELETE endpoints (4,5,6,7,8,9,10) | **UNDERCOUNT** — defensible only as a curated "high-consequence" subset, which the artifact never states |
| **6** | Reset DB (15), Change Password (13), Logout (16), and DELETE endpoints 4–10 | **UNDERCOUNT** — notably omits `POST /api/admin/reset-db`, the single most destructive endpoint in the app |
| **16 + 1** | nothing — but the member list was **never published** in the artifact | **CORRECT COUNT, UNSUPPORTED AS WRITTEN** — this inventory supplies the missing list and confirms it |

**Root cause of the chain's inconsistency**: each audit stage used a different inclusion rule (highest-consequence only → +import → full enumeration) without documenting the rule or updating the earlier figures.

---

## 4. The "52 Sites" Figure

- V3 Proof §1 claims "52 Sites across 6 Logical Destructive Flows".
- The composition of the 52 is **not documented** anywhere in the chain, and the V3 mutation ledger (231 sites) does not tag which rows belong to destructive flows.
- Reproducible site-level accounting for the 16 operations (from the 231-site ledger): ≈46 mutation/file-delete sites directly attributable (delete_user cascade ~14, delete_symbol 3, update_symbol_image 4, remove_symbol_from_board 2, delete_board 2, unassign_board 2, unassign_student 2, delete_achievement 2, delete_learning_mode 2, delete_notification 2, delete_student_profile 1, import_data 1, logout 2, change_password ~3, reset_password 2, reset-db 0 — `drop_all`/`create_all` are not ledger-style mutations).
- Plus schema.py rebuild internals, which are **absent from V3's 231-site ledger entirely** (no `schema.py` rows) — a small but real gap in the mutation ledger.
- **Verdict**: the "52" figure is not reproducible as stated; treat the **16 + 1 operation list** as the authoritative unit.

---

## 5. Borderline Cases Examined and Excluded (with rationale)

| Candidate | Why excluded |
| :--- | :--- |
| `POST /api/auth/admin/unlock-account` | State-clearing (removes lockout), but targeted and non-destructive; no data loss |
| `PUT /api/settings/ai` | Resets provider singletons only; no data destruction |
| `POST /api/learning/{session_id}/end` | Status transition (`active` → `completed`); no deletion |
| `PUT /api/auth/users/{user_id}` | Role/deactivation changes; state-changing but reversible, not destructive |
| `POST /api/boards/symbols/upload`, `POST /api/arasaac/import` | Create files; failure-path cleanup only |
| `POST /api/providers/tts/install`, `voice/install` | Install subprocesses; no user-data destruction |
| `remove_owned_upload` (helper) | Shared file-deletion helper — it is the *mechanism* for ops 3 and 11, not an operation itself |

---

## 6. Verification Evidence (commands)

- `grep -rn "5 destructive\|16 distinct\|6 flows" BACKEND_*.md` — located all three figures and their sources
- Live route table introspection — enumerated all 10 `DELETE` routes
- Full reads: `admin.py` (reset-db guards), `auth.py` logout, `learning_modes.py` delete, `guardian_profiles.py` delete, plus previously verified `auth_users.py` delete_user, `boards.py` delete_board, `symbols.py` delete/update_symbol_image, `users.py` reset/unassign, `export_import.py` import_data, `schema.py` rebuilds

---

## 7. Bottom Line

**The authoritative count is 16 API operations + 1 startup repair flow** (member-listed in §2). The chain's "5" and "6" are documented subsets with undocumented inclusion rules; the "16+1" was correct but never member-listed until now. The "52 sites" figure is not reproducible and should be retired in favor of the operation-level inventory.

**No application source, test, or frontend file was modified by this task.**