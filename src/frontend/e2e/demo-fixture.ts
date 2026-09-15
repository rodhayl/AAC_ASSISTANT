import type { APIRequestContext } from '@playwright/test';

/**
 * Demo-data fixture for specs that assert the "Comunicación General" board.
 *
 * Those specs used to require `AAC_SEED_SAMPLE_DATA=true` (the seeded CI job),
 * which meant the clean/unseeded suite could not exercise them at all. This
 * helper builds the *same* shape through the public API instead:
 *
 *  - a 3x4 board named `Comunicación General` owned by the admin, filled with
 *    the first 12 symbols of the catalog (exactly what `seed.py` picks), so the
 *    board is "playable" for symbol hunt and every symbol shows as "in use";
 *  - assigned to `student1`, so the student views can open it.
 *
 * It is idempotent and reuses a seeded board when one already exists, so the
 * seeded CI job is unaffected.
 */

export const DEMO_BOARD_NAME = 'Comunicación General';
const DEMO_BOARD_SYMBOLS = 12;
const GRID_ROWS = 3;
const GRID_COLS = 4;

type DemoBoard = { id: number; name: string };

type BoardRow = { id: number; name: string; user_id?: number };

type AdminSession = {
  userId: number;
  headers: Record<string, string>;
};

// One login per Playwright worker process: `/api/auth/token` is limited to ten
// requests per minute per IP, and the fixture runs in a `beforeEach`.
let adminSessionPromise: Promise<AdminSession> | null = null;

function adminSession(request: APIRequestContext): Promise<AdminSession> {
  adminSessionPromise ??= loginAsAdmin(request).catch((error: unknown) => {
    // Never cache a failure: the next call retries instead of rejecting every
    // remaining test in this worker with the first transient error.
    adminSessionPromise = null;
    throw error;
  });
  return adminSessionPromise;
}

/** The cached token was invalidated (password change bumps the security version). */
class StaleSessionError extends Error {}

function adminGet(
  request: APIRequestContext,
  session: AdminSession,
  path: string,
): ReturnType<APIRequestContext['get']> {
  return request.get(path, { headers: session.headers }).then((response) => {
    if (response.status() === 401) throw new StaleSessionError(path);
    return response;
  });
}

function adminPost(
  request: APIRequestContext,
  session: AdminSession,
  path: string,
  data: unknown,
): ReturnType<APIRequestContext['post']> {
  return request.post(path, { headers: session.headers, data }).then((response) => {
    if (response.status() === 401) throw new StaleSessionError(path);
    return response;
  });
}

async function loginAsAdmin(request: APIRequestContext): Promise<AdminSession> {
  const login = await request.post('/api/auth/token', {
    form: {
      username: process.env.E2E_ADMIN_USERNAME || 'admin1',
      password: process.env.E2E_ADMIN_PASSWORD || 'Admin123',
    },
  });
  if (!login.ok()) {
    throw new Error(`demo fixture: admin login failed (HTTP ${login.status()})`);
  }
  const { access_token: token } = (await login.json()) as { access_token: string };

  const me = await request.get('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } });
  if (!me.ok()) {
    throw new Error(`demo fixture: GET /api/auth/me failed (HTTP ${me.status()})`);
  }
  const profile = (await me.json()) as { id: number };
  return { userId: profile.id, headers: { Authorization: `Bearer ${token}` } };
}

async function createBoardWithSymbols(
  request: APIRequestContext,
  session: AdminSession,
): Promise<DemoBoard> {
  // The catalog listing lives on the boards router as `/api/boards/symbols`.
  const symbolsResponse = await adminGet(
    request,
    session,
    `/api/boards/symbols?limit=${DEMO_BOARD_SYMBOLS}`,
  );
  if (!symbolsResponse.ok()) {
    throw new Error(`demo fixture: GET /api/boards/symbols failed (HTTP ${symbolsResponse.status()})`);
  }
  const symbols = (await symbolsResponse.json()) as { id: number }[];

  const created = await adminPost(request, session, `/api/boards?user_id=${session.userId}`, {
      name: DEMO_BOARD_NAME,
      description: 'Basic vocabulary board with common symbols',
      is_public: true,
      is_template: true,
      grid_rows: GRID_ROWS,
      grid_cols: GRID_COLS,
      symbols: symbols.map((symbol, index) => ({
        symbol_id: symbol.id,
        position_x: index % GRID_COLS,
        position_y: Math.floor(index / GRID_COLS),
        size: 1,
        is_visible: true,
      })),
  });
  if (!created.ok()) {
    throw new Error(`demo fixture: board creation failed (HTTP ${created.status()})`);
  }
  return (await created.json()) as DemoBoard;
}

async function studentId(
  request: APIRequestContext,
  session: AdminSession,
): Promise<number | null> {
  const username = process.env.E2E_STUDENT_USERNAME || 'student1';
  const students = await adminGet(request, session, '/api/users/students');
  if (!students.ok()) return null;
  const body = (await students.json()) as unknown;
  const list = Array.isArray(body)
    ? body
    : ((body as { students?: unknown[]; items?: unknown[] }).students ??
      (body as { items?: unknown[] }).items ??
      []);
  const match = (list as { id: number; username: string }[]).find(
    (student) => student.username === username,
  );
  return match?.id ?? null;
}

/**
 * Ensure the demo board exists (with symbols) and is assigned to the student
 * account used by the role-specific specs. Safe to call from a `beforeEach`:
 * the lookup is idempotent and only writes when something is missing.
 *
 * Each call re-checks the current state (so a spec that unassigns or deletes
 * the board is repaired for the next one) but the admin session behind it is
 * memoized per worker: `/api/auth/token` allows ten requests per minute per
 * IP, and the demo specs share that budget with the specs that authenticate
 * on purpose. A memoized token can still be revoked mid-run — the settings
 * spec changes the admin password, which bumps the security version and
 * invalidates previous tokens — so a 401 drops the session and retries once.
 */
export async function ensureDemoBoard(request: APIRequestContext): Promise<DemoBoard> {
  try {
    return await buildDemoBoard(request);
  } catch (error) {
    if (!(error instanceof StaleSessionError)) throw error;
    adminSessionPromise = null;
    return buildDemoBoard(request);
  }
}

async function buildDemoBoard(request: APIRequestContext): Promise<DemoBoard> {
  const session = await adminSession(request);

  const boardsResponse = await adminGet(
    request,
    session,
    `/api/boards?limit=100&user_id=${session.userId}`,
  );
  if (!boardsResponse.ok()) {
    throw new Error(`demo fixture: GET /api/boards failed (HTTP ${boardsResponse.status()})`);
  }
  const boardsBody = (await boardsResponse.json()) as unknown;
  const boards = (Array.isArray(boardsBody)
    ? boardsBody
    : ((boardsBody as { boards?: unknown[]; items?: unknown[] }).boards ??
      (boardsBody as { items?: unknown[] }).items ??
      [])) as BoardRow[];

  const board =
    boards.find((candidate) => candidate.name === DEMO_BOARD_NAME) ??
    (await createBoardWithSymbols(request, session));

  // Assign to the student the role specs log in as. The endpoint is idempotent,
  // so re-assigning a seeded board is a no-op.
  const student = await studentId(request, session);
  if (student !== null) {
    const assigned = await adminPost(request, session, `/api/boards/${board.id}/assign`, {
      student_id: student,
    });
    if (!assigned.ok()) {
      throw new Error(`demo fixture: board assignment failed (HTTP ${assigned.status()})`);
    }
  }

  return { id: board.id, name: board.name };
}
