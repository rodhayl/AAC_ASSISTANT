import { useTranslation } from 'react-i18next';

interface SessionHistoryItem {
  id: number;
  topic: string;
  created_at: string;
  status: string;
  comprehension_score?: number;
}

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
    <div className="w-80 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          {t('conversationHistory')}
        </h3>
        <button
          onClick={onNewConversation}
          className="mt-2 w-full px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
        >
          {t('newConversation')}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {isLoadingHistory ? (
          <div className="flex justify-center p-4">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600" />
          </div>
        ) : sessionHistory.length === 0 ? (
          <div className="text-center text-gray-500 dark:text-gray-400 text-sm p-4">
            {t('noPrevious')}
          </div>
        ) : (
          <div className="space-y-2">
            {sessionHistory.map((session) => (
              <button
                key={session.id}
                onClick={() => onLoadSession(session.id)}
                className={`w-full text-left p-3 rounded-lg border transition-colors ${
                  currentSessionId === session.id
                    ? 'bg-indigo-50 dark:bg-indigo-900/30 border-indigo-300 dark:border-indigo-700'
                    : 'bg-gray-50 dark:bg-gray-700 border-gray-200 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-600'
                }`}
              >
                <div className="font-medium text-gray-900 dark:text-gray-100 text-sm truncate">
                  {session.topic}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {new Date(session.created_at).toLocaleDateString()}
                </div>
                {session.comprehension_score !== undefined && (
                  <div className="text-xs text-indigo-600 dark:text-indigo-400 mt-1">
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
