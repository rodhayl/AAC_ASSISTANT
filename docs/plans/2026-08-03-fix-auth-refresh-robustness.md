# Fix Auth Refresh Robustness Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Preserve authenticated sessions when malformed or expired access tokens have a valid refresh token, while fully clearing persisted session state when validation fails online.

**Architecture:** Add one `clearSession` closure to the Zustand auth store and use it for logout and all session teardown branches. Make `checkAuth` treat missing, malformed, and expired access-token payloads identically by attempting refresh first; only an online refresh failure clears the session. Regression tests will mock the API and inspect both Zustand state and the `auth-storage` persistence record.

**Tech Stack:** React, TypeScript, Zustand persist, Vitest, jsdom.

---

### Task 1: Add failing auth-store regression tests

**Files:**
- Create: `src/frontend/src/store/authStore.test.ts`

**Step 1: Write tests for malformed/expired refresh, full clear, logout, and offline preservation.**

Use valid JWT-shaped payloads for the expired case, a garbage access token for the undecodable case, mocked `/auth/refresh` responses for success/401/offline, and assert the persisted `auth-storage` state fields.

**Step 2: Run the focused test file.**

Run: `npm --prefix src/frontend test -- --run src/store/authStore.test.ts`

Expected: FAIL because malformed tokens currently skip refresh and teardown branches do not consistently clear all persisted fields.

### Task 2: Implement centralized teardown and refresh-first validation

**Files:**
- Modify: `src/frontend/src/store/authStore.ts`

**Step 1: Add `clearSession` inside the store creator.**

Set `user`, `token`, `refreshToken`, `isAuthenticated`, `sessionExpiresAt`, and `error` to their cleared values.

**Step 2: Use `clearSession` for logout and all online session teardown paths.**

Keep the existing manual `localStorage.removeItem('token')` compatibility cleanup, but do not remove `auth-storage`.

**Step 3: Unify malformed and expired payload handling.**

When the token has no decodable payload, no `exp`, or an expired `exp`, call `refreshAccessToken`; if it returns false and `navigator.onLine !== false`, call `clearSession`. Preserve offline refresh failures.

**Step 4: Run the focused tests and fix only implementation issues.**

Run: `npm --prefix src/frontend test -- --run src/store/authStore.test.ts`

Expected: PASS.

### Task 3: Run the frontend validation gate

**Files:** None.

**Step 1: Run all frontend tests.**

Run: `npm --prefix src/frontend test -- --run`

**Step 2: Run lint and build.**

Run: `npm --prefix src/frontend run lint`

Run: `npm --prefix src/frontend run build`

Expected: all commands exit 0.

**Step 3: Manually verify auth refresh and invalid-session navigation.**

Start backend and frontend using the mission manifest, use a fresh agent-browser session, exercise expired JWT refresh, garbage-token refresh, and invalid-pair redirect/clear behavior, then stop every process/session started.

### Task 4: Commit the verified feature

**Files:**
- `src/frontend/src/store/authStore.ts`
- `src/frontend/src/store/authStore.test.ts`

**Step 1: Review status and diff.**

Run: `git status --short` and `git diff --check`.

**Step 2: Commit the feature.**

Run: `git add src/frontend/src/store/authStore.ts src/frontend/src/store/authStore.test.ts && git commit -m "fix(fix-auth-refresh-robustness): refresh malformed access tokens"`
