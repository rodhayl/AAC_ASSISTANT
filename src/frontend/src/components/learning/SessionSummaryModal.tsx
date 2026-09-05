import { Award, CheckCircle2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { SessionSummary } from '../../store/learningStore';
import { Button } from '../ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';

interface SessionSummaryModalProps {
  summary: SessionSummary;
  onClose: () => void;
}

export function SessionSummaryModal({ summary, onClose }: SessionSummaryModalProps) {
  const { t } = useTranslation('learning');

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
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        showCloseButton={false}
        data-testid="session-summary-modal"
        className="max-w-lg p-6"
      >
        <DialogHeader className="flex-row items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-brand/10 text-brand">
              <Award className="w-6 h-6" />
            </div>
            <div>
              <DialogTitle className="text-lg font-semibold text-foreground">
                {t('summaryTitle')}
              </DialogTitle>
              <DialogDescription className="text-sm text-muted-foreground">
                {t('summarySubtitle')}
              </DialogDescription>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('closeSummary')}
            className="p-2 text-muted-foreground hover:bg-surface-hover rounded-lg"
          >
            <X className="w-5 h-5" />
          </button>
        </DialogHeader>

        {summary.summary && (
          <p className="text-sm text-foreground leading-relaxed bg-background/40 rounded-lg p-4 mb-4">
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
          <div className="rounded-lg border border-brand/20 bg-brand/10 p-3 text-center">
            <div className="text-2xl font-bold text-brand">
              {answered}
            </div>
            <div className="text-xs text-brand mt-1">
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
          <Button type="button" onClick={onClose} className="font-medium">
            {t('close')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
