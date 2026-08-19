import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LearningModesTab } from '../src/pages/Settings/LearningModesTab';

const { get, post, delete: deleteApi } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('../src/lib/api', () => ({
  default: {
    get,
    post,
    put: vi.fn(),
    delete: deleteApi,
  },
  extractError: (error: { message?: string } | undefined, fallback: string) =>
    error?.message || fallback,
}));

const authState = vi.hoisted(() => ({
  user: { id: 1, username: 'teacher1', user_type: 'teacher' },
}));

vi.mock('../src/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authState) => unknown) =>
    selector ? selector(authState) : authState,
}));

const INSTRUCTION = 'Habla de forma exagerada como andaluz.';

describe('LearningModesTab preview', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    deleteApi.mockReset();
    get.mockImplementation((url: string) => {
      if (url.includes('/learning-modes/')) return Promise.resolve({ data: [] });
      if (url.includes('/guardian-profiles/students')) {
        return Promise.resolve({
          data: [
            { id: 5, username: 'ana', display_name: 'Ana', has_profile: true },
            { id: 6, username: 'leo', display_name: 'Leo', has_profile: false },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });
    post.mockResolvedValue({
      data: {
        prompt: `BASE GUARDIAN PROMPT\n\nSpecial Instructions:\nfrases cortas\n\n${INSTRUCTION}`,
        template_name: 'default',
        has_guardian_profile: true,
        mode_instruction: INSTRUCTION,
      },
    });
  });

  it('create-mode form sends the auto-ask checkbox state', async () => {
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByText('Add New Learning Mode'));

    // The checkbox defaults to enabled
    const checkbox = screen.getByRole('checkbox', { name: /Auto-ask questions/i });
    expect(checkbox).toBeChecked();

    // Disable auto-asking for a conversational mode
    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();

    fireEvent.change(screen.getByPlaceholderText(/e.g. Daily Conversation/), {
      target: { value: 'Role Play' },
    });
    fireEvent.change(screen.getByPlaceholderText(/e.g. daily_conversation/), {
      target: { value: 'roleplay' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Instructions for the AI/), {
      target: { value: 'Act as a friendly shopkeeper.' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Save Mode/i }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/learning-modes/',
        expect.objectContaining({
          name: 'Role Play',
          key: 'roleplay',
          auto_ask_enabled: false,
        }),
      );
    });
  });

  it('blocks saving a mode without a system prompt instruction', async () => {
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByText('Add New Learning Mode'));
    fireEvent.change(screen.getByPlaceholderText(/e.g. Daily Conversation/), {
      target: { value: 'Role Play' },
    });
    fireEvent.change(screen.getByPlaceholderText(/e.g. daily_conversation/), {
      target: { value: 'roleplay' },
    });
    // prompt_instruction is intentionally left empty

    fireEvent.click(screen.getByRole('button', { name: /Save Mode/i }));

    // The localized validation message appears and no API call is made.
    expect(await screen.findByText('System prompt instruction is required')).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('previews the exact system prompt with the selected student', async () => {
    render(<LearningModesTab />);

    // Open the create-mode form
    fireEvent.click(await screen.findByText('Add New Learning Mode'));

    // Type the mode instruction
    fireEvent.change(screen.getByPlaceholderText(/Instructions for the AI/), {
      target: { value: INSTRUCTION },
    });

    // Open the preview modal
    fireEvent.click(screen.getByRole('button', { name: /Preview System Prompt/i }));
    const dialog = await screen.findByRole('dialog');

    // Select a student with a guardian profile; the preview re-runs with it
    const studentSelect = await screen.findByLabelText('Student');
    fireEvent.change(studentSelect, { target: { value: '5' } });

    await waitFor(() => {
      expect(post).toHaveBeenLastCalledWith(
        '/learning-modes/preview',
        expect.objectContaining({
          prompt_instruction: INSTRUCTION,
          student_id: 5,
        }),
      );
    });
    expect(within(dialog).getByText(/BASE GUARDIAN PROMPT/)).toBeInTheDocument();
    expect(within(dialog).getByText(new RegExp(INSTRUCTION))).toBeInTheDocument();
    expect(within(dialog).getByText(/Guardian profile included/)).toBeInTheDocument();
  });

  it('previews the default prompt when no student is selected', async () => {
    post.mockResolvedValue({
      data: {
        prompt: `BASE DEFAULT PROMPT\n\n${INSTRUCTION}`,
        template_name: 'default',
        has_guardian_profile: false,
        mode_instruction: INSTRUCTION,
      },
    });
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByText('Add New Learning Mode'));
    fireEvent.click(screen.getByRole('button', { name: /Preview System Prompt/i }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/learning-modes/preview',
        expect.objectContaining({ prompt_instruction: '', student_id: null }),
      );
    });
    expect(await screen.findByText(/BASE DEFAULT PROMPT/)).toBeInTheDocument();
    expect(screen.getByText(/No guardian profile/)).toBeInTheDocument();
  });

  it('previews a saved mode directly from its row without entering edit mode', async () => {
    const savedInstruction = 'Respuesta breve y siempre con emojis.';
    get.mockImplementation((url: string) => {
      if (url.includes('/learning-modes/')) {
        return Promise.resolve({
          data: [
            {
              id: 10,
              name: 'Andaluz',
              key: 'andalusian',
              description: 'Habla andaluz',
              prompt_instruction: savedInstruction,
              is_custom: true,
              created_by: 1,
            },
          ],
        });
      }
      if (url.includes('/guardian-profiles/students')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });
    post.mockResolvedValue({
      data: {
        prompt: `BASE PROMPT\n\n${savedInstruction}`,
        template_name: 'default',
        has_guardian_profile: false,
        mode_instruction: savedInstruction,
      },
    });

    render(<LearningModesTab />);

    // Click the row shortcut (Eye icon) for the saved mode
    fireEvent.click(await screen.findByRole('button', { name: /^Preview Andaluz$/ }));

    // The list view stays - no edit form was opened
    expect(screen.queryByText('Save Mode')).not.toBeInTheDocument();

    const dialog = await screen.findByRole('dialog');
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/learning-modes/preview',
        expect.objectContaining({
          mode_key: 'andalusian',
          prompt_instruction: savedInstruction,
          student_id: null,
        }),
      );
    });
    expect(within(dialog).getByText(new RegExp(savedInstruction))).toBeInTheDocument();
    expect(within(dialog).getByText(/Previewing saved mode/)).toBeInTheDocument();
  });

  it('shows the error from the backend when the preview fails', async () => {
    post.mockRejectedValue({ message: 'Preview failed on the server' });
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByText('Add New Learning Mode'));
    fireEvent.click(screen.getByRole('button', { name: /Preview System Prompt/i }));

    expect(await screen.findByText('Preview failed on the server')).toBeInTheDocument();
  });

  it('previews the full LLM request with a sample question', async () => {
    const sampleQuestion = '¿Por qué llueve?';
    const userMessage =
      'Previous conversation:\n    \n\n    Student\'s latest message: ¿Por qué llueve?\n\n    Topic: general conversation\n\n    Write a helpful response to the student (1-2 friendly sentences). Ask a question or share a fact about general conversation. Respond in Spanish.';
    post.mockResolvedValue({
      data: {
        prompt: `BASE PROMPT\n\n${INSTRUCTION}`,
        template_name: 'default',
        has_guardian_profile: false,
        mode_instruction: INSTRUCTION,
        user_message: userMessage,
        temperature: 0.7,
        max_tokens: 300,
      },
    });
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByText('Add New Learning Mode'));
    fireEvent.click(screen.getByRole('button', { name: /Preview System Prompt/i }));

    // Enable the sample-question mode and type a question
    fireEvent.click(screen.getByLabelText(/Preview with sample question/));
    fireEvent.change(await screen.findByLabelText('Sample student question'), {
      target: { value: sampleQuestion },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/learning-modes/preview',
        expect.objectContaining({ sample_question: sampleQuestion }),
      );
    });

    // The full request is shown: system prompt + user message + params
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Full LLM request')).toBeInTheDocument();
    expect(within(dialog).getByText('System prompt')).toBeInTheDocument();
    expect(within(dialog).getByText(new RegExp(INSTRUCTION))).toBeInTheDocument();
    expect(within(dialog).getByText(/Student's latest message: ¿Por qué llueve\?/)).toBeInTheDocument();
    expect(within(dialog).getByText(/temperature 0\.7 · max_tokens 300/)).toBeInTheDocument();
  });

  it('does not send a sample question when the toggle is off', async () => {
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByText('Add New Learning Mode'));
    fireEvent.click(screen.getByRole('button', { name: /Preview System Prompt/i }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/learning-modes/preview',
        expect.objectContaining({ sample_question: undefined }),
      );
    });
  });

  it('closes the preview modal with the Escape key', async () => {
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByText('Add New Learning Mode'));
    fireEvent.click(screen.getByRole('button', { name: /Preview System Prompt/i }));
    await screen.findByRole('dialog');

    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('traps Tab focus inside the dialog and wraps both directions', async () => {
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByText('Add New Learning Mode'));
    fireEvent.click(screen.getByRole('button', { name: /Preview System Prompt/i }));
    const dialog = await screen.findByRole('dialog');

    const focusables = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      ),
    );
    expect(focusables.length).toBeGreaterThan(1);
    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    // Opening the modal moves focus to the first focusable (the close button).
    await waitFor(() => {
      expect(document.activeElement).toBe(first);
    });

    // Tab from the last element wraps to the first.
    last.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(first);

    // Shift+Tab from the first element wraps to the last.
    first.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it('returns focus to the trigger button when the preview closes', async () => {
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByText('Add New Learning Mode'));
    const trigger = screen.getByRole('button', { name: /Preview System Prompt/i });
    trigger.focus();
    fireEvent.click(trigger);
    await screen.findByRole('dialog');

    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(document.activeElement).toBe(trigger);
    });
  });
});

describe('LearningModesTab delete', () => {
  const customMode = {
    id: 10,
    name: 'Andaluz',
    key: 'andalusian',
    description: 'Habla andaluz',
    prompt_instruction: 'Respuesta breve.',
    is_custom: true,
    created_by: 1,
  };

  beforeEach(() => {
    get.mockImplementation((url: string) => {
      if (url.includes('/learning-modes/')) return Promise.resolve({ data: [customMode] });
      return Promise.resolve({ data: [] });
    });
    deleteApi.mockReset();
    deleteApi.mockResolvedValue({ data: {} });
  });

  it('deletes a custom mode after confirming in the dialog', async () => {
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByRole('button', { name: /^Delete Andaluz$/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/delete this learning mode/i)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(deleteApi).toHaveBeenCalledWith('/learning-modes/10'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('keeps the mode when the delete dialog is dismissed', async () => {
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByRole('button', { name: /^Delete Andaluz$/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(deleteApi).not.toHaveBeenCalled();
    expect(screen.getByText('Andaluz')).toBeInTheDocument();
  });

  it('surfaces an error when deleting a mode fails', async () => {
    deleteApi.mockRejectedValue(new Error('delete down'));
    render(<LearningModesTab />);

    fireEvent.click(await screen.findByRole('button', { name: /^Delete Andaluz$/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    expect(await screen.findByText('delete down')).toBeInTheDocument();
  });
});

describe('LearningModesTab auto-ask badge', () => {
  it('shows an On badge for modes with auto-asking enabled and Off for disabled ones', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/learning-modes/')) {
        return Promise.resolve({
          data: [
            {
              id: 1,
              name: 'Roleplay',
              key: 'roleplay',
              description: 'Conversational',
              prompt_instruction: 'Act like a pirate',
              is_custom: true,
              created_by: 1,
              auto_ask_enabled: false,
            },
            {
              id: 2,
              name: 'Quiz',
              key: 'quiz',
              description: 'Adaptive questions',
              prompt_instruction: 'Ask questions',
              is_custom: false,
              created_by: null,
              auto_ask_enabled: true,
            },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });

    render(<LearningModesTab />);

    expect(await screen.findByText('Auto-ask: Off')).toBeInTheDocument();
    expect(screen.getByText('Auto-ask: On')).toBeInTheDocument();
  });

  it('treats legacy modes without the field as auto-ask enabled', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/learning-modes/')) {
        return Promise.resolve({
          data: [
            {
              id: 3,
              name: 'Legacy',
              key: 'legacy',
              description: 'Old mode',
              prompt_instruction: '',
              is_custom: true,
              created_by: 1,
            },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });

    render(<LearningModesTab />);

    expect(await screen.findByText('Auto-ask: On')).toBeInTheDocument();
  });
});
