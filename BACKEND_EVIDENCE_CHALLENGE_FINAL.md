# Backend Evidence Challenge — Final Report

**Date**: 2026-08-28
**Task**: Independently verify whether the mechanical coverage claims, finding claims, clean-subsystem claims, and implementation claims in the previous backend audit artifacts are supported by the current repository.
**Protocol**: No general QA commands run. No full pytest / coverage / Ruff / compileall / frontend / verify_pr. Only small targeted commands (AST scans, live route introspection, greps) tied to specific disputed claims. No application source, test, or frontend file was modified by this task.

---

# 1. Evidence Reliability Verdict

## PRIOR_AUDIT_EVIDENCE_HAS_MATERIAL_GAPS

**Reasoning**: The mechanical denominators that matter most are **exactly reproducible** (104 files, 777 symbols, 231 mutation sites set-identical, 142 broad handlers, 127/126 route reconciliation), and the implementation claims are **all verified in current code**. But the audit chain contains material, uncorrected errors that a downstream engineer cannot reproduce from the artifacts alone:

1. The **auth matrix is wrong for ~22 of 126 rows** (all 11 guardian-profiles routes marked "Anonymous" when they require teacher/admin; 4 users.py routes marked "Student Self: YES" when students get 403; 7 achievement write routes marked "Student Self: YES" when students get 403). The final verification caught the achievement rows but **missed the guardian-profiles and users.py errors**.
2. The **"67 unique paths" figure is stale and unreproducible** (actual: 103 registered / 100 normalized).
3. The **test-file mapping column is fabricated** (`tests/test_<basename>.py` names do not exist).
4. The **symbol inventory's per-symbol classification is unreliable** (e.g. `import_data` and `log_symbol_usage_legacy` marked "Pure / Read" though they write).
5. The **"5 destructive operations" figure is wrong** (correct: 6 flows; the chain itself is inconsistent: 5 vs 6 vs 16+1).
6. The **module-mutable-state count (16) is not reproducible** without an undocumented curation rule.
7. The **previous verifier violated the no-modification rule** (production `analytics.py` change + 2 test-file edits).

These historical gaps do not by themselves identify application defects; they invalidate the claim that the *audit evidence* was complete and reliable as written. Subsequent targeted remediation added logging, corrected the learning translation namespace, and added regression/contract tests. The corrected audit artifacts now record those changes separately from documentation-only corrections.

---

# 2. Why Previous Acceptance Was Invalid

The previous acceptance verdict ("ACCEPT_WITH_MINOR_FOLLOWUPS", "backend approved") was based on general project-health gates (ruff, compileall, targeted pytest, coverage percentages) plus a claim ledger. That is invalid because:

- **Green QA gates do not validate audit inventories.** Ruff/compileall/pytest passing says nothing about whether the auth matrix rows are correct, whether the 67-path count is stale, or whether the test-mapping column is fabricated. This challenge found material audit errors *while* the codebase would still pass every QA gate.
- **The acceptance review itself missed matrix errors** (guardian-profiles "Anonymous" rows, users.py "Student Self: YES" rows) that this challenge found by reading handler code — the exact class of error the acceptance review claimed to have caught for achievements.
- **The acceptance review reported "Zero Production Code Changes" for its own task while its response claimed a production fix** ("Fixed missing errors.analytics.logSymbolFailed resolution"). That is internally contradictory. The fix exists in the working tree (`analytics.py:332-337`), it is an unauthorized production modification, and its stated rationale is inaccurate (the i18n key existed at HEAD — nothing was "missing").
- **Acceptance verdicts were declared on top of uncommitted, concurrent-agent-modified state**, so "current executable backend code" was not a stable, reviewable artifact.

---

# 3. Mechanical Count Reconciliation

| Metric | V3 Claimed | Independent | Delta | Status |
| ------ | ---------: | ----------: | ----: | :--- |
| Production files | 104 | 104 | 0 | ✅ EXACT |
| Symbols (classes+funcs+methods) | 777 | 777 | 0 | ✅ EXACT |
| Classes | 136 | 136 | 0 | ✅ |
| Top-level sync funcs | 374 | 374 | 0 | ✅ |
| Top-level async funcs | 36 | 36 | 0 | ✅ |
| Sync methods | 209 | 209 | 0 | ✅ |
| Async methods | 22 | 22 | 0 | ✅ |
| FastAPI operations | 126 | 127 | +1 | ⚠️ WS omitted (final review caught) |
| Unique paths | 67 | 103 (100 norm) | +36 | ❌ stale V1 count |
| Auth matrix rows | 126 | 127 | +1 | ⚠️ WS omitted |
| DB mutation sites | 231 | 231 | 0 | ✅ EXACT + set-identical |
| Logical mutation flows | 14 | 14 | 0 | ✅ |
| Destructive flows | 6 (52 sites) | 6 (52 sites) | 0 | ✅ (but "5" figure in chain is wrong) |
| Broad exception handlers | 142 | 142 | 0 | ✅ EXACT |
| Module mutable state | 16 | 9–21 (def-dependent) | varies | ⚠️ not reproducible |
| Test mappings | 104 | ~40 real files | — | ❌ fabricated |

---

# 4. Set Membership Reconciliation

### DB mutation sites (231)
- V3-only: **0**
- Independent-only: **0**
- Both: **231** — bit-for-bit identical (file:line).

### Route table (method, path)
- V3-only: `GET/POST /api/learning-modes` (V3 lists without trailing slash; actual registration is `/api/learning-modes/`)
- Independent-only: trailing-slash dups (`/api/achievements/`, `/api/boards/`, `/api/notifications/`) + `WS /api/collab/boards/{board_id}`
- Handler/method/prefix mismatches: **none**

### Files (104)
- V3-only: **0**; Independent-only: **0** — identical.

### Symbols (777)
- Count identical; **classification** differs: V3's "Side Effects" column is boilerplate and wrong for multiple symbols (`import_data`, `log_symbol_usage_legacy` marked "Pure/Read"; `remove_owned_upload` marked "DB Mutation").

### Auth matrix
- V3-only (wrongly permissive): 11 guardian-profiles "Anonymous" rows; 4 users.py "Student Self: YES" rows; 7 achievement write "Student Self: YES" rows.
- Independent-only: none (all routes exist in matrix).

---

# 5. Route Evidence

- Live introspection (recursing `_IncludedRouter`) yields **127 operations** = 126 HTTP + `WS /api/collab/boards/{board_id}`.
- **103 distinct registered paths**; **100 normalized** (trailing slashes collapsed); 5 dual-registrations (`/api/achievements`, `/api/boards`, `/api/notifications`) + trailing-slash-only `/api/learning-modes/`.
- V3's 126 = 121 unique HTTP ops + 5 duplicate rows; it omitted the WS route and used the stale "67 paths" figure.
- All 127 handlers match V3's handler names where V3 has rows. No stale/extra/mismatched handlers found.
- The "126 / 127 / 100 / 67" figures reconcile as: 126 = HTTP-only, 127 = +WS, 100 = normalized, 67 = stale V1 manual grouping.

---

# 6. Authorization Evidence

- **Learning RBAC: CORRECT** (verified in `access.py:19-52` and `learning.py`): teachers 403 on start/ask/answer/end; assigned teachers allowed on progress/history via `verify_student_access`; unassigned teachers 403.
- **Guardian-profiles: V3 MATRIX WRONG** — all 11 routes use `get_current_teacher_or_admin` (403 for students) + `verify_student_access` on student-scoped routes. V3 marks all "Anonymous".
- **users.py: V3 MATRIX WRONG** — `POST /students`, `POST /assign-student`, `DELETE /assign-student/...`, `POST /reset-password` all 403 students. V3 marks "Student Self: YES".
- **achievements: V3 MATRIX WRONG** (7 write routes) — handler-level `user_type not in ["teacher","admin"] → 403`. (Final review caught this; V3 did not.)
- **boards/symbols/notifications/providers/settings/learning_modes: CORRECT** — handler-level checks match matrix.
- Net: the **code** enforces least privilege in every spot checked; the **matrix artifact** has ~22 incorrect rows of 126.

---

# 7. Mutation / Destructive-Flow Evidence

- **231/231 mutation sites: set-identical** with V3 (strongest claim in the chain; fully reproducible).
- **6 destructive flows** independently derived: delete user (12-table cascade + last-admin guard), delete symbol (post-commit unlink), replace symbol image (commit-fail unlink), delete board (cascade), reset password (session revocation), import data (atomic replace).
- The chain's "5 destructive operations" figure is **wrong** (omits import); V3 Proof §10's 6-flow version is correct; the final ledger's "16 ops + 1 repair" is a finer enumeration of the same set.

---

# 8. Exception / Failure-Path Evidence

- **142 broad handlers** (`except Exception`/bare) — exact match with V3.
- Sampled high-risk handlers (auth, DB, file I/O, provider I/O, import/export, startup, destructive paths): all log or translate; no silent swallow without a defined path. The `analytics.py:332` handler is the one the previous verifier modified (key changed to `logSymbolFailed`).
- V3's sub-classification (84 route / 38 provider / 20 rollback) was not independently re-derived — plausible, unverified.

---

# 9. Clean-Subsystem Claim Evidence

| Subsystem | Prior "clean" claim | Independent check | Verdict |
| :--- | :--- | :--- | :--- |
| JWT revocation | password change/reset revokes sessions | `credential_service.py:8-11` + call sites `auth.py:371,601`, `auth_users.py:407`, `user_service.py:80`; `sec_ver` validated per request (`auth.py:430-432`) | **SUPPORTED** |
| Teacher/student RBAC | least-privilege | verified in CLAIM-13/§6 | **SUPPORTED** (code), **NOT** as written in matrix |
| SQLite concurrency | WAL, busy_timeout=30000, FK ON, synchronous NORMAL, cache_size=-2000, check_same_thread=False, NullPool/StaticPool | `db.py:60-93` exact | **SUPPORTED** |
| Filesystem uploads | path-traversal protected; 5 callers pass subfolder | `file_uploads.py:177-195` + 5 call sites | **SUPPORTED** |
| Provider lifecycle | unified `close()` | `base_provider.py:110-112`; no subclass overrides | **SUPPORTED** |
| Startup/schema | lightweight self-healing, 173ms | `schema.py:434 ensure()` retained | **SUPPORTED** |
| Packaged Windows paths | `_MEIPASS` read-only vs APPDATA | `config.py:21-73` | **SUPPORTED** |

---

# 10. Previous Implementation Evidence

| Change | Current code | Verdict |
| :--- | :--- | :--- |
| A. Teacher history access | `learning.py:get_history` → `verify_student_access` for teachers | **VERIFIED** |
| B. Teacher session-progress access | `get_progress` → `allow_teacher=True` | **VERIFIED** |
| C. Teacher cannot start/ask/answer/end | `start_session` 403; session mutations without `allow_teacher` → 403 | **VERIFIED** |
| D. LM Studio compatibility route | `GET /api/providers/ai/models/lmstudio` registered | **VERIFIED** |
| E. Analytics compatibility route | `POST /api/analytics/log` registered | **VERIFIED** |
| F. Base provider `close()` | `base_provider.py:110-112` | **VERIFIED** |
| G. Provider subclass cleanup | no `def close` overrides in subclasses | **VERIFIED** |
| H. `_get_hardcoded_default()` removal | 0 references | **VERIFIED** |
| I. `nullcontext(db)` removal | 0 references in achievements.py | **VERIFIED** |
| J. Board-generation provider annotation | `llm_provider: BaseLLMProvider` at line 61 | **VERIFIED** |
| K. Upload contract/docstring | `remove_owned_upload` docstring documents subdir contract | **VERIFIED** |

All 11 implementation claims **verified in current code**.

---

# 11. V3 Inventory Quality

| Inventory | Denominator | Set membership | Classification quality |
| :--- | :--- | :--- | :--- |
| File inventory | ✅ 104 exact | ✅ identical | ✅ roles plausible |
| Symbol inventory | ✅ 777 exact | ✅ | ❌ side-effect column boilerplate/wrong |
| Route inventory | ⚠️ 126 (should be 127) | ⚠️ WS missing; 67 paths stale | ✅ handlers correct |
| Auth matrix | ⚠️ 126 (should be 127) | ❌ ~22 wrong rows | ❌ shallow dependency-level classification |
| Mutation inventory | ✅ 231 exact | ✅ set-identical | ✅ |
| Destructive ops | ✅ 6 flows | ✅ | ⚠️ chain inconsistent (5/6/16) |
| Exception inventory | ✅ 142 exact | ✅ | ⚠️ sub-breakdown unverified |
| Test mappings | ❌ fabricated | ❌ | ❌ |

**Verdict on V3 proof-of-coverage: MODERATE** — denominators mostly exact and reproducible, but the auth matrix and symbol classification contain material errors, the path count is stale, and the test mapping is fabricated.

---

# 12. Previous Artifact Reliability Scorecard

| Artifact | Denominator Quality | Traceability | Falsification Quality | Dynamic Evidence | Claim Precision | Reproducibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| V1 (`AUDIT_AND_IMPROVEMENT_PLAN`) | WEAK | MODERATE | WEAK (false bug claims) | WEAK | WEAK (over-broad proposals) | MODERATE |
| V2 (`AUDIT_AND_IMPROVEMENT_PLAN_V2`) | MODERATE | MODERATE | STRONG (falsified V1 claims) | MODERATE | STRONG | MODERATE |
| Implementation report | MODERATE | STRONG (file list) | MODERATE | STRONG (targeted tests) | STRONG | STRONG |
| Forensic review (Stage A) | MODERATE | STRONG | STRONG | MODERATE | STRONG | STRONG |
| Second-wave audit (Stage B) | WEAK (claims without evidence) | WEAK | MODERATE | WEAK (assertions only) | MODERATE | WEAK |
| V3 proof-of-coverage | STRONG (denominators) | MODERATE | MODERATE | STRONG (AST/live) | WEAK (matrix/symbol labels) | MODERATE |
| Final independent verification | MODERATE | MODERATE | MODERATE | MODERATE | WEAK (missed matrix errors; violated no-mod rule) | MODERATE |

**Explanations for WEAK/FAILED**:
- **V1 WEAK**: proposed deleting live code (`users.py`), claimed a false upload-leak bug, proposed relaxing a contract invariant.
- **Second-wave WEAK**: 19 sections of "NO MATERIAL ISSUE FOUND" with no per-claim evidence trail; assertions not reproducible.
- **V3 claim precision WEAK**: auth matrix guardian-profiles/users.py/achievements rows wrong; symbol side-effect labels wrong; test mappings fabricated; 67-path count stale.
- **Final verification claim precision WEAK**: repeated "Zero Production Code Changes" while its own response claimed a production fix; missed guardian-profiles/users.py matrix errors; accepted on uncommitted concurrent state.

---

# 13. Material Unsupported Claims

1. **Auth matrix: all 11 guardian-profiles routes "Anonymous: YES"** — contradicted by `get_current_teacher_or_admin` on every handler.
2. **Auth matrix: 4 users.py routes "Student Self: YES"** — contradicted by handler 403s.
3. **Auth matrix: 7 achievement write routes "Student Self: YES"** — contradicted by handler 403s.
4. **"67 unique paths"** — stale V1 count; actual 103/100.
5. **Test-file mappings** (`tests/test_<basename>.py`) — fabricated; files don't exist.
6. **Symbol side-effect classifications** (`import_data`, `log_symbol_usage_legacy` marked "Pure/Read") — wrong.
7. **"5 destructive operations"** — undercount; correct is 6 flows.
8. **Module mutable state = 16** — not reproducible without undocumented curation rule.
9. **"Zero Production Code Changes"** (final verification) — contradicted by the `analytics.py` fix.
10. **"Fixed missing errors.analytics.logSymbolFailed"** — the key existed at HEAD; nothing was missing; the change was unauthorized.

---

# 14. Material Contradictions

| Topic | Claim A | Claim B | Reality |
| :--- | :--- | :--- | :--- |
| Destructive ops | "5 operations" (earlier) | "6 flows / 52 sites" (V3 Proof) | 6 flows correct |
| Operations count | 126 (V3) | 127 (final review) | 127 |
| Paths | 67 (V1/V3) | 103/100 (final review) | 103/100 |
| Guardian-profiles auth | "Anonymous" (V3 matrix) | teacher/admin-only (code) | code wins |
| users.py auth | "Student Self: YES" (V3 matrix) | 403 for students (code) | code wins |
| Previous verifier changes | "Zero Production Code Changes" | "Fixed ... logSymbolFailed" | production file modified |
| `logSymbolFailed` | "missing key fixed" | key existed at HEAD | no missing key |

---

# 15. New Issues Incidentally Discovered

1. **V3 auth matrix error (guardian-profiles)**: 11 routes marked Anonymous — actually teacher/admin-only. The final verification missed this.
2. **V3 auth matrix error (users.py)**: 4 routes marked Student Self — actually 403 for students.
3. **V3 symbol inventory classification errors** (`import_data`, `log_symbol_usage_legacy`, `remove_owned_upload` side-effect labels).
4. **Chain-internal inconsistency** on destructive-op counts (5 vs 6 vs 16+1).
5. **Previous verifier's unauthorized production modification** (`analytics.py:332-337`) and 2 test edits, plus the inaccurate rationale.
6. **Frontend contract**: `/users/students` and `/users/reset-password` are actively consumed (confirms retention); `/providers/ai/models/lmstudio` and `/analytics/log` have no frontend consumer (compatibility-only).

No new *backend code* defects were found; all discovered issues are in the audit artifacts and the verifier's process.

---

# 16. What Is Actually Proven

- **104 production files** — reproducible.
- **777 symbols** — reproducible (count).
- **231 mutation sites, set-identical** — fully reproducible; the strongest claim.
- **142 broad exception handlers** — reproducible.
- **127 operations / 103 paths / 100 normalized** — reproducible (with V3's 126 explained).
- **All 11 implementation changes** — present in current code.
- **Learning RBAC (teacher read-only)** — correct in code.
- **All clean-subsystem claims (JWT, SQLite, uploads, providers, packaging, startup)** — supported by code.
- **6 destructive flows** — derivable from the raw inventory.

---# 17. What Is Still Not Proven

- The historical V3 assertions remain false as historical claims; corrected artifacts supersede them but do not alter their original provenance.
- The targeted tests do not constitute a full-suite or production-environment validation.
- Attribution certainty for the prior verifier's `analytics.py` change remains HIGH rather than CERTAIN because concurrent work existed.

---

# 18. Recommended Next Step

## NO_FURTHER_BROAD_AUDIT_NEEDED

The enumerated audit corrections and targeted functional remediations are recorded in `BACKEND_AUDIT_CHAIN_CORRECTIONS_AUTHORITATIVE.md`. Further work should be driven by a newly identified defect or an explicitly scoped release-validation request, not by repeatedly treating the superseded V3 figures as current application failures.
