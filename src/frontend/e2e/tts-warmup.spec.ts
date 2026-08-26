import { expect, test, type Page } from '@playwright/test';

/**
 * Verifies the lazy TTS warm-up contract end-to-end:
 *
 *   1. When the authenticated app loads, the browser warms every lazy model
 *      in the background: it pre-checks the local neural TTS capability
 *      (`/providers/voice-status`) and asks the backend to pre-load Kokoro
 *      and faster-whisper in one batched request (`/providers/warmup`) — all
 *      before any conversation starts.
 *   2. When a conversation produces its first spoken message, the queue
 *      synthesizes immediately (`/providers/tts/synthesize`): there is NO
 *      capability round-trip on the speak path (the check was cached during
 *      warm-up) and the first synthesis fires right after the message exists,
 *      so it never waits for the model.
 *
 * The TTS endpoints and the LLM-backed learning endpoints are mocked so the
 * spec is deterministic — it must not depend on kokoro-onnx being installed
 * or on a real LLM. Auth, routing, stores and the TTS queue are the real
 * frontend code, and everything else hits the real backend.
 */

interface ObservedRequest {
  url: string;
  method: string;
  at: number;
  postData?: string;
}

interface AudioPlayCall {
  src: string;
  resolved: boolean;
  rejected: string | null;
}

/** Window property set by the audio-play instrumentation script. */
interface InstrumentedWindow {
  __aacAudioPlayCalls?: AudioPlayCall[];
}

function audioPlayCalls(page: Page): Promise<AudioPlayCall[]> {
  return page.evaluate(() => {
    const win = window as unknown as InstrumentedWindow;
    return win.__aacAudioPlayCalls ?? [];
  });
}

/** A minimal valid 16-bit mono WAV so the synthesized audio has a duration. */
function minimalWav(): Buffer {
  const sampleRate = 8000;
  const numSamples = 160; // 20ms
  const dataSize = numSamples * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write('WAVE', 8);
  buffer.write('fmt ', 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20); // PCM
  buffer.writeUInt16LE(1, 22); // mono
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28); // byte rate
  buffer.writeUInt16LE(2, 32); // block align
  buffer.writeUInt16LE(16, 34); // bits per sample
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataSize, 40);
  return buffer;
}

const WELCOME_MESSAGE = 'Welcome! Let us practice speaking together.';

// The synthesized audio is played on a detached <audio> element without a
// user gesture; headless Chromium's autoplay policy would reject play()
// with NotAllowedError. This flag only lifts the browser's gesture
// requirement so playback can start in the automated run.
test.use({ launchOptions: { args: ['--autoplay-policy=no-user-gesture-required'] } });

test.describe('TTS warm-up', () => {
  test.use({ storageState: 'playwright/.auth/admin.json' });

  test('first spoken message of a conversation synthesizes without waiting for the model', async ({ page }) => {
    const requests: ObservedRequest[] = [];
    page.on('request', (req) => {
      requests.push({
        url: req.url(),
        method: req.method(),
        at: Date.now(),
        postData: req.method() === 'POST' ? req.postData() ?? undefined : undefined,
      });
    });

    // Instrument browser audio playback: record every play() call on an
    // <audio> element (its blob URL and whether playback actually started)
    // so the test can assert the synthesized audio is really played, not
    // merely requested.
    await page.addInitScript(() => {
      const calls: Array<{ src: string; resolved: boolean; rejected: string | null }> = [];
      (window as unknown as { __aacAudioPlayCalls?: typeof calls }).__aacAudioPlayCalls = calls;
      const originalPlay = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function () {
        const entry = { src: this.src || '', resolved: false, rejected: null as string | null };
        calls.push(entry);
        const promise = originalPlay.call(this);
        promise
          .then(() => { entry.resolved = true; })
          .catch((err: unknown) => { entry.rejected = String((err as Error)?.name ?? err); });
        return promise;
      };
    });

    // Force the persisted account to use the local neural TTS provider so the
    // test is independent of the account's stored voice preference.
    await page.addInitScript(() => {
      const raw = localStorage.getItem('auth-storage');
      if (!raw) return;
      try {
        const stored = JSON.parse(raw) as { state?: { user?: { settings?: Record<string, unknown> } } };
        const settings = stored.state?.user?.settings;
        if (settings) {
          settings.tts_provider = 'kokoro';
          settings.voice_mode_enabled = true;
          settings.tts_local_voice = 'default';
          settings.ui_language = 'en';
        }
        localStorage.setItem('auth-storage', JSON.stringify(stored));
      } catch {
        // Ignore: the store default provider is kokoro anyway.
      }
    });

    // Mock the TTS backend so the capability check and synthesis always work.
    await page.route('**/api/providers/voice-status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ tts_local: { available: true } }),
      });
    });
    await page.route('**/api/providers/warmup', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ tts: { warmed: true }, speech: { warmed: true } }),
      });
    });
    await page.route('**/api/providers/tts/synthesize', async (route) => {
      await route.fulfill({ status: 200, contentType: 'audio/wav', body: minimalWav() });
    });

    // Mock the LLM-backed learning calls so the welcome message is instant.
    // Regex (not a glob) because the start URL carries a `?user_id=` query
    // string that glob patterns do not match.
    await page.route(/\/api\/learning\/start(?:\?|$)/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          session_id: 9001,
          welcome_message: WELCOME_MESSAGE,
        }),
      });
    });
    await page.route('**/api/learning/*/ask', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          question_id: 1,
          question_text: 'What is your name?',
          choices: ['A', 'B', 'C'],
          provider_used: 'groq',
        }),
      });
    });

    await page.goto('/learning');

    // The warm-up must fire on page load, before any conversation starts:
    // one batched request pre-loads both backend models.
    await expect.poll(() => requests.some((r) => r.url.includes('/providers/warmup')), {
      timeout: 15000,
    }).toBe(true);

    const warmupAt = requests.find((r) => r.url.includes('/providers/warmup'))!.at;

    // Start a conversation; the mocked welcome arrives instantly.
    const startBtn = page.locator('[data-testid="learning-session-start"]');
    await expect(startBtn).toBeVisible({ timeout: 15000 });
    await startBtn.click();

    // The conversation's first message is displayed...
    await expect(page.getByText(WELCOME_MESSAGE)).toBeVisible({ timeout: 15000 });

    // ...and it is spoken immediately: the first synthesis request fires
    // right after the start request, without a capability re-check.
    await expect.poll(() => requests.some((r) => r.url.includes('/providers/tts/synthesize')), {
      timeout: 15000,
    }).toBe(true);

    // The synthesized audio must actually play in the browser, not just be
    // requested: an <audio> element is created from the blob and its play()
    // promise settles as resolved (playback started). Wait for the promise
    // to settle rather than asserting right after the call is recorded.
    await expect.poll(async () => {
      const calls = await audioPlayCalls(page);
      const first = calls[0];
      return first && (first.resolved || first.rejected !== null) ? first : null;
    }, { timeout: 15000 }).not.toBeNull();
    const playCalls = await audioPlayCalls(page);
    expect(playCalls[0].src.startsWith('blob:')).toBe(true);
    expect(playCalls[0].rejected).toBeNull();
    expect(playCalls[0].resolved).toBe(true);

    const startAt = requests.find((r) => r.url.includes('/api/learning/start'))!.at;
    const synth = requests.find((r) => r.url.includes('/providers/tts/synthesize'))!;
    const synthAt = synth.at;

    // Warm-up happened before the conversation began.
    expect(warmupAt).toBeLessThan(startAt);

    // The first spoken message was the conversation's welcome message.
    const synthBody = JSON.parse(synth.postData ?? '{}') as { text?: string };
    expect(synthBody.text).toContain(WELCOME_MESSAGE);

    // The start request is mocked (instant), so a healthy warm pipeline
    // synthesizes within a second. A pipeline that waited for the model or
    // for a fresh capability check would blow well past this bound.
    expect(synthAt - startAt).toBeLessThan(3000);

    // The capability was pre-cached during warm-up: the speak path never
    // re-checked voice-status. Exactly one check, from the warm-up itself,
    // before the conversation.
    const voiceStatusCalls = requests.filter((r) => r.url.includes('/providers/voice-status'));
    expect(voiceStatusCalls).toHaveLength(1);
    expect(voiceStatusCalls[0].at).toBeLessThan(startAt);

    // The consolidated warm-up replaced the per-model endpoints: exactly one
    // batched request, and no calls to the removed individual endpoints.
    const warmupCalls = requests.filter((r) => r.url.includes('/providers/warmup'));
    expect(warmupCalls).toHaveLength(1);
    expect(warmupCalls[0].at).toBeLessThan(startAt);
    expect(requests.some((r) => r.url.includes('/providers/tts/warmup'))).toBe(false);
    expect(requests.some((r) => r.url.includes('/providers/speech/warmup'))).toBe(false);

    // The batched request pre-loads every lazy model: Kokoro, faster-whisper,
    // and the fastembed semantic index.
    const warmupBody = JSON.parse(warmupCalls[0].postData ?? '{}') as { targets?: string[] };
    expect(warmupBody.targets?.slice().sort()).toEqual(['speech', 'tts', 'vector']);
  });
});
