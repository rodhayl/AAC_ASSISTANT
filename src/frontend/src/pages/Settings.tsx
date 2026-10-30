import { useState, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useSettingsStore } from '../store/settingsStore';
import { useTTSStore } from '../store/ttsStore';
import { useThemeStore } from '../store/themeStore';
import { useLocaleStore } from '../store/localeStore';
import api from '../lib/api';
import { config } from '../config';
import { User, Bell, Volume2, Moon, Shield, Cpu, Cloud, Download, Upload, RefreshCw, ChevronDown, ChevronUp, Check, AlertCircle, Edit2, Save, Circle, Globe, Clock, MousePointer, Eye, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useToastStore } from '../store/toastStore';

interface Preferences {
  tts_voice: string;
  ui_language: string;
  notifications_enabled: boolean;
  voice_mode_enabled: boolean;
  dark_mode: boolean;
  dwell_time: number;
  ignore_repeats: number;
  high_contrast: boolean;
}

export function Settings() {
  const { user } = useAuthStore();
  const { t } = useTranslation('settings');
  const { addToast } = useToastStore();
  const [preferences, setPreferences] = useState<Preferences>({
    tts_voice: user?.settings?.tts_voice || 'default',
    ui_language: user?.settings?.ui_language || 'es-ES',
    notifications_enabled: user?.settings?.notifications_enabled ?? true,
    voice_mode_enabled: user?.settings?.voice_mode_enabled ?? true,
    dark_mode: user?.settings?.dark_mode ?? false,
    dwell_time: user?.settings?.dwell_time ?? 0,
    ignore_repeats: user?.settings?.ignore_repeats ?? 0,
    high_contrast: user?.settings?.high_contrast ?? false,
  });
  const [prefsLoading, setPrefsLoading] = useState(false);
  const [prefsSaveSuccess, setPrefsSaveSuccess] = useState(false);
  const [prefsSaveError, setPrefsSaveError] = useState<string | null>(null);

  // Profile editing state
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileForm, setProfileForm] = useState({ display_name: '', email: '' });
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Password change state
  const [changeOpen, setChangeOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeLoading, setChangeLoading] = useState(false);

  // AI Settings state
  const {
    aiSettings,
    fallbackAISettings,
    ollamaModels,
    openRouterModels,
    lmStudioModels,
    loading,
    error,
    fetchAISettings,
    updateAISettings,
    fetchFallbackAISettings,
    updateFallbackAISettings,
    fetchOllamaModels,
    fetchOpenRouterModels,
    fetchLmStudioModels,
  } = useSettingsStore();

  const [aiOverride, setAiOverride] = useState<{
    provider?: 'ollama' | 'openrouter' | 'lmstudio';
    ollama_model?: string;
    openrouter_model?: string;
    lmstudio_model?: string;
    openrouter_api_key?: string;
    ollama_base_url?: string;
    lmstudio_base_url?: string;
    max_tokens?: number;
    temperature?: number;
  }>({});
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [modelSearchOpen, setModelSearchOpen] = useState(false);
  const [modelSearchQuery, setModelSearchQuery] = useState('');

  // Fallback settings state
  const [showFallback, setShowFallback] = useState(true);
  const [fallbackOverride, setFallbackOverride] = useState<{
    provider?: 'ollama' | 'openrouter' | 'lmstudio';
    ollama_model?: string;
    openrouter_model?: string;
    lmstudio_model?: string;
    openrouter_api_key?: string;
    ollama_base_url?: string;
    lmstudio_base_url?: string;
    max_tokens?: number;
    temperature?: number;
  }>({});
  const [fallbackModelSearchOpen, setFallbackModelSearchOpen] = useState(false);
  const [fallbackModelSearchQuery, setFallbackModelSearchQuery] = useState('');

  const [health, setHealth] = useState<{ ollama?: boolean; openrouter?: boolean; lmstudio?: { available: boolean } } | null>(null);

  // Learning Modes state
  type LearningMode = {
    id: number;
    name: string;
    key: string;
    description: string;
    prompt_instruction: string;
    is_custom: boolean;
    created_by: number | null;
  };
  const [learningModes, setLearningModes] = useState<LearningMode[]>([]);
  const [editingModeId, setEditingModeId] = useState<number | null>(null);
  const [modeForm, setModeForm] = useState({ name: '', key: '', description: '', prompt_instruction: '' });
  const [modeError, setModeError] = useState<string | null>(null);
  const [modeSuccess, setModeSuccess] = useState<string | null>(null);

  const fetchLearningModes = () => {
    api.get('/learning-modes/')
      .then(res => setLearningModes(res.data))
      .catch(err => console.error("Failed to fetch modes", err));
  };

  useEffect(() => {
    if (user?.user_type === 'admin' || user?.user_type === 'teacher') {
      fetchLearningModes();
    }
  }, [user]);

  const handleEditMode = (mode: LearningMode) => {
    setEditingModeId(mode.id);
    setModeForm({
      name: mode.name,
      key: mode.key,
      description: mode.description || '',
      prompt_instruction: mode.prompt_instruction
    });
    setModeError(null);
    setModeSuccess(null);
  };

  const handleCancelModeEdit = () => {
    setEditingModeId(null);
    setModeForm({ name: '', key: '', description: '', prompt_instruction: '' });
  };

  const handleSaveMode = async () => {
    try {
      if (editingModeId && editingModeId !== -1) {
        // Update
        await api.put(`/learning-modes/${editingModeId}`, {
          name: modeForm.name,
          description: modeForm.description,
          prompt_instruction: modeForm.prompt_instruction
        });
        setModeSuccess('Mode updated successfully');
      } else {
        // Create
        await api.post('/learning-modes/', modeForm);
        setModeSuccess('Mode created successfully');
      }
      fetchLearningModes();
      handleCancelModeEdit();
      setTimeout(() => setModeSuccess(null), 3000);
    } catch (err: unknown) {
      setModeError(extractErrorMessage(err, 'Failed to save mode'));
    }
  };

  const handleDeleteMode = async (id: number) => {
    if (!confirm('Are you sure you want to delete this learning mode?')) return;
    try {
      await api.delete(`/learning-modes/${id}`);
      fetchLearningModes();
      setModeSuccess('Mode deleted');
      setTimeout(() => setModeSuccess(null), 3000);
    } catch (err: unknown) {
      setModeError(extractErrorMessage(err, 'Failed to delete mode'));
    }
  };
  const [voiceStatus, setVoiceStatus] = useState<{
    ffmpeg?: { installed: boolean; path?: string | null };
    whisper?: { installed: boolean };
    sounddevice?: { installed: boolean; optional?: boolean };
    soundfile?: { installed: boolean; optional?: boolean };
    webrtcvad?: { installed: boolean; optional?: boolean };
  } | null>(null);

  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);

  useEffect(() => {
    const loadVoices = () => {
      const voices = window.speechSynthesis.getVoices();
      setAvailableVoices(voices);
    };

    loadVoices();
    if (window.speechSynthesis.onvoiceschanged !== undefined) {
      window.speechSynthesis.onvoiceschanged = loadVoices;
    }
  }, []);

  const filteredVoices = availableVoices.filter(v => {
    if (preferences.ui_language.startsWith('es')) {
      return v.lang.startsWith('es');
    }
    return v.lang.startsWith('en');
  });

  const isAdmin = user?.user_type === 'admin';
  const isTeacher = user?.user_type === 'teacher';

  // Load preferences from backend and sync with stores
  useEffect(() => {
    const loadPreferences = async () => {
      try {
        const res = await api.get('/auth/preferences');
        const voice = res.data.tts_voice || 'default';
        const darkMode = res.data.dark_mode ?? false;
        const language = res.data.ui_language || 'es-ES';

        setPreferences({
          tts_voice: voice,
          ui_language: language,
          notifications_enabled: res.data.notifications_enabled ?? true,
          voice_mode_enabled: res.data.voice_mode_enabled ?? true,
          dark_mode: darkMode,
          dwell_time: res.data.dwell_time ?? 0,
          ignore_repeats: res.data.ignore_repeats ?? 0,
          high_contrast: res.data.high_contrast ?? false,
        });
        // Sync with ttsStore for browser TTS
        useTTSStore.getState().setSelectedVoice(voice);
        // Sync with themeStore for dark mode
        useThemeStore.getState().setDarkMode(darkMode);
        // Sync with localeStore
        useLocaleStore.getState().setLocale(language);
      } catch (err) {
        console.error('Failed to load preferences:', err);
      }
    };
    loadPreferences();
  }, []);

  // Load AI settings (for all users to view, admin to edit)
  useEffect(() => {
    fetchAISettings();
    fetchFallbackAISettings();
  }, [fetchAISettings, fetchFallbackAISettings]);

  // Voice dependency status
  useEffect(() => {
    const fetchVoiceStatus = async () => {
      try {
        const res = await api.get('/providers/voice-status');
        setVoiceStatus(res.data);
      } catch (err) {
        console.error('Failed to fetch voice dependency status', err);
      }
    };
    fetchVoiceStatus();
  }, []);

  // Initialize profile form when user changes or when editing starts
  useEffect(() => {
    if (user) {
      setProfileForm({
        display_name: user.display_name || '',
        email: user.email || '',
      });
    }
  }, [user, editingProfile]);

  // Computed values for AI settings
  const currentAiProvider = aiOverride.provider ?? aiSettings?.provider ?? 'ollama';
  const currentOllamaModel = aiOverride.ollama_model ?? aiSettings?.ollama_model ?? '';
  const currentOpenRouterModel = aiOverride.openrouter_model ?? aiSettings?.openrouter_model ?? '';
  const currentLmStudioModel = aiOverride.lmstudio_model ?? aiSettings?.lmstudio_model ?? '';
  const currentSelectedModel = currentAiProvider === 'ollama' ? currentOllamaModel : currentOpenRouterModel;
  const currentOpenRouterApiKey = aiOverride.openrouter_api_key ?? aiSettings?.openrouter_api_key ?? '';
  const currentOllamaBaseUrl = aiOverride.ollama_base_url ?? aiSettings?.ollama_base_url ?? config.OLLAMA_BASE_URL;
  const currentLmStudioBaseUrl = aiOverride.lmstudio_base_url ?? aiSettings?.lmstudio_base_url ?? 'http://localhost:1234/v1';
  const currentMaxTokens = aiOverride.max_tokens ?? aiSettings?.max_tokens ?? 1024;
  const currentTemperature = aiOverride.temperature ?? aiSettings?.temperature ?? 0.5;

  const currentFallbackProvider = fallbackOverride.provider ?? fallbackAISettings?.provider ?? 'ollama';
  const currentFallbackOllamaModel = fallbackOverride.ollama_model ?? fallbackAISettings?.ollama_model ?? '';
  const currentFallbackOpenRouterModel = fallbackOverride.openrouter_model ?? fallbackAISettings?.openrouter_model ?? '';
  const currentFallbackLmStudioModel = fallbackOverride.lmstudio_model ?? fallbackAISettings?.lmstudio_model ?? '';
  const currentFallbackModel = currentFallbackProvider === 'ollama' ? currentFallbackOllamaModel : currentFallbackOpenRouterModel;
  const currentFallbackOpenRouterApiKey = fallbackOverride.openrouter_api_key ?? fallbackAISettings?.openrouter_api_key ?? '';
  const currentFallbackOllamaBaseUrl = fallbackOverride.ollama_base_url ?? fallbackAISettings?.ollama_base_url ?? config.OLLAMA_BASE_URL;
  const currentFallbackLmStudioBaseUrl = fallbackOverride.lmstudio_base_url ?? fallbackAISettings?.lmstudio_base_url ?? 'http://localhost:1234/v1';
  const currentFallbackMaxTokens = fallbackOverride.max_tokens ?? fallbackAISettings?.max_tokens ?? 1024;
  const currentFallbackTemperature = fallbackOverride.temperature ?? fallbackAISettings?.temperature ?? 0.5;

  // Auto-fetch models when provider changes (admin only)
  useEffect(() => {
    if (!isAdmin) return;
    const provider = currentAiProvider;
    if (provider === 'ollama' && ollamaModels.length === 0) {
      fetchOllamaModels(false);
    } else if (provider === 'openrouter' && openRouterModels.length === 0) {
      fetchOpenRouterModels(false);
    } else if (provider === 'lmstudio' && lmStudioModels.length === 0) {
      fetchLmStudioModels(false);
    }
  }, [isAdmin, currentAiProvider, ollamaModels.length, openRouterModels.length, lmStudioModels.length, fetchOllamaModels, fetchOpenRouterModels, fetchLmStudioModels]);

  useEffect(() => {
    if (!isAdmin) return;
    const provider = currentFallbackProvider;
    if (provider === 'ollama' && ollamaModels.length === 0) {
      fetchOllamaModels(true);
    } else if (provider === 'openrouter' && openRouterModels.length === 0) {
      fetchOpenRouterModels(true);
    } else if (provider === 'lmstudio' && lmStudioModels.length === 0) {
      fetchLmStudioModels(true);
    }
  }, [isAdmin, currentFallbackProvider, ollamaModels.length, openRouterModels.length, lmStudioModels.length, fetchOllamaModels, fetchOpenRouterModels, fetchLmStudioModels]);

  const extractErrorMessage = (err: unknown, defaultMsg: string): string => {
    const errWithResponse = err as { response?: { data?: { detail?: unknown } } };
    const detail = errWithResponse?.response?.data?.detail;

    if (typeof detail === 'string') {
      return detail;
    }

    if (Array.isArray(detail)) {
      // Handle Pydantic validation errors (array of objects)
      return detail
        .map((e: unknown) => {
          if (e && typeof e === 'object' && 'msg' in e && typeof (e as { msg?: unknown }).msg === 'string') {
            return (e as { msg: string }).msg;
          }
          return JSON.stringify(e);
        })
        .join(', ');
    }

    if (typeof detail === 'object' && detail !== null) {
      return JSON.stringify(detail);
    }

    return defaultMsg;
  };

  const handleSavePreferences = async () => {
    setPrefsLoading(true);
    setPrefsSaveSuccess(false);
    setPrefsSaveError(null);
    try {
      if (user) {
        // Update user preferences in DB via the correct endpoint for current user
        const res = await api.put('/auth/preferences', preferences);

        // Update local store state immediately
        const { setDarkMode } = useThemeStore.getState();
        const { setLocale } = useLocaleStore.getState();
        const { setSelectedVoice } = useTTSStore.getState();

        setDarkMode(preferences.dark_mode);
        setLocale(preferences.ui_language);
        setSelectedVoice(preferences.tts_voice);

        // Sync Auth Store to ensure persistence
        useAuthStore.setState((state) => {
          if (!state.user) return state;
          return {
            user: {
              ...state.user,
              settings: {
                ...(state.user.settings || {}),
                ...res.data
              }
            }
          };
        });

        setPrefsSaveSuccess(true);
        addToast(t('preferences.saved'), 'success');
      }
    } catch (e: unknown) {
      console.error('Failed to save preferences:', e);
      setPrefsSaveError(t('errors.saveFailed'));
      addToast(t('errors.saveFailed'), 'error');
    } finally {
      setPrefsLoading(false);
    }
  };

  const handleSaveProfile = async () => {
    setProfileSaving(true);
    setProfileError(null);
    try {
      const res = await api.put('/auth/profile', profileForm);
      // Update auth store with new user data, preserving existing data (like settings) if missing in response
      useAuthStore.setState((state) => {
        const newUser = { ...res.data };
        // Ensure settings is not null (use existing or undefined)
        if (newUser.settings === null || newUser.settings === undefined) {
          newUser.settings = state.user?.settings;
        }
        // Ensure user_type is preserved if missing (unlikely but safe)
        if (!newUser.user_type && state.user?.user_type) {
          newUser.user_type = state.user.user_type;
        }
        return { user: state.user ? { ...state.user, ...newUser } : newUser };
      });
      setProfileSuccess(true);
      setEditingProfile(false);
      setTimeout(() => setProfileSuccess(false), 3000);
    } catch (err: unknown) {
      setProfileError(extractErrorMessage(err, 'Failed to save profile'));
    } finally {
      setProfileSaving(false);
    }
  };

  const handleFetchModels = async () => {
    try {
      if (currentAiProvider === 'ollama') {
        await fetchOllamaModels(false);
      } else if (currentAiProvider === 'openrouter') {
        await fetchOpenRouterModels(false);
      } else {
        await fetchLmStudioModels(false);
      }
    } catch (error) {
      console.error('Failed to fetch models:', error);
    }
  };

  const handleFetchFallbackModels = async () => {
    try {
      if (currentFallbackProvider === 'ollama') {
        await fetchOllamaModels(true);
      } else if (currentFallbackProvider === 'openrouter') {
        await fetchOpenRouterModels(true);
      } else {
        await fetchLmStudioModels(true);
      }
    } catch (error) {
      console.error('Failed to fetch fallback models:', error);
    }
  };

  const voiceStatusItems = [
    {
      key: 'ffmpeg',
      label: t('ai.dependencies.ffmpeg.label'),
      help: t('ai.dependencies.ffmpeg.help'),
      link: 'https://ffmpeg.org/download.html',
      status: voiceStatus?.ffmpeg?.installed,
      extra: voiceStatus?.ffmpeg?.path,
    },
    {
      key: 'whisper',
      label: t('ai.dependencies.whisper.label'),
      help: t('ai.dependencies.whisper.help'),
      link: 'https://github.com/openai/whisper',
      status: voiceStatus?.whisper?.installed,
    },
    {
      key: 'sounddevice',
      label: t('ai.dependencies.sounddevice.label'),
      help: t('ai.dependencies.sounddevice.help'),
      link: 'https://python-sounddevice.readthedocs.io/',
      status: voiceStatus?.sounddevice?.installed,
    },
    {
      key: 'soundfile',
      label: t('ai.dependencies.soundfile.label'),
      help: t('ai.dependencies.soundfile.help'),
      link: 'https://pysoundfile.readthedocs.io/',
      status: voiceStatus?.soundfile?.installed,
    },
    {
      key: 'webrtcvad',
      label: t('ai.dependencies.webrtcvad.label'),
      help: t('ai.dependencies.webrtcvad.help'),
      link: 'https://visualstudio.microsoft.com/visual-cpp-build-tools/',
      status: voiceStatus?.webrtcvad?.installed,
      optional: true,
    },
  ];

  const handleSaveAllSettings = async () => {
    try {
      await updateAISettings({
        provider: currentAiProvider,
        ollama_model: currentOllamaModel,
        openrouter_model: currentOpenRouterModel,
        lmstudio_model: currentLmStudioModel,
        openrouter_api_key: currentOpenRouterApiKey,
        ollama_base_url: currentOllamaBaseUrl,
        lmstudio_base_url: currentLmStudioBaseUrl,
        max_tokens: currentMaxTokens,
        temperature: currentTemperature,
      });
      await updateFallbackAISettings({
        provider: currentFallbackProvider,
        ollama_model: currentFallbackOllamaModel,
        openrouter_model: currentFallbackOpenRouterModel,
        lmstudio_model: currentFallbackLmStudioModel,
        openrouter_api_key: currentFallbackOpenRouterApiKey,
        ollama_base_url: currentFallbackOllamaBaseUrl,
        lmstudio_base_url: currentFallbackLmStudioBaseUrl,
        max_tokens: currentFallbackMaxTokens,
        temperature: currentFallbackTemperature,
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (error) {
      console.error('Failed to save settings:', error);
    }
  };

  const checkHealth = async () => {
    try {
      const res = await api.get('/providers/health');
      setHealth(res.data);
    } catch { /* health check optional */ }
  };

  const handleExportData = async () => {
    if (!user) return;
    try {
      const boardsRes = await api.get('/boards/', { params: { user_id: user.id } });
      const achievementsRes = await api.get(`/achievements/user/${user.id}`);
      const pointsRes = await api.get(`/achievements/user/${user.id}/points`);
      const historyRes = await api.get(`/learning/history/${user.id}`, { params: { limit: 100 } });
      const assignedRes = user.user_type === 'student' ? await api.get('/boards/assigned', { params: { student_id: user.id } }) : { data: [] };
      const base = {
        meta: { exported_at: new Date().toISOString(), username: user.username },
        boards: boardsRes.data,
        assignedBoards: assignedRes.data,
        achievements: achievementsRes.data,
        totalPoints: pointsRes.data,
        learningHistory: historyRes.data,
      };
      const encoder = new TextEncoder();
      const raw = JSON.stringify(base);
      const digest = await crypto.subtle.digest('SHA-256', encoder.encode(raw));
      const hex = Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
      const data = { ...base, meta: { ...base.meta, checksum_sha256: hex, schema_version: '1' } };
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `aac-data-${user.username}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to export data:', error);
    }
  };

  const handleImportData = async (file: File) => {
    if (!user) return;
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      if (!json.meta || typeof json.meta !== 'object') throw new Error('Invalid export: missing meta');
      if (!Array.isArray(json.boards)) throw new Error('Invalid export: boards must be array');
      if (!Array.isArray(json.assignedBoards)) throw new Error('Invalid export: assignedBoards must be array');
      if (!Array.isArray(json.achievements)) throw new Error('Invalid export: achievements must be array');
      const baseForChecksum = {
        meta: { exported_at: json.meta.exported_at, username: json.meta.username },
        boards: json.boards,
        assignedBoards: json.assignedBoards,
        achievements: json.achievements,
        totalPoints: json.totalPoints,
        learningHistory: json.learningHistory,
      };
      const encoder = new TextEncoder();
      const digest = await crypto.subtle.digest('SHA-256', encoder.encode(JSON.stringify(baseForChecksum)));
      const hex = Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, '0')).join('');
      const expected = json.meta.checksum_sha256;
      if (!expected || typeof expected !== 'string' || expected !== hex) {
        throw new Error('Checksum mismatch: file may be tampered');
      }
      const boards = json.boards;
      for (const b of boards) {
        const createRes = await api.post('/boards/', {
          name: b.name,
          description: b.description,
          category: b.category,
          is_public: b.is_public,
          is_template: b.is_template,
          grid_rows: b.grid_rows ?? 4,
          grid_cols: b.grid_cols ?? 5,
        }, { params: { user_id: user.id } });
        const newBoard = createRes.data;
        for (const s of b.symbols || []) {
          await api.post(`/boards/${newBoard.id}/symbols`, {
            symbol_id: s.symbol?.id ?? s.symbol_id,
            position_x: s.position_x,
            position_y: s.position_y,
            size: s.size,
            is_visible: s.is_visible,
            custom_text: s.custom_text
          });
        }
      }
      if (user.user_type === 'student' && Array.isArray(json.assignedBoards)) {
        for (const ab of json.assignedBoards) {
          try {
            await api.post(`/boards/${ab.id}/assign`, { student_id: user.id });
          } catch { /* assignment optional */ }
        }
      }
      addToast(t('data.importSuccess'), 'success');
    } catch (error) {
      console.error('Failed to import data:', error);
      const errorMessage = error instanceof Error ? error.message : t('errors.unknownError', 'Unknown error');
      addToast(t('data.importFailed') + errorMessage, 'error');
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{t('title')}</h1>
        <p className="text-gray-500">{t('subtitle')}</p>
      </div>

      {/* Profile Section */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="h-16 w-16 bg-indigo-100 rounded-full flex items-center justify-center">
                <User className="h-8 w-8 text-indigo-600" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">{user?.display_name}</h2>
                <p className="text-gray-500 capitalize">{user?.user_type}</p>
              </div>
            </div>
            {!editingProfile ? (
              <button
                onClick={() => setEditingProfile(true)}
                className="flex items-center text-indigo-600 hover:text-indigo-700"
              >
                <Edit2 className="w-4 h-4 mr-1" />
                {t('profile.edit')}
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setEditingProfile(false)}
                  className="px-3 py-1 text-gray-600 hover:bg-gray-100 rounded"
                >
                  {t('profile.cancel')}
                </button>
                <button
                  onClick={handleSaveProfile}
                  disabled={profileSaving}
                  className="flex items-center px-3 py-1 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
                >
                  <Save className="w-4 h-4 mr-1" />
                  {profileSaving ? t('security.saving') : t('profile.save')}
                </button>
              </div>
            )}
          </div>
          {profileSuccess && (
            <div className="mt-3 flex items-center text-green-600 text-sm">
              <Check className="w-4 h-4 mr-1" /> {t('profile.updated')}
            </div>
          )}
          {profileError && (
            <div className="mt-3 flex items-center text-red-600 text-sm">
              <AlertCircle className="w-4 h-4 mr-1" /> {profileError}
            </div>
          )}
        </div>
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label htmlFor="profile-username" className="block text-sm font-medium text-gray-700 mb-1">{t('profile.username')}</label>
            <input
              id="profile-username"
              name="username"
              type="text"
              value={user?.username || ''}
              disabled
              autoComplete="username"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500"
            />
          </div>
          <div className="md:col-span-2">
            <label htmlFor="profile-display-name" className="block text-sm font-medium text-gray-700 mb-1">{t('profile.displayName')}</label>
            <input
              id="profile-display-name"
              name="display_name"
              type="text"
              value={editingProfile ? profileForm.display_name : (user?.display_name || '')}
              onChange={(e) => setProfileForm(prev => ({ ...prev, display_name: e.target.value }))}
              disabled={!editingProfile}
              autoComplete="name"
              className={`w-full px-3 py-2 border border-gray-300 rounded-lg ${!editingProfile ? 'bg-gray-50 text-gray-500' : 'bg-white'}`}
            />
          </div>
          <div className="md:col-span-2">
            <label htmlFor="profile-email" className="block text-sm font-medium text-gray-700 mb-1">{t('profile.email')}</label>
            <input
              id="profile-email"
              name="email"
              type="email"
              value={editingProfile ? profileForm.email : (user?.email || '')}
              onChange={(e) => setProfileForm(prev => ({ ...prev, email: e.target.value }))}
              disabled={!editingProfile}
              autoComplete="email"
              placeholder={editingProfile ? t('profile.emailPlaceholder') : t('profile.noEmail')}
              className={`w-full px-3 py-2 border border-gray-300 rounded-lg ${!editingProfile ? 'bg-gray-50 text-gray-500' : 'bg-white'}`}
            />
          </div>
        </div>
      </div>

      {/* Preferences */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('preferences.title')}</h3>
          <div className="flex items-center gap-3">
            {prefsSaveSuccess && (
              <span className="flex items-center text-green-600 text-sm">
                <Check className="w-4 h-4 mr-1" /> {t('preferences.saved')}
              </span>
            )}
            {prefsSaveError && (
              <span className="flex items-center text-red-600 text-sm">
                <AlertCircle className="w-4 h-4 mr-1" /> {prefsSaveError}
              </span>
            )}
            <button
              onClick={handleSavePreferences}
              disabled={prefsLoading}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium"
            >
              {prefsLoading ? t('security.saving') : t('preferences.savePrefs')}
            </button>
          </div>
        </div>
        <div className="divide-y divide-gray-200">
          <div className="p-6 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-indigo-50 rounded-lg">
                <Globe className="w-5 h-5 text-indigo-600" />
              </div>
              <div>
                <p className="font-medium text-gray-900">{t('preferences.language')}</p>
                <p className="text-sm text-gray-500">{t('preferences.languageHelp')}</p>
              </div>
            </div>
            <select
              id="pref-ui-language"
              name="ui_language"
              aria-label={t('preferences.language')}
              value={preferences.ui_language}
              onChange={(e) => setPreferences(prev => ({ ...prev, ui_language: e.target.value }))}
              className="block w-48 pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
            >
              <option value="es-ES">{t('languages.es-ES')}</option>
              <option value="en-US">{t('languages.en-US')}</option>
            </select>
          </div>

          <div className="p-6 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-blue-50 rounded-lg">
                <Volume2 className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="font-medium text-gray-900">{t('preferences.tts')}</p>
                <p className="text-sm text-gray-500">{t('preferences.ttsHelp')}</p>
              </div>
            </div>
            <select
              id="pref-tts-voice"
              name="tts_voice"
              aria-label={t('preferences.tts')}
              value={preferences.tts_voice}
              onChange={(e) => setPreferences(prev => ({ ...prev, tts_voice: e.target.value }))}
              className="block w-48 pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
            >
              <option value="default">{t('preferences.voices.default')}</option>
              {filteredVoices.length > 0 && <option disabled>──────────</option>}
              {filteredVoices.map(v => (
                <option key={v.voiceURI} value={v.voiceURI}>
                  {v.name} ({v.lang})
                </option>
              ))}
            </select>
          </div>

          <div className="p-6 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-purple-50 rounded-lg">
                <Volume2 className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <p className="font-medium text-gray-900">{t('preferences.voiceMode')}</p>
                <p className="text-sm text-gray-500">{t('preferences.voiceModeHelp')}</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                id="pref-voice-mode-enabled"
                name="voice_mode_enabled"
                type="checkbox"
                className="sr-only peer"
                checked={preferences.voice_mode_enabled}
                onChange={(e) => setPreferences(prev => ({ ...prev, voice_mode_enabled: e.target.checked }))}
                aria-label={t('preferences.voiceMode')}
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
            </label>
          </div>

          <div className="p-6 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-purple-50 rounded-lg">
                <Bell className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <p className="font-medium text-gray-900">{t('preferences.notifications')}</p>
                <p className="text-sm text-gray-500">{t('preferences.notificationsHelp')}</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                id="pref-notifications-enabled"
                name="notifications_enabled"
                type="checkbox"
                className="sr-only peer"
                checked={preferences.notifications_enabled}
                onChange={(e) => setPreferences(prev => ({ ...prev, notifications_enabled: e.target.checked }))}
                aria-label={t('preferences.notifications')}
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
            </label>
          </div>

          <div className="p-6 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-gray-100 rounded-lg">
                <Moon className="w-5 h-5 text-gray-600" />
              </div>
              <div>
                <p className="font-medium text-gray-900">{t('preferences.dark')}</p>
                <p className="text-sm text-gray-500">{t('preferences.darkHelp')}</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                id="pref-dark-mode"
                name="dark_mode"
                type="checkbox"
                className="sr-only peer"
                checked={preferences.dark_mode}
                onChange={(e) => setPreferences(prev => ({ ...prev, dark_mode: e.target.checked }))}
                aria-label={t('preferences.dark')}
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
            </label>
          </div>

          {/* Accessibility Settings */}
          <div className="p-6 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-green-50 rounded-lg">
                <Clock className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="font-medium text-gray-900">{t('preferences.dwellTime')}</p>
                <p className="text-sm text-gray-500">{t('preferences.dwellTimeHelp')}</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <input
                id="pref-dwell-time"
                name="dwell_time"
                type="range"
                min="0"
                max="2000"
                step="100"
                value={preferences.dwell_time}
                onChange={(e) => setPreferences(prev => ({ ...prev, dwell_time: parseInt(e.target.value) }))}
                className="w-32"
                aria-label={t('preferences.dwellTime')}
              />
              <span className="text-sm text-gray-600 w-16 text-right">{preferences.dwell_time}ms</span>
            </div>
          </div>

          <div className="p-6 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-orange-50 rounded-lg">
                <MousePointer className="w-5 h-5 text-orange-600" />
              </div>
              <div>
                <p className="font-medium text-gray-900">{t('preferences.ignoreRepeats')}</p>
                <p className="text-sm text-gray-500">{t('preferences.ignoreRepeatsHelp')}</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <input
                id="pref-ignore-repeats"
                name="ignore_repeats"
                type="range"
                min="0"
                max="2000"
                step="100"
                value={preferences.ignore_repeats}
                onChange={(e) => setPreferences(prev => ({ ...prev, ignore_repeats: parseInt(e.target.value) }))}
                className="w-32"
                aria-label={t('preferences.ignoreRepeats')}
              />
              <span className="text-sm text-gray-600 w-16 text-right">{preferences.ignore_repeats}ms</span>
            </div>
          </div>

          <div className="p-6 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-yellow-50 rounded-lg">
                <Eye className="w-5 h-5 text-yellow-600" />
              </div>
              <div>
                <p className="font-medium text-gray-900">{t('preferences.highContrast')}</p>
                <p className="text-sm text-gray-500">{t('preferences.highContrastHelp')}</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                id="pref-high-contrast"
                name="high_contrast"
                type="checkbox"
                className="sr-only peer"
                checked={preferences.high_contrast}
                onChange={(e) => setPreferences(prev => ({ ...prev, high_contrast: e.target.checked }))}
                aria-label={t('preferences.highContrast')}
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
            </label>
          </div>
        </div>
      </div>

      {/* Security */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('security.title')}</h3>
        </div>
        <div className="p-6">
          <button onClick={() => { setChangeOpen(true); setChangeError(null); }} className="flex items-center text-indigo-600 hover:text-indigo-700 font-medium">
            <Shield className="w-5 h-5 mr-2" />
            {t('security.change')}
          </button>
        </div>
      </div>

      {changeOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 dark:bg-opacity-70 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('security.change')}</h3>
            {changeError && <div className="mb-3 text-sm text-red-600">{changeError}</div>}
            <div className="space-y-3">
              <input id="current-password" name="current_password" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} placeholder={t('security.current')} className="w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label={t('security.current')} autoComplete="current-password" />
              <input id="new-password" name="new_password" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder={t('security.new')} className="w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label={t('security.new')} autoComplete="new-password" />
              <input id="confirm-password" name="confirm_password" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder={t('security.confirm')} className="w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label={t('security.confirm')} autoComplete="new-password" />
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setChangeOpen(false)} className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg">{t('profile.cancel')}</button>
              <button
                onClick={async () => {
                  if (!user) return;
                  setChangeLoading(true);
                  setChangeError(null);
                  try {
                    await api.post('/auth/change-password', { username: user.username, current_password: currentPassword, new_password: newPassword, confirm_password: confirmPassword });
                    setChangeOpen(false);
                    setCurrentPassword('');
                    setNewPassword('');
                    setConfirmPassword('');
                  } catch (e: unknown) {
                    setChangeError(extractErrorMessage(e, 'Failed to change password'));
                  } finally {
                    setChangeLoading(false);
                  }
                }}
                disabled={changeLoading || !currentPassword || !newPassword || !confirmPassword}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                {changeLoading ? t('security.saving') : t('security.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Data Management - Available to all users */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('data.title')}</h3>
          <p className="text-sm text-gray-500 mt-1">{t('data.subtitle')}</p>
        </div>
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <button
              onClick={handleExportData}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 flex items-center justify-center"
              title={t('data.exportClientTitle')}
            >
              <Download className="w-4 h-4 mr-2" />
              {t('data.exportClient')}
            </button>
            {(isAdmin || isTeacher) && (
              <button
                onClick={async () => {
                  if (!user) return;
                  try {
                    const response = await api.get('/data/export', { params: { username: user.username } });
                    const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `aac-data-${user.username}-server.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch (error) {
                    console.error('Server export failed:', error);
                    addToast(t('data.exportServerFailed'), 'error');
                  }
                }}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center justify-center"
                title={t('data.exportServerTitle')}
              >
                <Download className="w-4 h-4 mr-2" />
                {t('data.exportServer')}
              </button>
            )}
          </div>
          {(isAdmin || isTeacher) && (
            <div>
              <label className="flex items-center justify-center px-4 py-2 bg-gray-100 text-gray-700 rounded-lg cursor-pointer hover:bg-gray-200 w-full">
                <Upload className="w-4 h-4 mr-2" />
                {t('data.importBoards')}
                <input
                  id="import-boards-file"
                  name="import_boards_file"
                  type="file"
                  accept="application/json"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleImportData(f);
                  }}
                />
              </label>
            </div>
          )}
        </div>
      </div>

      {/* Learning Modes Configuration (Admin/Teacher Only) */}
      {(isAdmin || isTeacher) && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden mt-6">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Learning Modes</h3>
                <p className="text-sm text-gray-500 mt-1">Configure smart learning modes and prompts</p>
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
                  {learningModes.map(mode => (
                    <div key={mode.id} className="p-4 border border-gray-200 rounded-lg flex justify-between items-center">
                      <div>
                        <div className="font-semibold">{mode.name}</div>
                        <div className="text-sm text-gray-500">{mode.description}</div>
                        {!mode.is_custom && <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">System Default</span>}
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleEditMode(mode)}
                          className="p-2 text-indigo-600 hover:bg-indigo-50 rounded"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        {mode.is_custom && (
                          <button
                            onClick={() => handleDeleteMode(mode.id)}
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
                    setEditingModeId(-1); // -1 for new
                    setModeForm({ name: '', key: '', description: '', prompt_instruction: '' });
                  }}
                  className="w-full py-2 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 hover:border-indigo-500 hover:text-indigo-500 flex items-center justify-center"
                >
                  <Plus className="w-4 h-4 mr-2" /> Add New Learning Mode
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <h4 className="font-medium text-gray-900">{editingModeId === -1 ? 'Create New Mode' : 'Edit Mode'}</h4>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                  <input
                    value={modeForm.name}
                    onChange={e => setModeForm({ ...modeForm, name: e.target.value })}
                    className="w-full p-2 border rounded-lg"
                    placeholder="e.g. Daily Conversation"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Key (Internal ID)</label>
                  <input
                    value={modeForm.key}
                    onChange={e => setModeForm({ ...modeForm, key: e.target.value })}
                    className="w-full p-2 border rounded-lg"
                    placeholder="e.g. daily_conversation"
                    disabled={editingModeId !== -1} // Key cannot be changed after creation
                  />
                  <p className="text-xs text-gray-500 mt-1">Unique identifier for this mode.</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                  <input
                    value={modeForm.description}
                    onChange={e => setModeForm({ ...modeForm, description: e.target.value })}
                    className="w-full p-2 border rounded-lg"
                    placeholder="Brief description for the user"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">System Prompt Instruction</label>
                  <textarea
                    value={modeForm.prompt_instruction}
                    onChange={e => setModeForm({ ...modeForm, prompt_instruction: e.target.value })}
                    className="w-full p-2 border rounded-lg h-32 font-mono text-sm"
                    placeholder="Instructions for the AI on how to behave in this mode..."
                  />
                  <p className="text-xs text-gray-500 mt-1">This text is appended to the AI system prompt. It is not visible to the student.</p>
                </div>

                <div className="flex justify-end gap-3">
                  <button
                    onClick={handleCancelModeEdit}
                    className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleSaveMode}
                    className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
                  >
                    Save Mode
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* AI Provider Configuration (Admin Only) */}
      {isAdmin && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('ai.title')}</h3>
                <p className="text-sm text-gray-500 mt-1">{t('ai.subtitle')}</p>
              </div>
              {saveSuccess && (
                <div className="flex items-center text-green-600 text-sm font-medium">
                  <Check className="w-4 h-4 mr-1" /> {t('ai.saveOk')}
                </div>
              )}
            </div>
          </div>

          <div className="p-6 space-y-6">
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center">
                <AlertCircle className="w-5 h-5 mr-2" />
                {error}
              </div>
            )}

            {/* Provider Selection */}
            <div>
              <p className="block text-sm font-medium text-gray-700 mb-3">{t('ai.primary')}</p>
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => setAiOverride(prev => ({ ...prev, provider: 'ollama' }))}
                  className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${currentAiProvider === 'ollama'
                    ? 'border-indigo-600 bg-indigo-50'
                    : 'border-gray-200 hover:border-gray-300'
                    }`}
                >
                  <Cpu className="w-6 h-6 text-indigo-600" />
                  <div className="text-left">
                    <div className="font-medium text-gray-900">{t('ai.ollama')}</div>
                    <div className="text-xs text-gray-500">{t('ai.ollamaDesc')}</div>
                  </div>
                </button>
                <button
                  onClick={() => setAiOverride(prev => ({ ...prev, provider: 'openrouter' }))}
                  className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${currentAiProvider === 'openrouter'
                    ? 'border-indigo-600 bg-indigo-50'
                    : 'border-gray-200 hover:border-gray-300'
                    }`}
                >
                  <Cloud className="w-6 h-6 text-indigo-600" />
                  <div className="text-left">
                    <div className="font-medium text-gray-900">{t('ai.openrouter')}</div>
                    <div className="text-xs text-gray-500">{t('ai.openrouterDesc')}</div>
                  </div>
                </button>

                <button
                  onClick={() => setAiOverride(prev => ({ ...prev, provider: 'lmstudio' }))}
                  className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${currentAiProvider === 'lmstudio'
                    ? 'border-indigo-600 bg-indigo-50'
                    : 'border-gray-200 hover:border-gray-300'
                    }`}
                >
                  <Cpu className="w-6 h-6 text-indigo-600" />
                  <div className="text-left">
                    <div className="font-medium text-gray-900">LM Studio</div>
                    <div className="text-xs text-gray-500">Local OpenAI-API</div>
                  </div>
                </button>
              </div>
            </div>

            {/* Ollama Configuration */}
            {currentAiProvider === 'ollama' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">{t('ai.ollamaUrl')}</label>
                  <input
                    id="primary-ollama-base-url"
                    name="primary_ollama_base_url"
                    type="text"
                    value={currentOllamaBaseUrl}
                    onChange={(e) => setAiOverride(prev => ({ ...prev, ollama_base_url: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder={config.OLLAMA_BASE_URL}
                    aria-label="Primary Ollama Base URL"
                  />
                </div>

                <div className="relative">
                  <div className="flex items-center justify-between mb-2">
                    <label className="block text-sm font-medium text-gray-700">{t('ai.models')}</label>
                    <button
                      onClick={handleFetchModels}
                      disabled={loading}
                      className="flex items-center space-x-1 text-indigo-600 hover:text-indigo-700 text-sm font-medium disabled:opacity-50"
                    >
                      <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                      <span>{t('ai.refresh')}</span>
                    </button>
                  </div>
                  <div className="relative">
                    <input
                      id="primary-ollama-model-search"
                      name="primary_ollama_model_search"
                      type="text"
                      value={modelSearchQuery || currentSelectedModel}
                      onChange={(e) => { setModelSearchQuery(e.target.value); setModelSearchOpen(true); }}
                      onFocus={() => setModelSearchOpen(true)}
                      placeholder={t('ai.searchModels')}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      aria-label="Primary Ollama model search"
                    />
                    {modelSearchOpen && ollamaModels.length > 0 && (
                      <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                        {ollamaModels.filter(model => model.name.toLowerCase().includes(modelSearchQuery.toLowerCase())).map((model) => (
                          <button
                            key={model.name}
                            onClick={() => { setAiOverride(prev => ({ ...prev, ollama_model: model.name })); setModelSearchQuery(''); setModelSearchOpen(false); }}
                            className="w-full text-left px-4 py-2 hover:bg-indigo-50 transition-colors"
                          >
                            {model.name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  {currentSelectedModel && !modelSearchQuery && (
                    <div className="mt-1 text-sm text-gray-600">{t('ai.selected')} {currentSelectedModel}</div>
                  )}
                </div>

              </div>
            )}

            {/* OpenRouter Configuration */}
            {currentAiProvider === 'openrouter' && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="primary-openrouter-api-key" className="block text-sm font-medium text-gray-700 mb-2">{t('ai.apiKey')}</label>
                  <input
                    id="primary-openrouter-api-key"
                    name="primary_openrouter_api_key"
                    type="password"
                    value={currentOpenRouterApiKey}
                    onChange={(e) => setAiOverride(prev => ({ ...prev, openrouter_api_key: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder="sk-or-..."
                    aria-label="Primary OpenRouter API Key"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    {t('ai.getKey')} <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">openrouter.ai/keys</a>
                  </p>
                </div>

                <div className="relative">
                  <div className="flex items-center justify-between mb-2">
                    <label htmlFor="primary-openrouter-model-search" className="block text-sm font-medium text-gray-700">Available Models</label>
                    <button onClick={handleFetchModels} disabled={loading || !currentOpenRouterApiKey} className="flex items-center space-x-1 text-indigo-600 hover:text-indigo-700 text-sm font-medium disabled:opacity-50">
                      <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                      <span>Refresh</span>
                    </button>
                  </div>
                  <div className="relative">
                    <input
                      id="primary-openrouter-model-search"
                      name="primary_openrouter_model_search"
                      type="text"
                      value={modelSearchQuery || currentSelectedModel}
                      onChange={(e) => { setModelSearchQuery(e.target.value); setModelSearchOpen(true); }}
                      onFocus={() => setModelSearchOpen(true)}
                      placeholder={t('ai.searchModels')}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      aria-label="Primary OpenRouter model search"
                    />
                    {modelSearchOpen && openRouterModels.length > 0 && (
                      <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                        {openRouterModels.filter(model => model.name.toLowerCase().includes(modelSearchQuery.toLowerCase()) || model.id.toLowerCase().includes(modelSearchQuery.toLowerCase())).map((model) => (
                          <button
                            key={model.id}
                            onClick={() => { setAiOverride(prev => ({ ...prev, openrouter_model: model.id })); setModelSearchQuery(''); setModelSearchOpen(false); }}
                            className="w-full text-left px-4 py-2 hover:bg-indigo-50 transition-colors"
                          >
                            <div className="font-medium">{model.name}</div>
                            <div className="text-xs text-gray-500">{model.id}</div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  {currentSelectedModel && !modelSearchQuery && (
                    <div className="mt-1 text-sm text-gray-600">{t('ai.selected')} {currentSelectedModel}</div>
                  )}
                </div>
              </div>
            )}
            {/* LM Studio Configuration */}
            {currentAiProvider === 'lmstudio' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">LM Studio Base URL</label>
                  <input
                    id="primary-lmstudio-base-url"
                    name="primary_lmstudio_base_url"
                    type="text"
                    value={aiOverride.lmstudio_base_url ?? aiSettings?.lmstudio_base_url ?? 'http://localhost:1234/v1'}
                    onChange={(e) => setAiOverride(prev => ({ ...prev, lmstudio_base_url: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder="http://localhost:1234/v1"
                    aria-label="Primary LM Studio Base URL"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Default: http://localhost:1234/v1
                  </p>
                </div>

                <div className="relative">
                  <div className="flex items-center justify-between mb-2">
                    <label className="block text-sm font-medium text-gray-700">{t('ai.models')}</label>
                    <button
                      onClick={handleFetchModels}
                      disabled={loading}
                      className="flex items-center space-x-1 text-indigo-600 hover:text-indigo-700 text-sm font-medium disabled:opacity-50"
                    >
                      <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                      <span>{t('ai.refresh')}</span>
                    </button>
                  </div>
                  <div className="relative">
                    <label className="block text-sm font-medium text-gray-700">
                      Select Model
                    </label>
                    <select
                      id="primary-lmstudio-model"
                      name="primary_lmstudio_model"
                      value={aiOverride.lmstudio_model ?? aiSettings?.lmstudio_model ?? ''}
                      onChange={(e) => setAiOverride(prev => ({ ...prev, lmstudio_model: e.target.value }))}
                      className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
                      aria-label="Primary LM Studio model"
                    >
                      <option value="">Select a model...</option>
                      {lmStudioModels.length > 0 ? (
                        lmStudioModels.map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.id}
                          </option>
                        ))
                      ) : (
                        <option value="local-model">local-model (Default)</option>
                      )}
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* LLM Behavior Settings (applies to selected provider) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
              <div>
                <label htmlFor="primary-max-tokens" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('ai.maxTokens')}
                </label>
                <input
                  id="primary-max-tokens"
                  name="primary_max_tokens"
                  type="number"
                  min={64}
                  max={4096}
                  step={64}
                  value={currentMaxTokens}
                  onChange={(e) =>
                    setAiOverride(prev => ({ ...prev, max_tokens: Number(e.target.value) || 0 }))
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                  aria-label="Primary max tokens per reply"
                />
                <div className="mt-1 flex flex-wrap gap-2 text-xs">
                  <span className="text-gray-500 mr-1">{t('ai.presets')}</span>
                  <button
                    type="button"
                    onClick={() => setAiOverride(prev => ({ ...prev, max_tokens: 256 }))}
                    className="px-2 py-1 rounded border border-gray-300 hover:border-indigo-500 hover:text-indigo-600"
                  >
                    {t('ai.short')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setAiOverride(prev => ({ ...prev, max_tokens: 512 }))}
                    className="px-2 py-1 rounded border border-gray-300 hover:border-indigo-500 hover:text-indigo-600"
                  >
                    {t('ai.medium')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setAiOverride(prev => ({ ...prev, max_tokens: 1024 }))}
                    className="px-2 py-1 rounded border border-gray-300 hover:border-indigo-500 hover:text-indigo-600"
                  >
                    {t('ai.long')}
                  </button>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  {t('ai.maxTokensHelp')}
                </p>
              </div>
              <div>
                <label htmlFor="primary-temperature" className="block text-sm font-medium text-gray-700 mb-1">
                  {t('ai.temperature')}
                </label>
                <input
                  id="primary-temperature"
                  name="primary_temperature"
                  type="number"
                  min={0}
                  max={1.5}
                  step={0.1}
                  value={currentTemperature}
                  onChange={(e) =>
                    setAiOverride(prev => ({ ...prev, temperature: Number(e.target.value) }))
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                  aria-label="Primary temperature"
                />
                <p className="mt-1 text-xs text-gray-500">
                  {t('ai.temperatureHelp')}
                </p>
              </div>
            </div>

            {/* Provider Health Check */}
            <div className="flex items-center gap-2 pt-4 border-t border-gray-200">
              <button onClick={checkHealth} className="px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">{t('ai.health')}</button>
              {health && (
                <span className="text-xs text-gray-600">
                  {t('ai.ollamaStatus')} <span className={health.ollama ? 'text-green-600' : 'text-red-600'}>{health.ollama ? 'ok' : 'down'}</span> |
                  {t('ai.openrouterStatus')} <span className={health.openrouter ? 'text-green-600' : 'text-red-600'}>{health.openrouter ? 'ok' : 'down'}</span> |
                  <div className="flex items-center space-x-1">
                    <span>LM Studio:</span>
                    <span className={health.lmstudio?.available ? 'text-green-600' : 'text-red-600'}>
                      {health.lmstudio?.available ? 'ok' : 'down'}
                    </span>
                  </div>
                </span>
              )}
            </div>

            {/* Voice Dependency Status */}
            {voiceStatus && (
              <div className="mt-6 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('ai.voiceDeps')}</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{t('ai.voiceDepsHelp')}</p>
                  </div>
                </div>
                <div className="space-y-3">
                  {voiceStatusItems.map((item) => {
                    const ok = item.status === true;
                    return (
                      <div key={item.key} className="flex items-center justify-between bg-gray-50 dark:bg-gray-900 rounded-lg px-3 py-2">
                        <div className="flex items-center gap-3">
                          <Circle className={`w-4 h-4 ${ok ? 'text-green-500' : item.optional ? 'text-amber-500' : 'text-red-500'}`} fill={ok ? 'currentColor' : 'none'} />
                          <div>
                            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{item.label}</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">
                              {ok ? t('ai.installed') : t('ai.notInstalled')} {item.extra ? `(${item.extra})` : ''}
                            </div>
                            {!ok && (
                              <div className="text-xs text-amber-600 dark:text-amber-400">{item.help}</div>
                            )}
                          </div>
                        </div>
                        <a
                          href={item.link}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                          title={item.help}
                        >
                          How to install
                        </a>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Fallback Configuration */}
            <div className="pt-6 border-t border-gray-200">
              <button
                onClick={() => setShowFallback(!showFallback)}
                className="w-full flex items-center justify-between p-4 bg-amber-50 border border-amber-200 rounded-lg hover:bg-amber-100 transition-colors"
              >
                <div className="flex items-center space-x-2">
                  <Shield className="w-5 h-5 text-amber-600" />
                  <div className="text-left">
                    <div className="font-medium text-gray-900">Fallback AI Configuration</div>
                    <div className="text-sm text-gray-600">Backup provider if primary fails</div>
                  </div>
                </div>
                {showFallback ? <ChevronUp className="w-5 h-5 text-gray-500" /> : <ChevronDown className="w-5 h-5 text-gray-500" />}
              </button>

              {showFallback && (
                <div className="mt-4 space-y-6 p-6 bg-gray-50 rounded-lg border border-gray-200">
                  <div>
                    <p className="block text-sm font-medium text-gray-700 mb-3">Fallback Provider</p>
                    <div className="grid grid-cols-2 gap-4">
                      <button
                        onClick={() => setFallbackOverride(prev => ({ ...prev, provider: 'ollama' }))}
                        className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${currentFallbackProvider === 'ollama' ? 'border-amber-600 bg-amber-50' : 'border-gray-200 hover:border-gray-300'}`}
                      >
                        <Cpu className="w-6 h-6 text-amber-600" />
                        <div className="text-left">
                          <div className="font-medium text-gray-900">Ollama</div>
                          <div className="text-xs text-gray-500">Local LLM</div>
                        </div>
                      </button>
                      <button
                        onClick={() => setFallbackOverride(prev => ({ ...prev, provider: 'openrouter' }))}
                        className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${currentFallbackProvider === 'openrouter' ? 'border-amber-600 bg-amber-50' : 'border-gray-200 hover:border-gray-300'}`}
                      >
                        <Cloud className="w-6 h-6 text-amber-600" />
                        <div className="text-left">
                          <div className="font-medium text-gray-900">OpenRouter</div>
                          <div className="text-xs text-gray-500">Cloud API</div>
                        </div>
                      </button>

                      <button
                        onClick={() => setFallbackOverride(prev => ({ ...prev, provider: 'lmstudio' }))}
                        className={`p-4 border-2 rounded-lg flex items-center space-x-3 transition-colors ${currentFallbackProvider === 'lmstudio' ? 'border-amber-600 bg-amber-50' : 'border-gray-200 hover:border-gray-300'}`}
                      >
                        <Cpu className="w-6 h-6 text-amber-600" />
                        <div className="text-left">
                          <div className="font-medium text-gray-900">LM Studio</div>
                          <div className="text-xs text-gray-500">Local OpenAI-API</div>
                        </div>
                      </button>
                    </div>
                  </div>

                  {currentFallbackProvider === 'ollama' && (
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Ollama Base URL</label>
                        <input
                          id="fallback-ollama-base-url"
                          name="fallback_ollama_base_url"
                          type="text"
                          value={currentFallbackOllamaBaseUrl}
                          onChange={(e) => setFallbackOverride(prev => ({ ...prev, ollama_base_url: e.target.value }))}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                          placeholder={config.OLLAMA_BASE_URL}
                          aria-label="Fallback Ollama Base URL"
                        />
                      </div>
                      <div className="relative">
                        <div className="flex items-center justify-between mb-2">
                          <label className="block text-sm font-medium text-gray-700">Available Models</label>
                          <button onClick={handleFetchFallbackModels} disabled={loading} className="flex items-center space-x-1 text-amber-600 hover:text-amber-700 text-sm font-medium disabled:opacity-50">
                            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                            <span>Refresh</span>
                          </button>
                        </div>
                        <div className="relative">
                          <input
                            id="fallback-ollama-model-search"
                            name="fallback_ollama_model_search"
                            type="text"
                            value={fallbackModelSearchQuery || currentFallbackModel}
                            onChange={(e) => { setFallbackModelSearchQuery(e.target.value); setFallbackModelSearchOpen(true); }}
                            onFocus={() => setFallbackModelSearchOpen(true)}
                            placeholder="Search models..."
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                            aria-label="Fallback Ollama model search"
                          />
                          {fallbackModelSearchOpen && ollamaModels.length > 0 && (
                            <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                              {ollamaModels.filter(model => model.name.toLowerCase().includes(fallbackModelSearchQuery.toLowerCase())).map((model) => (
                                <button
                                  key={model.name}
                                  onClick={() => { setFallbackOverride(prev => ({ ...prev, ollama_model: model.name })); setFallbackModelSearchQuery(''); setFallbackModelSearchOpen(false); }}
                                  className="w-full text-left px-4 py-2 hover:bg-amber-50 transition-colors"
                                >
                                  {model.name}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                        {currentFallbackModel && !fallbackModelSearchQuery && (
                          <div className="mt-1 text-sm text-gray-600">Selected: {currentFallbackModel}</div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Fallback LLM Behavior Settings */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                    <div>
                      <label htmlFor="fallback-max-tokens" className="block text-sm font-medium text-gray-700 mb-1">
                        Fallback max tokens per reply
                      </label>
                      <input
                        id="fallback-max-tokens"
                        name="fallback_max_tokens"
                        type="number"
                        min={64}
                        max={4096}
                        step={64}
                        value={currentFallbackMaxTokens}
                        onChange={(e) =>
                          setFallbackOverride(prev => ({
                            ...prev,
                            max_tokens: Number(e.target.value) || 0,
                          }))
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 text-sm"
                        aria-label="Fallback max tokens per reply"
                      />
                      <div className="mt-1 flex flex-wrap gap-2 text-xs">
                        <span className="text-gray-500 mr-1">Presets:</span>
                        <button
                          type="button"
                          onClick={() => setFallbackOverride(prev => ({ ...prev, max_tokens: 256 }))}
                          className="px-2 py-1 rounded border border-gray-300 hover:border-amber-500 hover:text-amber-600"
                        >
                          Short (256)
                        </button>
                        <button
                          type="button"
                          onClick={() => setFallbackOverride(prev => ({ ...prev, max_tokens: 512 }))}
                          className="px-2 py-1 rounded border border-gray-300 hover:border-amber-500 hover:text-amber-600"
                        >
                          Medium (512)
                        </button>
                        <button
                          type="button"
                          onClick={() => setFallbackOverride(prev => ({ ...prev, max_tokens: 1024 }))}
                          className="px-2 py-1 rounded border border-gray-300 hover:border-amber-500 hover:text-amber-600"
                        >
                          Long (1024)
                        </button>
                      </div>
                      <p className="mt-1 text-xs text-gray-500">
                        Use a smaller value here if you want shorter answers when the system falls back to this provider.
                      </p>
                    </div>
                    <div>
                      <label htmlFor="fallback-temperature" className="block text-sm font-medium text-gray-700 mb-1">
                        Fallback temperature
                      </label>
                      <input
                        id="fallback-temperature"
                        name="fallback_temperature"
                        type="number"
                        min={0}
                        max={1.5}
                        step={0.1}
                        value={currentFallbackTemperature}
                        onChange={(e) =>
                          setFallbackOverride(prev => ({
                            ...prev,
                            temperature: Number(e.target.value),
                          }))
                        }
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 text-sm"
                        aria-label="Fallback temperature"
                      />
                      <p className="mt-1 text-xs text-gray-500">
                        You can keep fallback answers a bit more conservative (e.g. 0.3–0.6) so behavior stays predictable even if the primary provider is down.
                      </p>
                    </div>
                  </div>

                  {currentFallbackProvider === 'openrouter' && (
                    <div className="space-y-4">
                      <div>
                        <label htmlFor="fallback-openrouter-api-key" className="block text-sm font-medium text-gray-700 mb-2">OpenRouter API Key</label>
                        <input
                          id="fallback-openrouter-api-key"
                          name="fallback_openrouter_api_key"
                          type="password"
                          value={currentFallbackOpenRouterApiKey}
                          onChange={(e) => setFallbackOverride(prev => ({ ...prev, openrouter_api_key: e.target.value }))}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                          placeholder="sk-or-..."
                          aria-label="Fallback OpenRouter API Key"
                        />
                      </div>
                      <div className="relative">
                        <div className="flex items-center justify-between mb-2">
                          <label htmlFor="fallback-openrouter-model-search" className="block text-sm font-medium text-gray-700">Available Models</label>
                          <button onClick={handleFetchFallbackModels} disabled={loading || !currentFallbackOpenRouterApiKey} className="flex items-center space-x-1 text-amber-600 hover:text-amber-700 text-sm font-medium disabled:opacity-50">
                            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                            <span>Refresh</span>
                          </button>
                        </div>
                        <div className="relative">
                          <input
                            id="fallback-openrouter-model-search"
                            name="fallback_openrouter_model_search"
                            type="text"
                            value={fallbackModelSearchQuery || currentFallbackModel}
                            onChange={(e) => { setFallbackModelSearchQuery(e.target.value); setFallbackModelSearchOpen(true); }}
                            onFocus={() => setFallbackModelSearchOpen(true)}
                            placeholder="Search models..."
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                            aria-label="Fallback OpenRouter model search"
                          />
                          {fallbackModelSearchOpen && openRouterModels.length > 0 && (
                            <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                              {openRouterModels.filter(model => model.name.toLowerCase().includes(fallbackModelSearchQuery.toLowerCase()) || model.id.toLowerCase().includes(fallbackModelSearchQuery.toLowerCase())).map((model) => (
                                <button
                                  key={model.id}
                                  onClick={() => { setFallbackOverride(prev => ({ ...prev, openrouter_model: model.id })); setFallbackModelSearchQuery(''); setFallbackModelSearchOpen(false); }}
                                  className="w-full text-left px-4 py-2 hover:bg-amber-50 transition-colors"
                                >
                                  <div className="font-medium">{model.name}</div>
                                  <div className="text-xs text-gray-500">{model.id}</div>
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                        {currentFallbackModel && !fallbackModelSearchQuery && (
                          <div className="mt-1 text-sm text-gray-600">Selected: {currentFallbackModel}</div>
                        )}
                      </div>
                    </div>
                  )}
                  {currentFallbackProvider === 'lmstudio' && (
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">LM Studio Base URL</label>
                        <input
                          id="fallback-lmstudio-base-url"
                          name="fallback_lmstudio_base_url"
                          type="text"
                          value={fallbackOverride.lmstudio_base_url ?? fallbackAISettings?.lmstudio_base_url ?? 'http://localhost:1234/v1'}
                          onChange={(e) => setFallbackOverride(prev => ({ ...prev, lmstudio_base_url: e.target.value }))}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                          placeholder="http://localhost:1234/v1"
                          aria-label="Fallback LM Studio Base URL"
                        />
                      </div>
                      <div className="relative">
                        <label className="block text-sm font-medium text-gray-700">
                          Select Model
                        </label>
                        <select
                          id="fallback-lmstudio-model"
                          name="fallback_lmstudio_model"
                          value={fallbackOverride.lmstudio_model ?? fallbackAISettings?.lmstudio_model ?? ''}
                          onChange={(e) => setFallbackOverride(prev => ({ ...prev, lmstudio_model: e.target.value }))}
                          className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-amber-500 focus:border-amber-500 sm:text-sm rounded-md"
                          aria-label="Fallback LM Studio model"
                        >
                          <option value="">Select a model...</option>
                          {lmStudioModels.length > 0 ? (
                            lmStudioModels.map((model) => (
                              <option key={model.id} value={model.id}>
                                {model.id}
                              </option>
                            ))
                          ) : (
                            <option value="local-model">local-model (Default)</option>
                          )}
                        </select>
                      </div>
                    </div>
                  )}
                </div>
              )}
              {/* Single Save Button for All AI Settings */}
              <div className="flex justify-end pt-6 border-t border-gray-200">
                <button
                  onClick={handleSaveAllSettings}
                  disabled={loading}
                  className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                >
                  {loading ? 'Saving...' : 'Save AI Settings'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Read-only AI Settings for Non-Admins */}
      {!isAdmin && aiSettings && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">AI Configuration</h3>
            <p className="text-sm text-gray-500 mt-1">Current AI settings (View only - contact admin to change)</p>
          </div>
          <div className="p-6 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p className="block text-sm font-medium text-gray-700 mb-1">Primary Provider</p>
                <div className="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg capitalize flex items-center">
                  {aiSettings.provider === 'ollama' ? <Cpu className="w-4 h-4 mr-2 text-indigo-600" /> : <Cloud className="w-4 h-4 mr-2 text-indigo-600" />}
                  {aiSettings.provider}
                </div>
              </div>
              <div>
                <p className="block text-sm font-medium text-gray-700 mb-1">Primary Model</p>
                <div className="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg">
                  {(aiSettings.provider === 'ollama' ? aiSettings.ollama_model : aiSettings.openrouter_model) || 'Not configured'}
                </div>
              </div>
            </div>
            {fallbackAISettings && (
              <div className="pt-4 border-t border-gray-200">
                <h4 className="text-sm font-medium text-gray-700 mb-3 flex items-center">
                  <Shield className="w-4 h-4 mr-1 text-amber-600" />
                  Fallback Configuration
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="block text-sm font-medium text-gray-500 mb-1">Fallback Provider</p>
                    <div className="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg capitalize flex items-center text-sm">
                      {fallbackAISettings.provider === 'ollama' ? <Cpu className="w-4 h-4 mr-2 text-amber-600" /> : <Cloud className="w-4 h-4 mr-2 text-amber-600" />}
                      {fallbackAISettings.provider}
                    </div>
                  </div>
                  <div>
                    <p className="block text-sm font-medium text-gray-700 mb-1">Fallback Model</p>
                    <div className="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm">
                      {(fallbackAISettings.provider === 'ollama' ? fallbackAISettings.ollama_model : fallbackAISettings.openrouter_model) || 'Not configured'}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
