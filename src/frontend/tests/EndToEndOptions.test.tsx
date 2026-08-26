import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Mock } from 'vitest';
import { Settings } from '../src/pages/Settings';
import { SymbolHunt } from '../src/pages/SymbolHunt';
import { MemoryRouter } from 'react-router';
import api from '../src/lib/api';

// Mock API
vi.mock('../src/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  }
}));

// Mock Translations
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | { defaultValue: string }, arg3?: Record<string, string>) => {
        if (typeof arg2 === 'string') {
            // It's a default value
            let text = arg2;
            const options = arg3 || {};
            // Simple interpolation
            Object.keys(options).forEach(k => {
                text = text.replace(`{{${k}}}`, options[k]);
            });
            return text;
        }
        if (arg2 && typeof arg2 === 'object' && 'defaultValue' in arg2) return arg2.defaultValue;
        const values: Record<string, string> = {
          'symbolHunt.title': 'Symbol Hunt',
          'symbolHunt.selectBoard': 'Select a board to play',
          'symbolHunt.playNow': 'Play Now',
          'symbolHunt.find': 'Find {{label}}',
        };
        let text = values[key] || key;
        const options = (arg2 && typeof arg2 === 'object' ? arg2 : arg3) || {};
        Object.keys(options).forEach((k) => {
          text = text.replace(`{{${k}}}`, String(options[k]));
        });
        return text;
    },
    i18n: {
      changeLanguage: () => new Promise<void>((resolve) => resolve()),
    },
  }),
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
}));

// Mock TTS
const mockTTSState = {
  speak: vi.fn(),
  isSpeaking: false,
  voices: [],
  selectedVoice: null,
  rate: 1,
  pitch: 1,
  volume: 1,
  setSelectedVoice: vi.fn(),
  localVoice: 'default',
  setLocalVoice: vi.fn(),
  setTTSProvider: vi.fn(),
};
vi.mock('../src/store/ttsStore', () => ({
  useTTSStore: Object.assign(() => mockTTSState, { getState: () => mockTTSState }),
}));

// Mock Theme
const mockThemeState = {
  darkMode: false,
  setDarkMode: vi.fn(),
};
vi.mock('../src/store/themeStore', () => ({
  useThemeStore: Object.assign(() => mockThemeState, { getState: () => mockThemeState }),
}));

// Mock Locale
const mockLocaleState = {
  locale: 'es-ES',
  setLocale: vi.fn(),
};
vi.mock('../src/store/localeStore', () => ({
  useLocaleStore: Object.assign(() => mockLocaleState, { getState: () => mockLocaleState }),
}));


// Mock Auth
const authStoreState = vi.hoisted(() => ({ user: null as unknown, isAuthenticated: false }));
vi.mock('../src/store/authStore', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../src/store/authStore')>();
    const mockUseAuthStore = Object.assign(
      (selector?: (state: typeof authStoreState) => unknown) =>
        selector ? selector(authStoreState) : authStoreState,
      {
        setState: vi.fn(),
        getState: () => authStoreState,
      },
    );
    return {
        ...actual,
        useAuthStore: mockUseAuthStore,
    };
});

// Mock window.speechSynthesis
Object.defineProperty(window, 'speechSynthesis', {
  value: {
    getVoices: vi.fn().mockReturnValue([
      { name: 'Google US English', lang: 'en-US', voiceURI: 'Google US English' },
      { name: 'Google Español', lang: 'es-ES', voiceURI: 'Google Español' }
    ]),
    speak: vi.fn(),
    cancel: vi.fn(),
    onvoiceschanged: null,
  },
  writable: true,
});

describe('End-to-End Options Tests', () => {
  const mockUser = { id: 1, username: 'testuser', display_name: 'Test User' };
  
  beforeEach(() => {
    vi.clearAllMocks();
    authStoreState.user = mockUser;
    authStoreState.isAuthenticated = true;
  });

  // --- Option 4: Accessibility ---
  it('Option 4: Accessibility - Saves accessibility preferences', async () => {
    (api.get as unknown as Mock).mockImplementation((url: string) => {
      if (url === '/auth/preferences') {
        return Promise.resolve({ 
          data: { 
            dwell_time: 0, 
            ignore_repeats: 0, 
            high_contrast: false 
          } 
        });
      }
      if (url === '/providers/voice-status') return Promise.resolve({ data: {} });
      return Promise.resolve({ data: {} });
    });

    (api.put as unknown as Mock).mockResolvedValue({ data: { success: true } });

    render(
        <MemoryRouter>
            <Settings />
        </MemoryRouter>
    );

    // Wait for loading
    await waitFor(() => expect(screen.getByText('preferences.dwellTime')).toBeInTheDocument());

    // Find sliders
    // In Settings.tsx, the structure is:
    // div > div(text) + div > input
    // We can find the input by searching for the label text, then traversing up and down.
    const dwellLabel = screen.getByText('preferences.dwellTime');
    const dwellContainer = dwellLabel.closest('.p-6'); // The parent container has p-6 class
    const dwellInput = dwellContainer?.querySelector('input[type="range"]') as HTMLInputElement;

    expect(dwellInput).toBeInTheDocument();
    
    if (dwellInput) {
        fireEvent.change(dwellInput, { target: { value: '500' } });
    }

    // Save preferences
    const saveBtn = screen.getByText('preferences.saveAppearance');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith('/auth/preferences', expect.objectContaining({
        dwell_time: 500
      }));
    });
  });

  // --- Option 5: Gamification ---
  it('Option 5: Gamification - Plays Symbol Hunt game', async () => {
    const mockSymbols = [
      { id: 1, symbol_id: 101, custom_text: 'Dog', is_visible: true, position_x: 0, position_y: 0, symbol: { id: 101, label: 'Dog', image_path: '/dog.png' } },
      { id: 2, symbol_id: 102, custom_text: 'Cat', is_visible: true, position_x: 1, position_y: 0, symbol: { id: 102, label: 'Cat', image_path: '/cat.png' } }
    ];

    // The list endpoint returns serialized boards including their symbols;
    // the hunt hook needs them to decide playability by unique labels.
    const mockBoards = [
      { id: 1, name: 'Game Board', description: 'Fun', playable_symbols_count: 2, symbols: mockSymbols }
    ];
    
    const mockFullBoard = {
      id: 1,
      name: 'Game Board',
      grid_rows: 2,
      grid_cols: 2,
      symbols: mockSymbols
    };

    (api.get as unknown as Mock).mockImplementation((url: string) => {
      if (url === '/boards/') return Promise.resolve({ data: mockBoards });
      if (url === '/boards/assigned') return Promise.resolve({ data: [] });
      if (url === '/boards/1') return Promise.resolve({ data: mockFullBoard });
      return Promise.resolve({ data: {} });
    });

    render(
        <MemoryRouter>
            <SymbolHunt />
        </MemoryRouter>
    );

    // 1. Select Board
    await waitFor(() => expect(screen.getByText('Game Board')).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledWith('/boards/');
    fireEvent.click(screen.getByText('Play Now'));

    // 2. Game Starts
    // Expect "Find [Symbol]" instruction. Since it's random, we check if board is loaded.
    await waitFor(() => expect(screen.getByText('Dog')).toBeInTheDocument());
    expect(screen.getByText('Cat')).toBeInTheDocument();

    // Check for instruction text "Find {{label}}"
    // We mocked t to return key or default. "Find {{label}}" -> "symbolHunt.find"
    // The component actually uses t('symbolHunt.find', 'Find {{label}}', ...)
    // The mock implementation returns "symbolHunt.find" if no default, or default if present.
    // Wait, my mock returns default value if present.
    // In SymbolHunt: t('symbolHunt.find', 'Find {{label}}', { label })
    // So it should render "Find Dog" or "Find Cat".
    
    const instruction = await screen.findByText(/Find/);
    expect(instruction).toBeInTheDocument();
    
    const targetText = instruction.textContent?.replace('Find ', '');
    // Click the correct symbol
    if (targetText) {
        const targetSymbol = screen.getByText(targetText);
        fireEvent.click(targetSymbol);
        
        // 3. Feedback
        // Should see score increase to 1
        await waitFor(() => expect(screen.getByText('1')).toBeInTheDocument());
    }
  });

});
