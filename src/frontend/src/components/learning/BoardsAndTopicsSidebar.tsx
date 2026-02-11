import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import { useBoardStore } from '../../store/boardStore';
import {
    loadTopicsForUser,
    addTopic as addTopicHelper,
    removeTopic as removeTopicHelper,
    type SavedTopic
} from '../../lib/learningTopics';

interface BoardsAndTopicsSidebarProps {
    isOpen: boolean;
    onToggle: () => void;
    onStartActivity: (topic: string, purpose: string, boardId?: number) => void;
    isStartingSession: boolean;
    className?: string;
}

const COMMON_TOPICS = [
    "general",
    "daily",
    "food",
    "school",
    "emotions",
    "travel",
    "hobbies",
    "health",
    "shopping"
];

export function BoardsAndTopicsSidebar({
    isOpen,
    onToggle,
    onStartActivity,
    isStartingSession,
    className = ""
}: BoardsAndTopicsSidebarProps) {
    const { t } = useTranslation('learning');
    const { user } = useAuthStore();
    const { boards } = useBoardStore();

    const [topicsRevision, setTopicsRevision] = useState(0);
    const [selectedBoardId, setSelectedBoardId] = useState<string>('');
    const [topicMode, setTopicMode] = useState<'common' | 'custom'>('common');
    const [customTopic, setCustomTopic] = useState('');
    const [customPurpose, setCustomPurpose] = useState('');

    const userId = user?.id ?? null;
    const canManageTopics = useMemo(() => user?.user_type === 'teacher' || user?.user_type === 'admin', [user?.user_type]);
    const savedTopics = useMemo<SavedTopic[]>(() => {
        // Recompute when topicsRevision changes after add/remove actions.
        void topicsRevision;
        return userId ? loadTopicsForUser(userId) : [];
    }, [userId, topicsRevision]);

    const addSavedTopic = () => {
        let topicName = customTopic.trim();
        if (topicMode === 'common' && customTopic) {
            topicName = t(`topics.${customTopic}`);
        }
        if (!topicName) return;
        if (!user?.id) return;

        let boardName = 'General';
        if (selectedBoardId === 'custom') {
            boardName = customPurpose.trim() || 'General';
        } else if (selectedBoardId) {
            const board = boards.find(b => b.id.toString() === selectedBoardId);
            if (board) boardName = board.name;
        }

        const topic: SavedTopic = {
            id: Date.now(),
            board: boardName,
            topic: topicName,
            createdBy: user?.display_name || user?.username || 'Teacher',
        };
        addTopicHelper(user.id, topic);
        setTopicsRevision((value) => value + 1);
        setCustomTopic('');
        setCustomPurpose('');
        setTopicMode('common');
        setSelectedBoardId('');
    };

    const removeSavedTopic = (id: number) => {
        if (!user?.id) return;
        removeTopicHelper(user.id, id);
        setTopicsRevision((value) => value + 1);
    };

    const handleStart = (topicName: string, boardName: string) => {
        // Find board ID if possible, otherwise just pass board name as context/purpose
        // In Learning.tsx logic: boardId is passed if selectedBoardId is numeric.
        // Here we are starting from a SAVED topic which stores 'board' as a string name.
        // The parent onStartActivity expects specific params.
        // We'll pass the topic and use the board name as the purpose/context.
        // Ideally we would store boardId in SavedTopic but the interface uses string name.
        // We will look up board by name to find ID if possible.
        const board = boards.find(b => b.name === boardName);
        onStartActivity(topicName, boardName, board ? board.id : undefined);
    };

    return (
        <div className={`${isOpen ? 'w-80' : 'w-12'} transition-all duration-300 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden ${className}`}>
            <div className={`p-4 border-b border-gray-200 dark:border-gray-700 flex items-center ${isOpen ? 'justify-between' : 'justify-center'}`}>
                {isOpen && <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">{t('boardsTopics')}</h3>}
                <button
                    onClick={onToggle}
                    className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                    title={isOpen ? "Collapse sidebar" : "Expand sidebar"}
                >
                    {isOpen ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
                </button>
            </div>

            {isOpen && (
                <>
                    {canManageTopics && (
                        <div className="p-4 pt-0 border-b border-gray-200 dark:border-gray-700">
                            <div className="space-y-3 mt-3">
                                {/* Board Selection */}
                                <div>
                                    <label htmlFor="comp-board-select" className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">{t('selectBoard') || 'Board / Context'}</label>
                                    <select
                                        id="comp-board-select"
                                        value={selectedBoardId}
                                        onChange={(e) => setSelectedBoardId(e.target.value)}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm mb-2"
                                    >
                                        <option value="">{t('generalNoBoard')}</option>
                                        {boards.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                                        <option value="custom">{t('customContext')}</option>
                                    </select>
                                    {selectedBoardId === 'custom' && (
                                        <input
                                            type="text"
                                            value={customPurpose}
                                            onChange={(e) => setCustomPurpose(e.target.value)}
                                            placeholder={t('boardOptional')}
                                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                                        />
                                    )}
                                </div>

                                {/* Topic Selection */}
                                <div>
                                    <label htmlFor="comp-topic-select" className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">{t('topics.label', { defaultValue: 'Topic' })}</label>
                                    <select
                                        id="comp-topic-select"
                                        value={topicMode === 'custom' ? 'custom' : customTopic}
                                        onChange={(e) => {
                                            if (e.target.value === 'custom') {
                                                setTopicMode('custom');
                                                setCustomTopic('');
                                            } else {
                                                setTopicMode('common');
                                                setCustomTopic(e.target.value);
                                            }
                                        }}
                                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm mb-2"
                                    >
                                        <option value="" disabled>{t('selectTopic')}</option>
                                        {COMMON_TOPICS.map(key => <option key={key} value={key}>{t(`topics.${key}`)}</option>)}
                                        <option value="custom">{t('customTopic')}</option>
                                    </select>
                                    {topicMode === 'custom' && (
                                        <input
                                            type="text"
                                            value={customTopic}
                                            onChange={(e) => setCustomTopic(e.target.value)}
                                            placeholder={t('topicStudy')}
                                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm"
                                        />
                                    )}
                                </div>

                                <button
                                    type="button"
                                    onClick={addSavedTopic}
                                    className="w-full inline-flex items-center justify-center px-3 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 text-sm"
                                >
                                    <Plus className="w-4 h-4 mr-1" /> {t('saveTopic')}
                                </button>
                            </div>
                        </div>
                    )}
                    <div className="flex-1 overflow-y-auto p-3 space-y-2">
                        {savedTopics.length === 0 ? (
                            <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">{t('noSavedTopics')}</div>
                        ) : (
                            savedTopics.map((topic) => (
                                <div key={topic.id} className="p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex items-start gap-2">
                                    <div className="flex-1">
                                        <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{topic.topic}</div>
                                        <div className="text-xs text-gray-500 dark:text-gray-400">{topic.board}</div>
                                        <div className="text-[11px] text-gray-400">{t('by')} {topic.createdBy}</div>
                                        <div className="mt-2 flex gap-2">
                                            <button
                                                type="button"
                                                onClick={() => user && handleStart(topic.topic, topic.board || 'practice')}
                                                className="px-3 py-1 bg-indigo-600 text-white text-xs rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                                                disabled={isStartingSession}
                                            >
                                                {isStartingSession ? t('startingSession') : t('startStudy')}
                                            </button>
                                        </div>
                                    </div>
                                    {canManageTopics && (
                                        <button
                                            type="button"
                                            onClick={() => removeSavedTopic(topic.id)}
                                            className="text-gray-400 hover:text-red-600"
                                            title={t('removeTopic')}
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
