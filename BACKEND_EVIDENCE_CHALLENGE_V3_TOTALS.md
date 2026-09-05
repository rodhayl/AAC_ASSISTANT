# V3 Totals-Only Claims Verification: Module State (16), Mutation Flows (14), Destructive Sites (52)

**Date**: 2026-08-28
**Scope**: Verify the three remaining totals-only V3 claims with the same member-list standard used for the exception breakdown, filesystem I/O, and external I/O:
1. **16 module mutable-state sites** (V3 Proof §19)
2. **14 logical mutation flows** (V3 Proof §9; member list in `BACKEND_V3_MUTATION_INVENTORY.md`)
3. **52 destructive sites** (V3 Proof §1, §38)

**Method**: AST scans + live FastAPI route introspection + ledger-range counting over the 104 production files + `launcher.pyw`. Every count below has raw members.

---

## 1. Module Mutable-State Sites (V3: 16)

### 1.1 V3 claim (§19)

> **Module-Level Singletons**: 16 mutable module-level objects (locks, events, provider singletons) are protected by thread locks (`_provider_lock`, `_startup_lock`, `vector_store_operation_lock`).

No member list. Examples given are all **locks**.

### 1.2 Independent enumeration

**Rule A — threading sync primitives (locks + semaphores): exactly 16**

| # | Site | Kind |
| :--- | :--- | :--- |
| 1 | `src/aac_app/db.py:27` `_resource_lock` | RLock |
| 2 | `src/aac_app/providers/local_tts_provider.py:192` `_import_lock` | Lock |
| 3 | `src/aac_app/providers/local_tts_provider.py:418` `_provider_lock` | Lock |
| 4 | `src/aac_app/services/local_vector_store.py:47` `_engine_listener_lock` | Lock |
| 5 | `src/aac_app/services/local_vector_store.py:51` `vector_store_operation_lock` | RLock |
| 6 | `src/aac_app/services/notification_events.py:80` `_subscriber_lock` | RLock |
| 7 | `src/aac_app/services/prediction_service.py:59` `_catalog_lock` | RLock |
| 8 | `src/aac_app/services/runtime_translation.py:22` `_translation_slots` | BoundedSemaphore |
| 9 | `src/aac_app/services/runtime_translation.py:30` `_circuit_lock` | Lock |
| 10 | `src/aac_app/services/symbol_analytics.py:54` `_history_transition_lock` | RLock |
| 11 | `src/api/deps/providers.py:61` `_startup_lock` | Lock |
| 12 | `src/api/deps/providers.py:68` `_provider_lock` | Lock |
| 13 | `src/api/deps/providers.py:74` `_speech_release_lock` | Lock |
| 14 | `src/api/deps/settings.py:11` `_settings_cache_lock` | RLock |
| 15 | `src/api/routers/providers.py:43` `_voice_install_lock` | Lock |
| 16 | `src/api/routers/providers.py:44` `_tts_download_lock` | Lock |

**16 = 15 locks + 1 semaphore — EXACT MATCH under this rule.**

### 1.3 But the claim's own description is wrong

V3's text says the 16 are "locks, **events**, **provider singletons**". Neither is in the 16:

- **Events**: zero `threading.Event` module-level objects exist (the only Event usage is `_deferred_vector_store_events: list[threading.Event]` — a **list of events** created per-deferral, `deps/providers.py:41, 155` — itself an uncounted mutable container).
- **Provider singletons**: 7 in `deps/providers.py` (`_vector_store`, `_ollama_provider`, `_openrouter_provider`, `_lmstudio_provider`, `_groq_provider`, `_speech_provider`, `_achievement_system`) + `_local_tts_provider` (local_tts_provider.py:423), `faster_whisper` (local_speech_provider.py:25), `_template_manager` (template_manager.py:345), `_guardian_service` (guardian_profile_service.py:469), `_engine_instance`/`_session_factory` (db.py:43) — **none** are in the 16.

### 1.4 Full mutable module-state universe (beyond the 16)

**Mutable containers/registries (9, not in the 16):**
```
notification_events.py:79   _subscribers = {}
prediction_service.py:61    _catalog_cache = WeakKeyDictionary()
symbol_analytics.py:55      _history_transition_cache = WeakKeyDictionary()
symbol_image_backfill.py:290 _scheduled_tasks = set()
deps/providers.py:41        _deferred_vector_store_events = []
deps/providers.py:86        _speech_release_workers = {}
deps/providers.py:91        _pending_llm_close_tasks = set()
deps/settings.py:10         _settings_cache = {}
runtime_translation.py:13   _translation_client_factory = httpx.Client (swappable factory)
```

**Scalar counters/flags mutated via `global` (8):**
```
deps/providers.py:62        _startup_generation = 0
deps/providers.py:63        _warmup_generation_local = threading.local()
prediction_service.py:68    _catalog_generation
runtime_translation.py:132,147  _consecutive_failures, _circuit_open_until
local_tts_provider.py:197   _available, _import_error, _import_attempted
local_speech_provider.py:25,89  FASTER_WHISPER_AVAILABLE, faster_whisper
local_vector_store.py:215   FASTEMBED_AVAILABLE
```

**Verdict**: **16 is reproducible ONLY as "threading sync primitives"** (exact). The claim's descriptive text ("events, provider singletons") misdescribes the members; the true mutable module-state universe (sync primitives + containers + singletons + scalars) is **38–46 sites**. The 16 undercounts real mutable state; the description is wrong; the number itself is defensible under a narrower, undocumented rule.

---

## 2. Logical Mutation Flows (V3: 14)

### 2.1 V3 claim (§9 + mutation inventory)

> 231 mutation sites and 14 logical mutation flows. **Unreviewed Flows: 0**. "All mutation flows enforce single transaction boundaries or clean rollback unlinking."

Member list EXISTS: FLOW-01…FLOW-14 in `BACKEND_V3_MUTATION_INVENTORY.md`.

### 2.2 Entry-point verification against the live route table

| Flow | V3 entry point | Actual (live table) | Verdict |
| :--- | :--- | :--- | :--- |
| FLOW-01 | `POST /api/auth/register` | `register` | **MATCH** |
| FLOW-02 | `POST /api/auth/token` | `login_for_access_token` | **MATCH** |
| FLOW-03 | `POST /api/auth/change-password` | `change_password` | **MATCH** |
| FLOW-04 | `POST /api/users/reset-password` | `reset_user_password` | **MATCH** |
| FLOW-05 | `DELETE /api/auth/users/{user_id}` | `delete_user` | **MATCH** |
| FLOW-06 | `POST /api/boards` | `create_board` (registered `/api/boards` AND `/api/boards/`) | **MATCH** (slash variant) |
| FLOW-07 | `DELETE /api/boards/{board_id}` | `delete_board` | **MATCH** |
| FLOW-08 | `POST /api/symbols/{symbol_id}/image` | **`POST /api/boards/symbols/{symbol_id}/image`** | **PATH WRONG** |
| FLOW-09 | `DELETE /api/symbols/{symbol_id}` | **`DELETE /api/boards/symbols/{symbol_id}`** | **PATH WRONG** |
| FLOW-10 | `POST /api/learning/start` | `start_session` | **MATCH** |
| FLOW-11 | `POST /api/learning/{session_id}/answer` | `submit_answer` | **MATCH** |
| FLOW-12 | `POST /api/learning/{session_id}/end` | `end_session` | **MATCH** |
| FLOW-13 | `POST /api/settings/ai` | **`PUT /api/settings/ai`** | **METHOD WRONG** |
| FLOW-14 | `POST /api/data/import` | `import_data` | **MATCH** |

**11/14 exact, 1 slash-variant, 3 with entry-point errors** (FLOW-08/09 paths, FLOW-13 method). The symbols routes moved under the boards router (`/api/boards/symbols/...`); settings/ai is PUT.

### 2.3 Completeness: the 14 flows do NOT cover all 231 sites

Ledger sites by file (231 total). Files with mutation sites **not attributable to any of the 14 flows**:

| File | Sites | Mutation domain missing from the flow table |
| :--- | ---: | :--- |
| `src/aac_app/seed.py` | 15 | Startup seeding (users, boards, symbols, achievements) |
| `src/api/routers/board_ai.py` | 13 | AI board generation (creates boards/symbols) |
| `src/api/routers/achievements.py` | 8 | Achievement CRUD |
| `src/api/routers/notifications.py` | 7 | Notification CRUD |
| `src/aac_app/services/guardian_profile_service.py` | 6 | Guardian profile CRUD |
| `src/aac_app/services/lockout_service.py` | 6 | Account lockout (used by FLOW-02, partially covered) |
| `src/api/routers/learning_modes.py` | 5 | Learning-mode CRUD |
| `src/api/routers/board_assignments.py` | 4 | Board assignment/unassignment |
| `src/api/routers/arasaac.py` + `arasaac_library_import.py` | 6 | ARASAAC symbol import |
| `src/api/routers/guardian_profiles.py` | 3 | Guardian profile routes |
| `src/api/routers/auth_preferences.py` | 2 | User preferences |
| `src/api/routers/providers.py` | 2 | Provider settings |
| `src/api/logging_config.py` | 1 | Log rotation |
| `src/scripts/account_admin.py` | 1 | Admin script |
| **Total outside the 14 flows** | **≥73 (31.6%)** | |

The remaining ~158 sites fall inside flow files but the flow table's DB-write columns are **partial** (e.g., FLOW-11 lists `LearningSession, SymbolUsageLog, UserAchievement` but the answer path also touches progress/notification state; FLOW-05's "Cascades 12 DB tables" is a group label covering **30 individual ledger sites** in `delete_user` alone).

**Verdict**: the 14-flow table is a **partial grouping of major user-facing flows**, not a complete partition of the 231 sites. "Unreviewed Flows: 0" is true only for the 14 rows; at least 8 mutation entry points (seeding, AI board generation, achievements CRUD, notifications CRUD, guardian profiles, learning modes, ARASAAC import, preferences/providers settings) are absent from the flow table. The grouping did not "hide" individual sites (the 231-site ledger is complete and set-identical), but the completeness implication of "231 sites AND 14 flows" is misleading.

---

## 3. Destructive Sites (V3: 52)

### 3.1 V3 claim (§1, §38)

> "52 Sites across 6 Logical Destructive Flows" — composition never documented; ledger does not tag destructive rows.

### 3.2 Independent site-level count for the 16 destructive operations

Ledger sites (file:line) falling inside each destructive handler's range:

| Op | Handler range | Ledger sites | Lines |
| :--- | :--- | ---: | :--- |
| 1 delete_user | auth_users.py:543–756 | **30** | 592, 601, 606, 611, 614, 622, 625, 630, 644, 649, 652, 657, 662, 675, 680, 685, 694, 697, 699, 700, 701, 702, 706, 711, 716, 721, 726, 735, 744, 755 |
| 2 delete_board | boards.py:194–217 | 2 | 215, 216 |
| 3 delete_symbol | symbols.py:409–429 | 3 | 427, 428, 429 |
| 4 remove_symbol_from_board | symbols.py:627–638 | 2 | 636, 637 |
| 5 unassign_board | board_assignments.py:102–141 | 2 | 139, 140 |
| 6 unassign_student | users.py:184–225 | 2 | 223, 224 |
| 7 delete_achievement | achievements.py:306–362 | 2 | 358, 359 |
| 8 delete_learning_mode | learning_modes.py:236–267 | 2 | 265, 266 |
| 9 delete_notification | notifications.py:253–290 | 2 | 288, 289 |
| 10 delete_student_profile | guardian_profiles.py:350–390 | 1 | 383 |
| 11 update_symbol_image | symbols.py:381–402 | 4 | 393, 395, 396, 402 |
| 12 reset_user_password | users.py:228–315 | 1 | 314 |
| 13 change_password | auth_users.py:350–420 | 2 | 408, 409 |
| 14 import_data | export_import.py:767–857 | 1 | 855 |
| 15 reset_database | admin.py:14–57 | **0** | `drop_all`/`create_all` are DDL, not ledger-style mutations |
| 16 logout | auth.py:355–378 | 2 | 372, 373 |
| | **TOTAL** | **58** | |

Plus schema.py rebuild internals (FK table drop/rename @210–330, label dedup, seed duplicate delete) — **entirely absent from the 231-site ledger** (no `schema.py` rows).

### 3.3 Reconciliation

- **52 is not reproducible**: the 6-flow subset (ops 1, 2, 3, 11, 12, 14) contains **41** ledger sites (30+2+3+4+1+1); the full 16-op set contains **58**; neither equals 52 under any clean rule.
- The earlier "≈46" estimate in `BACKEND_EVIDENCE_CHALLENGE_DESTRUCTIVE_INVENTORY.md` §4 **undercounted** the delete_user cascade (30 sites, not ~14) — this document corrects it to **58**.
- The single biggest component is the 12-table cascade inside `delete_user` (30 sites), which V3's "Cascades 12 DB tables" group label compressed to one row.
- **Verdict**: 52 unsupported; authoritative site-level accounting = **58 ledger sites across the 16 ops + schema.py internals (unledgered)**. Operation-level inventory (16 + 1) remains the authoritative unit.

---

## 4. Reconciliation Summary

| Metric | V3 | Independent | Delta | Verdict |
| ------ | -: | ----------: | ----: | ------- |
| Module mutable-state sites | 16 | 16 sync primitives (exact) / 38–46 full universe | 0 / +22–30 | **MATCHES only under "sync primitives" rule**; claim text ("events, provider singletons") misdescribes members |
| Logical mutation flows | 14 | 14 (11 exact, 1 slash, 3 entry-point errors) | 0 | **COUNT OK, 3/14 entry points wrong, coverage partial** — ≥73 sites (31.6%) in flows absent from the table |
| Destructive sites | 52 | **58** (16 ops) | +6 | **NOT REPRODUCIBLE**; 52 unsupported; corrects the earlier ≈46 estimate |

## 5. Bottom Line

- **16 module-state**: the number is reproducible only as "threading sync primitives" (15 locks + 1 semaphore); the claim's own description (events, provider singletons) is wrong — the true mutable-state universe is 38–46 sites.
- **14 flows**: entry points mostly correct (11/14) but 3 are stale/wrong (symbols paths, settings method) and the table is a partial grouping — 31.6% of mutation sites belong to flows not represented.
- **52 destructive sites**: unsupported; independent count is **58 ledger sites** for the 16 ops (delete_user cascade = 30 alone) + unledgered schema.py internals.

These three claims do not invalidate the verified core (231-site ledger remains set-identical; 16 ops remain the correct destructive unit) but they further confirm **PRIOR_AUDIT_EVIDENCE_HAS_MATERIAL_GAPS**: presentation-level totals repeatedly fail the member-list standard.

## 6. Repository Modification Confirmation

`Production backend modified by this task: NONE`
`Backend tests modified by this task: NONE`
`Frontend modified by this task: NONE`
`Concurrent work reverted/overwritten: NONE`