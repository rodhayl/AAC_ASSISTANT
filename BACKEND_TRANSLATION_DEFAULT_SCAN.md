# Backend Translation Helper Default Namespace Scan

**Date**: 2026-08-28

## Scope

Scanned backend translation helpers and default/static translation calls under `src/`, including `get_text`, `get_shared_text`, `TranslationService.get`, and callback defaults passed to access helpers. Locale keys were resolved independently against both `en` and `es` JSON namespaces.

## Results

- `src/api/deps/auth.py:get_text`: default namespace is `common`, default key is `errors.unknown`; the key exists in both locales.
- `src/api/deps/access.py:get_learning_session_or_404`: default callback explicitly uses `namespace="pages/learning"`; `errors.sessionNotFound`, `errors.unauthorized`, and `errors.sessionNotActive` exist in both locales.
- `src/api/deps/access.py` board helper defaults use the `common` namespace; their `errors.boards.*` keys exist in both locales.
- `src/api/routers/learning.py:get_text`: local wrapper explicitly uses `namespace="pages/learning"`. Its `errors.unauthorizedUser`, `errors.unknownError`, `errors.noSymbolsProvided`, and `errors.unauthorized` keys exist in both locales.
- All other statically resolvable backend translation calls checked against their effective `common` namespace resolved in both locales.

## Apparent mismatches rejected

An initial namespace-agnostic scan flagged learning-router calls as missing from `common`. They are false positives: those calls bind to the local `learning.py:get_text` wrapper, which routes to `pages/learning`. The keys are present at `src/frontend/src/locales/{en,es}/pages/learning.json`.

## Regression coverage

Added focused contract tests in `tests/test_backend_translation_contract.py` covering the learning-session default namespace, required learning error keys in both locales, and the learning router's local namespace wrapper.

## Disposition

No additional confirmed namespace mismatch was found. The previously identified `get_learning_session_or_404` mismatch remains remediated and is covered by `tests/test_teacher_student_access.py` plus the contract tests above.
