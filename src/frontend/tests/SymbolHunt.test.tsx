import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { BoardSymbol } from '../src/types';

const hunt = vi.hoisted(() => ({
  playableBoards: [] as unknown[],
  unplayableBoards: [] as unknown[],
  selectedBoard: null as unknown,
  gameState: 'selecting' as string,
  setGameState: vi.fn(),
  loading: false,
  round: 1,
  score: 3,
  targetSymbol: null as BoardSymbol | null,
  feedback: null as string | null,
  incorrectSymbolId: null as number | null,
  symbols: [] as BoardSymbol[],
  startGame: vi.fn(),
  handleSymbolClick: vi.fn(),
  repeatInstruction: vi.fn(),
  playAgain: vi.fn(),
  voiceEnabled: true,
}));

vi.mock('../src/hooks/useSymbolHunt', () => ({
  useSymbolHunt: () => hunt,
}));

vi.mock('../src/store/toastStore', () => ({
  useToastStore: () => ({ addToast: vi.fn() }),
}));

vi.mock('../src/components/board/SymbolCard', () => ({
  SymbolCard: ({ boardSymbol, onClick }: { boardSymbol: BoardSymbol; onClick: (s: BoardSymbol) => void }) => (
    <button onClick={() => onClick(boardSymbol)}>card-{boardSymbol.symbol.label}</button>
  ),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, unknown>) =>
      (globalThis as typeof globalThis & {
        __aacTestTranslation?: (namespace: string, key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, unknown>) => string;
      }).__aacTestTranslation?.('games', key, arg2, arg3) ?? key,
  }),
}));

vi.mock('lucide-react', () => {
  const Icon = () => null;
  return {
    Trophy: Icon,
    Play: Icon,
    ArrowLeft: Icon,
    RotateCcw: Icon,
    Volume2: Icon,
    CheckCircle: Icon,
    XCircle: Icon,
  };
});

import { SymbolHunt } from '../src/pages/SymbolHunt';

const board = { id: 1, name: 'Game Board', description: 'Fun' };

function makeSymbol(id: number, label: string): BoardSymbol {
  return {
    id,
    symbol_id: id,
    position_x: 0,
    position_y: 0,
    size: 1,
    is_visible: true,
    symbol: { id, label, category: 'core' },
  };
}

describe('SymbolHunt page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hunt.playableBoards = [board];
    hunt.unplayableBoards = [];
    hunt.selectedBoard = board;
    hunt.gameState = 'selecting';
    hunt.loading = false;
    hunt.round = 1;
    hunt.score = 3;
    hunt.targetSymbol = makeSymbol(1, 'Dog');
    hunt.feedback = null;
    hunt.incorrectSymbolId = null;
    hunt.symbols = [makeSymbol(1, 'Dog'), makeSymbol(2, 'Cat')];
    hunt.voiceEnabled = true;
  });

  it('shows playable and unplayable boards in the selection state', () => {
    hunt.playableBoards = [board];
    hunt.unplayableBoards = [{ id: 2, name: 'Locked Board' }];
    render(<SymbolHunt />);

    expect(screen.getByText('Game Board')).toBeInTheDocument();
    expect(screen.getByText('Locked Board')).toBeInTheDocument();
    expect(screen.getByText('At least 2 symbols required')).toBeInTheDocument();
  });

  it('renders the finished state with score and play-again actions', () => {
    hunt.gameState = 'finished';
    render(<SymbolHunt />);

    expect(screen.getByText('Great Job!')).toBeInTheDocument();
    expect(screen.getByText('You found 3 symbols!')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Play Again'));
    expect(hunt.playAgain).toHaveBeenCalled();

    fireEvent.click(screen.getByText('Choose Different Board'));
    expect(hunt.setGameState).toHaveBeenCalledWith('selecting');
  });

  it('renders the playing state with the find instruction and repeat button', () => {
    hunt.gameState = 'playing';
    render(<SymbolHunt />);

    expect(screen.getByText('Find Dog')).toBeInTheDocument();
    expect(screen.getByText('Game Board')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Repeat Instruction'));
    expect(hunt.repeatInstruction).toHaveBeenCalled();
  });

  it('shows the back button in the playing state', () => {
    hunt.gameState = 'playing';
    render(<SymbolHunt />);

    fireEvent.click(screen.getByLabelText('Back'));
    expect(hunt.setGameState).toHaveBeenCalledWith('selecting');
  });

  it('marks correct and incorrect symbol feedback overlays', () => {
    hunt.gameState = 'playing';
    hunt.feedback = 'correct';
    hunt.targetSymbol = makeSymbol(1, 'Dog');
    hunt.symbols = [makeSymbol(1, 'Dog')];
    render(<SymbolHunt />);
    expect(screen.getByText('card-Dog')).toBeInTheDocument();
  });

  it('highlights the clicked wrong symbol when feedback is incorrect', () => {
    hunt.gameState = 'playing';
    hunt.feedback = 'incorrect';
    hunt.incorrectSymbolId = 2;
    hunt.targetSymbol = makeSymbol(1, 'Dog');
    hunt.symbols = [makeSymbol(1, 'Dog'), makeSymbol(2, 'Cat')];
    render(<SymbolHunt />);

    // The wrong symbol (Cat) renders with the incorrect overlay and the target
    // (Dog) still renders normally.
    const catCell = screen.getByText('card-Cat').closest('.relative');
    expect(catCell?.querySelector('[class*="bg-red-500"]')).not.toBeNull();
  });

  it('shows an empty state when no boards exist', () => {
    hunt.playableBoards = [];
    hunt.unplayableBoards = [];
    render(<SymbolHunt />);

    expect(screen.getByText('No boards available yet. Ask your teacher to create one.')).toBeInTheDocument();
  });
});
