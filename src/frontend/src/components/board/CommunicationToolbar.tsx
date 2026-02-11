import { Home, ArrowLeft, Keyboard, Bell, ThumbsUp, ThumbsDown, Heart, MessageSquare, Search, BookOpen, Ear } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { AccessibleButton } from '../ui/AccessibleButton';

interface CommunicationToolbarProps {
  onHome: () => void;
  onBack: () => void;
  onToggleKeyboard: () => void;
  onToggleChat: () => void;
  onSearch: () => void;
  onContext: () => void;
  onPartnerMic: () => void;
  onQuickResponse: (text: string, type?: 'positive' | 'negative' | 'neutral' | 'alert') => void;
  onAttention: () => void;
  isKeyboardOpen: boolean;
  isChatOpen: boolean;
  canGoBack: boolean;
}

export function CommunicationToolbar({
  onHome,
  onBack,
  onToggleKeyboard,
  onToggleChat,
  onSearch,
  onContext,
  onPartnerMic,
  onQuickResponse,
  onAttention,
  isKeyboardOpen,
  isChatOpen,
  canGoBack
}: CommunicationToolbarProps) {
  const { t } = useTranslation('boards');

  return (
    <div className="glass-panel p-2 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)] z-30 w-full overflow-hidden">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-2 overflow-x-auto hide-scrollbar">

        {/* Navigation Group */}
        <div className="flex items-center gap-2 pr-2 border-r border-gray-200 dark:border-gray-700">
          <AccessibleButton
            onClick={onHome}
            className="p-3 rounded-xl bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors flex flex-col items-center min-w-[4rem]"
            title={t('home', 'Home')}
          >
            <Home className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('home', 'Home')}</span>
          </AccessibleButton>

          <AccessibleButton
            onClick={onBack}
            disabled={!canGoBack}
            className={`p-3 rounded-xl bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors flex flex-col items-center min-w-[4rem] ${!canGoBack ? 'opacity-50 cursor-not-allowed' : ''}`}
            title={t('back', 'Back')}
          >
            <ArrowLeft className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('back', 'Back')}</span>
          </AccessibleButton>
        </div>

        {/* Quick Responses Group */}
        <div className="flex items-center gap-2 flex-1 justify-center min-w-max">
          <AccessibleButton
            onClick={() => onQuickResponse(t('yes', 'Yes'), 'positive')}
            className="p-3 rounded-xl bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 hover:bg-green-200 dark:hover:bg-green-900/50 transition-colors flex flex-col items-center min-w-[4rem]"
          >
            <ThumbsUp className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('yes', 'Yes')}</span>
          </AccessibleButton>

          <AccessibleButton
            onClick={() => onQuickResponse(t('no', 'No'), 'negative')}
            className="p-3 rounded-xl bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors flex flex-col items-center min-w-[4rem]"
          >
            <ThumbsDown className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('no', 'No')}</span>
          </AccessibleButton>

          <AccessibleButton
            onClick={() => onQuickResponse(t('thanks', 'Thanks'), 'neutral')}
            className="p-3 rounded-xl bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 hover:bg-yellow-200 dark:hover:bg-yellow-900/50 transition-colors flex flex-col items-center min-w-[4rem]"
          >
            <Heart className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('thanks', 'Thanks')}</span>
          </AccessibleButton>
        </div>

        {/* Tools Group */}
        <div className="flex items-center gap-2 pl-2 border-l border-gray-200 dark:border-gray-700">
          <AccessibleButton
            onClick={onPartnerMic}
            className="p-3 rounded-xl bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 hover:bg-orange-200 dark:hover:bg-orange-900/50 transition-colors flex flex-col items-center min-w-[4rem]"
            title={t('listen', 'Listen')}
          >
            <Ear className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('listen', 'Listen')}</span>
          </AccessibleButton>

          <AccessibleButton
            onClick={onSearch}
            className="p-3 rounded-xl bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors flex flex-col items-center min-w-[4rem]"
            title={t('search', 'Search')}
          >
            <Search className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('search', 'Search')}</span>
          </AccessibleButton>

          <AccessibleButton
            onClick={onContext}
            className="p-3 rounded-xl bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors flex flex-col items-center min-w-[4rem]"
            title={t('context', 'Context')}
          >
            <BookOpen className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('topic', 'Topic')}</span>
          </AccessibleButton>

          <AccessibleButton
            onClick={onToggleChat}
            className={`p-3 rounded-xl transition-colors flex flex-col items-center min-w-[4rem] ${isChatOpen ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600'}`}
            title={t('chat', 'Chat')}
          >
            <MessageSquare className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('chat', 'Chat')}</span>
          </AccessibleButton>

          <AccessibleButton
            onClick={onToggleKeyboard}
            className={`p-3 rounded-xl transition-colors flex flex-col items-center min-w-[4rem] ${isKeyboardOpen ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600'}`}
            title={t('keyboard', 'Keyboard')}
          >
            <Keyboard className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('type', 'Type')}</span>
          </AccessibleButton>

          <AccessibleButton
            onClick={onAttention}
            className="p-3 rounded-xl bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 hover:bg-orange-200 dark:hover:bg-orange-900/50 transition-colors flex flex-col items-center min-w-[4rem]"
            title={t('attention', 'Attention')}
          >
            <Bell className="w-6 h-6 mb-1" />
            <span className="text-[10px] font-medium uppercase">{t('alert', 'Alert')}</span>
          </AccessibleButton>
        </div>
      </div>
    </div>
  );
}
