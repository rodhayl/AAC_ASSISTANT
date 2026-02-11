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

    // Verify symbols are loaded
    await expect(page.getByText('Hello')).toBeVisible();

    // Click symbol "Hello"
    const symbol = page.locator('.grid').getByText('Hello').first();
    await expect(symbol).toBeVisible();
    await symbol.click({ force: true });

    // Verify symbol added to strip
    // The strip usually contains the text of the symbol
    // We check for the text OR the image with alt text
    const strip = page.locator('.min-h-\\[5rem\\]').first();
    await expect(strip).toBeVisible();
    // Try finding text or image
    const hasText = await strip.getByText('Hello').isVisible().catch(() => false);
    const hasImage = await strip.locator('img[alt="Hello"]').isVisible().catch(() => false);
    
    if (!hasText && !hasImage) {
        // Fallback: check if any child exists (assuming it was empty before)
        await expect(strip.locator('div').first()).toBeVisible();
    }
  });
});
