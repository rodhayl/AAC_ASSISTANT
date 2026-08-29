import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, Check, Copy, Edit2, Eye, Plus, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import api, { extractError } from '../../lib/api';
import { useAutoHide } from '../../hooks/useAutoHide';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { IconButton } from '../../components/ui/icon-button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog';
import type { LearningMode } from './types';
import { Button } from '../../components/ui/button';

interface PreviewStudent {
  id: number;
  username: string;
  display_name: string;
  has_profile: boolean;
}

interface ModeForm {
  name: string;
  key: string;
  description: string;
  prompt_instruction: string;
  auto_ask_enabled: boolean;
}

// Single source of truth for the "blank" mode form used on first render,
// when canceling an edit, and when starting to create a new mode.
const EMPTY_MODE_FORM: ModeForm = {
  name: '',
  key: '',
  description: '',
  prompt_instruction: '',
  auto_ask_enabled: true,
};

export function LearningModesTab() {
  const user = useAuthStore(state => state.user);
  const { t } = useTranslation('settings');
  const [learningModes, setLearningModes] = useState<LearningMode[]>([]);
  const [editingModeId, setEditingModeId] = useState<number | null>(null);
  const [modeForm, setModeForm] = useState<ModeForm>({ ...EMPTY_MODE_FORM });
  const [modeError, setModeError] = useState<string | null>(null);
  const [modeSuccess, setModeSuccess] = useState<string | null>(null);
  const [pendingDeleteMode, setPendingDeleteMode] = useState<LearningMode | null>(null);
  const [deletingMode, setDeletingMode] = useState(false);

  // System prompt preview state
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewPrompt, setPreviewPrompt] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewStudents, setPreviewStudents] = useState<PreviewStudent[]>([]);
  const [previewStudentId, setPreviewStudentId] = useState<number | ''>('');
  const [previewMeta, setPreviewMeta] = useState<{
    template_name: string;
    has_guardian_profile: boolean;
  } | null>(null);
  const [copied, setCopied] = useState(false);
  // The saved mode being previewed from its list row (null = preview the
  // unsaved form's instruction).
  const [previewMode, setPreviewMode] = useState<LearningMode | null>(null);
  // 'Preview with sample question': render the full LLM request (system +
  // user message) for a realistic student question instead of just the prompt.
  const [sampleEnabled, setSampleEnabled] = useState(false);
  const [sampleQuestion, setSampleQuestion] = useState('');
  const [previewUserMessage, setPreviewUserMessage] = useState<string | null>(null);
  const [previewParams, setPreviewParams] = useState<{
    temperature: number | null;
    max_tokens: number | null;
  } | null>(null);
  // Monotonic counter so stale preview responses (from an earlier student
  // selection) are ignored when a newer request has already started.
  const previewRequestIdRef = useRef(0);

  const fetchLearningModes = useCallback(() => {
    api
      .get('/learning-modes/')
      .then((res) => setLearningModes(res.data))
      .catch((err) => console.error('Failed to fetch modes', err));
  }, []);

  useEffect(() => {
    if (user?.user_type === 'admin' || user?.user_type === 'teacher') {
      fetchLearningModes();
    }
  }, [fetchLearningModes, user]);

  useAutoHide(copied, () => setCopied(false), 2000);
  useAutoHide(modeSuccess, () => setModeSuccess(null));

  const runPreview = useCallback(
    async (studentId?: number | null, source?: LearningMode | null) => {
      const resolvedId =
        studentId === undefined
          ? previewStudentId === ''
            ? null
            : previewStudentId
          : studentId;
      // `source` is passed explicitly when opening the preview so the request
      // is not affected by the (still pending) previewMode state update.
      const mode = source !== undefined ? source : previewMode;
      const requestId = ++previewRequestIdRef.current;
      setPreviewLoading(true);
      setPreviewError(null);
      setPreviewPrompt(null);
      setPreviewMeta(null);
      try {
        // A saved-mode preview sends its key and saved instruction; otherwise
        // the unsaved form text is used (no mode_key).
        const useSample =
          sampleEnabled && sampleQuestion.trim().length > 0;
        const res = await api.post('/learning-modes/preview', {
          mode_key: mode ? mode.key : undefined,
          prompt_instruction: mode
            ? mode.prompt_instruction
            : modeForm.prompt_instruction,
          student_id: resolvedId,
          sample_question: useSample ? sampleQuestion.trim() : undefined,
        });
        // Ignore a stale response if a newer preview started meanwhile.
        if (requestId !== previewRequestIdRef.current) return;
        setPreviewPrompt(res.data.prompt);
        setPreviewUserMessage(res.data.user_message ?? null);
        setPreviewParams(
          res.data.temperature !== undefined || res.data.max_tokens !== undefined
            ? {
                temperature: res.data.temperature ?? null,
                max_tokens: res.data.max_tokens ?? null,
              }
            : null,
        );
        setPreviewMeta({
          template_name: res.data.template_name,
          has_guardian_profile: res.data.has_guardian_profile,
        });
      } catch (err) {
        if (requestId !== previewRequestIdRef.current) return;
        setPreviewError(extractError(err, t('learningModes.previewFailed')));
      } finally {
        if (requestId === previewRequestIdRef.current) setPreviewLoading(false);
      }
    },
    [
      modeForm.prompt_instruction,
      previewMode,
      previewStudentId,
      sampleEnabled,
      sampleQuestion,
      t,
    ],
  );

  const openPreview = async (sourceMode?: LearningMode | null) => {
    // No sourceMode = preview the unsaved form's instruction; a sourceMode
    // previews that saved mode directly from its row (no edit mode needed).
    setPreviewMode(sourceMode ?? null);
    setPreviewOpen(true);
    setPreviewPrompt(null);
    setPreviewError(null);
    setCopied(false);
    if (previewStudents.length === 0) {
      try {
        const res = await api.get('/guardian-profiles/students');
        setPreviewStudents(res.data || []);
      } catch {
        setPreviewStudents([]);
      }
    }
    await runPreview(undefined, sourceMode ?? null);
  };

  const closePreview = useCallback(() => {
    // Invalidate any in-flight preview request so its response cannot
    // repopulate state after the modal is closed.
    previewRequestIdRef.current += 1;
    setPreviewOpen(false);
    setPreviewPrompt(null);
    setPreviewError(null);
    setPreviewMeta(null);
    setPreviewUserMessage(null);
    setPreviewParams(null);
  }, []);

  const copyPrompt = async () => {
    if (!previewPrompt) return;
    try {
      await navigator.clipboard.writeText(previewPrompt);
      setCopied(true);
    } catch {
      /* clipboard may be unavailable (e.g. insecure context) */
    }
  };

  const handleEditMode = (mode: LearningMode) => {
    setEditingModeId(mode.id);
    setModeForm({
      name: mode.name,
      key: mode.key,
      description: mode.description || '',
      prompt_instruction: mode.prompt_instruction,
      auto_ask_enabled: mode.auto_ask_enabled ?? true,
    });
    setModeError(null);
    setModeSuccess(null);
  };

  const handleCancelModeEdit = () => {
    setEditingModeId(null);
    setModeForm({ ...EMPTY_MODE_FORM });
  };

  const handleSaveMode = async () => {
    // Client-side validation keeps required fields from reaching the backend
    // (which would otherwise surface raw English Pydantic 422 messages).
    if (!modeForm.name.trim()) {
      setModeError(t('learningModes.nameRequired'));
      return;
    }
    if (editingModeId === -1 && !modeForm.key.trim()) {
      setModeError(t('learningModes.keyRequired'));
      return;
    }
    if (!modeForm.prompt_instruction.trim()) {
      setModeError(t('learningModes.promptRequired'));
      return;
    }
    setModeError(null);
    try {
      if (editingModeId && editingModeId !== -1) {
        await api.put(`/learning-modes/${editingModeId}`, {
          name: modeForm.name,
          description: modeForm.description,
          prompt_instruction: modeForm.prompt_instruction,
          auto_ask_enabled: modeForm.auto_ask_enabled,
        });
        setModeSuccess(t('learningModes.updated'));
      } else {
        await api.post('/learning-modes/', modeForm);
        setModeSuccess(t('learningModes.created'));
      }
      fetchLearningModes();
      handleCancelModeEdit();
    } catch (err: unknown) {
      setModeError(extractError(err, t('learningModes.saveFailed')));
    }
  };

  const handleDeleteMode = (id: number) => {
    const mode = learningModes.find((candidate) => candidate.id === id);
    if (mode) setPendingDeleteMode(mode);
  };

  const confirmDeleteMode = async () => {
    if (!pendingDeleteMode) return;
    setDeletingMode(true);
    try {
      await api.delete(`/learning-modes/${pendingDeleteMode.id}`);
      setPendingDeleteMode(null);
      fetchLearningModes();
      setModeSuccess(t('learningModes.deleted'));
    } catch (err: unknown) {
      setModeError(extractError(err, t('learningModes.deleteFailed')));
      setPendingDeleteMode(null);
    } finally {
      setDeletingMode(false);
    }
  };

  return (
    <section
      id="settings-learning-modes"
      aria-labelledby="settings-learning-modes-heading"
      className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div className="p-6 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h3
              id="settings-learning-modes-heading"
              className="text-lg font-semibold text-gray-900 dark:text-gray-100"
            >
              {t('tabs.learningModes')}
            </h3>
            <p className="text-sm text-gray-500 mt-1 dark:text-gray-400">{t('learningModes.subtitle')}</p>
          </div>
          {modeSuccess && (
            <div className="flex items-center text-green-600 text-sm font-medium">
              <Check className="w-4 h-4 mr-1" /> {modeSuccess}
            </div>
          )}
        </div>
      </div>

      <div className="p-6">
        {modeError && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center mb-4">
            <AlertCircle className="w-5 h-5 mr-2" />
            {modeError}
          </div>
        )}

        {!editingModeId ? (
          <div>
            <div className="space-y-2 mb-4">
              {learningModes.map((mode) => (
                <div key={mode.id} className="p-4 border border-gray-200 rounded-lg flex justify-between items-center">
                  <div>
                    <div className="font-semibold">{mode.name}</div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">{mode.description}</div>
                    <div className="flex gap-2 mt-1.5">
                      {!mode.is_custom && (
                        <span className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded">{t('learningModes.systemDefault')}</span>
                      )}
                      <span
                        className={`text-xs px-2 py-0.5 rounded ${
                          mode.auto_ask_enabled !== false
                            ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400'
                            : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200'
                        }`}
                        title={mode.auto_ask_enabled !== false ? t('learningModes.autoAskTitle') : t('learningModes.manualAskTitle')}
                      >
                        {t('learningModes.autoAskLabel')}: {mode.auto_ask_enabled !== false ? t('learningModes.on') : t('learningModes.off')}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <IconButton
                      label={`${t('learningModes.preview')} ${mode.name}`}
                      title={t('learningModes.previewSystemPrompt')}
                      type="button"
                      onClick={() => { void openPreview(mode); }}
                      className="p-2 text-indigo-600 hover:bg-indigo-50 rounded"
                    >
                      <Eye className="w-4 h-4" />
                    </IconButton>
                    <button
                      onClick={() => handleEditMode(mode)}
                      aria-label={`${t('learningModes.edit')} ${mode.name}`}
                      className="p-2 text-indigo-600 hover:bg-indigo-50 rounded"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    {mode.is_custom && (
                      <button
                        type="button"
                        onClick={() => handleDeleteMode(mode.id)}
                        aria-label={`${t('learningModes.delete')} ${mode.name}`}
                        title={t('learningModes.deleteModeTitle')}
                        className="p-2 text-red-600 hover:bg-red-50 rounded"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <button
              onClick={() => {
                setEditingModeId(-1);
                setModeForm({ ...EMPTY_MODE_FORM });
              }}
              className="w-full py-2 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 hover:border-indigo-500 hover:text-indigo-500 flex items-center justify-center dark:text-gray-400"
            >
              <Plus className="w-4 h-4 mr-2" /> {t('learningModes.addNew')}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <h4 className="font-medium text-gray-900 dark:text-gray-100">
              {editingModeId === -1 ? t('learningModes.createNew') : t('learningModes.editMode')}
            </h4>
            <div>
              <label htmlFor="learning-mode-name" className="block text-sm font-medium text-gray-700 mb-1 dark:text-gray-300">{t('learningModes.name')}</label>
              <input
                id="learning-mode-name"
                value={modeForm.name}
                onChange={(event) => setModeForm({ ...modeForm, name: event.target.value })}
                className="w-full p-2 border rounded-lg"
                placeholder={t('learningModes.namePlaceholder')}
              />
            </div>
            <div>
              <label htmlFor="learning-mode-key" className="block text-sm font-medium text-gray-700 mb-1 dark:text-gray-300">{t('learningModes.key')}</label>
              <input
                id="learning-mode-key"
                value={modeForm.key}
                onChange={(event) => setModeForm({ ...modeForm, key: event.target.value })}
                className="w-full p-2 border rounded-lg"
                placeholder={t('learningModes.keyPlaceholder')}
                disabled={editingModeId !== -1}
              />
              <p className="text-xs text-gray-500 mt-1 dark:text-gray-400">{t('learningModes.keyHelp')}</p>
            </div>
            <div>
              <label htmlFor="learning-mode-description" className="block text-sm font-medium text-gray-700 mb-1 dark:text-gray-300">{t('learningModes.description')}</label>
              <input
                id="learning-mode-description"
                value={modeForm.description}
                onChange={(event) => setModeForm({ ...modeForm, description: event.target.value })}
                className="w-full p-2 border rounded-lg"
                placeholder={t('learningModes.descriptionPlaceholder')}
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <label htmlFor="mode-prompt-instruction" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('learningModes.promptInstruction')}
                </label>
                <button
                  type="button"
                  onClick={() => { void openPreview(); }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition-colors"
                >
                  <Eye className="w-3.5 h-3.5" />
                  {t('learningModes.previewSystemPrompt')}
                </button>
              </div>
              <textarea
                id="mode-prompt-instruction"
                value={modeForm.prompt_instruction}
                onChange={(event) => setModeForm({ ...modeForm, prompt_instruction: event.target.value })}
                className="w-full p-2 border rounded-lg h-32 font-mono text-sm"
                placeholder={t('learningModes.promptPlaceholder')}
              />
              <p className="text-xs text-gray-500 mt-1 dark:text-gray-400">
                {t('learningModes.promptHelp')}
              </p>
            </div>
            <label className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer pt-1">
              <input
                type="checkbox"
                checked={modeForm.auto_ask_enabled}
                onChange={(event) =>
                  setModeForm({ ...modeForm, auto_ask_enabled: event.target.checked })
                }
                className="mt-0.5 w-4 h-4 accent-indigo-600"
              />
              <span className="leading-tight">
                <span className="font-medium">{t('learningModes.autoAsk')}</span>
                <span className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  {t('learningModes.autoAskHelp')}
                </span>
              </span>
            </label>
            <div className="flex justify-end gap-3">
              <button
                onClick={handleCancelModeEdit}
                className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
              >
                {t('learningModes.cancel')}
              </button>
              <Button onClick={handleSaveMode}  >
                {t('learningModes.saveMode')}
              </Button>
            </div>
          </div>
        )}
      </div>

      {previewOpen && (
        <Dialog open onOpenChange={(open) => { if (!open) closePreview(); }}>
          <DialogContent
            showCloseButton={false}
            className="max-w-3xl max-h-[85vh] flex flex-col p-0"
          >
            <div className="flex items-start justify-between p-5 border-b border-gray-200 dark:border-gray-700">
              <div>
                <DialogHeader>
                  <DialogTitle className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                    {t('learningModes.previewSystemPrompt')}
                  </DialogTitle>
                </DialogHeader>
                <p className="text-sm text-gray-500 mt-1 dark:text-gray-400">
                  {previewMode
                    ? t('learningModes.previewingSaved', { name: previewMode.name })
                    : t('learningModes.previewingForm')}
                </p>
              </div>
              <button
                type="button"
                onClick={closePreview}
                aria-label={t('learningModes.closePreview')}
                className="p-2 text-gray-500 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 border-b border-gray-200 dark:border-gray-700 space-y-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex-1 min-w-48">
                  <label htmlFor="preview-student" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    {t('learningModes.student')}
                  </label>
                  <select
                    id="preview-student"
                    value={previewStudentId}
                    onChange={(event) => {
                      const value = event.target.value === '' ? '' : Number(event.target.value);
                      setPreviewStudentId(value);
                      void runPreview(value === '' ? null : value);
                    }}
                    className="w-full p-2 border rounded-lg text-sm"
                  >
                    <option value="">{t('learningModes.noStudent')}</option>
                    {previewStudents.map((student) => (
                      <option key={student.id} value={student.id}>
                        {student.display_name}{student.has_profile ? ` • ${t('learningModes.guardianProfile')}` : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => { void runPreview(); }}
                  loading={previewLoading}
                >
                  {previewLoading ? t('learningModes.loading') : t('learningModes.preview')}
                </Button>
                <button
                  type="button"
                  onClick={copyPrompt}
                  disabled={!previewPrompt}
                  className="inline-flex items-center gap-1.5 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60"
                >
                  <Copy className="w-4 h-4" />
                  {copied ? t('learningModes.copied') : t('learningModes.copy')}
                </button>
              </div>

              <label className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer pt-1">
                <input
                  type="checkbox"
                  checked={sampleEnabled}
                  onChange={(event) => {
                    setSampleEnabled(event.target.checked);
                    if (!event.target.checked) {
                      // Invalidate any in-flight sample request so its response
                      // cannot repopulate the (now hidden) user message.
                      previewRequestIdRef.current += 1;
                      setPreviewUserMessage(null);
                      setPreviewParams(null);
                    }
                  }}
                  className="mt-0.5 w-4 h-4 accent-indigo-600"
                />
                <span className="leading-tight">
                  <span className="font-medium">{t('learningModes.previewWithSample')}</span>
                  <span className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {t('learningModes.sampleHelp')}
                  </span>
                </span>
              </label>
              {sampleEnabled && (
                <div className="flex items-end gap-2">
                  <div className="flex-1">
                    <label htmlFor="preview-sample-question" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      {t('learningModes.sampleQuestion')}
                    </label>
                    <input
                      id="preview-sample-question"
                      value={sampleQuestion}
                      onChange={(event) => setSampleQuestion(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && sampleQuestion.trim()) {
                          void runPreview();
                        }
                      }}
                      placeholder={t('learningModes.samplePlaceholder')}
                      className="w-full p-2 border rounded-lg text-sm"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => { void runPreview(); }}
                    disabled={previewLoading || !sampleQuestion.trim()}
                    className="px-3 py-2 border border-indigo-200 text-indigo-600 rounded-lg text-sm font-medium hover:bg-indigo-50 disabled:opacity-50"
                  >
                    {t('learningModes.run')}
                  </button>
                </div>
              )}
            </div>

            <div className="flex-1 overflow-auto p-5">
              {previewMeta && (
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  {t('learningModes.template')} <span className="font-medium">{previewMeta.template_name}</span> ·{' '}
                  {previewMeta.has_guardian_profile
                    ? t('learningModes.guardianIncluded')
                    : t('learningModes.noGuardian')}
                </div>
              )}
              {previewError && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center mb-3">
                  <AlertCircle className="w-5 h-5 mr-2" />
                  {previewError}
                </div>
              )}
              {previewLoading ? (
                <div className="text-sm text-gray-500 dark:text-gray-400">{t('learningModes.buildingPrompt')}</div>
              ) : previewPrompt ? (
                <div className="space-y-3">
                  {previewUserMessage && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        {t('learningModes.fullRequest')}
                      </span>
                      {previewParams && (
                        <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                          {t('learningModes.temperature')} {previewParams.temperature ?? '—'} · {t('learningModes.maxTokens')} {previewParams.max_tokens ?? '—'}
                        </span>
                      )}
                    </div>
                  )}
                  <div>
                    <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                      {t('learningModes.systemPrompt')}
                    </div>
                    <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-900 rounded-lg p-4">
                      {previewPrompt}
                    </pre>
                  </div>
                  {previewUserMessage && (
                    <div>
                      <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                        {t('learningModes.userMessage')} <span className="font-normal">{t('learningModes.userMessageHelp')}</span>
                      </div>
                      <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-900 rounded-lg p-4 border border-indigo-100 dark:border-indigo-900">
                        {previewUserMessage}
                      </pre>
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </DialogContent>
        </Dialog>
      )}

      <ConfirmDialog
        isOpen={pendingDeleteMode != null}
        onClose={() => setPendingDeleteMode(null)}
        onConfirm={confirmDeleteMode}
        title={t('learningModes.deleteModeTitle')}
        description={t('learningModes.confirmDelete')}
        confirmText={t('learningModes.delete')}
        cancelText={t('learningModes.cancel')}
        variant="danger"
        isLoading={deletingMode}
      />
    </section>
  );
}
