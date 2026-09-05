import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    'topicPicker.summary': `${options?.topics ?? ''} topics from ${options?.teachers ?? ''} teachers`,
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
    const groupIds = Array.from(document.querySelectorAll('[data-testid^="sidebar-topic-group-"]:not([data-testid="sidebar-topic-group-summary"])'))
      .map((element) => element.getAttribute('data-testid'));
    expect(groupIds).toEqual([
      'sidebar-topic-group-Mr. García',
      'sidebar-topic-group-Ms. Johnson',
    ]);
    // One topic per teacher, so a number-only count pill appears in both
    // headings (full text as the tooltip).
    const msHeading = screen.getByTestId('sidebar-topic-group-Ms. Johnson').querySelector('h4')!;
    const mrHeading = screen.getByTestId('sidebar-topic-group-Mr. García').querySelector('h4')!;
    expect(msHeading.textContent).toContain('1');
    expect(msHeading.querySelector('span[title]')?.getAttribute('title')).toBe('1 topics');
    expect(mrHeading.textContent).toContain('1');
    expect(mrHeading.querySelector('span[title]')?.getAttribute('title')).toBe('1 topics');
    // A total summary line sits above the groups.
    expect(screen.getByTestId('sidebar-topic-group-summary')).toHaveTextContent('2 topics from 2 teachers');
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
    // No summary line in flat mode either.
    expect(screen.queryByTestId('sidebar-topic-group-summary')).not.toBeInTheDocument();
  });

  it('drops the board ID when the topic board no longer exists', async () => {
    // The user only sees one accessible board (id 7). A saved topic
    // referencing a deleted board (id 99) must start without board context.
    boardState.boards = [{ id: 7, name: 'Visible' } as never];
    loadMock.mockResolvedValue([
      { id: 1, board: 'Deleted board', boardId: 99, topic: 'Astronomía', createdBy: 'Ms. Johnson' },
      { id: 2, board: 'Visible', boardId: 7, topic: 'Cocina', createdBy: 'Ms. Johnson' },
    ]);
    const startActivity = vi.fn();
    render(
      <BoardsAndTopicsSidebar
        isOpen
        onToggle={vi.fn()}
        onStartActivity={startActivity}
        isStartingSession={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Astronomía')).toBeInTheDocument();
    });
    fireEvent.click(screen.getAllByRole('button', { name: 'Start' })[0]);
    await waitFor(() => {
      // No boardId: the dangling reference is dropped instead of persisted.
      expect(startActivity).toHaveBeenCalledWith('Astronomía', 'Deleted board', undefined);
    });

    fireEvent.click(screen.getAllByRole('button', { name: 'Start' })[1]);
    await waitFor(() => {
      expect(startActivity).toHaveBeenCalledWith('Cocina', 'Visible', 7);
    });
  });
});
