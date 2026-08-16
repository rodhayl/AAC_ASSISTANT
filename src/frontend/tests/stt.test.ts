import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('stt (local speech-to-text)', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.resetModules();
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('initLocalSTT resolves true when the backend reports STT available', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ stt: { available: true } }),
    });
    const { initLocalSTT, isLocalSTTAvailable } = await import('../src/lib/stt');

    await expect(initLocalSTT()).resolves.toBe(true);
    expect(isLocalSTTAvailable()).toBe(true);
  });

  it('initLocalSTT resolves false when the backend reports STT unavailable', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ stt: { available: false } }),
    });
    const { initLocalSTT } = await import('../src/lib/stt');

    await expect(initLocalSTT()).resolves.toBe(false);
  });

  it('initLocalSTT resolves false when the probe fails', async () => {
    fetchMock.mockRejectedValue(new Error('network down'));
    const { initLocalSTT } = await import('../src/lib/stt');

    await expect(initLocalSTT()).resolves.toBe(false);
  });

  it('transcribeAudio posts the blob and returns the recognized text', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ text: 'hola mundo' }),
    });
    const { transcribeAudio } = await import('../src/lib/stt');

    const text = await transcribeAudio(new Blob(['audio'], { type: 'audio/webm' }), 'es-ES');

    expect(text).toBe('hola mundo');
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/providers/transcribe?lang=es'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('transcribeAudio throws when the backend responds with an error', async () => {
    fetchMock.mockResolvedValue({ ok: false });
    const { transcribeAudio } = await import('../src/lib/stt');

    await expect(transcribeAudio(new Blob(['x']), 'en')).rejects.toThrow();
  });
});
