import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { Plus, Trash2, LayoutGrid, Edit, Copy, UserPlus, Search, Play } from 'lucide-react';

import { useBoardStore } from '../store/boardStore';
import { useAuthStore } from '../store/authStore';
import { useSettingsStore } from '../store/settingsStore';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { IconButton } from '../components/ui/icon-button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import type { User } from '../types';
import { useTranslation } from 'react-i18next';
import { formatDate } from '../lib/format';

import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { StatusMessage } from '../components/ui/StatusMessage';

import { FormLabel } from '@/components/ui/FormLabel';
import { SectionTitle } from '@/components/ui/SectionTitle';

export function Boards() {
  const boards = useBoardStore((state) => state.boards);
  const assignedBoards = useBoardStore((state) => state.assignedBoards);
  const isListLoading = useBoardStore((state) => state.isListLoading);
  const error = useBoardStore((state) => state.error);
  const fetchBoards = useBoardStore((state) => state.fetchBoards);
  const fetchAssignedBoards = useBoardStore((state) => state.fetchAssignedBoards);
  const createBoard = useBoardStore((state) => state.createBoard);
  const deleteBoard = useBoardStore((state) => state.deleteBoard);
  const duplicateBoard = useBoardStore((state) => state.duplicateBoard);
  const assignBoardToStudent = useBoardStore((state) => state.assignBoardToStudent);
  const hasMore = useBoardStore((state) => state.hasMore);
  const page = useBoardStore((state) => state.page);
  const user = useAuthStore((state) => state.user);
  const aiSettings = useSettingsStore((state) => state.aiSettings);
  const fetchAISettings = useSettingsStore((state) => state.fetchAISettings);
  const { t, i18n } = useTranslation('boards');
  const { t: tError } = useTranslation('error');

  const [isCreating, setIsCreating] = useState(false);
  const [creatingBoard, setCreatingBoard] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [newBoardName, setNewBoardName] = useState('');
  const [newBoardDescription, setNewBoardDescription] = useState('');
  const [aiEnabled, setAiEnabled] = useState(false);
  const [isLanguageLearning, setIsLanguageLearning] = useState(false);
  const [aiConfigError, setAiConfigError] = useState<string | null>(null);

  const [assignOpenId, setAssignOpenId] = useState<number | null>(null);
  const [students, setStudents] = useState<User[]>([]);
  const [studentsLoading, setStudentsLoading] = useState(false);
  const [assignLoading, setAssignLoading] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [selectedStudentId, setSelectedStudentId] = useState<number | null>(null);
  const studentsRequestRef = useRef(0);
  // Hard cap on paginated walks: prevents an infinite request loop if the
  // endpoint stops shrinking pages.
  const MAX_WALK_PAGES = 200;

  const [deleteBoardId, setDeleteBoardId] = useState<number | null>(null);
  const [selectedBoardIds, setSelectedBoardIds] = useState<Set<number>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [bulkDeleteError, setBulkDeleteError] = useState<string | null>(null);

  // Fetch personal boards for the current user. Search only affects this
  // request; assigned boards are loaded separately because they have no search
  // parameter and should not be re-requested on every query change.
  const lastBoardRequestKeyRef = useRef<string | null>(null);
  const lastSearchQueryRef = useRef(searchQuery);
  const userId = user?.id;
  const userType = user?.user_type;
  const studentsContextKey = `${userId ?? 'anonymous'}:${userType ?? 'anonymous'}`;
  const studentsContextRef = useRef(studentsContextKey);
  studentsContextRef.current = studentsContextKey;

  useEffect(() => {
    // The student roster is account-scoped. Clear it before the next account's
    // request starts so an old roster cannot remain actionable in the panel.
    studentsRequestRef.current += 1;
    setStudents([]);
    setStudentsLoading(false);
    setAssignOpenId(null);
    setAssignLoading(false);
    setAssignError(null);
    setSelectedStudentId(null);
    return () => {
      studentsRequestRef.current += 1;
    };
  }, [studentsContextKey]);

  useEffect(() => {
    if (!userId || !userType) {
      lastBoardRequestKeyRef.current = null;
      lastSearchQueryRef.current = searchQuery;
      return;
    }

    const userKey = `${userId}:${userType}`;
    const userChanged = lastBoardRequestKeyRef.current !== userKey;
    const searchChanged = lastSearchQueryRef.current !== searchQuery;
    if (!userChanged && !searchChanged) return;

    lastBoardRequestKeyRef.current = userKey;
    lastSearchQueryRef.current = searchQuery;
    const loadBoards = () => {
      if (userType === 'admin') {
        fetchBoards(undefined, searchQuery);
      } else {
        fetchBoards(userId, searchQuery);
      }
    };

    // Load immediately for a new user; debounce only search changes.
    if (userChanged) {
      loadBoards();
      return;
    }

    const timer = setTimeout(loadBoards, 300);
    return () => clearTimeout(timer);
  }, [fetchBoards, userId, userType, searchQuery]);

  const lastAssignedUserIdRef = useRef<number | null>(null);
  useEffect(() => {
    if (user?.user_type !== 'student') {
      lastAssignedUserIdRef.current = null;
      return;
    }
    if (lastAssignedUserIdRef.current === user.id) return;
    lastAssignedUserIdRef.current = user.id;
    fetchAssignedBoards(user.id);
  }, [fetchAssignedBoards, user?.id, user?.user_type]);

  const effectiveUserId = user?.user_type === 'admin' ? undefined : user?.id;

  // Preload AI settings
  useEffect(() => {
    if (!aiSettings) {
      void fetchAISettings();
    }
  }, [aiSettings, fetchAISettings]);

  const primaryProvider = aiSettings?.provider;
  const primaryModel = primaryProvider === 'openrouter'
    ? aiSettings?.openrouter_model
    : primaryProvider === 'lmstudio'
      ? aiSettings?.lmstudio_model
      : primaryProvider === 'groq'
        ? aiSettings?.groq_model
        : aiSettings?.ollama_model;
  const primaryReady = Boolean(primaryProvider && primaryModel);
  const resolvedProvider = primaryProvider;
  const resolvedModel = primaryModel;

  // AI config validation
  useEffect(() => {
    if (!aiEnabled) {
      setAiConfigError(null);
      return;
    }
    if (!primaryReady) {
      setAiConfigError(t('aiSettingsMissing'));
      return;
    }
    setAiConfigError(null);
  }, [aiEnabled, primaryReady, t]);

  const openAssign = async (boardId: number) => {
    const contextKey = studentsContextKey;
    if (studentsContextRef.current !== contextKey) return;
    const requestId = ++studentsRequestRef.current;
    setAssignOpenId(boardId);
    setAssignError(null);
    setSelectedStudentId(null);
    if (!students.length) {
      setStudentsLoading(true);
      try {
        const loadedStudents: User[] = [];
        let skip = 0;
        let pagesFetched = 0;
        const pageSize = 1000;
        while (true) {
          // Guarantee termination even if a backend bug keeps returning full
          // pages.
          pagesFetched += 1;
          if (pagesFetched > MAX_WALK_PAGES) {
            throw new Error('Pagination did not terminate');
          }
          if (
            requestId !== studentsRequestRef.current ||
            studentsContextRef.current !== contextKey
          ) return;
          const params = {
            ...(skip > 0 ? { skip } : {}),
            limit: pageSize,
            user_type: 'student',
          };
          const res = await api.get('/auth/users', { params });
          if (
            requestId !== studentsRequestRef.current ||
            studentsContextRef.current !== contextKey
          ) return;
          const page = res.data as User[];
          if (!Array.isArray(page)) {
            throw new Error('Invalid response format: expected array');
          }
          loadedStudents.push(...page);
          if (page.length < pageSize) break;
          skip += page.length;
        }
        if (
          requestId !== studentsRequestRef.current ||
          studentsContextRef.current !== contextKey
        ) return;
        setStudents(loadedStudents);
      } catch {
        if (
          requestId === studentsRequestRef.current &&
          studentsContextRef.current === contextKey
        ) {
          setAssignError(t('loadStudentsError'));
        }
      } finally {
        if (
          requestId === studentsRequestRef.current &&
          studentsContextRef.current === contextKey
        ) {
          setStudentsLoading(false);
        }
      }
    }
  };

  const closeAssign = () => {
    studentsRequestRef.current += 1;
    setAssignOpenId(null);
    setStudentsLoading(false);
    setAssignLoading(false);
    setAssignError(null);
    setSelectedStudentId(null);
  };

  const submitAssign = async (boardId: number) => {
    if (!selectedStudentId) return;
    const contextKey = studentsContextKey;
    const requestId = studentsRequestRef.current;
    const assignedStudentId = selectedStudentId;
    const assignedBy = user?.id;
    const isCurrentRequest = () =>
      requestId === studentsRequestRef.current &&
      studentsContextRef.current === contextKey;
    setAssignLoading(true);
    setAssignError(null);
    try {
      await assignBoardToStudent(boardId, assignedStudentId, assignedBy);
      if (!isCurrentRequest()) return;
      closeAssign();
    } catch {
      if (isCurrentRequest()) {
        setAssignError(t('assignBoardError'));
      }
    } finally {
      if (isCurrentRequest()) {
        setAssignLoading(false);
      }
    }
  };

  const handleCreateBoard = async (e: React.FormEvent) => {
    e.preventDefault();
    if (creatingBoard) return;
    if (!newBoardName.trim() || !user) return;
    if (aiEnabled && (!resolvedProvider || !resolvedModel)) {
      setAiConfigError(t('aiIncompleteError'));
      return;
    }
    setCreatingBoard(true);
    try {
      await createBoard(
        {
          name: newBoardName,
          description: newBoardDescription,
          category: 'general',
          is_public: false,
          is_template: false,
          ai_enabled: aiEnabled,
          ai_provider: aiEnabled ? resolvedProvider : undefined,
          ai_model: aiEnabled ? resolvedModel : undefined,
          locale: i18n.language,
          is_language_learning: isLanguageLearning,
        },
        user.id
      );
      setNewBoardName('');
      setNewBoardDescription('');
      setAiEnabled(false);
      setIsLanguageLearning(false);
      setAiConfigError(null);
      setIsCreating(false);
    } catch {
      // The store surfaces the failure in the error banner; swallow here so
      // the onSubmit promise does not reject unhandled.
    } finally {
      setCreatingBoard(false);
    }
  };

  const handleDeleteBoard = (id: number) => {
    setDeleteBoardId(id);
  };

  const confirmDeleteBoard = async () => {
    if (deleteBoardId) {
      await deleteBoard(deleteBoardId);
      setDeleteBoardId(null);
    }
  };

  const boardsToShow = useMemo(() => {
    const uniqueBoards = new Map<number, typeof boards[number]>();
    const normalizedSearch = searchQuery.trim().toLocaleLowerCase();
    const visibleAssignedBoards = normalizedSearch
      ? assignedBoards.filter((board) => board.name.toLocaleLowerCase().includes(normalizedSearch))
      : assignedBoards;
    for (const board of [...boards, ...visibleAssignedBoards]) {
      uniqueBoards.set(board.id, board);
    }
    return Array.from(uniqueBoards.values());
  }, [assignedBoards, boards, searchQuery]);

  const toggleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedBoardIds(new Set(boardsToShow.map(b => b.id)));
    } else {
      setSelectedBoardIds(new Set());
    }
  };

  const handleForceRefresh = async () => {
    if (!user) return;
    await fetchBoards(effectiveUserId, searchQuery, true, 1);
  };

  const handleLoadMore = async () => {
    if (!user) return;
    await fetchBoards(effectiveUserId, searchQuery, false, page + 1);
  };

  const confirmBulkDelete = async () => {
    const ids = Array.from(selectedBoardIds);
    if (ids.length === 0) return;

    setBulkDeleting(true);
    setBulkDeleteError(null);
    try {
      const batchSize = 10;
      const failedIds: number[] = [];
      for (let i = 0; i < ids.length; i += batchSize) {
        const batch = ids.slice(i, i + batchSize);
        const results = await Promise.allSettled(batch.map(id => api.delete(`/boards/${id}`)));
        results.forEach((result, index) => {
          if (result.status === 'rejected') failedIds.push(batch[index]);
        });
      }
      await fetchBoards(effectiveUserId, searchQuery, true, 1);
      setSelectedBoardIds(new Set(failedIds));
      if (failedIds.length > 0) {
        setBulkDeleteError(t('bulkDeleteFailed'));
      }
    } finally {
      setBulkDeleting(false);
      setBulkDeleteOpen(false);
    }
  };

  if (isListLoading && boards.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ConfirmDialog
        isOpen={!!deleteBoardId}
        onClose={() => setDeleteBoardId(null)}
        onConfirm={confirmDeleteBoard}
        title={t('deleteBoardTitle')}
        description={t('deleteConfirm')}
        confirmText={t('delete')}
        cancelText={t('cancel')}
        variant="danger"
      />
      <ConfirmDialog
        isOpen={bulkDeleteOpen}
        onClose={() => setBulkDeleteOpen(false)}
        onConfirm={confirmBulkDelete}
        title={t('bulkDeleteTitle')}
        description={t('bulkDeleteConfirm', { count: selectedBoardIds.size })}
        confirmText={t('delete')}
        cancelText={t('cancel')}
        variant="danger"
      />
      <div className="flex flex-col md:flex-row gap-4 justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{t('title')}</h1>
          <p className="text-muted-foreground mt-1">{t('subtitle')}</p>
        </div>
        <div className="flex gap-4 w-full md:w-auto">
          <div className="relative flex-1 md:w-64">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4 " />              <input
                id="boards-search"
                name="boards_search"
                type="text"
                placeholder={t('searchPlaceholder')}
                aria-label={t('searchPlaceholder')}

              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
            />
          </div>
          <Button data-testid="force-refresh" variant="ghost" onClick={handleForceRefresh} disabled={isListLoading}>
            {t('refresh')}
          </Button>
          <Button onClick={() => setIsCreating(true)}>
            <Plus className="w-5 h-5 mr-2" />
            {t('newBoard')}
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <label htmlFor="select-all-boards" className="flex items-center gap-2 text-sm text-foreground">
          <input
            id="select-all-boards"
            name="select_all_boards"
            type="checkbox"
            aria-label={t('selectAll')}
            checked={boardsToShow.length > 0 && selectedBoardIds.size === boardsToShow.length}
            onChange={(e) => toggleSelectAll(e.target.checked)}
            className="rounded border-border"
          />
          {t('selectAll')}
        </label>
        <div className="flex items-center gap-3">
          {selectedBoardIds.size > 0 && (
            <Button variant="destructive" onClick={() => setBulkDeleteOpen(true)} disabled={bulkDeleting}>
              {t('deleteSelected')} ({selectedBoardIds.size})
            </Button>
          )}
          {hasMore && (
            <Button variant="ghost" onClick={handleLoadMore} disabled={isListLoading}>
              {t('loadMore')}
            </Button>
          )}
        </div>
      </div>

      {bulkDeleteError && (
        <StatusMessage variant="error">
          {bulkDeleteError}
        </StatusMessage>
      )}

      {error && (
        <StatusMessage variant="error">
          <h2 className="font-semibold">{tError('title')}</h2>
          <p className="text-sm mt-1">{tError('subtitle')}</p>
          <p className="text-sm mt-2">{error}</p>
          <Button
            type="button"
            variant="default"
            size="sm"
            className="mt-3"
            onClick={() => void handleForceRefresh()}
            disabled={isListLoading}
          >
            {tError('retry')}
          </Button>
        </StatusMessage>
      )}

      {isCreating && (
        <div className="bg-surface p-6 rounded-xl shadow-sm border border-border mb-6">
          <SectionTitle as="h3" className="mb-4">{t('createTitle')}</SectionTitle>
          <form onSubmit={handleCreateBoard} className="space-y-4">
            <div>
              <FormLabel htmlFor="new-board-name">{t('boardName')}</FormLabel>
              <input
                id="new-board-name"
                name="new_board_name"
                type="text"
                value={newBoardName}
                onChange={(e) => setNewBoardName(e.target.value)}
                className="w-full px-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
                placeholder={t('placeholderName')}
                required
              />
            </div>
            <div>
              <FormLabel htmlFor="new-board-description">{t('description')}</FormLabel>
              <input
                id="new-board-description"
                name="new_board_description"
                type="text"
                value={newBoardDescription}
                onChange={(e) => setNewBoardDescription(e.target.value)}
                className="w-full px-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
                placeholder={t('optionalDescription')}
              />
            </div>

            <div className="border-t border-border pt-4">
              <div className="flex items-center mb-3">
                <input
                  type="checkbox"
                  id="isLanguageLearning"
                  checked={isLanguageLearning}
                  onChange={(e) => setIsLanguageLearning(e.target.checked)}
                  className="w-4 h-4 text-brand rounded focus:ring-brand"
                />
                <label htmlFor="isLanguageLearning" className="ml-2 text-sm font-medium text-foreground">
                  {t('languageLearning')}
                </label>
              </div>
              {isLanguageLearning && (
                <p className="text-xs text-muted-foreground mb-3 ml-6">
                  {t('languageLearningDesc')}
                </p>
              )}
              <div className="flex items-center mb-3">
                <input
                  type="checkbox"
                  id="aiEnabledNew"
                  checked={aiEnabled}
                  onChange={(e) => setAiEnabled(e.target.checked)}
                  className="w-4 h-4 text-brand rounded focus:ring-brand"
                />
                <label htmlFor="aiEnabledNew" className="ml-2 text-sm font-medium text-foreground">
                  {t('enableAI')}
                </label>
              </div>
              {aiEnabled && (
                <div className="grid grid-cols-1 gap-3">
                  <label
                    className={`relative block p-3 rounded-lg border transition-colors ${primaryReady ? '' : 'opacity-60'}`}
                  >
                    <div className="font-semibold text-foreground">{t('primaryAI')}</div>
                    <div className="text-sm text-muted-foreground capitalize">
                      {primaryReady ? `${primaryProvider} - ${primaryModel}` : t('notConfigured')}
                    </div>
                  </label>
                  {aiConfigError && (
                    <div className="text-sm text-red-600 dark:text-red-400 md:col-span-2">{aiConfigError}</div>
                  )}
                </div>
              )}
            </div>

            <div className="flex justify-end space-x-3">
              <Button type="button" variant="ghost" onClick={() => setIsCreating(false)}>
                {t('cancel')}
              </Button>
              <Button type="submit" loading={creatingBoard} disabled={!newBoardName.trim() || !!aiConfigError || creatingBoard}>
                {t('create')}
              </Button>
            </div>
          </form>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {boardsToShow.map((board) => (
          <div key={board.id} className="relative bg-surface rounded-xl shadow-sm border border-border hover:shadow-md transition-shadow">
            <div className="p-6">
                <div className="flex justify-between items-start mb-4">
                  <Link to={`/boards/${board.id}`} className="block mr-4">
                    <div className="p-2 bg-brand/10 rounded-lg">
                      <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500 via-blue-500 to-purple-500 flex items-center justify-center shadow-inner">
                        <LayoutGrid className="w-5 h-5 text-white" />
                      </div>
                    </div>
                  </Link>
                  <div className="flex space-x-2">
                    {(user?.user_type === 'admin' || board.user_id === user?.id) && (
                      <button
                        onClick={() => handleDeleteBoard(board.id)}
                        className="p-2 text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                        aria-label={t('delete')}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                    {user && (
                      <button
                        onClick={() => duplicateBoard(board.id, user.id)}
                        className="p-2 text-muted-foreground hover:text-brand hover:bg-brand/20 rounded-lg transition-colors"
                        aria-label={t('duplicateBoard')}
                      >
                        <Copy className="w-4 h-4" />
                      </button>
                    )}
                    {user && (user.user_type === 'admin' || board.user_id === user.id) && (
                      <IconButton
                        label={t('assignToStudent')}
                        title={t('assignToStudentTitle')}
                        onClick={() => openAssign(board.id)}
                        className="p-2 text-muted-foreground hover:text-brand hover:bg-brand/20 rounded-lg transition-colors"
                      >
                        <UserPlus className="w-4 h-4" />
                      </IconButton>
                    )}
                  </div>
                </div>
                <Link to={`/boards/${board.id}`} className="block">
                  <SectionTitle as="h3" className="mb-1">{board.name}</SectionTitle>
                  <p className="text-muted-foreground text-sm mb-4 line-clamp-2">
                    {board.description || t('noDescriptionProvided')}
                  </p>
                </Link>
              <div className="flex items-center justify-between text-sm text-muted-foreground pt-4 border-t border-border">
                <span>{formatDate(board.created_at)}</span>
                <div className="flex items-center gap-3">
                  <Link
                    to={`/play/${board.id}`}
                    className="flex items-center text-green-700 dark:text-green-400 hover:text-green-800 dark:hover:text-green-300 font-medium"
                    title={t('enterSpeakMode')}
                  >
                    <Play className="w-4 h-4 mr-1 fill-current" />
                    {t('speakMode')}
                  </Link>
                  {(user?.user_type === 'admin' || board.user_id === user?.id) && (
                    <Link
                      to={`/boards/${board.id}`}
                      className="flex items-center text-brand hover:text-brand font-medium"
                    >
                      <Edit className="w-4 h-4 mr-1" />
                      {t('editBoard')}
                    </Link>
                  )}
                </div>
              </div>
              {assignOpenId === board.id && (
                <div className="mt-4 p-4 bg-brand/10 border border-brand/20 rounded-lg">
                  <div className="flex items-center space-x-3">
                    <Select
                      value={selectedStudentId == null ? 'none' : String(selectedStudentId)}
                      onValueChange={(value) => setSelectedStudentId(value === 'none' || value == null ? null : parseInt(value, 10))}
                      disabled={studentsLoading}
                      items={[
                        { value: 'none', label: t('selectStudent') },
                        ...students.map((s) => ({ value: String(s.id), label: s.display_name || s.username })),
                      ]}
                    >
                      <SelectTrigger aria-label={t('selectStudent')} className="flex-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">{t('selectStudent')}</SelectItem>
                        {students.map(s => (
                          <SelectItem key={s.id} value={String(s.id)}>{s.display_name || s.username}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button variant="default" size="sm" onClick={() => submitAssign(board.id)} loading={assignLoading} disabled={!selectedStudentId}>
                      {t('assign')}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={closeAssign}>
                      {t('close')}
                    </Button>
                  </div>
                  {assignError && <div className="text-sm text-red-600 dark:text-red-400 mt-2">{assignError}</div>}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
