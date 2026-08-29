import { beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
// Initialize i18next so translated strings (including {{answer}} interpolation)
// resolve against the real resources, and pin the language to English.
import i18n, { ensureLocale } from '../src/i18n/index';
import { LearningQuestionCard } from '../src/components/learning/LearningQuestionCard';

beforeEach(async () => {
  await ensureLocale('en');
  await i18n.changeLanguage('en');
});

describe('LearningQuestionCard', () => {
  it('renders nothing when there is no question', () => {
    const { container } = render(
      <LearningQuestionCard question={null} disabled={false} onAnswer={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when the question has no choices', () => {
    const { container } = render(
      <LearningQuestionCard
        question={{ success: true, question_text: 'No choices here' }}
        disabled={false}
        onAnswer={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the answer choices and reports the tapped choice', () => {
    const onAnswer = vi.fn();
    render(
      <LearningQuestionCard
        question={{
          success: true,
          question_text: 'Which animal says miau?',
          choices: ['Cat', 'Dog', 'Cow'],
          correct_answer_index: 0,
        }}
        disabled={false}
        onAnswer={onAnswer}
      />,
    );

    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(3);

    fireEvent.click(screen.getByRole('button', { name: 'Dog' }));
    expect(onAnswer).toHaveBeenCalledTimes(1);
    expect(onAnswer).toHaveBeenCalledWith('Dog');
  });

  it('disables the choice buttons while a request is in flight', () => {
    render(
      <LearningQuestionCard
        question={{
          success: true,
          question_text: 'Pick one',
          choices: ['A', 'B'],
          correct_answer_index: 1,
        }}
        disabled
        onAnswer={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'A' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'B' })).toBeDisabled();
  });

  it('highlights the correct answer green when the reveal is shown', () => {
    render(
      <LearningQuestionCard
        question={{
          success: true,
          question_text: 'Which animal says miau?',
          choices: ['Cat', 'Dog', 'Cow'],
          correct_answer_index: 0,
        }}
        disabled={false}
        onAnswer={vi.fn()}
        revealed={{ choice: 'Cat', isCorrect: true }}
      />,
    );

    const correct = screen.getByRole('button', { name: 'Cat' });
    expect(correct.getAttribute('data-correct')).toBe('true');
    expect(correct.className).toContain('bg-green-700');
    expect(screen.getByTestId('reveal-caption').textContent).toContain('Correct');
    // All buttons are disabled once the answer is revealed
    screen.getAllByRole('button').forEach((button) => expect(button).toBeDisabled());
  });

  it('marks a wrong pick red and names the correct answer in the caption', () => {
    render(
      <LearningQuestionCard
        question={{
          success: true,
          question_text: 'Which animal says miau?',
          choices: ['Cat', 'Dog', 'Cow'],
          correct_answer_index: 0,
        }}
        disabled={false}
        onAnswer={vi.fn()}
        revealed={{ choice: 'Dog', isCorrect: false }}
      />,
    );

    expect(screen.getByRole('button', { name: 'Dog' }).className).toContain('bg-red-600');
    expect(screen.getByRole('button', { name: 'Cat' }).className).toContain('bg-green-700');
    expect(screen.getByTestId('reveal-caption').textContent).toContain('Cat');
  });

  it('a revealed answer with no verdict shows a neutral state and disables choices', () => {
    render(
      <LearningQuestionCard
        question={{
          success: true,
          question_text: 'Pick one',
          choices: ['A', 'B'],
          correct_answer_index: 0,
        }}
        disabled={false}
        onAnswer={vi.fn()}
        revealed={{ choice: 'A', isCorrect: null }}
      />,
    );

    expect(screen.getByTestId('reveal-caption').textContent).toContain('Answer received');
    screen.getAllByRole('button').forEach((button) => expect(button).toBeDisabled());
  });
});
