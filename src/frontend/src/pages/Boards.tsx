import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Trash2, LayoutGrid, Edit, Copy, UserPlus, Search, Play } from 'lucide-react';

import { useBoardStore } from '../store/boardStore';
import { useAuthStore } from '../store/authStore';
import { useSettingsStore } from '../store/settingsStore';
import api from '../lib/api';
import { Button } from '../components/ui/Button';
import type { User } from '../types';
import { useTranslation } from 'react-i18next';
import { formatDate } from '../lib/format';

import { ConfirmDialog } from '../components/ui/ConfirmDialog';

export function Boards() {
  const {
    boards,
    isLoading,
    error,
    fetchBoards,
    createBoard,
    deleteBoard,
    duplicateBoard,
    assignBoardToStudent,
    hasMore,
    page,
  } = useBoardStore();
  const { user } = useAuthStore();
  const { aiSettings, fallbackAISettings, fetchAISettings, fetchFallbackAISettings } = useSettingsStore();
  const { t, i18n } = useTranslation('boards');

  const [isCreating, setIsCreating] = useState(false);
  const [creatingBoard, setCreatingBoard] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [newBoardName, setNewBoardName] = useState('');
  const [newBoardDescription, setNewBoardDescription] = useState('');
  const [aiEnabled, setAiEnabled] = useState(false);
  const [isLanguageLearning, setIsLanguageLearning] = useState(false);
  const [aiSource, setAiSource] = useState<'primary' | 'fallback'>('primary');
  const [aiConfigError, setAiConfigError] = useState<string | null>(null);

  const [assignOpenId, setAssignOpenId] = useState<number | null>(null);
  const [students, setStudents] = useState<User[]>([]);
  const [studentsLoading, setStudentsLoading] = useState(false);
  const [assignLoading, setAssignLoading] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [selectedStudentId, setSelectedStudentId] = useState<number | null>(null);

  const [deleteBoardId, setDeleteBoardId] = useState<number | null>(null);
  const [selectedBoardIds, setSelectedBoardIds] = useState<Set<number>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);

  // Fetch boards for current user
  const didInitialFetchRef = useRef(false);
  useEffect(() => {
    if (!user) return;

    // Initial load: fetch immediately so e2e tests that wait on the spinner are stable.
    if (!didInitialFetchRef.current) {
      didInitialFetchRef.current = true;
      if (user.user_type === 'student') {
        fetchBoards(user.id, searchQuery);
      } else if (user.user_type === 'admin') {
        fetchBoards(undefined, searchQuery);
      } else {
        fetchBoards(user.id, searchQuery);
      }
      return;
    }

    const timer = setTimeout(() => {
      if (user.user_type === 'student') {
        fetchBoards(user.id, searchQuery);
      } else if (user.user_type === 'admin') {
        fetchBoards(undefined, searchQuery);
      } else {
        fetchBoards(user.id, searchQuery);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [fetchBoards, user, searchQuery]);

  const effectiveUserId = user?.user_type === 'admin' ? undefined : user?.id;

  // Preload AI settings
  useEffect(() => {
    if (!aiSettings) fetchAISettings().catch(() => {});
    if (!fallbackAISettings) fetchFallbackAISettings().catch(() => {});
  }, [aiSettings, fallbackAISettings, fetchAISettings, fetchFallbackAISettings]);

  const primaryProvider = aiSettings?.provider;
  const primaryModel = primaryProvider === 'openrouter' ? aiSettings?.openrouter_model : aiSettings?.ollama_model;
  const fallbackProvider = fallbackAISettings?.provider;
  const fallbackModel = fallbackProvider === 'openrouter' ? fallbackAISettings?.openrouter_model : fallbackAISettings?.ollama_model;
  const primaryReady = Boolean(primaryProvider && primaryModel);
  const fallbackReady = Boolean(fallbackProvider && fallbackModel);
  const selectedSettings = aiSource === 'fallback' ? fallbackAISettings : aiSettings;
  const resolvedProvider = selectedSettings?.provider;
  const resolvedModel = resolvedProvider === 'openrouter' ? selectedSettings?.openrouter_model : selectedSettings?.ollama_model;

  // AI config validation
  useEffect(() => {
    if (!aiEnabled) {
      setAiConfigError(null);
      return;
    }
    if (!primaryReady) {
      setAiConfigError('AI settings are missing a configured provider/model. Update them in Settings first.');
      return;
    }
    if (aiSource === 'fallback' && !fallbackReady) {
      setAiConfigError('Fallback AI is not configured. Switch back to primary or configure fallback in Settings.');
      return;
    }
    setAiConfigError(null);
  }, [aiEnabled, aiSource, primaryReady, fallbackReady]);

  const openAssign = async (boardId: number) => {
    setAssignOpenId(boardId);
    setAssignError(null);
    setSelectedStudentId(null);
    if (!students.length) {
      setStudentsLoading(true);
      try {
        const res = await (await import('../lib/api')).default.get('/auth/users');
        setStudents((res.data as User[]).filter(u => u.user_type === 'student'));
      } catch {
        setAssignError(t('loadStudentsError'));
      } finally {
        setStudentsLoading(false);
      }
    }
  };

  const submitAssign = async (boardId: number) => {
    if (!selectedStudentId) return;
    setAssignLoading(true);
    setAssignError(null);
    try {
      await assignBoardToStudent(boardId, selectedStudentId, user?.id);
      setAssignOpenId(null);
    } catch {
      setAssignError(t('assignBoardError'));
    } finally {
      setAssignLoading(false);
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
      setAiSource('primary');
      setAiConfigError(null);
      setIsCreating(false);
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

  const boardsToShow = useMemo(() => (boards.length > 0 ? boards : useBoardStore.getState().assignedBoards), [boards]);

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
    try {
      const batchSize = 10;
      for (let i = 0; i < ids.length; i += batchSize) {
        const batch = ids.slice(i, i + batchSize);
        await Promise.allSettled(batch.map(id => api.delete(`/boards/${id}`)));
      }
      await fetchBoards(effectiveUserId, searchQuery, true, 1);
      setSelectedBoardIds(new Set());
    } finally {
      setBulkDeleting(false);
      setBulkDeleteOpen(false);
    }
  };

  if (isLoading && boards.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ConfirmDialog
        isOpen={!!deleteBoardId}
        onClose={() => setDeleteBoardId(null)}
        onConfirm={confirmDeleteBoard}
        title={t('deleteConfirm')} // Using title as "Are you sure...?" for now, or could be "Delete Board"
        description={t('deleteConfirm')}
        confirmText={t('delete') || 'Delete'}
        cancelText={t('cancel')}
        variant="danger"
      />
      <ConfirmDialog
        isOpen={bulkDeleteOpen}
        onClose={() => setBulkDeleteOpen(false)}
        onConfirm={confirmBulkDelete}
        title={t('deleteConfirm')}
        description={t('deleteConfirm')}
        confirmText={t('delete') || 'Delete'}
        cancelText={t('cancel')}
        variant="danger"
      />
      <div className="flex flex-col md:flex-row gap-4 justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('title')}</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">{t('subtitle')}</p>
        </div>
        <div className="flex gap-4 w-full md:w-auto">
          <div className="relative flex-1 md:w-64">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
            <input
              id="boards-search"
              name="boards_search"
              type="text"
              placeholder={t('searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
          </div>
          <Button data-testid="force-refresh" variant="ghost" onClick={handleForceRefresh} disabled={isLoading}>
            {t('refresh')}
          </Button>
          <Button onClick={() => setIsCreating(true)}>
            <Plus className="w-5 h-5 mr-2" />
            {t('newBoard')}
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <label htmlFor="select-all-boards" className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input
            id="select-all-boards"
            name="select_all_boards"
            type="checkbox"
            aria-label={t('selectAll')}
            checked={boardsToShow.length > 0 && selectedBoardIds.size === boardsToShow.length}
            onChange={(e) => toggleSelectAll(e.target.checked)}
            className="rounded border-gray-300 dark:border-gray-600"
          />
          {t('selectAll')}
        </label>
        <div className="flex items-center gap-3">
          {selectedBoardIds.size > 0 && (
            <Button variant="danger" onClick={() => setBulkDeleteOpen(true)} disabled={bulkDeleting}>
              {t('deleteSelected')} ({selectedBoardIds.size})
            </Button>
          )}
          {hasMore && (
            <Button variant="ghost" onClick={handleLoadMore} disabled={isLoading}>
              {t('loadMore')}
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-4 rounded-lg">
          {error}
        </div>
      )}

      {isCreating && (
        <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 mb-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('createTitle')}</h3>
          <form onSubmit={handleCreateBoard} className="space-y-4">
            <div>
              <label htmlFor="new-board-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('boardName')}</label>
              <input
                id="new-board-name"
                name="new_board_name"
                type="text"
                value={newBoardName}
                onChange={(e) => setNewBoardName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                placeholder="e.g., Daily Activities"
                required
              />
            </div>
            <div>
              <label htmlFor="new-board-description" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('description')}</label>
              <input
                id="new-board-description"
                name="new_board_description"
                type="text"
                value={newBoardDescription}
                onChange={(e) => setNewBoardDescription(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                placeholder={t('optionalDescription')}
              />
            </div>

            <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
              <div className="flex items-center mb-3">
                <input
                  type="checkbox"
                  id="isLanguageLearning"
                  checked={isLanguageLearning}
                  onChange={(e) => setIsLanguageLearning(e.target.checked)}
                  className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                />
                <label htmlFor="isLanguageLearning" className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('languageLearning', 'Language Learning Board')}
                </label>
              </div>
              {isLanguageLearning && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3 ml-6">
                  {t('languageLearningDesc', 'Symbols will always be displayed in their original language.')}
                </p>
              )}
              <div className="flex items-center mb-3">
                <input
                  type="checkbox"
                  id="aiEnabledNew"
                  checked={aiEnabled}
                  onChange={(e) => setAiEnabled(e.target.checked)}
                  className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                />
                <label htmlFor="aiEnabledNew" className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('enableAI')}
                </label>
              </div>
              {aiEnabled && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label
                    className={`relative block p-3 rounded-lg border transition-colors cursor-pointer ${aiSource === 'primary' ? 'border-indigo-500 ring-2 ring-indigo-200 dark:ring-indigo-400/40' : 'border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-500/60'} ${primaryReady ? '' : 'opacity-60 cursor-not-allowed'}`}
                  >
                    <input
                      type="radio"
                      className="sr-only"
                      checked={aiSource === 'primary'}
                      onChange={() => setAiSource('primary')}
                      disabled={!primaryReady}
                    />
                    <div className="font-semibold text-gray-900 dark:text-gray-100">{t('primaryAI')}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400 capitalize">
                      {primaryReady ? `${primaryProvider} - ${primaryModel}` : t('notConfigured')}
                    </div>
                  </label>
                  <label
                    className={`relative block p-3 rounded-lg border transition-colors cursor-pointer ${aiSource === 'fallback' ? 'border-indigo-500 ring-2 ring-indigo-200 dark:ring-indigo-400/40' : 'border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-500/60'} ${fallbackReady ? '' : 'opacity-60 cursor-not-allowed'}`}
                  >
                    <input
                      type="radio"
                      className="sr-only"
                      checked={aiSource === 'fallback'}
                      onChange={() => setAiSource('fallback')}
                      disabled={!fallbackReady}
                    />
                    <div className="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                      {t('fallbackAI')}
                      {!fallbackReady && <span className="text-xs text-amber-600">({t('notConfigured')})</span>}
                    </div>
                    <div className="text-sm text-gray-600 dark:text-gray-400 capitalize">
                      {fallbackReady ? `${fallbackProvider} - ${fallbackModel}` : t('setupFallback')}
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
          <div key={board.id} className="relative bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 hover:shadow-md transition-shadow">
            <div className="p-6">
                <div className="flex justify-between items-start mb-4">
                  <Link to={`/boards/${board.id}`} className="block mr-4">
                    <div className="p-2 bg-indigo-50 dark:bg-indigo-900/30 rounded-lg">
                      <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500 via-blue-500 to-purple-500 flex items-center justify-center shadow-inner">
                        <LayoutGrid className="w-5 h-5 text-white" />
                      </div>
                    </div>
                  </Link>
                  <div className="flex space-x-2">
                    <button
                      onClick={() => handleDeleteBoard(board.id)}
                      className="p-2 text-gray-400 dark:text-gray-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                      aria-label="Delete board"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                    {user && (
                      <button
                        onClick={() => duplicateBoard(board.id, user.id)}
                        className="p-2 text-gray-400 dark:text-gray-500 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded-lg transition-colors"
                        aria-label="Duplicate board"
                      >
                        <Copy className="w-4 h-4" />
                      </button>
                    )}
                    {user && (user.user_type === 'teacher' || user.user_type === 'admin') && (
                      <button
                        onClick={() => openAssign(board.id)}
                        className="p-2 text-gray-400 dark:text-gray-500 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded-lg transition-colors"
                        title="Assign to Student"
                        aria-label="Assign to student"
                      >
                        <UserPlus className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
                <Link to={`/boards/${board.id}`} className="block">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">{board.name}</h3>
                  <p className="text-gray-500 dark:text-gray-400 text-sm mb-4 line-clamp-2">
                    {board.description || t('noDescriptionProvided')}
                  </p>
                </Link>
              <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400 pt-4 border-t border-gray-100 dark:border-gray-700">
                <span>{formatDate(board.created_at)}</span>
                <div className="flex items-center gap-3">
                  <Link
                    to={`/play/${board.id}`}
                    className="flex items-center text-green-600 dark:text-green-400 hover:text-green-700 dark:hover:text-green-300 font-medium"
                    title={t('enterSpeakMode')}
                  >
                    <Play className="w-4 h-4 mr-1 fill-current" />
                    {t('speakMode')}
                  </Link>
                  <Link
                    to={`/boards/${board.id}`}
                    className="flex items-center text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 font-medium"
                  >
                    <Edit className="w-4 h-4 mr-1" />
                    {t('editBoard')}
                  </Link>
                </div>
              </div>
              {assignOpenId === board.id && (
                <div className="mt-4 p-4 bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-100 dark:border-indigo-800 rounded-lg">
                  <div className="flex items-center space-x-3">
                    <select
                      value={selectedStudentId ?? ''}
                      onChange={(e) => setSelectedStudentId(parseInt(e.target.value))}
                      className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                      disabled={studentsLoading}
                    >
                      <option value="">{t('selectStudent')}</option>
                      {students.map(s => (
                        <option key={s.id} value={s.id}>{s.display_name || s.username}</option>
                      ))}
                    </select>
                    <Button variant="primary" size="sm" onClick={() => submitAssign(board.id)} loading={assignLoading} disabled={!selectedStudentId}>
                      {t('assign')}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setAssignOpenId(null)}>
                      {t('close')}
                    </Button>
                  </div>
                  {assignError && <div className="text-sm text-red-600 mt-2">{assignError}</div>}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
