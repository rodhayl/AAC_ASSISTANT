import { test, expect } from '@playwright/test';

test.describe('Communication', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });
  
  test.beforeEach(async ({ page }) => {
    // Mock Auth Me
    await page.route('**/api/auth/me', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                id: 1,
                username: 'admin',
                user_type: 'admin',
                display_name: 'Admin User',
                settings: { ui_language: 'en' }
            })
        });
    });

    // Mock Boards List
    await page.route('**/api/boards/?*', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
                { 
                    id: 1, 
                    name: 'Mock Board', 
                    description: 'Mock Desc', 
                    owner_id: 1, 
                    is_public: true, 
                    grid_cols: 4, 
                    grid_rows: 4,
                    playable_symbols_count: 10 // Ensure board is playable
                }
            ])
        });
    });

    // Mock Board Details
    await page.route('**/api/boards/1', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                id: 1, 
                name: 'Mock Board', 
                description: 'Mock Desc', 
                owner_id: 1, 
                is_public: true, 
                grid_cols: 4, 
                grid_rows: 4,
                playable_symbols_count: 10,
                symbols: [ // Include symbols in details just in case
                    {
                        id: 1,
                        board_id: 1,
                        symbol_id: 101,
                        label: "Hello",
                        position_x: 0,
                        position_y: 0,
                        color: "#FFFFFF",
                        is_visible: true,
                        symbol: { id: 101, label: "Hello", image_url: "/vite.svg" }
                    }
                ]
            })
        });
    });

    // Mock Board Symbols
    await page.route(/\/api\/boards\/\d+\/symbols/, async route => {
        console.log('Mocking symbols for:', route.request().url());
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
                {
                    id: 1,
                    board_id: 1,
                    symbol_id: 101,
                    label: "Hello",
                    position_x: 0,
                    position_y: 0,
                    color: "#FFFFFF",
                    symbol: { id: 101, label: "Hello", image_url: "/vite.svg" }
                },
                {
                    id: 2,
                    board_id: 1,
                    symbol_id: 102,
                    label: "World",
                    position_x: 1,
                    position_y: 0,
                    color: "#FFFFFF",
                    symbol: { id: 102, label: "World", image_url: "/vite.svg" }
                }
            ])
        });
    });
  });

  test('should open a board and add symbols', async ({ page }) => {
    await page.goto('/communication');
    
    // Find a playable board
    // Target the card itself which should be clickable
    const playableBoard = page.getByRole('button', { name: 'Mock Board' }).first();
    await expect(playableBoard).toBeVisible();
    await playableBoard.click({ force: true });
    
    // Now we should be in board view
    await expect(page.locator('.grid')).toBeVisible();

    // Verify and click the grid symbol itself. The assistant panel may also
    // contain the same label, so use the card's accessible action name.
    const symbol = page.locator('.grid').getByRole('button', {
      name: 'Add Hello to sentence',
    });
    await expect(symbol).toBeVisible();
    // Keyboard activation is deterministic and follows the accessibility
    // contract even when dwell-time pointer activation is enabled.
    await symbol.press('Enter');

    // Verify the symbol label was added to the sentence strip. The strip's
    // label span is stable even when drag-and-drop wrappers change shape.
    const strip = page.getByTestId('sentence-strip');
    await expect(strip).toBeVisible();
    await expect(strip.locator('span').filter({ hasText: 'Hello' })).toBeVisible();
  });
});
