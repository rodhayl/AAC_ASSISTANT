import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom';
import { CommunicationToolbar } from '../src/components/board/CommunicationToolbar';

// Mock useTranslation
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, unknown>) =>
      (globalThis as typeof globalThis & {
        __aacTestTranslation?: (namespace: string, key: string, arg2?: string | Record<string, unknown>, arg3?: Record<string, unknown>) => string;
      }).__aacTestTranslation?.('boards', key, arg2, arg3) ?? key,
  }),
}));

// Mock AccessibleButton
vi.mock('../src/components/ui/AccessibleButton', () => ({
  AccessibleButton: ({ onClick, disabled, title, children, className }: Record<string, unknown>) => (
    <button
      type="button"
      onClick={onClick as () => void}
      disabled={disabled as boolean}
      title={title as string}
      className={className as string}
    >
      {children as React.ReactNode}
    </button>
  ),
}));

const defaultProps = {
  onHome: vi.fn(),
  onBack: vi.fn(),
  onToggleKeyboard: vi.fn(),
  onToggleChat: vi.fn(),
  onSearch: vi.fn(),
  onContext: vi.fn(),
  onPartnerMic: vi.fn(),
  onQuickResponse: vi.fn(),
  onAttention: vi.fn(),
  isKeyboardOpen: false,
  isChatOpen: false,
  canGoBack: true,
};

function renderToolbar(overrides: Partial<typeof defaultProps> = {}) {
  return render(<CommunicationToolbar {...defaultProps} {...overrides} />);
}

describe('CommunicationToolbar', () => {
  it('renders core navigation and tool buttons', () => {
    renderToolbar();
    // Navigation group
    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByText('Back')).toBeInTheDocument();
    // Quick responses
    expect(screen.getByText('Yes')).toBeInTheDocument();
    expect(screen.getByText('No')).toBeInTheDocument();
    expect(screen.getByText('Thanks')).toBeInTheDocument();
    // Tools group
    expect(screen.getByText('Listen')).toBeInTheDocument();
    expect(screen.getByText('Search')).toBeInTheDocument();
    expect(screen.getByText('Topic')).toBeInTheDocument();
    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.getByText('Type')).toBeInTheDocument();
    expect(screen.getByText('Alert')).toBeInTheDocument();
  });

  it('calls onHome when the Home button is clicked', () => {
    const onHome = vi.fn();
    renderToolbar({ onHome });
    screen.getByText('Home').click();
    expect(onHome).toHaveBeenCalledTimes(1);
  });

  it('calls onBack when the Back button is clicked', () => {
    const onBack = vi.fn();
    renderToolbar({ onBack });
    screen.getByText('Back').click();
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('disables the Back button when canGoBack is false', () => {
    renderToolbar({ canGoBack: false });
    const backButton = screen.getByText('Back').closest('button')!;
    expect(backButton).toBeDisabled();
    expect(backButton.className).toMatch(/opacity-50/);
  });

  it('calls onToggleKeyboard when the Type button is clicked', () => {
    const onToggleKeyboard = vi.fn();
    renderToolbar({ onToggleKeyboard });
    screen.getByTitle('Keyboard').click();
    expect(onToggleKeyboard).toHaveBeenCalledTimes(1);
  });

  it('calls onToggleChat when the Chat button is clicked', () => {
    const onToggleChat = vi.fn();
    renderToolbar({ onToggleChat });
    screen.getByText('Chat').click();
    expect(onToggleChat).toHaveBeenCalledTimes(1);
  });

  it('calls onSearch when the Search button is clicked', () => {
    const onSearch = vi.fn();
    renderToolbar({ onSearch });
    screen.getByText('Search').click();
    expect(onSearch).toHaveBeenCalledTimes(1);
  });

  it('calls onContext when the Topic button is clicked', () => {
    const onContext = vi.fn();
    renderToolbar({ onContext });
    screen.getByTitle('Context').click();
    expect(onContext).toHaveBeenCalledTimes(1);
  });

  it('calls onQuickResponse with type positive for the Yes button', () => {
    const onQuickResponse = vi.fn();
    renderToolbar({ onQuickResponse });
    screen.getByText('Yes').click();
    expect(onQuickResponse).toHaveBeenCalledWith('Yes', 'positive');
  });

  it('calls onQuickResponse with type negative for the No button', () => {
    const onQuickResponse = vi.fn();
    renderToolbar({ onQuickResponse });
    screen.getByText('No').click();
    expect(onQuickResponse).toHaveBeenCalledWith('No', 'negative');
  });

  it('calls onQuickResponse with type neutral for the Thanks button', () => {
    const onQuickResponse = vi.fn();
    renderToolbar({ onQuickResponse });
    screen.getByText('Thanks').click();
    expect(onQuickResponse).toHaveBeenCalledWith('Thanks', 'neutral');
  });

  it('calls onAttention when the Alert button is clicked', () => {
    const onAttention = vi.fn();
    renderToolbar({ onAttention });
    screen.getByTitle('Attention').click();
    expect(onAttention).toHaveBeenCalledTimes(1);
  });

  it('calls onPartnerMic when the Listen button is clicked', () => {
    const onPartnerMic = vi.fn();
    renderToolbar({ onPartnerMic });
    screen.getByText('Listen').click();
    expect(onPartnerMic).toHaveBeenCalledTimes(1);
  });
});
