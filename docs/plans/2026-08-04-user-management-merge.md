# User Management Merge Implementation Plan

> **Document status (2026-08-12): COMPLETED / HISTORICAL.** The shared user-management page, route rewiring, tests, and validation described below are already integrated. Treat the task and commit instructions as provenance only; do not execute them as pending work.
>
> **Current outcome:** `src/frontend/src/pages/UserManagement.tsx` serves the parameterized teacher/admin routes; `src/frontend/src/pages/Students.tsx` remains the student-management page. The current frontend gate is documented in `README.md`; no historical commit command below is pending.

> **Historical workflow note:** the original plan referenced an external plan-execution workflow file, which is not part of the current repository. Do not follow that historical instruction; use the current validation commands in `README.md`.

**Goal:** Replace the duplicated teacher and admin management pages with one role-parameterized page while preserving all existing management flows and access controls.

**Architecture:** Keep `/teachers` and `/admins` as stable, admin-only routes. Both routes lazy-load `pages/UserManagement.tsx` and pass `role="teacher"` or `role="admin"`. The page selects the existing role-specific i18n namespace and API filter, sharing all state, forms, table actions, validation, and error handling.

**Tech Stack:** React 19, TypeScript, React Router, Zustand auth store, Axios API client, react-i18next, Vitest.

---

### Task 1: Replace duplicated page implementations

**Files:**
- Create: `src/frontend/src/pages/UserManagement.tsx`
- Delete: `src/frontend/src/pages/Teachers.tsx`
- Delete: `src/frontend/src/pages/Admins.tsx`

Implement one `UserManagementPage({ role }: { role: 'teacher' | 'admin' })`. Preserve list, create, edit, reset-password, delete, validation, loading, and API error behavior. Keep self-delete enabled for the admin row so the backend 400 detail is surfaced in the page error banner.

### Task 2: Rewire lazy routes and preloaders

**Files:**
- Modify: `src/frontend/src/App.tsx`
- Modify: `src/frontend/src/components/Sidebar.tsx`

Load the shared page once and render it with the route-specific role prop. Update sidebar preloading to import `UserManagement` for both links while preserving `/teachers`, `/admins`, labels, and admin-only filtering.

### Task 3: Verify the merge

**Files:**
- Test: existing frontend Vitest suite

Run frontend lint, tests, and build. Start the manifest backend and frontend services, then use an isolated agent-browser session to verify admin navigation to both role pages, list/create validation, edit/reset/delete controls, self-delete error display, and non-admin redirect. Stop all services and commit the feature.
