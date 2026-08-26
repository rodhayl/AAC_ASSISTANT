import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom';
import type { BoardSymbol } from '../src/types';

// Mock @dnd-kit/core
vi.mock('@dnd-kit/core', () => ({
  DndContext: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  closestCenter: () => {},
  DragOverlay: () => null,
  PointerSensor: vi.fn(),
  TouchSensor: vi.fn(),
  useSensor: vi.fn(() => ({})),
  useSensors: vi.fn(() => []),
}));

// Mock @dnd-kit/sortable
vi.mock('@dnd-kit/sortable', () => ({
  SortableContext: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  horizontalListSortingStrategy: {},
  useSortable: () => ({
    setNodeRef: vi.fn(),
    transform: null,
    transition: '',
    attributes: {},
    listeners: {},
    isDragging: false,
  }),
}));

// Mock @dnd-kit/utilities
vi.mock('@dnd-kit/utilities', () => ({
  CSS: { Transform: { toString: () => '' } },
}));

// Mock category style
vi.mock('../src/lib/symbolCategoryStyle', () => ({
  getCategoryStyle: () => ({
    border: 'border-blue-300',
    dot: 'bg-blue-400',
    hoverBorder: 'hover:border-blue-500',
  }),
}));

// Mock SymbolImage
vi.mock('../src/components/common/SymbolImage', () => ({
  SymbolImage: ({ imagePath }: { imagePath: string }) => (
    imagePath ? <img data-testid="symbol-image" src={imagePath} alt="" /> : null
  ),
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key === 'tapSymbolsToSpeak' ? 'Tap symbols to create a sentence...' : key,
  }),
}));

import { SentenceStrip } from '../src/components/board/SentenceStrip';

const symbol = (id: number, label: string): BoardSymbol => ({
  id,
  symbol_id: id,
  position_x: 0,
  position_y: 0,
  size: 1,
  is_visible: true,
  symbol: {
    id,
    label,
    image_path: '',
    category: 'social',
    language: 'en',
    is_builtin: true,
    created_at: '2024-01-01',
  },
});

const apple = symbol(1, 'apple');
const banana = symbol(2, 'banana');

function renderStrip(
  symbols: BoardSymbol[] = [],
  overrides: Record<string, unknown> = {},
) {
  return render(
    <SentenceStrip
      symbols={symbols}
      onRemove={vi.fn()}
      onClear={vi.fn()}
      onSpeak={vi.fn()}
      isSpeaking={false}
      {...overrides}
    />,
  );
}

describe('SentenceStrip', () => {
  it('renders an empty placeholder when no symbols are present', () => {
    renderStrip();
    expect(screen.getByTestId('sentence-empty')).toBeInTheDocument();
    expect(
      screen.getByText('Tap symbols to create a sentence...'),
    ).toBeInTheDocument();
  });

  it('renders symbol labels when symbols are present', () => {
    renderStrip([apple, banana]);
    expect(screen.getByText('apple')).toBeInTheDocument();
    expect(screen.getByText('banana')).toBeInTheDocument();
  });

  it('shows the sentence preview text when symbols are present', () => {
    renderStrip([apple, banana]);
    expect(screen.getByTestId('sentence-preview')).toHaveTextContent(
      'apple banana',
    );
  });

  it('shows custom_text in preview when available', () => {
    const s = {
      ...apple,
      custom_text: 'Granny Smith',
    };
    renderStrip([s, banana]);
    expect(screen.getByTestId('sentence-preview')).toHaveTextContent(
      'Granny Smith banana',
    );
  });

  it('disables Clear button when symbols list is empty', () => {
    renderStrip();
    expect(screen.getByTestId('sentence-clear')).toBeDisabled();
  });

  it('enables Clear button when symbols are present', () => {
    renderStrip([apple]);
    expect(screen.getByTestId('sentence-clear')).not.toBeDisabled();
  });

  it('calls onClear when the Clear button is clicked', () => {
    const onClear = vi.fn();
    renderStrip([apple], { onClear });
    fireEvent.click(screen.getByTestId('sentence-clear'));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('disables the Speak button when empty', () => {
    renderStrip();
    expect(screen.getByTestId('sentence-speak')).toBeDisabled();
  });

  it('disables the Speak button when isSpeaking is true', () => {
    renderStrip([apple], { isSpeaking: true });
    expect(screen.getByTestId('sentence-speak')).toBeDisabled();
  });

  it('enables the Speak button when symbols are present', () => {
    renderStrip([apple]);
    expect(screen.getByTestId('sentence-speak')).not.toBeDisabled();
  });

  it('calls onSpeak when the Speak button is clicked', () => {
    const onSpeak = vi.fn();
    renderStrip([apple], { onSpeak });
    fireEvent.click(screen.getByTestId('sentence-speak'));
    expect(onSpeak).toHaveBeenCalledTimes(1);
  });

  it('renders the Backspace button when onBackspace is provided', () => {
    renderStrip([apple], { onBackspace: vi.fn() });
    expect(screen.getByTestId('sentence-backspace')).toBeInTheDocument();
  });

  it('does not render the Backspace button when onBackspace is absent', () => {
    renderStrip([apple]);
    expect(screen.queryByTestId('sentence-backspace')).toBeNull();
  });

  it('calls onBackspace when the backspace button is clicked', () => {
    const onBackspace = vi.fn();
    renderStrip([apple, banana], { onBackspace });
    fireEvent.click(screen.getByTestId('sentence-backspace'));
    expect(onBackspace).toHaveBeenCalledTimes(1);
  });

  it('renders the Ask AI button when onAskAI is provided', () => {
    renderStrip([apple], { onAskAI: vi.fn() });
    expect(screen.getByTestId('sentence-ask-ai')).toBeInTheDocument();
  });

  it('does not render the Ask AI button when onAskAI is absent', () => {
    renderStrip([apple]);
    expect(screen.queryByTestId('sentence-ask-ai')).toBeNull();
  });

  it('calls onAskAI when the Ask AI button is clicked', () => {
    const onAskAI = vi.fn();
    renderStrip([apple], { onAskAI });
    fireEvent.click(screen.getByTestId('sentence-ask-ai'));
    expect(onAskAI).toHaveBeenCalledTimes(1);
  });
});
