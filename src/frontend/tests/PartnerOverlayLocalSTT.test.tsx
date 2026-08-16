import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { PartnerOverlay } from '../src/components/board/PartnerOverlay';

// The component prefers the local STT engine; drive it deterministically.
vi.mock('../src/lib/stt', () => ({
  initLocalSTT: vi.fn().mockResolvedValue(true),
  transcribeAudio: vi.fn().mockResolvedValue('hola amigo'),
}));

vi.mock('lucide-react', () => ({
  X: () => <div data-testid="icon-x" />,
  Mic: () => <div data-testid="icon-mic" />,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultVal: string) => defaultVal || key,
    i18n: { language: 'es-ES' },
  }),
  initReactI18next: { type: '3rdParty', init: () => {} },
}));

class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];
  readonly mimeType = 'audio/webm';
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

function makeStream(): MediaStream {
  return { getTracks: () => [{ stop: vi.fn() }] } as unknown as MediaStream;
}

describe('PartnerOverlay local STT', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    FakeMediaRecorder.instances = [];
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    vi.stubGlobal('navigator', {
      mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(makeStream()) },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('records with MediaRecorder and shows the transcription when local STT is available', async () => {
    render(<PartnerOverlay isOpen={true} onClose={vi.fn()} />);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    // The local engine was chosen: MediaRecorder was created, no browser API.
    expect(FakeMediaRecorder.instances).toHaveLength(1);
    expect(screen.getByText(/Listening to partner/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    // Simulate captured audio, then a stop that triggers transcription.
    act(() => {
      FakeMediaRecorder.instances[0].ondataavailable?.({ data: new Blob(['audio']) });
    });
    act(() => {
      FakeMediaRecorder.instances[0].stop();
      FakeMediaRecorder.instances[0].finishStop();
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.getByText(/hola amigo/)).toBeInTheDocument();
  });

  it('falls back to an error message when local transcription fails', async () => {
    const { transcribeAudio } = await import('../src/lib/stt');
    vi.mocked(transcribeAudio).mockRejectedValueOnce(new Error('transcription failed'));

    render(<PartnerOverlay isOpen={true} onClose={vi.fn()} />);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    act(() => {
      FakeMediaRecorder.instances[0].ondataavailable?.({ data: new Blob(['audio']) });
    });
    act(() => {
      FakeMediaRecorder.instances[0].stop();
      FakeMediaRecorder.instances[0].finishStop();
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.getByText(/Speech recognition is not available\./)).toBeInTheDocument();
  });
});
