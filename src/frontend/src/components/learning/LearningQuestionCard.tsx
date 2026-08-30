import { CheckCircle2, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { QuestionResponse } from '../../types';
import type { RevealedAnswer } from '../../store/learningStore';

interface LearningQuestionCardProps {
  question: QuestionResponse | null;
  disabled: boolean;
  onAnswer: (choice: string) => void;
  revealed?: RevealedAnswer | null;
}

export function LearningQuestionCard({
  question,
  disabled,
  onAnswer,
  revealed = null,
}: LearningQuestionCardProps) {
  const { t } = useTranslation('learning');

  if (!question) return null;

  const choices = question.choices ?? [];
  if (choices.length === 0) return null;

  const isAnswered = revealed !== null;
  const revealedIsCorrect = revealed?.isCorrect ?? null;
  // A wrong pick is only "final" once the tutor revealed the full answer;
  // before that the student keeps retrying with progressive hints and the
  // correct choice must stay hidden.
  const isFinal =
    revealedIsCorrect !== false || revealed?.answerRevealed === true;
  const correctIndex = question.correct_answer_index;
  const correctLabel =
    correctIndex !== undefined && correctIndex >= 0 && correctIndex < choices.length
      ? choices[correctIndex]
      : undefined;

  const caption = isAnswered
    ? revealedIsCorrect === true
      ? t('correctAnswer')
      : revealedIsCorrect === false
        ? isFinal
          ? t('notQuite', {
              answer: correctLabel ?? revealed?.choice ?? '',
            })
          : t('tryAgain')
        : t('answerReceived')
    : null;

  return (
    <div className="px-4 pb-2" data-testid="question-card">
      <div
        className={`rounded-xl border p-3 transition-colors ${
          isAnswered
            ? revealedIsCorrect === true
              ? 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20'
              : revealedIsCorrect === false
                ? 'border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20'
                : 'border-border bg-muted/50'
            : 'border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/20'
        }`}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-medium text-purple-700 dark:text-purple-300">
            {t('chooseAnswer')}
          </div>
          {caption && (
            <div
              data-testid="reveal-caption"
              className={`flex items-center gap-1 text-xs font-semibold ${
                revealedIsCorrect === true
                  ? 'text-green-700 dark:text-green-400'
                  : revealedIsCorrect === false
                    ? 'text-red-700 dark:text-red-400'
                    : 'text-muted-foreground'
              }`}
            >
              {revealedIsCorrect === true ? (
                <CheckCircle2 className="w-3.5 h-3.5" />
              ) : revealedIsCorrect === false ? (
                <XCircle className="w-3.5 h-3.5" />
              ) : null}
              {caption}
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {choices.map((choice, index) => {
            const isCorrectChoice = correctIndex === index;
            // Every failed pick on this question stays marked and disabled.
            const wrongPicks =
              revealed?.wrongChoices ??
              (revealed?.isCorrect === false ? [revealed.choice] : []);
            const isWrongPick = wrongPicks.includes(choice);
            let buttonClass =
              'px-3 py-1.5 rounded-lg border text-sm transition-colors ';
            if (!isAnswered) {
              buttonClass +=
                'bg-surface border-brand/50 text-foreground hover:bg-brand/10 hover:border-brand';
            } else if (!isFinal) {
              // Hint state: only the failed picks are marked and disabled;
              // the rest stay available for another attempt and the correct
              // choice is NOT revealed.
              buttonClass += isWrongPick
                ? 'bg-red-600 dark:bg-red-500 text-white border-red-600 dark:border-red-500'
                : 'bg-surface border-brand/50 text-foreground hover:bg-brand/10 hover:border-brand';
            } else if (isCorrectChoice) {
              buttonClass +=
                'bg-green-700 text-white border-green-700 dark:border-green-700 font-medium';
            } else if (isWrongPick) {
              buttonClass +=
                'bg-red-600 dark:bg-red-500 text-white border-red-600 dark:border-red-500';
            } else {
              buttonClass +=
                'bg-surface border-border text-muted-foreground opacity-60';
            }
            return (
              <button
                key={`${index}-${choice}`}
                type="button"
                onClick={() => onAnswer(choice)}
                disabled={disabled || (isAnswered && (isFinal || isWrongPick))}
                aria-label={choice}
                data-correct={isCorrectChoice ? 'true' : undefined}
                className={buttonClass}
              >
                {choice}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
