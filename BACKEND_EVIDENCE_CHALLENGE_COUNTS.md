# Backend Evidence Challenge — Counts (V3 Claimed vs Independently Computed)

**Date**: 2026-08-28
**Method**: Independent AST parse, live FastAPI route introspection, regex/AST mechanical scans of the **current working tree** (`HEAD` = `310540d` + uncommitted backend changes). V3 inventory rows were NOT used as input for the independent counts; they were only compared afterward.

---

## 1. Previous Claimed Counts (extracted verbatim from artifacts)

| Metric | V3 Claimed | Source Artifact | Source Location |
| ------ | ---------: | --------------- | --------------- |
| Production files | 104 | `BACKEND_V3_FILE_INVENTORY.md` | Header "Total Production Files Inventoried: 104" |
| Production symbols | 777 | `BACKEND_V3_SYMBOL_INVENTORY.md` | Header "Total Production Symbols Inventoried: 777" |
| Classes | 136 | `BACKEND_FINAL_INDEPENDENT_VERIFICATION.md` | §5 "Classes: 136" |
| Top-level sync functions | 374 | same | §5 |
| Top-level async functions | 36 | same | §5 |
| Sync methods | 209 | same | §5 |
| Async methods | 22 | same | §5 |
| FastAPI operations | 126 | `BACKEND_V3_ROUTE_INVENTORY.md` | Header "Total Registered Operations: 126"; also `BACKEND_V3_PROOF_OF_COVERAGE.md` §1 |
| Unique API paths | 67 | `BACKEND_AUDIT_V3_PROOF_OF_COVERAGE.md` | §1 "Unique API Paths Registered: 67"; `BACKEND_API_INVENTORY.md` "Total Unique Paths: 67" |
| Auth matrix rows | 126 | `BACKEND_V3_AUTH_MATRIX.md` | Header "Total Endpoints Mapped: 126" |
| DB mutation sites | 231 | `BACKEND_V3_MUTATION_INVENTORY.md` | Header "Total Mutation Sites Identified: 231" |
| Logical mutation flows | 14 | same | Header "Logical Mutation Flows: 14" |
| Destructive operation sites | 52 / 6 flows | `BACKEND_AUDIT_V3_PROOF_OF_COVERAGE.md` | §1 "Destructive Operations Inventoried: 52 Sites across 6 Logical Destructive Flows" |
| Filesystem I/O sites | 68 | same | §1 |
| External I/O sites | 44 | same | §1 |
| Broad exception handlers | 142 | same | §1 |
| Module-level mutable state | 16 | same | §1 |
| Test files mapped | 104 (one per file) | `BACKEND_V3_FILE_INVENTORY.md` | "Tests" column |
| 5 destructive operations | 5 | `BACKEND_FINAL_VERDICT_TABLE.md` VRD-19 (also earlier reports) | §10 of V3 Proof lists 6; final reports say 5 |

Note: The "5 destructive operations" figure appears in earlier summaries; V3 Proof §10 lists **6** destructive flows (Delete User, Delete Symbol, Replace Symbol Image, Delete Board, Reset Password, Import Data). The final verification ledger says "16 distinct destructive/state-clearing API operations and 1 startup repair flow". These three figures (5 / 6 / 16+1) are mutually inconsistent across the chain.

---

## 2. Independently Computed Counts (current working tree)

| Metric | Independent | Method |
| ------ | ----------: | ------ |
| Production Python files (`src/` + `launcher.pyw`) | **104** | os.walk of `src/` (excluding `__pycache__`, `node_modules` vendored `flatted.py`) + `launcher.pyw` |
| Operator scripts (`scripts/`) | **16** | `ls scripts/*.py` |
| Classes | **136** | AST top-level ClassDef |
| Top-level sync functions | **374** | AST top-level FunctionDef |
| Top-level async functions | **36** | AST top-level AsyncFunctionDef |
| Sync methods | **209** | AST FunctionDef inside ClassDef |
| Async methods | **22** | AST AsyncFunctionDef inside ClassDef |
| **Symbols total** | **777** | 136+374+36+209+22 |
| Nested functions (excluded) | 33 | AST walk |
| FastAPI app operations | **127** | live `app.routes` walk incl. `_IncludedRouter` recursion, minus docs/mounts (126 HTTP + 1 WS) |
| Distinct registered app paths | **103** | live route table |
| Normalized paths (trailing slash collapsed) | **100** | live route table |
| Auth matrix rows | **127** | same route table (126 HTTP + WS) |
| DB mutation sites (V3 universe) | **231** | regex `db|session|self.db|self.session.(add|commit|flush|delete|execute|rollback)(` + `os.remove`/`os.unlink`/`remove_owned_upload` |
| — breakdown | 63 add, 67 commit, 11 delete, 28 execute, 41 flush, 11 rollback, 4 file-delete, 6 remove_owned_upload | same |
| Direct file write sites | 9 | grep `.write_text/.write_bytes/.open("w"/"wb")/shutil.copyfile` |
| Broad exception handlers (`except Exception` / bare) | **142** | AST Try handlers |
| Total try/except handlers | 232 | AST |
| Module-level mutable state (broad scan) | 21 candidates; 9 bare-name; V3's 16 = subset | AST + grep |
| Filesystem write/delete sites (broad) | 52 | regex |
| External I/O sites (broad) | 56 | regex |
| Provider implementations | 4 LLM + 2 speech/TTS | file inventory |
| Lifecycle hooks | lifespan in `src/api/main.py`; `_start_provider_warmup_thread`, background tasks | read |

---

## 3. Deltas

| Metric | V3 Claimed | Independent | Delta | Explanation |
| ------ | ---------: | ----------: | ----: | :--- |
| Production files | 104 | 104 | 0 | Exact match |
| Symbols | 777 | 777 | 0 | Exact match |
| Classes | 136 | 136 | 0 | Exact |
| Top-level funcs (sync) | 374 | 374 | 0 | Exact |
| Top-level funcs (async) | 36 | 36 | 0 | Exact |
| Methods (sync) | 209 | 209 | 0 | Exact |
| Methods (async) | 22 | 22 | 0 | Exact |
| FastAPI operations | 126 | 127 | **+1** | V3 omitted `WS /api/collab/boards/{board_id}` |
| Unique paths | 67 | 103 (100 norm) | **+36** | "67" is a stale V1 count; V3 copied it |
| Auth matrix rows | 126 | 127 | +1 | Same WS omission |
| DB mutation sites | 231 | 231 | 0 | Exact — and **set-identical** (see below) |
| Logical mutation flows | 14 | 14 | 0 | Count matches; **3/14 entry points wrong** (FLOW-08/09 symbols paths are `/api/boards/symbols/...`; FLOW-13 is PUT not POST) and **coverage partial** — ≥73 sites (31.6%) in flows absent from the table (seed, board_ai, achievements, notifications, guardian profiles, learning modes, arasaac, preferences). See `BACKEND_EVIDENCE_CHALLENGE_V3_TOTALS.md` §2 |
| Destructive sites | 52 / 6 flows | **58 sites** / 16 ops | +6 | "52" not reproducible; independent ledger-site count for the 16 ops = **58** (delete_user cascade alone = 30). Corrects the earlier ≈46 estimate. See `BACKEND_EVIDENCE_CHALLENGE_V3_TOTALS.md` §3 |
| Filesystem I/O | 68 | **96 curated** (41 write/delete) | +28 | Supersedes the earlier "52" regex figure. Per-site curation of 133 raw candidates removes 37 false positives (13 `absolute`, 12 `str/datetime.replace` — zero `Path.replace` exist, 4 dict `.copy`, 2 list `.remove`, 1 `logger.remove`, 1 `webbrowser.open`, 1 `Image.open(BytesIO)`, 3 `Path.home`). V3's 68 has no member list and no clean exclusion rule → **NOT REPRODUCIBLE** (see `BACKEND_EVIDENCE_CHALLENGE_V3_SUBCLAIMS.md` §2) |
| External I/O | 44 | **25 core / 38 extended** | −6…−19 | Precise scan: 14 outbound HTTP calls + 7 client instantiations + 2 subprocess + 2 engine inference = 25 core; +5 client closes +5 `shutil.which` +1 `webbrowser.open` +1 WS +1 SSE = 38. 44 only reachable by counting Groq/LMStudio's **inherited** OpenRouter sites per subclass (undocumented) → **NOT REPRODUCIBLE** (see `BACKEND_EVIDENCE_CHALLENGE_V3_SUBCLAIMS.md` §3) |
| Broad exception handlers | 142 | 142 | 0 | Exact match |
| Exception breakdown | 84/38/20 | **17/40/20** (+65 residual) | −67/+2/0 | "84 route-level boundaries" is a residual (142−38−20); only 17 of 142 raise `HTTPException`. "20 rollback/cleanup" matches (one of several decompositions). "38 provider/transcription" ≈ 40 by strict rule. "Logging on all error paths" contradicted: 24 no-log handlers incl. 3 bare `pass` (see `BACKEND_EVIDENCE_CHALLENGE_V3_SUBCLAIMS.md` §1) |
| Module mutable state | 16 | **16 sync primitives** (exact) / 38–46 full universe | 0 / +22–30 | 16 = exactly the 15 locks + 1 semaphore; V3's text claims "events, provider singletons" which are NOT in the 16 (true universe: +9 containers, +14 singletons/engines, +8 scalars). See `BACKEND_EVIDENCE_CHALLENGE_V3_TOTALS.md` §1 |
| Test mappings | 104 | ~40 real files | — | V3's `tests/test_<basename>.py` names are **synthetic placeholders**; most do not exist |

---

## 4. Set-Membership Differences (the mandatory comparison)

### 4.1 DB mutation sites — **SET-IDENTICAL**
Parsed all 231 `MUT-####` rows (file, line) from `BACKEND_V3_MUTATION_INVENTORY.md` and compared against my independent (file:line) scan:
- V3-only: **0**
- Independent-only: **0**
- Both: **231/231**

This is the strongest mechanical claim in the chain and it reproduces exactly.

### 4.2 Route table (method, path)
- V3-only: `GET /api/learning-modes`, `POST /api/learning-modes` (V3 listed without trailing slash; actual registration is `/api/learning-modes/` only)
- Independent-only: `GET /api/achievements/`, `POST /api/achievements/`, `GET /api/boards/`, `POST /api/boards/`, `POST /api/notifications/` (trailing-slash duplicates), `WS /api/collab/boards/{board_id}`
- Handler mismatches: none found (all 127 handlers match V3's handler names where V3 has the row)
- Method mismatches: none
- Prefix mismatches: none (V3's paths are correct once normalized)

### 4.3 Files (104) — SET-IDENTICAL
V3's 104-file list matches my independent walk exactly (103 in `src/` + `launcher.pyw`; excludes vendored `src/frontend/node_modules/flatted/python/flatted.py`).

### 4.4 Symbols (777) — COUNT-IDENTICAL, CLASSIFICATION WEAK
Count matches exactly, but the per-symbol "Side Effects" and "Callers/Reachability" columns are **canned boilerplate**:
- `log_symbol_usage_legacy` (SYM-0508) marked "Pure / Read / Dependency" — it WRITES (`SymbolUsageLog` insert).
- `import_data` (SYM-0586) marked "Pure / Read" — it WRITES boards/symbols/achievements.
- `remove_owned_upload` (SYM-0483) marked "Route Handler / DB Mutation" — it does NO DB mutation; it unlinks files.
- Every launcher function marked "Route Handler / DB Mutation" or "Pure / Read / Dependency" — generic.
- `reset_database` (SYM-0503) marked "Route Handler / DB Mutation" — correct, but the column is not evidence of review depth.

### 4.5 Auth matrix (see `BACKEND_EVIDENCE_CHALLENGE_CLAIMS.md` CLM-17)
- V3 marks **all 11 guardian-profiles routes as "Anonymous: YES"** — WRONG. Every handler uses `get_current_teacher_or_admin` (403 for students, requires auth). Most also call `verify_student_access`.
- V3 marks `POST /api/users/students`, `POST /api/users/assign-student`, `DELETE /api/users/assign-student/...`, `POST /api/users/reset-password` as "Student Self: YES" — WRONG. Handlers raise 403 for students (verified in `users.py`).
- V3 marks achievement write routes (`POST /api/achievements`, `PUT/DELETE /{id}`, `POST /{id}/award`) as "Student Self: YES" — WRONG. Handler-level `user_type not in ["teacher","admin"] → 403` (verified in `achievements.py`).
- V3 marks `GET /api/auth/users/student-summaries` "Student Self: YES" — needs check; the shared dependency is `get_current_active_user`, but handler-level roster logic exists.
- The learning rows (student self / assigned teacher / unassigned teacher) are **CORRECT** — verified against `access.py` and `learning.py`.

### 4.6 Exception handlers — COUNT-IDENTICAL (142)

---

## 5. Explanation of Every Discrepancy

1. **126 vs 127 operations**: V3 extracted only `APIRoute` instances and missed the WebSocket route (`WS /api/collab/boards/{board_id}`). The final verification caught this (+1). Confirmed by live introspection.
2. **67 vs 103/100 paths**: "67" originates in `BACKEND_API_INVENTORY.md` (V1, manual grouping). V3 reused it without recomputation. Live table: 103 distinct registered paths, 100 after collapsing trailing slashes. The 5 dual-registrations are `/api/achievements`, `/api/boards`, `/api/notifications` (with and without trailing slash) and the trailing-slash-only `/api/learning-modes/`.
3. **Guardian-profiles "Anonymous" rows**: mechanical error in V3's matrix — it classified by route group instead of reading the dependency. The actual dependency is `get_current_teacher_or_admin` (defined in `guardian_profiles.py:34-43`).
4. **users.py "Student Self: YES" rows**: same class of error — matrix recorded the dependency (`get_current_active_user`) rather than handler-level 403 checks.
5. **Symbol side-effect labels**: V3's symbol inventory used a fixed set of column values not derived from the symbol's actual behavior. Counts are trustworthy; classification is not.
6. **Test mappings**: `tests/test_<basename>.py` names (e.g. `test_common.py`, `test_history.py`, `test_account_admin.py`) do not exist. Real tests live in differently named files. V3 fabricated the mapping column.
7. **Module mutable state 16**: V3's 16 is a curated subset of ~21 candidates; the inclusion rule (excludes scalars like `_startup_generation = 0`, `_consecutive_failures = 0`, `_circuit_open_until = 0.0`, and factory assignments like `_translation_client_factory = httpx.Client`) is undocumented. 9 bare-name mutable objects found by strict AST; the V3 list is plausible but not reproducible without the undocumented rule.
8. **Destructive flows 5 vs 6 vs 16+1**: the chain itself is inconsistent. V3 Proof §10 lists 6 flows; earlier reports say 5; final ledger says 16 ops + 1 repair flow. The 6-flow list is the defensible one (delete user, delete symbol, replace symbol image, delete board, reset password, import data). The "5" figure undercounts by omitting import-data replacement.
9. **Filesystem 68 / external 44**: superseded by the sub-claims verification (`BACKEND_EVIDENCE_CHALLENGE_V3_SUBCLAIMS.md`). Curated universes: **96 FS sites** (41 write/delete) and **25 core / 38 extended external I/O** — both with full member lists. V3's 68 and 44 have no member lists; 44 is only reachable via undocumented inherited-sites counting; 68 via no clean rule. Both totals are **NOT REPRODUCIBLE**.
10. **Exception breakdown 84/38/20**: 84 is an arithmetic residual mislabeled as "route-level error boundaries" (only 17 of 142 broad handlers raise `HTTPException`); 38 ≈ 40 by strict rule; 20 matches. "Diagnostic logging on all error paths" is contradicted (24 no-log handlers, 3 bare `pass`).

---

## 6. Bottom Line

- **Exactly reproducible**: files (104), symbols (777), mutation sites (231, set-identical), broad exception handlers (142).
- **Reproducible with known corrections**: operations (127 not 126), paths (103/100 not 67), auth matrix (guardian-profiles + users.py rows wrong).
- **Not reproducible / fabricated**: test-file mappings; symbol side-effect classifications; the "67" path count; the "5" destructive-operations figure; the 84/38/20 exception breakdown; the 68 filesystem and 44 external-I/O totals (no member lists; see `BACKEND_EVIDENCE_CHALLENGE_V3_SUBCLAIMS.md`).