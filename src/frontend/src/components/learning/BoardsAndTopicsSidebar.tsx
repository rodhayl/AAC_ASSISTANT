import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import { useBoardStore } from '../../store/boardStore';
import { Button } from '../ui/button';
import { IconButton } from '../ui/icon-button';
import { cn } from '../../lib/utils';
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
    const user = useAuthStore((state) => state.user);
    const boards = useBoardStore((state) => state.boards);

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

        let boardName = t('boardNameDefault');
        if (selectedBoardId === 'custom') {
            boardName = customPurpose.trim() || t('boardNameDefault');
        } else if (selectedBoardId) {
            const board = boards.find(b => b.id.toString() === selectedBoardId);
            if (board) boardName = board.name;
        }

        const topic: SavedTopic = {
            id: Date.now(),
            board: boardName,
            topic: topicName,
            createdBy: user?.display_name || user?.username || t('teacherDefault'),
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
        <div className={cn(
            'flex flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-sm transition-all duration-300',
            isOpen ? 'w-80' : 'w-12',
            className,
        )}>
            <div className={cn('flex items-center border-b border-border p-4', isOpen ? 'justify-between' : 'justify-center')}>
                {isOpen && <h3 className="text-lg font-semibold text-foreground truncate">{t('boardsTopics')}</h3>}
                <button
                    onClick={onToggle}
                    className="p-1 hover:bg-surface-hover rounded"
                    title={isOpen ? t('collapseSidebar') : t('expandSidebar')}
                >
                    {isOpen ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
                </button>
            </div>

            {isOpen && (
                <>
                    {canManageTopics && (
                        <div className="p-4 pt-0 border-b border-border">
                            <div className="space-y-3 mt-3">
                                {/* Board Selection */}
                                <div>
                                    <label htmlFor="comp-board-select" className="block text-xs font-medium text-foreground mb-1">{t('selectBoard')}</label>
                                    <select
                                        id="comp-board-select"
                                        value={selectedBoardId}
                                        onChange={(e) => setSelectedBoardId(e.target.value)}
                                        className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground text-sm mb-2"
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
                                            className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground text-sm"
                                        />
                                    )}
                                </div>

                                {/* Topic Selection */}
                                <div>
                                    <label htmlFor="comp-topic-select" className="block text-xs font-medium text-foreground mb-1">{t('topics.label')}</label>
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
                                        className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground text-sm mb-2"
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
                                            className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground text-sm"
                                        />
                                    )}
                                </div>

                                <Button type="button" onClick={addSavedTopic} className="w-full inline-flex items-center justify-center" >
                                    <Plus className="w-4 h-4 mr-1" /> {t('saveTopic')}
                                </Button>
                            </div>
                        </div>
                    )}
                    <div className="flex-1 overflow-y-auto p-3 space-y-2">
                        {savedTopics.length === 0 ? (
                            <div className="text-sm text-muted-foreground text-center py-4">{t('noSavedTopics')}</div>
                        ) : (
                            savedTopics.map((topic) => (
                                <div key={topic.id} className="p-3 rounded-lg border border-border bg-background flex items-start gap-2">
                                    <div className="flex-1">
                                        <div className="text-sm font-semibold text-foreground">{topic.topic}</div>
                                        <div className="text-xs text-muted-foreground">{topic.board}</div>
                                        <div className="text-[11px] text-muted-foreground">{t('by')} {topic.createdBy}</div>
                                        <div className="mt-2 flex gap-2">
                                            <Button
                                                type="button"
                                                size="xs"
                                                onClick={() => user && handleStart(topic.topic, topic.board || 'practice')}
                                                disabled={isStartingSession}
                                            >
                                                {isStartingSession ? t('startingSession') : t('startStudy')}
                                            </Button>
                                        </div>
                                    </div>
                                    {canManageTopics && (
                                        <IconButton
                                            label={t('removeTopic')}
                                            type="button"
                                            onClick={() => removeSavedTopic(topic.id)}
                                            className="text-muted-foreground hover:text-red-600"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </IconButton>
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
