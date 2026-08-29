import { test, expect } from '@playwright/test';

// The prediction source names emitted by PredictionService (see
// tests/test_prediction_service.py). The E2E test asserts the GUI wiring — that
// typing produces real predictions — not the tier logic itself, which is
// already unit-tested deterministically.
const KNOWN_SOURCES = new Set([
  'history',
  'general_model',
  'popular',
  'fallback',
  'standard_library',
  'board_personal',
  'board_popular',
  'board_layout',
  'punctuation',
  'category',
]);

test.describe('Prediction tiers', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test.beforeEach(async ({ page }) => {
    // Only the LLM-backed question generation is mocked. Boards, learning
    // modes, session persistence, and predictions all hit the real backend.
    await page.route('**/api/learning/*/ask', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          question_id: 1,
          question_text: 'Mock question',
          choices: ['Choice A', 'Choice B', 'Choice C'],
          correct_answer_index: 0,
        }),
      });
    });
  });

  test('typing in learning produces predictions in the smartbar', async ({ page }) => {
    await page.goto('/learning');

    // Create this spec's own session instead of relying on one planted by
    // another spec or by manual setup.
    const startButton = page.getByTestId('learning-session-start');
    await expect(startButton).toBeVisible({ timeout: 30000 });
    const startRequest = page.waitForRequest(
      (request) =>
        request.url().includes('/api/learning/start') && request.method() === 'POST',
    );
    await startButton.click();
    await startRequest;
    await expect(page.getByTestId('learning-session-active')).toBeVisible();

    // The auto-ask populates the first question; the free-text input becomes
    // interactive once the session is active.
    const input = page.locator('#learning-text-input');
    await expect(input).toBeVisible({ timeout: 30000 });

    // Wait for the next-symbol request that carries the word we type. The
    // Smartbar fires one request per input change.
    const predictionResponse = page.waitForResponse((response) => {
      if (!response.url().includes('/api/analytics/next-symbol')) return false;
      if (response.request().method() !== 'POST' || response.status() !== 200) return false;
      try {
        const body = response.request().postDataJSON() as { current_symbols?: string };
        return typeof body?.current_symbols === 'string' && body.current_symbols.includes('hello');
      } catch {
        return false;
      }
    });

    await input.fill('hello ');
    const response = await predictionResponse;
    const predictions = (await response.json()) as Array<{ label: string; source: string }>;

    expect(Array.isArray(predictions)).toBe(true);
    expect(predictions.length).toBeGreaterThan(0);
    for (const prediction of predictions) {
      expect(typeof prediction.label).toBe('string');
      expect(prediction.label.trim().length).toBeGreaterThan(0);
      expect(KNOWN_SOURCES.has(prediction.source)).toBe(true);
    }

    // The smartbar renders at least one selectable suggestion (not the empty
    // "No suggestions found" placeholder).
    await expect(page.locator('button.h-14').first()).toBeVisible();
  });
});
