import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { CommunicationToolbar } from '../components/board/CommunicationToolbar';
import { SentenceStrip } from '../components/board/SentenceStrip';
import { KeyboardOverlay } from '../components/board/KeyboardOverlay';
import type { BoardSymbol } from '../types';

// Mock icons
vi.mock('lucide-react', () => ({
  Home: () => <div data-testid="icon-home" />,
  ArrowLeft: () => <div data-testid="icon-arrow-left" />,
  Keyboard: () => <div data-testid="icon-keyboard" />,
  Bell: () => <div data-testid="icon-bell" />,
  ThumbsUp: () => <div data-testid="icon-thumbs-up" />,
  ThumbsDown: () => <div data-testid="icon-thumbs-down" />,
  Heart: () => <div data-testid="icon-heart" />,
  HelpCircle: () => <div data-testid="icon-help-circle" />,
  AlertTriangle: () => <div data-testid="icon-alert-triangle" />,
  Play: () => <div data-testid="icon-play" />,
  Delete: () => <div data-testid="icon-delete" />,
  Trash2: () => <div data-testid="icon-trash2" />,
  X: () => <div data-testid="icon-x" />,
  Volume2: () => <div data-testid="icon-volume2" />,
  Send: () => <div data-testid="icon-send" />,
  History: () => <div data-testid="icon-history" />,
  Sparkles: () => <div data-testid="icon-sparkles" />,
  Ear: () => <div data-testid="icon-ear" />,
  MessageSquare: () => <div data-testid="icon-message-square" />,
  Search: () => <div data-testid="icon-search" />,
  BookOpen: () => <div data-testid="icon-book-open" />,
}));

// Mock translation
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultVal: string) => defaultVal || key,
  }),
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
}));

describe('CommunicationToolbar', () => {
  it('renders all buttons', () => {
    render(
      <CommunicationToolbar 
        onHome={vi.fn()} 
        onBack={vi.fn()} 
        onToggleKeyboard={vi.fn()} 
        onQuickResponse={vi.fn()} 
        onAttention={vi.fn()} 
        onToggleChat={vi.fn()}
        onSearch={vi.fn()}
        onContext={vi.fn()}
        onPartnerMic={vi.fn()}
        isKeyboardOpen={false} 
        isChatOpen={false}
        canGoBack={true} 
      />
    );

    expect(screen.getByTitle('Home')).toBeInTheDocument();
    expect(screen.getByTitle('Back')).toBeInTheDocument();
    expect(screen.getByTitle('Keyboard')).toBeInTheDocument();
    expect(screen.getByTitle('Attention')).toBeInTheDocument();
    expect(screen.getByText('Yes')).toBeInTheDocument();
    expect(screen.getByText('No')).toBeInTheDocument();
    expect(screen.getByText('Thanks')).toBeInTheDocument();
  });

  it('calls handlers on click', () => {
    const onHome = vi.fn();
    const onQuickResponse = vi.fn();
    
    render(
      <CommunicationToolbar 
        onHome={onHome} 
        onBack={vi.fn()} 
        onToggleKeyboard={vi.fn()} 
        onQuickResponse={onQuickResponse} 
        onAttention={vi.fn()} 
        onToggleChat={vi.fn()}
        onSearch={vi.fn()}
        onContext={vi.fn()}
        onPartnerMic={vi.fn()}
        isKeyboardOpen={false} 
        isChatOpen={false}
        canGoBack={true} 
      />
    );

    fireEvent.click(screen.getByTitle('Home'));
    expect(onHome).toHaveBeenCalled();

    fireEvent.click(screen.getByText('Yes'));
    expect(onQuickResponse).toHaveBeenCalledWith('Yes', 'positive');
  });

  it('disables back button when canGoBack is false', () => {
    render(
      <CommunicationToolbar 
        onHome={vi.fn()} 
        onBack={vi.fn()} 
        onToggleKeyboard={vi.fn()} 
        onQuickResponse={vi.fn()} 
        onAttention={vi.fn()} 
        onToggleChat={vi.fn()}
        onSearch={vi.fn()}
        onContext={vi.fn()}
        onPartnerMic={vi.fn()}
        isKeyboardOpen={false} 
        isChatOpen={false}
        canGoBack={false} 
      />
    );

    expect(screen.getByTitle('Back')).toBeDisabled();
  });
});

describe('SentenceStrip', () => {
  const mockSymbol: BoardSymbol = {
    id: 1,
    symbol_id: 1,
    position_x: 0,
    position_y: 0,
    size: 1,
    is_visible: true,
    symbol: {
      id: 1,
      label: 'Hello',
      image_path: '/hello.png',
      category: 'social',
      description: '',
      language: 'en',
      is_builtin: true,
      is_in_use: true,
      created_at: ''
    }
  };

  it('renders symbols', () => {
    render(
      <SentenceStrip 
        symbols={[mockSymbol]} 
        onRemove={vi.fn()} 
        onClear={vi.fn()} 
        onSpeak={vi.fn()} 
        isSpeaking={false} 
      />
    );

    expect(screen.getAllByText('Hello')).toHaveLength(2);
  });

  it('calls backspace', () => {
    const onBackspace = vi.fn();
    render(
      <SentenceStrip 
        symbols={[mockSymbol]} 
        onRemove={vi.fn()} 
        onClear={vi.fn()} 
        onBackspace={onBackspace}
        onSpeak={vi.fn()} 
        isSpeaking={false} 
      />
    );

    fireEvent.click(screen.getByLabelText('Backspace'));
    expect(onBackspace).toHaveBeenCalled();
  });

  it('calls speak item on click', () => {
    const onSpeakItem = vi.fn();
    render(
      <SentenceStrip 
        symbols={[mockSymbol]} 
        onRemove={vi.fn()} 
        onClear={vi.fn()} 
        onSpeak={vi.fn()} 
        onSpeakItem={onSpeakItem}
        isSpeaking={false} 
      />
    );

    // Click the first 'Hello' which is the symbol card
    fireEvent.click(screen.getAllByText('Hello')[0].closest('div')!);
    expect(onSpeakItem).toHaveBeenCalledWith('Hello');
  });
});

describe('KeyboardOverlay', () => {
  it('renders when open', () => {
    render(
      <KeyboardOverlay 
        isOpen={true} 
        onClose={vi.fn()} 
        onSpeak={vi.fn()} 
      />
    );

    expect(screen.getByPlaceholderText('Type something here...')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    render(
      <KeyboardOverlay 
        isOpen={false} 
        onClose={vi.fn()} 
        onSpeak={vi.fn()} 
      />
    );

    expect(screen.queryByPlaceholderText('Type something here...')).not.toBeInTheDocument();
  });

  it('speaks text', () => {
    const onSpeak = vi.fn();
    render(
      <KeyboardOverlay 
        isOpen={true} 
        onClose={vi.fn()} 
        onSpeak={onSpeak} 
      />
    );

    const input = screen.getByPlaceholderText('Type something here...');
    fireEvent.change(input, { target: { value: 'Hello World' } });
    fireEvent.click(screen.getByText('Speak'));

    expect(onSpeak).toHaveBeenCalledWith('Hello World');
  });
});
