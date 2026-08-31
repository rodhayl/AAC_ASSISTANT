import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LearningSessionResponse } from '../src/types';
import { useVoiceRecorder } from '../src/components/learning/useVoiceRecorder';

class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];
  readonly mimeType = 'audio/webm;codecs=opus';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  state: 'inactive' | 'recording' = 'inactive';

  constructor(readonly stream: MediaStream) {
    FakeMediaRecorder.instances.push(this);
  }

  start() {
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
  }

  finishStop() {
    this.onstop?.();
  }
}

type Track = { stop: ReturnType<typeof vi.fn> };

type TestStream = MediaStream & { track: Track };

function makeStream(): TestStream {
  const track = { stop: vi.fn() };
  return {
    track,
    getTracks: () => [track],
  } as unknown as TestStream;
}

function makeOptions() {
  return {
    currentSession: { session_id: 42 } as LearningSessionResponse,
    isLoading: false,
    sessionDifficulty: 'adaptive',
    sessionTopic: 'Audio Conversation',
    startSession: vi.fn().mockResolvedValue(undefined),
    submitVoiceAnswer: vi.fn().mockResolvedValue(undefined),
    addToast: vi.fn(),
    microphoneAccessMessage: 'Microphone unavailable',
  };
}

describe('useVoiceRecorder lifecycle', () => {
  beforeEach(() => {
    FakeMediaRecorder.instances = [];
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('passes the selected default mode when voice starts a new session', async () => {
    const stream = makeStream();
    const options = {
      ...makeOptions(),
      currentSession: null,
      userId: 7,
      modeKey: 'roleplay',
    };
    vi.stubGlobal('navigator', {
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    const { result } = renderHook(() => useVoiceRecorder(options));

    await act(async () => {
      await result.current.startRecording();
    });

    expect(options.startSession).toHaveBeenCalledWith(
      expect.objectContaining({
        topic: 'Audio Conversation',
        purpose: 'voice',
        mode_key: 'roleplay',
      }),
      7,
    );
  });

  it('does not resurrect a discarded recording when stop is delivered late', async () => {
    const stream = makeStream();
    vi.stubGlobal('navigator', {
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    const { result } = renderHook(() => useVoiceRecorder(makeOptions()));

    await act(async () => {
      await result.current.startRecording();
    });
    const recorder = FakeMediaRecorder.instances[0];
    expect(result.current.isRecording).toBe(true);

    act(() => result.current.discardRecording());
    expect(stream.track.stop).toHaveBeenCalledTimes(1);

    act(() => recorder.finishStop());
    expect(result.current.isRecording).toBe(false);
    expect(result.current.hasRecording).toBe(false);
  });

  it('does not let a stale recorder callback stop a newer stream', async () => {
    const firstStream = makeStream();
    const secondStream = makeStream();
    const getUserMedia = vi.fn()
      .mockResolvedValueOnce(firstStream)
      .mockResolvedValueOnce(secondStream);
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });
    const { result } = renderHook(() => useVoiceRecorder(makeOptions()));

    await act(async () => {
      await result.current.startRecording();
    });
    const firstRecorder = FakeMediaRecorder.instances[0];
    act(() => result.current.discardRecording());

    await act(async () => {
      await result.current.startRecording();
    });
    const secondRecorder = FakeMediaRecorder.instances[1];
    act(() => firstRecorder.finishStop());

    expect(firstStream.track.stop).toHaveBeenCalledTimes(1);
    expect(secondStream.track.stop).not.toHaveBeenCalled();
    expect(result.current.isRecording).toBe(true);

    act(() => {
      secondRecorder.ondataavailable?.({ data: new Blob(['audio']) });
      result.current.stopRecording();
    });
    act(() => secondRecorder.finishStop());
    expect(result.current.hasRecording).toBe(true);
  });

  it('cancels a pending microphone request when discarded', async () => {
    const stream = makeStream();
    let resolveStream: ((value: TestStream) => void) | undefined;
    const getUserMedia = vi.fn().mockImplementation(() => new Promise<TestStream>((resolve) => {
      resolveStream = resolve;
    }));
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });
    const { result } = renderHook(() => useVoiceRecorder(makeOptions()));

    let startPromise: Promise<void> | undefined;
    act(() => {
      startPromise = result.current.startRecording();
    });
    act(() => result.current.discardRecording());

    await act(async () => {
      resolveStream?.(stream);
      await startPromise;
    });

    expect(FakeMediaRecorder.instances).toHaveLength(0);
    expect(stream.track.stop).toHaveBeenCalledTimes(1);
    expect(result.current.isRecording).toBe(false);
    expect(result.current.hasRecording).toBe(false);
  });

  it('ignores a concurrent start while microphone access is pending', async () => {
    const stream = makeStream();
    let resolveStream: ((value: TestStream) => void) | undefined;
    const getUserMedia = vi.fn().mockImplementation(() => new Promise<TestStream>((resolve) => {
      resolveStream = resolve;
    }));
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });
    const { result } = renderHook(() => useVoiceRecorder(makeOptions()));

    let firstStart: Promise<void> | undefined;
    act(() => {
      firstStart = result.current.startRecording();
    });
    await act(async () => {
      await result.current.startRecording();
    });
    expect(getUserMedia).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveStream?.(stream);
      await firstStart;
    });
    expect(result.current.isRecording).toBe(true);
    expect(FakeMediaRecorder.instances).toHaveLength(1);
  });

  it('uses the recorder MIME type and ignores duplicate sends', async () => {
    const stream = makeStream();
    const options = makeOptions();
    let resolveSubmit: (() => void) | undefined;
    options.submitVoiceAnswer.mockImplementation(() => new Promise<void>((resolve) => {
      resolveSubmit = resolve;
    }));
    vi.stubGlobal('navigator', {
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    const { result } = renderHook(() => useVoiceRecorder(options));

    await act(async () => {
      await result.current.startRecording();
    });
    const recorder = FakeMediaRecorder.instances[0];
    act(() => recorder.ondataavailable?.({ data: new Blob(['audio'], { type: 'audio/webm' }) }));
    act(() => result.current.stopRecording());
    act(() => recorder.finishStop());

    let firstSend: Promise<void> | undefined;
    act(() => {
      firstSend = result.current.sendRecording();
      void result.current.sendRecording();
    });
    expect(options.submitVoiceAnswer).toHaveBeenCalledTimes(1);
    expect(options.submitVoiceAnswer.mock.calls[0][1]).toBeInstanceOf(Blob);
    expect(options.submitVoiceAnswer.mock.calls[0][1].type).toBe('audio/webm;codecs=opus');

    await act(async () => {
      resolveSubmit?.();
      await firstSend;
    });
    expect(result.current.hasRecording).toBe(false);
  });

  it('releases the microphone and ignores a late stop after unmount', async () => {
    const stream = makeStream();
    vi.stubGlobal('navigator', {
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    const { result, unmount } = renderHook(() => useVoiceRecorder(makeOptions()));

    await act(async () => {
      await result.current.startRecording();
    });
    const recorder = FakeMediaRecorder.instances[0];
    unmount();

    expect(stream.track.stop).toHaveBeenCalledTimes(1);
    expect(() => recorder.finishStop()).not.toThrow();
  });
});
