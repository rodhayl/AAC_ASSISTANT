import { test, expect } from '@playwright/test';

test.describe('Learning', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test.beforeEach(async ({ page }) => {
    // Mock auto-asked adaptive questions so the flow does not hit the LLM
    await page.route('**/api/learning/*/ask', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          question_id: 1,
          question_text: 'Mock question',
          choices: ['Choice A', 'Choice B', 'Choice C'],
          correct_answer_index: 0
        })
      });
    });

    // Mock Learning Answer API to avoid real LLM dependency
    await page.route('**/api/learning/*/answer', async route => {
      console.log(`[Mock] Intercepted Learning Answer: ${route.request().url()}`);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          is_correct: null,
          transcription: null,
          feedback_message: "Mocked AI response",
          confidence: 0.8,
          comprehension_score: 0.0,
          next_action: "continue_questions",
          questions_answered: 0
        })
      });
    });

    await page.goto('/learning');
  });

  test('should start a practice session', async ({ page }) => {
    // Remove networkidle which is flaky
    // Check if input is already visible (active session)
    const input = page.getByPlaceholder(/type|escribe/i).last();

    // Give it a moment to render
    await page.waitForTimeout(2000);

    if (await input.isVisible()) {
      // Already started
      await expect(input).toBeVisible();
    } else {
      const startBtn = page.getByRole('button', { name: /start session|comenzar sesión/i });
      await expect(startBtn).toBeVisible({ timeout: 10000 });
      await startBtn.click();
      await expect(input).toBeVisible();
    }
  });

  test('does not start another session after the current session is ended', async ({ page }) => {
    let startRequests = 0;
    page.on('request', request => {
      if (request.url().includes('/api/learning/start') && request.method() === 'POST') {
        startRequests += 1;
      }
    });
    await page.route('**/api/learning/start**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          session_id: 900000 + startRequests,
          welcome_message: 'E2E welcome',
        }),
      });
    });
    await page.route('**/api/learning/*/end', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          session_id: 900001,
          summary: 'E2E session completed',
          comprehension_score: 0,
          questions_answered: 0,
          correct_answers: 0,
        }),
      });
    });
    await page.route('**/api/achievements/user/*/check', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    });

    const startButton = page.getByTestId('learning-session-start');
    await expect(startButton).toBeVisible();
    await startButton.click();
    await expect(page.getByTestId('learning-session-active')).toBeVisible();
    expect(startRequests).toBe(1);

    await page.getByTestId('learning-session-active').click();
    const confirmation = page.getByRole('dialog');
    await expect(confirmation).toBeVisible();
    await confirmation.getByRole('button', { name: /end session|finalizar sesión/i }).click();

    await expect(page.getByTestId('session-summary-modal')).toBeVisible();
    await expect(page.getByTestId('learning-session-active')).not.toBeVisible();
    await expect(page.getByTestId('learning-session-start')).toBeVisible();
    await expect(page.locator('[role="log"]')).not.toContainText('E2E welcome');

    // Keep the page mounted long enough to catch a delayed auto-start or a
    // stale callback from the completed session.
    await page.waitForTimeout(2000);
    expect(startRequests).toBe(1);
  });

  test('should chat with companion', async ({ page }) => {
    // Check if we are on the right page
    await expect(page).toHaveURL('/learning');
    await expect(page.locator('.animate-spin')).not.toBeVisible({ timeout: 10000 });

    // Find input
    const input = page.getByPlaceholder(/type|escribe/i).last();

    // Ensure session is started via API/Store injection if button not clicked
    // Wait for the session state to settle before submitting. The input can
    // render while the initial session request is still in flight; checking
    // only input visibility can otherwise submit with no active session.
    const startBtn = page.getByTestId('learning-session-start');
    const endBtn = page.getByTestId('learning-session-active');
    if (!(await endBtn.isVisible())) {
      await expect(startBtn).toBeVisible({ timeout: 15000 });
      await startBtn.click();
    }
    await expect(endBtn).toBeVisible({ timeout: 15000 });

    await expect(input).toBeVisible();
    await input.fill('Hello');

    // Find send button (icon button usually)
    const sendBtn = page.locator('button[type="submit"]').first();

    // Check if button is disabled?

    // Count messages before
    // Use a more generic selector for message bubbles (bg-gray-100 or bg-indigo-100)
    const messagesBefore = await page.locator('.rounded-2xl').count();

    await sendBtn.click();

    // Wait for message count to increase
    // This covers both user message appearing and AI response
    await expect(async () => {
      const messagesAfter = await page.locator('.rounded-2xl').count();
      expect(messagesAfter).toBeGreaterThan(messagesBefore);
    }).toPass({ timeout: 45000 });
  });

  test('should load session from history', async ({ page }) => {
    await page.goto('/learning');

    // Wait for spinners to disappear (handle multiple spinners gracefully)
    try {
      await expect(async () => {
        const spinnerCount = await page.locator('.animate-spin').count();
        expect(spinnerCount).toBe(0);
      }).toPass({ timeout: 10000 });
    } catch {
      // If spinners persist, continue anyway
      console.log('[Test] Spinners still present after timeout - continuing');
    }

    const historyToggle = page.getByRole('button', {
      name: /show history|hide history|mostrar historial|ocultar historial/i,
    });
    await expect(historyToggle).toBeVisible();
    const historyResponsePromise = page.waitForResponse((response) =>
      response.request().method() === 'GET' &&
      response.url().includes('/api/learning/history/')
    );
    await historyToggle.click();
    const historyResponse = await historyResponsePromise;
    expect(historyResponse.ok()).toBe(true);

    const historyPanel = page.getByTestId('learning-history-panel');
    await expect(historyPanel).toBeVisible();
    await expect(
      historyPanel.getByRole('heading', { name: /conversation history|historial de conversación/i }),
    ).toBeVisible();
    await expect(historyPanel.locator('.animate-spin')).not.toBeVisible();

    const historyItems = historyPanel.getByTestId('learning-history-item');
    if (await historyItems.count() === 0) {
      await expect(
        historyPanel.getByText(/no previous sessions|no hay sesiones previas/i),
      ).toBeVisible();
      return;
    }

    await historyItems.first().click();

    const input = page.getByPlaceholder(/type|escribe/i).last();
    await expect(input).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Games', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('should play symbol hunt', async ({ page }) => {
    await page.goto('/symbol-hunt');

    // Wait for content
    await expect(page.locator('main')).toBeVisible();

    // The seeded demo board is playable (12 symbols), so a "Play Now" action
    // must be present. Its absence would mean the seed/assignment regressed.
    const playBtn = page.locator('button').filter({ hasText: /play now|jugar/i }).first();
    await expect(playBtn).toBeVisible({ timeout: 15000 });

    await playBtn.click();

    // The game shows the target instruction and the symbol grid.
    await expect(page.getByText(/find|encuentra/i)).toBeVisible();
    await expect(page.locator('.grid')).toBeVisible();
  });
});
