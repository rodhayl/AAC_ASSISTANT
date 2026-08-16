import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Mic } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { initLocalSTT, transcribeAudio } from '../../lib/stt';
import { useToastStore } from '../../store/toastStore';

interface PartnerOverlayProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Partner microphone overlay for the communication board.
 *
 * Prefers the backend's local faster-whisper speech-to-text (which works in
 * every browser, including Firefox on Linux). When that optional extra is
 * missing, it falls back to the browser's SpeechRecognition API (Chrome/Edge).
 */
export function PartnerOverlay({ isOpen, onClose }: PartnerOverlayProps) {
  const { t, i18n } = useTranslation('boards');
  const addToast = useToastStore((state) => state.addToast);
  const [transcript, setTranscript] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const mimeTypeRef = useRef('audio/webm');
  const isMounted = useRef(false);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  const stopBrowserRecognition = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        /* an already-stopped recognition may throw */
      }
      recognitionRef.current = null;
    }
  }, []);

  const releaseStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }, []);

  const stopLocalRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
  }, []);

  const stopListening = useCallback(() => {
    stopBrowserRecognition();
    stopLocalRecording();
    if (isMounted.current) {
      setIsListening(false);
    }
  }, [stopBrowserRecognition, stopLocalRecording]);

  const transcribe = useCallback(
    async (blob: Blob) => {
      try {
        const text = await transcribeAudio(blob, i18n.language || 'es');
        if (isMounted.current) setTranscript(text);
      } catch {
        if (isMounted.current) {
          setTranscript(t('speechNotAvailable', 'Speech recognition is not available.'));
          addToast(
            t('transcriptionFailed', 'Could not transcribe the recording.'),
            'error',
          );
        }
      }
    },
    [i18n.language, t, addToast],
  );

  const startLocalRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!isMounted.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const mediaRecorder = new MediaRecorder(stream);
      mimeTypeRef.current = mediaRecorder.mimeType || 'audio/webm';
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      mediaRecorder.onstop = () => {
        if (!isMounted.current) return;
        const blob = new Blob(chunksRef.current, { type: mimeTypeRef.current });
        chunksRef.current = [];
        mediaRecorderRef.current = null;
        releaseStream();
        if (blob.size === 0) {
          setIsListening(false);
          return;
        }
        setIsListening(false);
        setIsTranscribing(true);
        void transcribe(blob).finally(() => {
          if (isMounted.current) setIsTranscribing(false);
        });
      };

      mediaRecorder.start();
      if (isMounted.current) setIsListening(true);
    } catch (error) {
      console.warn('Microphone access was denied or unavailable:', error);
      releaseStream();
      if (isMounted.current) {
        setTranscript(t('speechNotAvailable', 'Speech recognition is not available.'));
        addToast(
          t('microphoneAccessError', 'Microphone access was denied or unavailable.'),
          'error',
        );
      }
    }
  }, [releaseStream, transcribe, t, addToast]);

  const startBrowserListening = useCallback(() => {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      setTranscript(t('speechNotSupported', 'Speech recognition not supported in this browser.'));
      return;
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognitionRef.current = recognition;

    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = i18n.language || 'es-ES';

    recognition.onstart = () => {
      if (isMounted.current) setIsListening(true);
    };
    recognition.onend = () => {
      if (isMounted.current) setIsListening(false);
    };
    recognition.onerror = () => {
      if (isMounted.current) {
        setIsListening(false);
        setTranscript(t('speechNotAvailable', 'Speech recognition is not available.'));
      }
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    recognition.onresult = (event: any) => {
      let finalTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        finalTranscript += event.results[i][0].transcript;
      }
      if (isMounted.current) setTranscript(finalTranscript);
    };

    recognition.start();
  }, [i18n.language, t]);

  const startListening = useCallback(async () => {
    const available = await initLocalSTT();
    if (!isMounted.current) return;
    if (available) {
      await startLocalRecording();
    } else {
      startBrowserListening();
    }
  }, [startLocalRecording, startBrowserListening]);

  const resetForClose = useCallback(() => {
    stopListening();
    setTranscript('');
  }, [stopListening]);

  // Auto-start/stop only when the overlay opens or closes. Depending on the
  // (stable) callbacks would re-run the effect whenever a translation
  // function identity changes mid-recording and start a second microphone
  // stream, so the effect is keyed on isOpen alone.
  useEffect(() => {
    if (!isOpen) {
      // Deliberate close transition: the overlay renders nothing while closed,
      // so resetting its internal state is a prop-to-state sync, not a derived
      // render optimization.
      resetForClose();
      return undefined;
    }
    void startListening();
    return () => {
      stopBrowserRecognition();
      stopLocalRecording();
      releaseStream();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm" role="presentation">
      <div
        className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-3xl p-6 flex flex-col items-center text-center relative"
        role="dialog"
        aria-modal="true"
        aria-labelledby="partner-overlay-title"
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 rounded-full bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600"
          aria-label={t('close', 'Close')}
        >
          <X className="w-6 h-6" />
        </button>

        <div className="mb-6">
          <div className={`p-4 rounded-full inline-flex items-center justify-center ${isListening ? 'bg-red-100 text-red-600 animate-pulse' : 'bg-gray-100 text-gray-500'}`}>
            <Mic className="w-12 h-12" />
          </div>
          <h2 id="partner-overlay-title" className="mt-4 text-xl font-semibold text-gray-900 dark:text-gray-100">
            {isTranscribing
              ? t('transcribing', 'Transcribing...')
              : isListening
                ? t('listening', 'Listening to partner...')
                : t('paused', 'Paused')}
          </h2>
        </div>

        <div className="w-full min-h-[200px] bg-gray-50 dark:bg-gray-900/50 rounded-xl p-6 flex items-center justify-center border-2 border-dashed border-gray-200 dark:border-gray-700 overflow-y-auto max-h-[60vh]">
          {transcript ? (
            <p className="text-3xl md:text-4xl font-bold text-gray-800 dark:text-gray-100 leading-relaxed">
              "{transcript}"
            </p>
          ) : (
            <p className="text-gray-400 italic text-xl">
              {isTranscribing
                ? t('transcribing', 'Transcribing...')
                : t('waitingForSpeech', 'Waiting for speech...')}
            </p>
          )}
        </div>

        <div className="mt-6 flex gap-4">
          <button
            onClick={() => {
              if (isListening || isTranscribing) stopListening();
              else void startListening();
            }}
            disabled={isTranscribing}
            className={`px-6 py-3 rounded-xl text-white font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${isListening ? 'bg-red-500 hover:bg-red-600' : 'bg-indigo-600 hover:bg-indigo-700'}`}
          >
            {isListening
              ? t('stopListening', 'Stop Listening')
              : t('startListening', 'Start Listening')}
          </button>
        </div>
      </div>
    </div>
  );
}
