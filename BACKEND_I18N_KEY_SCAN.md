# Backend i18n Key Reference Scan (post-locale-cleanup)

**Date**: 2026-08-28
**Trigger**: The concurrent frontend locale cleanup removed `logFailed` and `providerResponseError` from `common.json`, orphaning the backend's `errors.analytics.logFailed` reference (already fixed to `logSymbolFailed` — see `BACKEND_VERIFIER_PRIOR_MUTATION_DISCLOSURE.md` §3). This scan checks whether **any other** backend i18n references were orphaned.

## Method

AST extraction of every `get_text(...)` / `translation_service.get(...)` key argument across the 104 production files + `launcher.pyw` + `scripts/`, resolved against `src/frontend/src/locales/{en,es}/common.json` and `pages/learning.json`, with namespace attribution corrected for `learning.py`'s local `get_text` wrapper (`namespace="pages/learning"`, `learning.py:28-31`).

## Results

| Category | Count | Detail |
| :--- | ---: | :--- |
| Static refs resolving in en AND es | **233** | all namespaces |
| Static refs initially flagged dangling | 10 | **all false positives** — `learning.py` refs (`errors.unauthorizedUser`, `errors.unknownError`, `errors.noSymbolsProvided`) use the local wrapper → `pages/learning` namespace, where they exist (`pages/learning.json` errors subkeys) |
| **Actively dangling static keys** | **0** | — |
| Dynamic keys traced | 15 | all resolve or fall back by design (below) |
| Latent dangling default | **1** | `src/api/deps/access.py:32` (below) |

## The one latent dangling default

**`src/api/deps/access.py:32`** — `get_learning_session_or_404` default message lambda:

```python
message = message or (lambda key: get_text(current_user, key))   # common namespace
...
detail=message("errors.sessionNotFound")                          # line ~33
```

- `errors.sessionNotFound` exists in **`pages/learning`** (en/es) but **NOT in `common`** (en/es).
- **Not currently triggered**: all 6 callers in `learning.py` (lines 97, 127, 160, 219, 268, 296) pass `message=lambda key: get_text(current_user, key)` (the pages/learning wrapper). The default fires only if a future caller omits `message` — then a 404 would return the raw string `errors.sessionNotFound`.
- Severity: **latent / defensive**, not an active bug. Fixed in `src/api/deps/access.py`: the default lambda now explicitly passes `namespace="pages/learning"`, matching the key's locale namespace.

## Dynamic keys traced — all OK

| Site | Key | Result |
| :--- | :--- | :--- |
| `access.py:129` `error_key` default | `errors.boards.unauthorizedModifyBoard` | ✓ exists (common, en/es) |
| `access.py:129` callers | `errors.boards.unauthorizedSuggestions` (board_ai.py:339), `unauthorizedAssign` (board_assignments.py:68), `unauthorizedUnassign` (board_assignments.py:120) | ✓ all exist |
| `access.py:245` `error_key` | same defaults/callers | ✓ |
| `auth_helpers.py:77` ← `auth_service.py:23-40` | `errors.passwordRequired/Length/Uppercase/Lowercase/Number` | ✓ all exist under `errors.*` (common, en/es) — note: **not** `errors.auth.*` |
| `responses.py:343, 480` | `correctAnswer`, `feedback.goodTry` | ✓ exist (pages/learning, en/es) |
| `session.py:154` | `topics.{topic_key}` — 9 mapped keys (general, daily, food, school, emotions, travel, hobbies, health, shopping) | ✓ all exist (en/es); unmapped topics fall back to raw string by design (`session.py:155-157`) |
| `session.py:171` | `welcomeContext` / `welcomeMessage` / `welcomeMessageSymbol` | ✓ all exist |
| `auth.py:86` | `key` — the `get_text` definition's own dispatcher | not a reference |

## Removed-key reconciliation

- `logFailed` — the **only** backend-referenced key the cleanup removed. Already migrated to `logSymbolFailed` (analytics.py:332-337, dispositioned KEEP).
- `providerResponseError` — **no backend references** (frontend-only key; removed cleanly).
- No other removed keys are referenced by the backend.

## Conclusion

**Zero actively dangling backend i18n references.** The concurrent locale cleanup orphaned exactly one backend key (`logFailed`), already repaired. The latent `access.py` default was corrected to use the `pages/learning` namespace, so future callers cannot emit a raw `errors.sessionNotFound` key.

## Repository Modification Confirmation

`Production backend modified by this task: YES — access.py default translation namespace corrected`
`Backend tests modified by this task: NONE`
`Frontend modified by this task: NONE`
`Concurrent work reverted/overwritten: NONE`