import { useTranslation } from 'react-i18next';
import type { SessionHistoryItem } from '../../store/learningStore';
import { Button } from '../ui/button';

interface LearningHistoryPanelProps {
  sessionHistory: SessionHistoryItem[];
  isLoadingHistory: boolean;
  currentSessionId?: number;
  onLoadSession: (sessionId: number) => void;
  onNewConversation: () => void;
}

export function LearningHistoryPanel({
  sessionHistory,
  isLoadingHistory,
  currentSessionId,
  onLoadSession,
  onNewConversation,
}: LearningHistoryPanelProps) {
  const { t } = useTranslation('learning');

  return (
    <div data-testid="learning-history-panel" className="w-80 bg-surface rounded-xl shadow-sm border border-border flex flex-col overflow-hidden">
      <div className="p-4 border-b border-border">
        <h3 className="text-lg font-semibold text-foreground">
          {t('conversationHistory')}
        </h3>
        <Button onClick={onNewConversation} className="mt-2 w-full font-medium" >
          {t('newConversation')}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {isLoadingHistory ? (
          <div className="flex justify-center p-4">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-brand" />
          </div>
        ) : sessionHistory.length === 0 ? (
          <div className="text-center text-muted-foreground text-sm p-4">
            {t('noPrevious')}
          </div>
        ) : (
          <div className="space-y-2">
            {sessionHistory.map((session) => (
              <button
                data-testid="learning-history-item"
                key={session.id}
                onClick={() => onLoadSession(session.id)}
                className={`w-full text-left p-3 rounded-lg border transition-colors ${
                  currentSessionId === session.id
                    ? 'bg-brand/10 border-brand/50'
                    : 'bg-background border-border hover:bg-surface-hover'
                }`}
              >
                <div className="font-medium text-foreground text-sm truncate">
                  {session.topic}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {new Date(session.created_at).toLocaleDateString()}
                </div>
                {session.comprehension_score !== undefined && (
                  <div className="text-xs text-brand mt-1">
                    {t('score')} {Math.round(session.comprehension_score * 100)}%
                  </div>
                )}
                <div
                  className={`text-xs mt-1 ${
                    session.status === 'completed'
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-orange-600 dark:text-orange-400'
                  }`}
                >
                  {session.status === 'completed' ? t('completed') : t('inProgress')}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
