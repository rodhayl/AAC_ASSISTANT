import { useCallback, useEffect, useMemo, useState } from 'react';
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

import { SectionTitle } from '@/components/ui/SectionTitle';
import { TeacherAvatar } from './TeacherAvatar';

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
    const assignedBoards = useBoardStore((state) => state.assignedBoards);
    const availableBoards = useMemo(() => {
        const uniqueBoards = new Map<number, (typeof boards)[number]>();
        for (const board of [...boards, ...assignedBoards]) {
            uniqueBoards.set(board.id, board);
        }
        return Array.from(uniqueBoards.values());
    }, [assignedBoards, boards]);

    const [selectedBoardId, setSelectedBoardId] = useState<string>('');
    const [topicMode, setTopicMode] = useState<'common' | 'custom'>('common');
    const [customTopic, setCustomTopic] = useState('');
    const [customPurpose, setCustomPurpose] = useState('');
    const [savedTopics, setSavedTopics] = useState<SavedTopic[]>([]);

    const userId = user?.id ?? null;
    const canManageTopics = useMemo(() => user?.user_type === 'teacher' || user?.user_type === 'admin', [user?.user_type]);

    // When the list mixes several teachers, group the topics under per-teacher
    // headings (avatar + name) — the same rule the topic picker uses. A lone
    // teacher's topics (or the owner's own list) stay flat and uncluttered.
    const teacherGroups = useMemo(() => {
        const teachers = Array.from(
            new Set(savedTopics.map((topic) => topic.createdBy).filter(Boolean)),
        );
        if (teachers.length < 2) return null;
        return teachers.map((teacher) => ({
            teacher,
            topics: savedTopics.filter((topic) => topic.createdBy === teacher),
        }));
    }, [savedTopics]);

    const loadSavedTopics = useCallback(async () => {
        if (!userId) return;
        try {
            const topics = await loadTopicsForUser(userId, canManageTopics);
            setSavedTopics(topics);
        } catch {
            setSavedTopics([]);
        }
    }, [userId, canManageTopics]);

    useEffect(() => {
        if (!userId) return;
        let cancelled = false;
        // Teachers/admins trigger the one-time localStorage migration; students
        // read the topics their roster teachers saved (server-side).
        void loadTopicsForUser(userId, canManageTopics)
            .then((topics) => {
                if (!cancelled) setSavedTopics(topics);
            })
            .catch(() => {
                if (!cancelled) setSavedTopics([]);
            });
        return () => {
            cancelled = true;
        };
    }, [userId, canManageTopics]);

    const addSavedTopic = async () => {
        let topicName = customTopic.trim();
        if (topicMode === 'common' && customTopic) {
            topicName = t(`topics.${customTopic}`);
        }
        if (!topicName) return;
        if (!user?.id) return;

        let boardName = t('boardNameDefault');
        let boardId: number | undefined;
        if (selectedBoardId === 'custom') {
            boardName = customPurpose.trim() || t('boardNameDefault');
        } else if (selectedBoardId) {
            const board = availableBoards.find(b => b.id.toString() === selectedBoardId);
            if (board) {
                boardName = board.name;
                boardId = board.id;
            }
        }

        try {
            await addTopicHelper(user.id, {
                board: boardName,
                ...(boardId !== undefined ? { boardId } : {}),
                topic: topicName,
            });
            await loadSavedTopics();
        } catch {
            // Keep the form intact so the teacher can retry.
            return;
        }
        setCustomTopic('');
        setCustomPurpose('');
        setTopicMode('common');
        setSelectedBoardId('');
    };

    const removeSavedTopic = async (id: number) => {
        if (!user?.id) return;
        try {
            await removeTopicHelper(user.id, id);
            await loadSavedTopics();
        } catch {
            // Deletion failure leaves the list untouched.
        }
    };

    const handleStart = (savedTopic: SavedTopic) => {
        // Keep the durable ID when available. The name lookup is only a
        // compatibility fallback for topics saved before board IDs existed;
        // IDs avoid selecting the wrong board when names are duplicated.
        const board = savedTopic.boardId !== undefined
            ? availableBoards.find((item) => item.id === savedTopic.boardId)
            : availableBoards.find((item) => item.name === savedTopic.board);
        onStartActivity(savedTopic.topic, savedTopic.board, board?.id ?? savedTopic.boardId);
    };

    return (
        <div className={cn(
            'flex flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-sm transition-all duration-300',
            isOpen ? 'w-80' : 'w-12',
            className,
        )}>
            <div className={cn('flex items-center border-b border-border p-4', isOpen ? 'justify-between' : 'justify-center')}>
                {isOpen && <SectionTitle as="h3" className="truncate">{t('boardsTopics')}</SectionTitle>}
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
                                        {availableBoards.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
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
                    <div className="flex-1 overflow-y-auto p-3 space-y-3">
                        {savedTopics.length === 0 ? (
                            <div className="text-sm text-muted-foreground text-center py-4">{t('noSavedTopics')}</div>
                        ) : teacherGroups ? (
                            <>
                            <p className="px-1 pb-1 text-[11px] font-medium text-muted-foreground" data-testid="sidebar-topic-group-summary">
                                {t('topicPicker.summary', {
                                    topics: teacherGroups.reduce((total, group) => total + group.topics.length, 0),
                                    teachers: teacherGroups.length,
                                })}
                            </p>
                            {teacherGroups.map((group) => (
                                <div key={group.teacher} data-testid={`sidebar-topic-group-${group.teacher}`}>
                                    <h4 className="flex items-center gap-1.5 px-1 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                        <TeacherAvatar name={group.teacher} className="h-4 w-4" />
                                        {t('topicPicker.savedBy', { teacher: group.teacher })}
                                        <span
                                            className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
                                            title={t('topicPicker.topicCount', { count: group.topics.length })}
                                        >
                                            {group.topics.length}
                                        </span>
                                    </h4>
                                    <div className="space-y-2">
                                        {group.topics.map((topic) => (
                                            <div key={topic.id} className="p-3 rounded-lg border border-border bg-background flex items-start gap-2">
                                                <div className="flex-1">
                                                    <div className="text-sm font-semibold text-foreground">{topic.topic}</div>
                                                    <div className="text-xs text-muted-foreground">{topic.board}</div>
                                                    <div className="mt-2 flex gap-2">
                                                        <Button
                                                            type="button"
                                                            size="xs"
                                                            onClick={() => user && handleStart(topic)}
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
                                                        className="text-muted-foreground hover:text-red-600 dark:text-red-400"
                                                    >
                                                        <Trash2 className="w-4 h-4" />
                                                    </IconButton>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))}
                            </>
                        ) : (
                            savedTopics.map((topic) => (
                                <div key={topic.id} className="p-3 rounded-lg border border-border bg-background flex items-start gap-2">
                                    <div className="flex-1">
                                        <div className="text-sm font-semibold text-foreground">{topic.topic}</div>
                                        <div className="text-xs text-muted-foreground">{topic.board}</div>
                                        <div className="mt-2 flex gap-2">
                                            <Button
                                                type="button"
                                                size="xs"
                                                onClick={() => user && handleStart(topic)}
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
                                            className="text-muted-foreground hover:text-red-600 dark:text-red-400"
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
