import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { VoiceTab } from '../src/pages/Settings/VoiceTab';

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../src/lib/api', () => ({
  default: {
    get,
    post,
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

    get.mockResolvedValue({
      data: {
        stt: { provider: 'faster-whisper', installed: false, model: 'small' },
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
});
