# External dependency context

The CLI companion needs only Node.js 24+. The React source snapshot is not standalone. The following direct package imports/style dependencies occur in the selected source/tests; version strings are from the historical project manifest, not a current security recommendation or an installation recipe. Transitive dependencies have not been audited or installed for this sample. There is no lockfile/build gate for this reduced frontend.

| Package | Historical declared version |
| --- | --- |
| `@base-ui/react` | `^1.7.0` |
| `@dnd-kit/core` | `^6.3.1` |
| `@dnd-kit/sortable` | `^10.0.0` |
| `@dnd-kit/utilities` | `^3.2.2` |
| `@testing-library/jest-dom` | `^6.6.3` |
| `@testing-library/react` | `^16.3.2` |
| `class-variance-authority` | `^0.7.1` |
| `clsx` | `^2.1.1` |
| `lucide-react` | `^0.554.0` |
| `react` | `19.2.8` |
| `react-i18next` | `^15.0.0` |
| `shadcn` | `^4.19.0` |
| `sonner` | `^2.0.8` |
| `tailwind-merge` | `^3.6.0` |
| `tailwindcss` | `^4.1.18` |
| `tw-animate-css` | `^1.4.0` |
| `vitest` | `^4.1.10` |

React rendering/DOM, localization, drag-and-drop, controls/icons, style utilities and Vitest/Testing Library are represented. Original authentication, API, WebSocket and speech infrastructure is omitted; see SOURCE_SCOPE.md. No claims about present-day vulnerability status are made.
