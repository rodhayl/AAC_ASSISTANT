import { useCallback, useEffect, useRef, useState } from 'react';
import type { ToastType } from '../../store/toastStore';
import type { LearningSessionResponse } from '../../types';

interface UseVoiceRecorderOptions {
  currentSession: LearningSessionResponse | null;
  userId?: number;
  isLoading: boolean;
  sessionDifficulty: string;
  startSession: (data: {
    topic: string;
    purpose: string;
    difficulty: string;
  }, userId: number) => Promise<void>;
  submitVoiceAnswer: (sessionId: number, audioBlob: Blob) => Promise<void>;
  addToast: (message: string, type?: ToastType) => void;
  microphoneAccessMessage: string;
}

interface UseVoiceRecorderResult {
  isRecording: boolean;
  hasRecording: boolean;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  discardRecording: () => void;
  sendRecording: () => Promise<void>;
}

/**
 * Owns the browser MediaRecorder lifecycle for Learning.
 *
 * The hook intentionally starts a voice session before requesting the
 * microphone, matching the previous page behavior. Permission failures are
 * caught here so the composer never remains in a recording state.
 */
export function useVoiceRecorder({
  currentSession,
  userId,
  isLoading,
  sessionDifficulty,
  startSession,
  submitVoiceAnswer,
  addToast,
  microphoneAccessMessage,
}: UseVoiceRecorderOptions): UseVoiceRecorderResult {
  const [isRecording, setIsRecording] = useState(false);
  const [hasRecording, setHasRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const recordingGenerationRef = useRef(0);

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const startRecording = useCallback(async () => {
    try {
      if (!currentSession && userId) {
        await startSession({
          topic: 'audio conversation',
          purpose: 'voice',
          difficulty: sessionDifficulty,
        }, userId);
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const generation = ++recordingGenerationRef.current;
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        // Discard/unmount can stop a recorder asynchronously. Do not let that
        // late callback resurrect a recording the user already discarded.
        if (generation === recordingGenerationRef.current) {
          setHasRecording(true);
        }
        releaseStream();
        mediaRecorderRef.current = null;
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (error) {
      console.warn('Microphone access was denied or unavailable:', error);
      setIsRecording(false);
      mediaRecorderRef.current = null;
      chunksRef.current = [];
      releaseStream();
      addToast(microphoneAccessMessage, 'error');
    }
  }, [
    addToast,
    currentSession,
    microphoneAccessMessage,
    releaseStream,
    sessionDifficulty,
    startSession,
    userId,
  ]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }, [isRecording]);

  const discardRecording = useCallback(() => {
    recordingGenerationRef.current += 1;
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
    mediaRecorderRef.current = null;
    chunksRef.current = [];
    setHasRecording(false);
    releaseStream();
  }, [releaseStream]);

  const sendRecording = useCallback(async () => {
    if (!currentSession || chunksRef.current.length === 0 || isLoading) {
      return;
    }

    const audioBlob = new Blob(chunksRef.current, { type: 'audio/wav' });
    await submitVoiceAnswer(currentSession.session_id, audioBlob);
    chunksRef.current = [];
    setHasRecording(false);
  }, [currentSession, isLoading, submitVoiceAnswer]);

  useEffect(() => {
    return () => {
      recordingGenerationRef.current += 1;
      if (mediaRecorderRef.current?.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
      mediaRecorderRef.current = null;
      releaseStream();
      chunksRef.current = [];
    };
  }, [releaseStream]);

  return {
    isRecording,
    hasRecording,
    startRecording,
    stopRecording,
    discardRecording,
    sendRecording,
  };
}
