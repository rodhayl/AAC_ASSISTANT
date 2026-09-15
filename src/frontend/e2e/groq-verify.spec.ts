import { expect, test, type Page } from '@playwright/test';

/**
 * End-to-end browser verification of the Groq AI provider flow against a real
 * production server (no API mocks):
 *   1. Settings -> AI Provider: Groq card, API key + model selection, health.
 *   2. Learning: start a session and receive a real Groq-generated question.
 *
 * Requires the production server on PLAYWRIGHT_BASE_URL (default 8086), the
 * admin account admin1/Admin123, and a valid Groq API key set via
 * E2E_GROQ_API_KEY (or the hardcoded default below for local verification).
 */

const GROQ_API_KEY = process.env.E2E_GROQ_API_KEY;
const GROQ_MODEL = process.env.E2E_GROQ_MODEL || 'openai/gpt-oss-20b';

if (!GROQ_API_KEY) {
  throw new Error('E2E_GROQ_API_KEY is required to run this verification spec.');
}

type AiSettings = Record<string, unknown>;

/** Read the persisted AI settings through the page's own session. */
async function readAiSettings(page: Page): Promise<AiSettings> {
  return page.evaluate(async () => {
    const raw = localStorage.getItem('auth-storage');
    const token = raw ? (JSON.parse(raw).state?.token as string) : '';
    const res = await fetch('/api/settings/ai', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      throw new Error(`GET /api/settings/ai failed: HTTP ${res.status}`);
    }
    const body = await res.json();
    return (body.settings ?? body) as Record<string, unknown>;
  });
}

/**
 * The verification run types a live paid key into the settings form, which
 * auto-saves it. Restore the pre-run values afterwards (even when an
 * assertion fails) so a shared or CI server never keeps the key.
 */
async function restoreAiSettings(page: Page, settings: AiSettings): Promise<void> {
  const restorable: AiSettings = { ...settings };
  delete restorable.can_edit;
  for (const key of ['groq_api_key', 'openrouter_api_key']) {
    // A masked value must never be written back over the real secret.
    if (restorable[key] === '********') delete restorable[key];
  }
  await page.evaluate(async (payload) => {
    const raw = localStorage.getItem('auth-storage');
    const token = raw ? (JSON.parse(raw).state?.token as string) : '';
    const res = await fetch('/api/settings/ai', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`settings restore failed: HTTP ${res.status}`);
    }
  }, restorable);
}

async function loginAsAdmin(page: Page) {
  await page.goto('/login');
  await page.evaluate(() => {
    localStorage.clear();
    localStorage.setItem('i18nextLng', 'en');
    localStorage.setItem('aac_assistant_locale', 'en');
  });
  await page.reload();
  await expect(page.locator('button[type="submit"]')).toBeVisible();
  await page.locator('#username').fill(process.env.E2E_ADMIN_USERNAME || 'admin1');
  await page.locator('#password').fill(process.env.E2E_ADMIN_PASSWORD || 'Admin123');
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL('/', { timeout: 20000 });
  await expect(page.getByRole('button', { name: /sign out|cerrar/i })).toBeVisible({
    timeout: 20000,
  });
}

test.describe('Groq provider end-to-end', () => {
  test.use({ storageState: undefined });

  // Captured by the settings test and restored in afterEach, which runs even
  // when an assertion fails. A live paid key must never be left configured
  // just because the spec stopped early.
  let capturedSettings: AiSettings | null = null;

  test.afterEach(async ({ page }) => {
    const settings = capturedSettings;
    capturedSettings = null;
    if (!settings) return;
    await restoreAiSettings(page, settings);
  });

  test('settings UI configures Groq and reports healthy', async ({ page }) => {
    await loginAsAdmin(page);
    capturedSettings = await readAiSettings(page);

    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: /settings|ajustes/i })).toBeVisible();

    // The AI Provider section is always rendered; the Groq card is the 4th.
    const groqCard = page.locator('#settings-ai button', { hasText: 'Groq' });
    await expect(groqCard).toBeVisible();
    await groqCard.click();

    // Fill the API key and select the model from the fetched model list.
    const apiKeyInput = page.locator('#primary-groq-api-key');
    await expect(apiKeyInput).toBeVisible();
    await apiKeyInput.fill(GROQ_API_KEY);

    // Refresh fetches models from Groq with the request-scoped key header.
    const refreshBtn = page.locator('#settings-ai button', { hasText: /refresh|actualizar/i });
    await expect(refreshBtn).toBeEnabled();
    await refreshBtn.click();

    const modelSearch = page.locator('#primary-groq-model-search');
    await expect(modelSearch).toBeVisible();
    await modelSearch.fill(GROQ_MODEL);
    const modelOption = page
      .locator('#settings-ai div.absolute.z-10 button', { hasText: GROQ_MODEL })
      .first();
    await expect(modelOption).toBeVisible({ timeout: 20000 });
    await modelOption.click();

    // Wait for the auto-save (500ms debounce) to persist groq settings. The
    // PUT only fires when a value actually changed: on a server that already
    // has this exact key+model persisted, the auto-save is a no-op. Verify
    // the persisted state either through the PUT echo or by polling the
    // settings endpoint, so the spec works in both fresh and pre-configured
    // environments.
    const putPromise = page
      .waitForResponse(
        (r) => r.url().includes('/api/settings/ai') && r.request().method() === 'PUT',
        { timeout: 15000 },
      )
      .catch(() => null);
    const putResponse = await putPromise;

    let persisted: Record<string, unknown> = {};
    if (putResponse) {
      const putBody = (await putResponse.json()) as Record<string, unknown>;
      persisted = (putBody.settings ?? putBody) as Record<string, unknown>;
    } else {
      // No PUT happened (values already persisted); confirm by GET using the
      // token the auth store keeps in localStorage. A non-OK response is a
      // failure, not an empty object to assert against.
      persisted = await readAiSettings(page);
    }
    expect(persisted.provider).toBe('groq');
    expect(persisted.groq_model).toBe(GROQ_MODEL);

    // Check Provider Health: the real key must report Groq available. The UI
    // language follows the admin's persisted preference (may be es-ES), so
    // assertions match both English and Spanish text.
    await page.getByRole('button', { name: /check provider health|comprobar estado/i }).click();
    await expect(page.getByText(/Groq:\s*ok/)).toBeVisible({ timeout: 30000 });
    await expect(
      page.getByText(/Groq (is available and responding|está disponible y responde correctamente)/i),
    ).toBeVisible({ timeout: 30000 });
  });

  test('learning: starts a session and receives a real Groq question', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/learning');

    // Sessions start from the student-facing topic picker (the older
    // `learning-session-start` button was replaced by it).
    const topicCard = page.locator('[data-testid^="topic-card-"]').first();
    await expect(topicCard).toBeVisible({ timeout: 20000 });

    // The first adaptive question is auto-requested; wait for the real Groq
    // response (a reasoning model can take a while).
    const askResponse = page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        /\/api\/learning\/\d+\/ask$/.test(new URL(r.url()).pathname),
      { timeout: 180000 },
    );
    await topicCard.click();

    const response = await askResponse;
    expect(response.status()).toBe(200);
    const body = (await response.json()) as {
      question_text?: string | null;
      choices?: string[] | null;
      provider_used?: string | null;
    };
    // The provider that actually served the question must be Groq, and the
    // question must be real generated content rather than a fallback.
    expect(body.provider_used).toBe('groq');
    expect((body.question_text ?? '').trim().length).toBeGreaterThan(0);
    expect((body.choices ?? []).length).toBeGreaterThan(0);

    // A real question renders with non-empty choices in the UI.
    const questionCard = page.locator('[data-testid="question-card"]');
    await expect(questionCard).toBeVisible({ timeout: 60000 });
    const choices = questionCard.locator('button[aria-label]');
    await expect(choices.first()).toBeVisible();
    expect(await choices.count()).toBeGreaterThan(0);
  });
});