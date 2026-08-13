import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    t: (key: string, defaultValue?: string) => defaultValue || key,
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
        preferences={{ tts_voice: 'default', ui_language: 'en-US', notifications_enabled: true, voice_mode_enabled: true, dark_mode: false, dwell_time: 0, ignore_repeats: 0, high_contrast: false }}
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
          tts_voice: 'default',
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
          tts_voice: 'default',
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
    expect(select).toBeEnabled();
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
});
