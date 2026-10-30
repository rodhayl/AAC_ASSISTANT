# AAC Assistant — historical frontend source snapshot

Selected frontend source from **31 August 2026**, before the September–October
refactors. This is a substantial **source-review sample**, not the complete
application, the current private product, or an installable AAC tool.

For interviews, access to the current private codebase may be requested from the author.

## Technical tour

The original files under `historical/frontend/` retain their original contents:

- **Board rendering and editing:** `CommunicationGrid`, `SymbolCard`,
  `BoardEditorGrid`, `DraggableSymbol`, `DroppableCell` and editor toolbar/settings.
- **Sentence composition:** `SentenceStrip` demonstrates draggable ordering,
  deletion, selection and action callbacks. `KeyboardOverlay` shows typed phrases,
  simple bilingual suggestions and local history handling.
- **Presentation and interactions:** communication toolbar, suggestion display,
  reusable controls/dialogs, accessible-interaction hook, symbol images and
  category styling, theme tokens, and English/Spanish labels.
- **Logic and tests:** original grid/symbol helpers, board-editor utilities and
  selected original Vitest/component test sources.

This exposes real component contracts, state/effect management, drag-and-drop,
localization, callbacks, styling and test design. It does **not** demonstrate a
working authentication flow, backend, AI model, speech service or complete app.
No replacement UI, simulated backend or invented product implementation was added.

## Small executable companion

A separate CLI harness exercises the historical pure helper modules with
synthetic data. With **Node.js 24 or newer**, no packages need installing:

```sh
node demo.mjs
node --test tests/historical.test.mjs
```

Expected phrase: `I want water.` This CLI and its six focused tests are the
**only execution validated here**. They need no credentials, server, model,
Internet connection, browser or real records. TypeScript stripping is built into
Node; this is not a TypeScript static typecheck.

## Source snapshot, not a standalone frontend

The historical React components and Vitest test files are retained for technical
inspection. **They were not built or executed as a frontend in this snapshot.**
The original app entrypoints, package/build configuration, authentication stores,
HTTP/WebSocket adapters and service integrations are intentionally absent.
Consequently some imports point to omitted application infrastructure; see
[SOURCE_SCOPE.md](SOURCE_SCOPE.md) for the exact inventory and
[DEPENDENCIES.md](DEPENDENCIES.md) for external packages. Installing those packages
alone does not make this an application. No runnable frontend is promised.

The source is not all side-effect-free: for example `KeyboardOverlay` retains
browser local-history code, image components can load supplied URLs, and some
components expect speech/auth callbacks or omitted adapters. They are not mounted
by the CLI. Do not turn this snapshot into a deployment with real user data
without an independent integration/security review.

## Provenance, rights and limits

See [PROVENANCE.md](PROVENANCE.md). All historical files are byte-identical to the
selected commit; only documentation and the small CLI/test harness are new. No
September–October implementation is included. The original [MIT license](LICENSE)
is preserved; the new harness/docs are also MIT. No ARASAAC images, recordings,
models, databases, private reports, secrets, Git history, Actions or releases are
included. The license does not relicense excluded third-party assets or later
private versions.

Historical behavior and limitations are preserved, not silently repaired: grid
capacity assumes valid dimensions, duplicate placements use last-write-wins, and
glossing uses basic English templates. This sample does not establish clinical
suitability, effectiveness, accessibility conformance or production security.
