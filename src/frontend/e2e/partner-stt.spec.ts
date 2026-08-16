import { test, expect } from '@playwright/test';

// Headless browsers do not implement getUserMedia or MediaRecorder. These
// shims let the real local STT flow run end-to-end: the overlay records (fake
// microphone), stops, and uploads a genuine WAV to the real
// /api/providers/transcribe endpoint, which the backend transcribes with
// faster-whisper. The blob carries a valid RIFF/WAVE header so the backend's
// audio signature check accepts it.
const mediaShims = `(() => {
  const writeString = (view, offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  const makeWav = () => {
    const sampleRate = 16000;
    const numSamples = sampleRate; // 1 second of silence
    const buffer = new ArrayBuffer(44 + numSamples * 2);
    const view = new DataView(buffer);
    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + numSamples * 2, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, 'data');
    view.setUint32(40, numSamples * 2, true);
    return new Blob([buffer], { type: 'audio/wav' });
  };

  const fakeStream = { getTracks: () => [{ stop() {} }] };
  const fakeMediaDevices = { getUserMedia: async () => fakeStream };
  try {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: fakeMediaDevices,
    });
  } catch {
    try {
      Object.defineProperty(Navigator.prototype, 'mediaDevices', {
        configurable: true,
        value: fakeMediaDevices,
      });
    } catch {
      /* engine keeps its native mediaDevices; the local path cannot run */
    }
  }

  class FakeMediaRecorder {
    constructor() {
      this.mimeType = 'audio/wav';
      this.state = 'inactive';
      this.ondataavailable = null;
      this.onstop = null;
    }
    start() {
      this.state = 'recording';
    }
    stop() {
      this.state = 'inactive';
      if (typeof this.ondataavailable === 'function') {
        this.ondataavailable({ data: makeWav() });
      }
      if (typeof this.onstop === 'function') {
        this.onstop();
      }
    }
  }
  window.MediaRecorder = FakeMediaRecorder;
})();`;

test.describe('Partner overlay local speech-to-text', () => {
  test.use({ storageState: 'playwright/.auth/student.json' });

  test('records and transcribes through the local endpoint', async ({ page }) => {
    await page.addInitScript(mediaShims);
    await page.goto('/communication');

    // The partner overlay prefers the backend faster-whisper engine. Skip when
    // the optional voice extra is not installed on this server, because the
    // local transcription endpoint does not exist in that case and the overlay
    // correctly falls back to the browser SpeechRecognition API instead.
    const sttAvailable = await page.evaluate(async () => {
      let token = '';
      try {
        const raw = localStorage.getItem('auth-storage');
        token = raw ? (JSON.parse(raw).state?.token ?? '') : '';
      } catch {
        /* token stays empty */
      }
      try {
        const res = await fetch('/api/providers/voice-status', {
          headers: { Authorization: `Bearer ${token}` },
        });
        return res.ok ? Boolean((await res.json())?.stt?.available) : false;
      } catch {
        return false;
      }
    });
    test.skip(!sttAvailable, 'faster-whisper voice extra is not installed on this server');

    // Open the seeded board, then the partner microphone overlay.
    const board = page.getByRole('button', { name: /General Communication/ }).first();
    await expect(board).toBeVisible();
    await board.click();
    await expect(
      page.getByRole('button', { name: /Add .* to sentence/ }).first(),
    ).toBeVisible();

    await page.getByTitle('Listen').click();
    await expect(
      page.getByRole('dialog', { name: /Listening to partner/ }),
    ).toBeVisible();

    // Stopping the recording uploads the captured WAV to the real local
    // transcription endpoint; the backend transcribes it and answers 200.
    const transcribeResponse = page.waitForResponse(
      (r) => r.url().includes('/api/providers/transcribe') && r.request().method() === 'POST',
      { timeout: 60000 },
    );
    await page.getByRole('button', { name: /Stop Listening/ }).click();
    const response = await transcribeResponse;
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.provider).toBe('local');
    expect(typeof body.text).toBe('string');

    // Once the transcription request settles, the overlay returns to a paused
    // state ready for the next recording.
    await expect(page.getByRole('dialog', { name: /Paused/ })).toBeVisible();
  });
});
