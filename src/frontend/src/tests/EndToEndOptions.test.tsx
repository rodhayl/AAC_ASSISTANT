import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Mock } from 'vitest';
import { BoardPlayer } from '../pages/BoardPlayer';
import { Settings } from '../pages/Settings';
import { SymbolHunt } from '../pages/SymbolHunt';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import api from '../lib/api';
import { useAuthStore } from '../store/authStore';
import { useBoardStore } from '../store/boardStore';

// Mock API
vi.mock('../lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  }
}));

// Mock Board Store
vi.mock('../store/boardStore', () => ({
  useBoardStore: vi.fn(),
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
        return key;
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
};
vi.mock('../store/ttsStore', () => ({
  useTTSStore: Object.assign(() => mockTTSState, { getState: () => mockTTSState }),
}));

// Mock Theme
const mockThemeState = {
  darkMode: false,
  setDarkMode: vi.fn(),
};
vi.mock('../store/themeStore', () => ({
  useThemeStore: Object.assign(() => mockThemeState, { getState: () => mockThemeState }),
}));

// Mock Locale
const mockLocaleState = {
  locale: 'es-ES',
  setLocale: vi.fn(),
};
vi.mock('../store/localeStore', () => ({
  useLocaleStore: Object.assign(() => mockLocaleState, { getState: () => mockLocaleState }),
}));


// Mock Auth
vi.mock('../store/authStore', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../store/authStore')>();
    const mockUseAuthStore = Object.assign(vi.fn(), {
      setState: vi.fn(),
      getState: vi.fn(),
    });
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

// Mock React Router
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
    const actual = await importOriginal<typeof import('react-router-dom')>();
    return {
        ...actual,
        useNavigate: () => mockNavigate,
    };
});

describe('End-to-End Options Tests', () => {
  const mockUser = { id: 1, username: 'testuser', display_name: 'Test User' };
  
  beforeEach(() => {
    vi.clearAllMocks();
    (useAuthStore as unknown as Mock).mockReturnValue({ user: mockUser, isAuthenticated: true });
    (useBoardStore as unknown as Mock).mockReturnValue({
        currentBoard: null,
        fetchBoard: vi.fn(),
        isLoading: false,
        error: null
    });
  });

  // --- Option 1: Speak Mode ---
  it('Option 1: Speak Mode - Adds symbols to sentence strip', async () => {
    const mockBoard = {
      id: 1,
      name: 'Test Board',
      grid_rows: 2,
      grid_cols: 2,
      symbols: [
        { id: 1, symbol_id: 101, custom_text: 'Hello', is_visible: true, position_x: 0, position_y: 0, symbol: { id: 101, label: 'Hello', image_path: '/hello.png' } }
      ]
    };

    (useBoardStore as unknown as Mock).mockReturnValue({
        currentBoard: mockBoard,
        fetchBoard: vi.fn(),
        isLoading: false,
        error: null
    });

    (api.get as unknown as Mock).mockImplementation((url: string) => {
      if (url.includes('/analytics/next-symbol')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });

    render(
      <MemoryRouter initialEntries={['/play/1']}>
        <Routes>
          <Route path="/play/:id" element={<BoardPlayer />} />
        </Routes>
      </MemoryRouter>
    );

    // Wait for board to load
    await waitFor(() => expect(screen.getByText('Hello')).toBeInTheDocument());

    // Click symbol
    fireEvent.click(screen.getByText('Hello'));

    // Check if added to sentence strip
    // We can check if SentenceStrip renders it.
    // Or check if tts.enqueue was called (implied Speak Mode action)
    // But specifically "adds to sentence strip":
    const sentenceStripItems = await screen.findAllByText('Hello');
    expect(sentenceStripItems.length).toBeGreaterThanOrEqual(2);
  });

  // --- Option 2: Folders ---
  it('Option 2: Folders - Navigates to linked board', async () => {
    const mockBoard1 = {
      id: 1,
      name: 'Main Board',
      grid_rows: 2,
      grid_cols: 2,
      symbols: [
        { 
          id: 1, 
          symbol_id: 101, 
          custom_text: 'Go to Food', 
          is_visible: true, 
          position_x: 0, 
          position_y: 0, 
          linked_board_id: 2, 
          symbol: { id: 101, label: 'Folder', image_path: '/folder.png' } 
        }
      ]
    };

    (useBoardStore as unknown as Mock).mockReturnValue({
        currentBoard: mockBoard1,
        fetchBoard: vi.fn(),
        isLoading: false,
        error: null
    });

    render(
      <MemoryRouter initialEntries={['/play/1']}>
        <Routes>
          <Route path="/play/:id" element={<BoardPlayer />} />
        </Routes>
      </MemoryRouter>
    );

    // Wait for first board
    await waitFor(() => expect(screen.getByText('Go to Food')).toBeInTheDocument());

    // Click folder symbol
    fireEvent.click(screen.getByText('Go to Food'));

    // Expect navigation to Board 2
    expect(mockNavigate).toHaveBeenCalledWith('/play/2');
  });

  // --- Option 3: Smartbar ---
  it('Option 3: Smartbar - Shows predictive suggestions', async () => {
    const mockBoard = {
      id: 1,
      name: 'Test Board',
      grid_rows: 2,
      grid_cols: 2,
      symbols: [
        { id: 1, symbol_id: 101, custom_text: 'I want', is_visible: true, position_x: 0, position_y: 0, symbol: { id: 101, label: 'I want', image_path: '/iwant.png' } }
      ]
    };

    const mockSuggestions = [
      { symbol_id: 201, label: 'Water', image_path: '/water.png' }
    ];

    (useBoardStore as unknown as Mock).mockReturnValue({
        currentBoard: mockBoard,
        fetchBoard: vi.fn(),
        isLoading: false,
        error: null
    });

    (api.get as unknown as Mock).mockImplementation((url: string) => {
      if (url.includes('/analytics/next-symbol')) {
          return Promise.resolve({ data: mockSuggestions });
      }
      return Promise.resolve({ data: {} });
    });

    render(
      <MemoryRouter initialEntries={['/play/1']}>
        <Routes>
          <Route path="/play/:id" element={<BoardPlayer />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText('I want')).toBeInTheDocument());
    
    // Click symbol to trigger suggestions
    fireEvent.click(screen.getByText('I want'));

    // Verify API call was made
    await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith(
            expect.stringContaining('/analytics/next-symbol'), 
            expect.anything()
        );
    });

    // Check if suggestion appears in Smartbar
    await waitFor(() => expect(screen.getByText('Water')).toBeInTheDocument(), { timeout: 3000 });
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
    const saveBtn = screen.getByText('preferences.savePrefs');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith('/auth/preferences', expect.objectContaining({
        dwell_time: 500
      }));
    });
  });

  // --- Option 5: Gamification ---
  it('Option 5: Gamification - Plays Symbol Hunt game', async () => {
    const mockBoards = [
      { id: 1, name: 'Game Board', description: 'Fun', playable_symbols_count: 2 }
    ];
    
    const mockFullBoard = {
      id: 1,
      name: 'Game Board',
      grid_rows: 2,
      grid_cols: 2,
      symbols: [
        { id: 1, symbol_id: 101, custom_text: 'Dog', is_visible: true, position_x: 0, position_y: 0, symbol: { id: 101, label: 'Dog', image_path: '/dog.png' } },
        { id: 2, symbol_id: 102, custom_text: 'Cat', is_visible: true, position_x: 1, position_y: 0, symbol: { id: 102, label: 'Cat', image_path: '/cat.png' } }
      ]
    };

    (api.get as unknown as Mock).mockImplementation((url: string) => {
      if (url === '/boards/') return Promise.resolve({ data: mockBoards });
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
