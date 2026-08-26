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
  const correctIndex = question.correct_answer_index;
  const correctLabel =
    correctIndex !== undefined && correctIndex >= 0 && correctIndex < choices.length
      ? choices[correctIndex]
      : undefined;

  const caption = isAnswered
    ? revealedIsCorrect === true
      ? t('correctAnswer')
      : revealedIsCorrect === false
        ? t('notQuite', {
            answer: correctLabel ?? revealed?.choice ?? '',
          })
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
                : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50'
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
                    : 'text-gray-600 dark:text-gray-300'
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
            const isPicked = revealed?.choice === choice;
            let buttonClass =
              'px-3 py-1.5 rounded-lg border text-sm transition-colors ';
            if (!isAnswered) {
              buttonClass +=
                'bg-white dark:bg-gray-800 border-purple-300 dark:border-purple-700 text-gray-800 dark:text-gray-100 hover:bg-purple-100 dark:hover:bg-purple-900/40 hover:border-purple-400';
            } else if (isCorrectChoice) {
              buttonClass +=
                'bg-green-600 dark:bg-green-500 text-white border-green-600 dark:border-green-500 font-medium';
            } else if (isPicked) {
              buttonClass +=
                'bg-red-600 dark:bg-red-500 text-white border-red-600 dark:border-red-500';
            } else {
              buttonClass +=
                'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600 text-gray-400 dark:text-gray-500 opacity-60';
            }
            return (
              <button
                key={`${index}-${choice}`}
                type="button"
                onClick={() => onAnswer(choice)}
                disabled={disabled || isAnswered}
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
