# Corrected Authorization Matrix — Guardian Profiles, Users, Achievements

**Purpose**: Targeted re-verification of the auth-matrix gaps identified in `BACKEND_EVIDENCE_CHALLENGE_FINAL.md` (§13 items 1–3). Every route in `src/api/routers/guardian_profiles.py`, `users.py`, and `achievements.py` was re-traced from dependency → role check → ownership/assignment check → handler, with file:line evidence.

**Scope**: 31 registered route rows (11 guardian-profiles + 7 users + 13 achievements incl. 2 trailing-slash duplicates). Other routers were already verified correct in the challenge (learning, boards, symbols, notifications, providers, settings, learning_modes, auth, auth_users, auth_preferences, admin, arasaac, export_import, config, collab).

**Method**: full handler reads + `grep -n` evidence pins + live route table (handlers matched). **No code modified.**

---

## Legend

- **Anon** = no authentication required
- **StSelf** = authenticated student accessing own resource
- **StOther** = authenticated student accessing another user's resource
- **AsgT** = teacher with explicit `StudentTeacher` roster link to the target student
- **UnasgT** = teacher without roster link
- **Admin** = administrator
- Enforcement: dependency used + handler-level checks (file:line)
- V3 verdict: what `BACKEND_V3_AUTH_MATRIX.md` claimed, and whether it matches reality

---

## 1. Guardian Profiles (`src/api/routers/guardian_profiles.py`)

Shared dependency: `get_current_teacher_or_admin` (defined **lines 34–43**: `get_current_active_user` + `user_type not in ("teacher","admin") → 403`).
Roster helper: `verify_student_access` (`src/api/deps/auth.py:155–200`: student must exist (404) and be `user_type=student` (400); admin → allow all; teacher → only explicit roster (403 otherwise); students can never pass).

| Method + Path | Handler | Anon | StSelf | StOther | AsgT | UnasgT | Admin | Enforcement (file:line) | V3 row verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| GET `/api/guardian-profiles/templates` | `list_templates` | NO | NO | NO | YES | YES | YES | dep `get_current_teacher_or_admin` @52 | **WRONG** (V3: Anonymous YES) |
| GET `/api/guardian-profiles/templates/{template_name}` | `get_template` | NO | NO | NO | YES | YES | YES | dep @66 | **WRONG** (V3: Anonymous YES) |
| POST `/api/guardian-profiles/templates/{template_name}/preview` | `preview_template` | NO | NO | NO | YES | YES | YES | dep @96 | **WRONG** (V3: Anonymous YES) |
| GET `/api/guardian-profiles/students` | `list_students_with_profiles` | NO | NO | NO | YES (assigned only — `teacher_id` filter @136–139) | NO (empty list) | YES (all) | dep @128 | **WRONG** (V3: Anonymous YES) |
| GET `/api/guardian-profiles/students/{student_id}` | `get_student_profile` | NO | NO | NO | YES | NO | YES | dep @155 + `verify_student_access` @164 | **WRONG** (V3: Anonymous YES) |
| POST `/api/guardian-profiles/students/{student_id}` | `create_student_profile` | NO | NO | NO | YES | NO | YES | dep @184 + verify @192 | **WRONG** (V3: Anonymous YES) |
| PUT `/api/guardian-profiles/students/{student_id}` | `update_student_profile` | NO | NO | NO | YES | NO | YES | dep @270 + verify @279 | **WRONG** (V3: Anonymous YES) |
| DELETE `/api/guardian-profiles/students/{student_id}` | `delete_student_profile` | NO | NO | NO | **NO** (403 even for assigned teachers) | NO | YES | dep @353 + **admin-only check @362** + verify @368 | **WRONG** (V3: Anonymous YES) |
| GET `/api/guardian-profiles/students/{student_id}/history` | `get_profile_history` | NO | NO | NO | YES | NO | YES | dep @403 + verify @411 | **WRONG** (V3: Anonymous YES) |
| GET `/api/guardian-profiles/students/{student_id}/effective-profile` | `get_effective_profile` | NO | NO | NO | YES | NO | YES | dep @424 + verify @433 | **WRONG** (V3: Anonymous YES) |
| GET `/api/guardian-profiles/students/{student_id}/system-prompt` | `get_student_system_prompt` | NO | NO | NO | YES | NO | YES | dep @446 + verify @455 | **WRONG** (V3: Anonymous YES) |

**Guardian-profiles: 11/11 V3 rows WRONG.** Actual: teacher/admin only; student-scoped routes additionally require roster; delete is admin-only.

---

## 2. Users (`src/api/routers/users.py`)

| Method + Path | Handler | Anon | StSelf | StOther | AsgT | UnasgT | Admin | Enforcement (file:line) | V3 row verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| ~~GET `/api/users/me`~~ | removed (duplicate of `/api/auth/me`) | — | — | — | — | — | — | — | — |
| ~~PUT `/api/users/me`~~ | removed (duplicate of `/api/auth/profile`) | — | — | — | — | — | — | — | — |
| GET `/api/users/students` | `get_students` | NO | YES (returns `[self]` @63–65) | N/A | YES (assigned only) | NO (empty) | YES (all) | dep @50; role branches @54–66 | **CORRECT** |
| POST `/api/users/students` | `create_student` | NO | **NO** (403 @76–84) | N/A | YES (auto-assigns self @96–101) | YES | YES | dep @72 + `user_type not in ["admin","teacher"] → 403` @76–84 | **WRONG** (V3: Student Self YES) |
| POST `/api/users/assign-student` | `assign_student` | NO | **NO** (403 @130–134) | N/A | YES (self only @139–146) | YES | YES | dep @126 + 403 @130 + teacher-self @139 | **WRONG** (V3: Student Self YES) |
| DELETE `/api/users/assign-student/{student_id}/{teacher_id}` | `unassign_student` | NO | **NO** (403 @193–197) | N/A | YES (own `teacher_id` only @199–206) | YES | YES | dep @189 + 403 @193 + teacher-self @199 | **WRONG** (V3: Student Self YES) |
| POST `/api/users/reset-password` | `reset_user_password` | NO | **NO** (403 @236–240) | N/A | YES (assigned students only @277–289) | NO | YES (except self @264–269 → 400) | dep @232 + 403 @236 + admin self-guard @264 + roster @277 | **WRONG** (V3: Student Self YES) |

**Users: 4/7 V3 rows WRONG.** Students get 403 on create-student, assign, unassign, and reset-password.

---

## 3. Achievements (`src/api/routers/achievements.py`)

| Method + Path | Handler | Anon | StSelf | StOther | AsgT | UnasgT | Admin | Enforcement (file:line) | V3 row verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| GET `/api/achievements` (+ `/` dup) | `list_all_achievements` | NO | **NO** (403 @92–95) | N/A | YES | YES | YES | dep @88 + `user_type not in ["teacher","admin"] → 403` @92 | **WRONG** (V3: Student Self YES ×2 rows) |
| POST `/api/achievements` (+ `/` dup) | `create_achievement` | NO | **NO** (403 @137–140) | N/A | YES (own creations; target must be rostered @154) | YES | YES | dep @133 + 403 @137 + `verify_student_access(target)` @154 | **WRONG** (V3: Student Self YES ×2 rows) |
| GET `/api/achievements/categories` | `get_categories` | NO | **NO** (403 @44–47) | N/A | YES | YES | YES | dep @41 + 403 @44 | **WRONG** (V3: Student Self YES) |
| GET `/api/achievements/criteria-types` | `get_criteria_types` | NO | **NO** (403 @62–65) | N/A | YES | YES | YES | dep @59 + 403 @62 | **WRONG** (V3: Student Self YES) |
| GET `/api/achievements/leaderboard` | `get_leaderboard` | NO | YES | N/A | YES | YES | YES | dep @509; **no role restriction** (any authenticated user) | **CORRECT** |
| GET `/api/achievements/user/{user_id}` | `get_user_achievements` | NO | YES (self branch @452) | NO (verify → 403) | YES | NO | YES | dep @447 + self-or-`verify_student_access` @452 | **CORRECT** |
| POST `/api/achievements/user/{user_id}/check` | `check_achievements` | NO | YES (self branch @470) | NO | YES | NO | YES | dep @465 + self-or-verify @470 | **CORRECT** |
| GET `/api/achievements/user/{user_id}/points` | `get_user_points` | NO | YES (self branch @496) | NO | YES | NO | YES | dep @491 + self-or-verify @496 | **CORRECT** |
| PUT `/api/achievements/{achievement_id}` | `update_achievement` | NO | **NO** (403 @211–214) | N/A | YES (own creations only @232) | YES | YES (incl. system) | dep @207 + 403 @211 + owner-or-admin @232 + verify target @244 | **WRONG** (V3: Student Self YES) |
| DELETE `/api/achievements/{achievement_id}` | `delete_achievement` | NO | **NO** (403 @313–316) | N/A | YES (own creations only @343) | YES | YES (except system @334 → 403 for everyone) | dep @309 + 403 @313 + system-block @334 + owner-or-admin @343 | **WRONG** (V3: Student Self YES) |
| POST `/api/achievements/{achievement_id}/award` | `award_achievement` | NO | **NO** (403 @375–378) | N/A | YES (rostered students only @395) | NO | YES | dep @371 + 403 @375 + `verify_student_access(target)` @395 | **WRONG** (V3: Student Self YES) |

**Achievements: 9/13 V3 rows WRONG** (8 unique paths; the GET/POST list rows are dual-registered, so 9 of 13 matrix rows). Teacher update/delete is additionally constrained by creator-ownership (system achievements: admin can update but nobody can delete).

---

## 4. Summary of Corrections

| Router | Rows | V3 CORRECT | V3 WRONG | Nature of V3 error |
| :--- | ---: | ---: | ---: | :--- |
| guardian-profiles | 11 | 0 | **11** | marked "Anonymous: YES"; actual: teacher/admin-only + roster + admin-only delete |
| users | 7 | 3 | **4** | marked "Student Self: YES"; actual: students 403 on all 4 mutating routes |
| achievements | 13 | 4 | **9** | marked "Student Self: YES" on teacher/admin-only routes |
| **Total** | **31** | **7** | **24** | — |

**V3 matrix wrong rows overall: 24 of 126** (the 24 above; all other routers verified correct in the challenge — learning, boards, symbols, notifications, providers, settings, learning_modes, auth, auth_users, auth_preferences, admin, arasaac, export_import, config).

Root cause of the V3 error: the matrix classified by the top-level dependency (`get_current_active_user`) instead of reading the handler-level role checks (`user_type not in [...] → 403`) and handler-level roster checks (`verify_student_access`). The prior "final verification" caught the achievements error class but **missed guardian-profiles and users.py**.

## 5. Verification Evidence (commands)

- `grep -n "get_current_teacher_or_admin\|verify_student_access\|user_type != \"admin\"" src/api/routers/guardian_profiles.py` → dep @34–43; verify @164,192,279,368,411,433,455; admin-only @362
- `grep -n "user_type\|403\|Depends(get_current" src/api/routers/users.py` → 403 checks @76,130,193,236; roster @277–289
- `grep -n "verify_student_access\|user_type not in\|created_by != current_user.id" src/api/routers/achievements.py` → 403 checks @44,62,92,137,211,313,375; verify @154,244,395,452,470,496; ownership @232,343; system-block @334
- Full reads of all three files (guardian_profiles.py 464 lines, users.py 315 lines, achievements.py 515 lines)
- Live route table: all 31 rows' handlers matched to the above functions

**No application source, test, or frontend file was modified by this task.**