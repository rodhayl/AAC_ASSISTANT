import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { VoiceTab } from '../src/pages/Settings/VoiceTab';

const { get, post, put } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}));

vi.mock('../src/lib/api', () => ({
  default: {
    get,
    post,
    put,
  },
  extractError: (error: { message?: string } | undefined, fallback: string) =>
    error?.message || fallback,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'ai.sttModel': 'Speech-to-text model',
      'ai.installAutomatically': 'Install automatically',
      'ai.installComplete': 'Voice dependencies installed.',
      'ai.installFailed': 'Automatic voice installation failed.',
      'ai.localVoice': 'Local neural voice',
      'ai.localVoiceHelp': 'Pick a specific Kokoro voice.',
      'ai.localSpeed': 'Neural voice speed',
      'ai.localSpeedHelp': 'How fast Kokoro speaks.',
      'ai.speedNormal': 'Normal',
      'ai.voiceDefault': 'Default (auto)',
      'ai.sttModelSaved': 'Speech-to-text model updated.',
      'ai.sttModelSaveFailed': 'Could not update the speech-to-text model.',
      'ai.ttsWarmupInProgress': 'Pre-loading the local neural voice model in the background…',
      'ai.ttsWarmupReady': 'Local neural voice model ready (pre-loaded in the background).',
      'ai.speechWarmupInProgress': 'Pre-loading the speech-to-text model in the background…',
      'ai.speechWarmupReady': 'Speech-to-text model ready (pre-loaded in the background).',
      'ai.vectorWarmupInProgress': 'Pre-loading the semantic search model in the background…',
      'ai.vectorWarmupReady': 'Semantic search model ready (pre-loaded in the background).',
      'ai.installing': 'Installing...',
      'ai.dependencies.localTts.label': 'Kokoro local neural voice',
      'ai.dependencies.localTts.help': 'Prepared by start.sh and used when Kokoro is selected above',
      'preferences.tts': 'Text-to-Speech Voice',
      'preferences.ttsHelp': 'Choose the voice for reading symbols',
      'preferences.ttsEngine': 'Voice output engine',
      'preferences.ttsEngineHelp': 'Choose one engine for spoken panels and messages.',
      'preferences.selectedEngine': 'Selected engine',
      'preferences.defaultEngine': 'default',
      'preferences.engineSingleChoiceHelp': 'Only this engine speaks.',
      'preferences.ttsProviders.kokoro': 'Kokoro (local neural voice)',
      'preferences.ttsProviders.browser': 'Browser / system voice',
      'preferences.browserVoice': 'Browser voice',
      'preferences.browserVoiceHelp': 'Uses voices installed by your browser or operating system.',
      'preferences.hoverSpeak': 'Read suggestions aloud on hover',
      'preferences.hoverSpeakHelp': 'Resting the pointer on a symbol suggestion speaks its word aloud.',
      'preferences.hoverSpeakDelay': 'Time before speaking',
      'preferences.hoverSpeakDelayHelp': 'How long the pointer must rest on the symbol.',
      'preferences.kokoroUnavailable': 'Kokoro is not ready.',
      'voice.americanEnglish': 'American English',
      'voice.britishEnglish': 'British English',
      'voice.female': 'Female',
      'voice.male': 'Male',
    }[key] ?? key),
  }),
}));

describe('VoiceTab', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    put.mockReset();

    get.mockResolvedValue({
      data: {
        stt: {
          provider: 'faster-whisper',
          installed: false,
          model: 'tiny',
          models: {
            tiny: { size: '~39M parameters / ~75MB', description: 'Fastest, lowest memory use', selected: true },
            base: { size: '~74M parameters / ~145MB', description: 'Fast with improved accuracy' },
            small: { size: '~244M parameters / ~465MB', description: 'Balanced accuracy and speed' },
            medium: { size: '~769M parameters / ~1.5GB', description: 'Higher accuracy, slower' },
            'large-v3': { size: '~1.55B parameters / ~3GB', description: 'Highest accuracy, slowest' },
          },
        },
        ffmpeg: { installed: false, available: false, required: false },
        tts: { provider: 'browser', client_side: true, installed: true },
        actions: {
          install_voice: {
            supported: true,
            in_progress: false,
            reason: null,
            platform: 'win32',
          },
        },
      },
    });
    post.mockResolvedValue({
      data: {
        success: true,
        installed: true,
        message: 'Voice dependencies installed.',
      },
    });
  });

  it('shows the default tiny STT model and all supported model choices before installation', async () => {
    get.mockResolvedValue({
      data: {
        stt: {
          provider: 'faster-whisper',
          installed: false,
          model: 'tiny',
          models: {
            tiny: { size: '~39M parameters / ~75MB', description: 'Fastest, lowest memory use', selected: true },
            base: { size: '~74M parameters / ~145MB', description: 'Fast with improved accuracy' },
            small: { size: '~244M parameters / ~465MB', description: 'Balanced accuracy and speed' },
            medium: { size: '~769M parameters / ~1.5GB', description: 'Higher accuracy, slower' },
            'large-v3': { size: '~1.55B parameters / ~3GB', description: 'Highest accuracy, slowest' },
          },
        },
        actions: {},
      },
    });

    render(
      <VoiceTab
        preferences={{ tts_provider: 'kokoro', tts_voice: 'default', tts_local_voice: 'default', ui_language: 'en-US', notifications_enabled: true, voice_mode_enabled: true, dark_mode: false, dwell_time: 0, ignore_repeats: 0, high_contrast: false }}
        setPreferences={vi.fn()}
        filteredVoices={[]}
        showStatus
      />
    );

    const select = await screen.findByRole('combobox', { name: 'Speech-to-text model' });
    expect(select).toHaveValue('tiny');
    expect(select).toBeEnabled();
    expect(screen.getByRole('option', { name: /tiny/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /base/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /small/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /medium/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /large-v3/ })).toBeInTheDocument();

    fireEvent.change(select, { target: { value: 'small' } });
    await waitFor(() => expect(put).toHaveBeenCalledWith('/providers/stt/model', { model: 'small' }));
  });

  it('offers one-click voice installation for missing faster-whisper', async () => {
    render(
      <VoiceTab
        preferences={{
          tts_provider: 'kokoro',
          tts_voice: 'default',
          tts_local_voice: 'default',
          ui_language: 'en-US',
          notifications_enabled: true,
          voice_mode_enabled: true,
          dark_mode: false,
          dwell_time: 0,
          ignore_repeats: 0,
          high_contrast: false,
        }}
        setPreferences={vi.fn()}
        filteredVoices={[]}
        showStatus
      />
    );

    const installButton = await screen.findByRole('button', {
      name: 'Install automatically',
    });
    fireEvent.click(installButton);

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/providers/voice/install',
        {},
        expect.objectContaining({ timeout: 600000 })
      );
    });
    await waitFor(() => {
      expect(get).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText('Voice dependencies installed.')).toBeInTheDocument();
  });

  it('lets the user pick a specific Kokoro voice grouped by language', async () => {
    get.mockResolvedValue({
      data: {
        tts_local: {
          provider: 'kokoro',
          installed: true,
          model_present: true,
          available: true,
          voices: [
            { name: 'ef_dora', language: 'es', gender: 'female', region: null },
            { name: 'em_santa', language: 'es', gender: 'male', region: null },
            { name: 'em_alex', language: 'es', gender: 'male', region: null },
            { name: 'af_sarah', language: 'en', gender: 'female', region: 'american' },
          ],
        },
        actions: {},
      },
    });

    render(
      <VoiceTab
        preferences={{
          tts_provider: 'kokoro',
          tts_voice: 'default',
          tts_local_voice: 'default',
          ui_language: 'en-US',
          notifications_enabled: true,
          voice_mode_enabled: true,
          dark_mode: false,
          dwell_time: 0,
          ignore_repeats: 0,
          high_contrast: false,
        }}
        setPreferences={vi.fn()}
        filteredVoices={[]}
        showStatus
      />
    );

    const select = await screen.findByRole('combobox', { name: 'Local neural voice' });
    await waitFor(() => {
      expect(select).toBeEnabled();
    });
    // The Spanish voices are offered alongside the English ones.
    expect(await screen.findByRole('option', { name: /ef_dora/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /em_santa/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /em_alex/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /af_sarah/ })).toBeInTheDocument();
    // Voices are grouped by language.
    expect(screen.getByRole('group', { name: /Español/ })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: /English/ })).toBeInTheDocument();

    fireEvent.change(select, { target: { value: 'ef_dora' } });

    const { useTTSStore } = await import('../src/store/ttsStore');
    expect(useTTSStore.getState().localVoice).toBe('ef_dora');
    expect(localStorage.getItem('aac_local_voice')).toBe('ef_dora');
  });

  it('applies the selected Kokoro speed to the store and the preferences draft', async () => {
    get.mockResolvedValue({
      data: {
        tts_local: {
          provider: 'kokoro',
          installed: true,
          model_present: true,
          available: true,
          voices: [{ name: 'ef_dora', language: 'es', gender: 'female', region: null }],
        },
        actions: {},
      },
    });
    const setPreferences = vi.fn();

    render(
      <VoiceTab
        preferences={{
          tts_provider: 'kokoro',
          tts_voice: 'default',
          tts_local_voice: 'default',
          tts_local_speed: 1.0,
          ui_language: 'en-US',
          notifications_enabled: true,
          voice_mode_enabled: true,
          dark_mode: false,
          dwell_time: 0,
          ignore_repeats: 0,
          high_contrast: false,
        }}
        setPreferences={setPreferences}
        filteredVoices={[]}
        showStatus
      />
    );

    const select = await screen.findByRole('combobox', { name: 'Neural voice speed' });
    await waitFor(() => {
      expect(select).toBeEnabled();
    });
    expect(select).toHaveValue('1');

    fireEvent.change(select, { target: { value: '1.5' } });

    const { useTTSStore } = await import('../src/store/ttsStore');
    expect(useTTSStore.getState().localSpeed).toBe(1.5);
    expect(localStorage.getItem('aac_local_speed')).toBe('1.5');
    const updater = setPreferences.mock.calls[0][0] as (prev: { tts_local_speed: number }) => { tts_local_speed: number };
    expect(updater({ tts_local_speed: 1.0 })).toEqual({ tts_local_speed: 1.5 });
    localStorage.removeItem('aac_local_speed');
  });

  it('shows a spinner while the Kokoro model is pre-loading in the background', async () => {
    const { useTTSStore } = await import('../src/store/ttsStore');
    act(() => {
      useTTSStore.setState({ ttsWarmupStatus: 'warming' });
    });
    try {
      render(
        <VoiceTab
          preferences={{
            tts_provider: 'kokoro',
            tts_voice: 'default',
            tts_local_voice: 'default',
            ui_language: 'en-US',
            notifications_enabled: true,
            voice_mode_enabled: true,
            dark_mode: false,
            dwell_time: 0,
            ignore_repeats: 0,
            high_contrast: false,
          }}
          setPreferences={vi.fn()}
          filteredVoices={[]}
        />
      );

      const indicator = await screen.findByTestId('tts-warmup-indicator');
      expect(indicator).toBeInTheDocument();
      expect(screen.getByText(/pre-loading the local neural voice model in the background/i)).toBeInTheDocument();
    } finally {
      act(() => {
        useTTSStore.setState({ ttsWarmupStatus: 'idle' });
      });
    }
  });

  it('reports when the Kokoro model finished pre-loading', async () => {
    const { useTTSStore } = await import('../src/store/ttsStore');
    act(() => {
      useTTSStore.setState({ ttsWarmupStatus: 'ready' });
    });
    try {
      render(
        <VoiceTab
          preferences={{
            tts_provider: 'kokoro',
            tts_voice: 'default',
            tts_local_voice: 'default',
            ui_language: 'en-US',
            notifications_enabled: true,
            voice_mode_enabled: true,
            dark_mode: false,
            dwell_time: 0,
            ignore_repeats: 0,
            high_contrast: false,
          }}
          setPreferences={vi.fn()}
          filteredVoices={[]}
        />
      );

      const indicator = await screen.findByTestId('tts-warmup-indicator');
      expect(screen.getByText(/local neural voice model ready/i)).toBeInTheDocument();
      expect(indicator.querySelector('.text-green-600')).not.toBeNull();
    } finally {
      act(() => {
        useTTSStore.setState({ ttsWarmupStatus: 'idle' });
      });
    }
  });

  it('shows the speech-to-text pre-load status in the admin status section', async () => {
    const { useTTSStore } = await import('../src/store/ttsStore');
    act(() => {
      useTTSStore.setState({ speechWarmupStatus: 'warming' });
    });
    try {
      render(
        <VoiceTab
          preferences={{
            tts_provider: 'kokoro',
            tts_voice: 'default',
            tts_local_voice: 'default',
            ui_language: 'en-US',
            notifications_enabled: true,
            voice_mode_enabled: true,
            dark_mode: false,
            dwell_time: 0,
            ignore_repeats: 0,
            high_contrast: false,
          }}
          setPreferences={vi.fn()}
          filteredVoices={[]}
          showStatus
        />
      );

      const indicator = await screen.findByTestId('speech-warmup-indicator');
      expect(indicator).toBeInTheDocument();
      expect(screen.getByText(/pre-loading the speech-to-text model in the background/i)).toBeInTheDocument();
    } finally {
      act(() => {
        useTTSStore.setState({ speechWarmupStatus: 'idle' });
      });
    }
  });

  it('shows the semantic search pre-load status in the admin status section', async () => {
    const { useTTSStore } = await import('../src/store/ttsStore');
    act(() => {
      useTTSStore.setState({ vectorWarmupStatus: 'warming' });
    });
    try {
      render(
        <VoiceTab
          preferences={{
            tts_provider: 'kokoro',
            tts_voice: 'default',
            tts_local_voice: 'default',
            ui_language: 'en-US',
            notifications_enabled: true,
            voice_mode_enabled: true,
            dark_mode: false,
            dwell_time: 0,
            ignore_repeats: 0,
            high_contrast: false,
          }}
          setPreferences={vi.fn()}
          filteredVoices={[]}
          showStatus
        />
      );

      const indicator = await screen.findByTestId('vector-warmup-indicator');
      expect(indicator).toBeInTheDocument();
      expect(screen.getByText(/pre-loading the semantic search model in the background/i)).toBeInTheDocument();
    } finally {
      act(() => {
        useTTSStore.setState({ vectorWarmupStatus: 'idle' });
      });
    }
  });

  it('drops a stale ready badge when the backend reports the model is no longer loaded', async () => {
    const { useTTSStore } = await import('../src/store/ttsStore');
    act(() => {
      useTTSStore.setState({ ttsWarmupStatus: 'ready' });
    });
    get.mockResolvedValue({
      data: {
        tts_local: { provider: 'kokoro', installed: true, model_present: true, available: true, model_loaded: false },
        actions: {},
      },
    });
    try {
      render(
        <VoiceTab
          preferences={{
            tts_provider: 'kokoro',
            tts_voice: 'default',
            tts_local_voice: 'default',
            ui_language: 'en-US',
            notifications_enabled: true,
            voice_mode_enabled: true,
            dark_mode: false,
            dwell_time: 0,
            ignore_repeats: 0,
            high_contrast: false,
          }}
          setPreferences={vi.fn()}
          filteredVoices={[]}
        />
      );

      // The backend says the model is not resident (server restart / provider
      // reset), so the stale "ready" badge must disappear.
      await waitFor(() => {
        expect(screen.queryByTestId('tts-warmup-indicator')).not.toBeInTheDocument();
      });
      expect(useTTSStore.getState().ttsWarmupStatus).toBe('idle');
    } finally {
      act(() => {
        useTTSStore.setState({ ttsWarmupStatus: 'idle' });
      });
    }
  });

  it('hides the pre-load indicators while the warm-up has not started', async () => {
    render(
      <VoiceTab
        preferences={{
          tts_provider: 'kokoro',
          tts_voice: 'default',
          tts_local_voice: 'default',
          ui_language: 'en-US',
          notifications_enabled: true,
          voice_mode_enabled: true,
          dark_mode: false,
          dwell_time: 0,
          ignore_repeats: 0,
          high_contrast: false,
        }}
        setPreferences={vi.fn()}
        filteredVoices={[]}
        showStatus
      />
    );

    expect(screen.queryByTestId('tts-warmup-indicator')).not.toBeInTheDocument();
    expect(screen.queryByTestId('speech-warmup-indicator')).not.toBeInTheDocument();
    expect(screen.queryByTestId('vector-warmup-indicator')).not.toBeInTheDocument();
    // Flush the mount fetch inside act so its state update is not reported as
    // an un-acted update after the test body finishes.
    await waitFor(() => expect(get).toHaveBeenCalled());
  });

  it('toggles hover-to-speak and only shows the delay picker when enabled', async () => {
    const setPreferences = vi.fn();

    const { rerender } = render(
      <VoiceTab
        preferences={{
          tts_provider: 'browser',
          tts_voice: 'default',
          tts_local_voice: 'default',
          ui_language: 'en-US',
          notifications_enabled: true,
          voice_mode_enabled: true,
          dark_mode: false,
          dwell_time: 0,
          ignore_repeats: 0,
          high_contrast: false,
          hover_speak_enabled: false,
          hover_speak_delay_ms: 1000,
        }}
        setPreferences={setPreferences}
        filteredVoices={[]}
      />
    );

    const checkbox = screen.getByRole('checkbox', {
      name: 'Read suggestions aloud on hover',
    });
    expect(checkbox).not.toBeChecked();
    // The delay picker stays hidden while the feature is off.
    expect(
      screen.queryByRole('combobox', { name: 'Time before speaking' }),
    ).not.toBeInTheDocument();

    fireEvent.click(checkbox);
    // The checkbox is fully controlled, so the handler toggles from the
    // previous preference value instead of reading event.target.checked.
    const toggle = setPreferences.mock.calls[0][0] as (
      prev: { hover_speak_enabled: boolean },
    ) => { hover_speak_enabled: boolean };
    expect(toggle({ hover_speak_enabled: false })).toEqual({
      hover_speak_enabled: true,
    });
    expect(toggle({ hover_speak_enabled: true })).toEqual({
      hover_speak_enabled: false,
    });

    rerender(
      <VoiceTab
        preferences={{
          tts_provider: 'browser',
          tts_voice: 'default',
          tts_local_voice: 'default',
          ui_language: 'en-US',
          notifications_enabled: true,
          voice_mode_enabled: true,
          dark_mode: false,
          dwell_time: 0,
          ignore_repeats: 0,
          high_contrast: false,
          hover_speak_enabled: true,
          hover_speak_delay_ms: 1000,
        }}
        setPreferences={setPreferences}
        filteredVoices={[]}
      />
    );

    const delaySelect = screen.getByRole('combobox', { name: 'Time before speaking' });
    expect(delaySelect).toHaveValue('1000');

    fireEvent.change(delaySelect, { target: { value: '2000' } });
    const update = setPreferences.mock.calls[1][0] as (
      prev: { hover_speak_delay_ms: number },
    ) => { hover_speak_delay_ms: number };
    expect(update({ hover_speak_delay_ms: 1000 })).toEqual({
      hover_speak_delay_ms: 2000,
    });

    await waitFor(() => expect(get).toHaveBeenCalled());
  });
});
