import { beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import i18n, { ensureLocale } from '../src/i18n/index';
import { SessionSummaryModal } from '../src/components/learning/SessionSummaryModal';

beforeEach(async () => {
  await ensureLocale('en');
  await i18n.changeLanguage('en');
});

const BASE_SUMMARY = {
  success: true,
  session_id: 9,
  summary: 'Great work completing your session!',
  comprehension_score: 0.75,
  questions_answered: 4,
  correct_answers: 3,
};

describe('SessionSummaryModal', () => {
  it('renders the summary text and the session stats', () => {
    render(<SessionSummaryModal summary={BASE_SUMMARY} onClose={vi.fn()} />);

    expect(screen.getByText('Great work completing your session!')).toBeInTheDocument();
    // 75% comprehension
    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('closes when the close button is clicked', () => {
    const onClose = vi.fn();
    render(<SessionSummaryModal summary={BASE_SUMMARY} onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: 'Close summary' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes on Escape', () => {
    const onClose = vi.fn();
    render(<SessionSummaryModal summary={BASE_SUMMARY} onClose={onClose} />);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('falls back to statistics when top-level numbers are absent', () => {
    render(
      <SessionSummaryModal
        summary={{
          success: true,
          session_id: 10,
          summary: 'OK',
          statistics: {
            questions_answered: 6,
            correct_answers: 5,
            comprehension_score: 0.83,
          },
        }}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('83%')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });
});
