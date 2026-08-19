import { useCallback, useRef } from 'react';
import { Award, CheckCircle2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { SessionSummary } from '../../store/learningStore';
import { useModalFocusTrap } from '../../hooks/useModalFocusTrap';

interface SessionSummaryModalProps {
  summary: SessionSummary;
  onClose: () => void;
}

export function SessionSummaryModal({ summary, onClose }: SessionSummaryModalProps) {
  const { t } = useTranslation('learning');
  const dialogRef = useRef<HTMLDivElement | null>(null);

  const close = useCallback(() => {
    onClose();
  }, [onClose]);

  useModalFocusTrap(dialogRef, true, close);

  const comprehensionPercent =
    summary.comprehension_score !== undefined
      ? Math.round(summary.comprehension_score * 100)
      : summary.statistics?.comprehension_score !== undefined
        ? Math.round(summary.statistics.comprehension_score * 100)
        : undefined;
  const answered =
    summary.questions_answered ?? summary.statistics?.questions_answered ?? 0;
  const correct = summary.correct_answers ?? summary.statistics?.correct_answers ?? 0;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={close}
      role="presentation"
      data-testid="session-summary-modal"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-summary-title"
        className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-lg w-full p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300">
              <Award className="w-6 h-6" />
            </div>
            <div>
              <h4
                id="session-summary-title"
                className="text-lg font-semibold text-gray-900 dark:text-gray-100"
              >
                {t('summaryTitle', 'Session Summary')}
              </h4>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('summarySubtitle', 'Great job — here is how you did.')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label={t('closeSummary', 'Close summary')}
            className="p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {summary.summary && (
          <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed bg-gray-50 dark:bg-gray-900/40 rounded-lg p-4 mb-4">
            {summary.summary}
          </p>
        )}

        <div className="grid grid-cols-3 gap-3 mb-5">
          <div className="rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20 p-3 text-center">
            <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">
              {comprehensionPercent !== undefined ? `${comprehensionPercent}%` : '—'}
            </div>
            <div className="text-xs text-emerald-700 dark:text-emerald-400 mt-1">
              {t('score')}
            </div>
          </div>
          <div className="rounded-lg border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-900/20 p-3 text-center">
            <div className="text-2xl font-bold text-indigo-700 dark:text-indigo-400">
              {answered}
            </div>
            <div className="text-xs text-indigo-700 dark:text-indigo-400 mt-1">
              {t('questionsAnswered')}
            </div>
          </div>
          <div className="rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 p-3 text-center">
            <div className="flex items-center justify-center text-2xl font-bold text-green-700 dark:text-green-400">
              <CheckCircle2 className="w-5 h-5 mr-1" />
              {correct}
            </div>
            <div className="text-xs text-green-700 dark:text-green-400 mt-1">
              {t('correctAnswers')}
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="button"
            onClick={close}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
          >
            {t('close', 'Close')}
          </button>
        </div>
      </div>
    </div>
  );
}
