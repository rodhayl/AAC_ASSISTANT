import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BoardsAndTopicsSidebar } from '../src/components/learning/BoardsAndTopicsSidebar';
import { loadTopicsForUser } from '../src/lib/learningTopics';

const authState = vi.hoisted(() => ({
  user: { id: 5, username: 'student1', display_name: 'Alex', user_type: 'student' as const },
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));

const boardState = vi.hoisted(() => ({
  boards: [],
  assignedBoards: [],
}));

vi.mock('../src/store/boardStore', () => ({
  useBoardStore: (selector?: (state: typeof boardState) => unknown) =>
    selector ? selector(boardState) : boardState,
}));

vi.mock('../src/lib/learningTopics', () => ({
  loadTopicsForUser: vi.fn(),
  addTopic: vi.fn(),
  removeTopic: vi.fn(),
}));

const translate = (key: string, options?: Record<string, string>) => {
  const translations: Record<string, string> = {
    boardsTopics: 'Boards & Topics',
    collapseSidebar: 'Collapse',
    expandSidebar: 'Expand',
    noSavedTopics: 'No saved topics',
    by: 'By',
    'topicPicker.savedBy': `Saved by ${options?.teacher ?? ''}`,
    'topicPicker.topicCount': `${options?.count ?? ''} topics`,
    startStudy: 'Start',
    startingSession: 'Starting...',
    removeTopic: 'Remove topic',
  };
  return translations[key] ?? key;
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: translate }),
}));

vi.mock('lucide-react', () => {
  const Icon = () => null;
  return { ChevronLeft: Icon, ChevronRight: Icon, Plus: Icon, Trash2: Icon };
});

vi.mock('../src/components/ui/button', () => ({
  Button: ({ children, ...props }: { children: React.ReactNode; [k: string]: unknown }) => (
    <button type="button" {...props}>{children}</button>
  ),
}));

vi.mock('../src/components/ui/icon-button', () => ({
  IconButton: ({ children, label, ...props }: { children: React.ReactNode; label: string; [k: string]: unknown }) => (
    <button type="button" aria-label={label} {...props}>{children}</button>
  ),
}));

vi.mock('../src/components/ui/SectionTitle', () => ({
  SectionTitle: ({ children }: { children: React.ReactNode }) => <h3>{children}</h3>,
}));

const loadMock = vi.mocked(loadTopicsForUser);

function renderSidebar() {
  return render(
    <BoardsAndTopicsSidebar
      isOpen
      onToggle={vi.fn()}
      onStartActivity={vi.fn()}
      isStartingSession={false}
    />,
  );
}

describe('BoardsAndTopicsSidebar saved-by attribution', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('groups topics under per-teacher headings when teachers are mixed', async () => {
    loadMock.mockResolvedValue([
      { id: 1, board: 'El cielo', topic: 'Astronomía', createdBy: 'Ms. Johnson' },
      { id: 2, board: 'Recetas', topic: 'Cocina', createdBy: 'Mr. García' },
    ]);
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText('Saved by Ms. Johnson')).toBeInTheDocument();
    });
    expect(screen.getByText('Saved by Mr. García')).toBeInTheDocument();
    // Each group carries the teacher's avatar (initials).
    expect(screen.getByText('MJ')).toBeInTheDocument();
    expect(screen.getByText('MG')).toBeInTheDocument();
    // Group containers exist per teacher, with the topic count in the heading.
    expect(screen.getByTestId('sidebar-topic-group-Ms. Johnson')).toBeInTheDocument();
    expect(screen.getByTestId('sidebar-topic-group-Mr. García')).toBeInTheDocument();
    // One topic per teacher, so the count badge appears in both headings.
    expect(screen.getAllByText('1 topics')).toHaveLength(2);
  });

  it('stays flat without labels when only one teacher saved topics', async () => {
    loadMock.mockResolvedValue([
      { id: 1, board: 'El cielo', topic: 'Astronomía', createdBy: 'Ms. Johnson' },
      { id: 2, board: 'Recetas', topic: 'Cocina', createdBy: 'Ms. Johnson' },
    ]);
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText('Astronomía')).toBeInTheDocument();
    });
    expect(screen.queryByText(/Saved by/)).not.toBeInTheDocument();
    expect(screen.queryByTestId(/sidebar-topic-group-/)).not.toBeInTheDocument();
  });
});
