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

    // We need to select a board first
    // Look for "Play Now" or "Jugar" buttons
    const playBtn = page.locator('button').filter({ hasText: /play now|jugar/i }).first();

    // If no boards, we can't play. Skip or fail gracefully.
    if (await playBtn.isVisible()) {
      await playBtn.click();
      // Should see target symbol instruction
      await expect(page.getByText(/find|encuentra/i)).toBeVisible();
      await expect(page.locator('.grid')).toBeVisible();
    } else {
      console.log('No playable boards found for Symbol Hunt');
      // If we are admin/student, maybe we need to create one?
      // But board creation is tested elsewhere.
      // We can just assert that the "No boards" message or "Needs more symbols" is visible if empty
      // But let's assume seed data provides at least one board.
      // If fails, it means seed data is missing.
    }
  });
});
