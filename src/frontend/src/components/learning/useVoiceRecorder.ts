import { useCallback, useEffect, useRef, useState } from 'react';
import type { ToastType } from '../../store/toastStore';
import type { LearningSessionResponse } from '../../types';

interface UseVoiceRecorderOptions {
  currentSession: LearningSessionResponse | null;
  userId?: number;
  isLoading: boolean;
  sessionDifficulty: string;
  sessionTopic: string;
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
  sessionTopic,
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
  const recordingMimeTypeRef = useRef('audio/wav');
  const recordingSessionIdRef = useRef<number | null>(null);
  const recordingUserIdRef = useRef<number | null>(null);
  const recordingGenerationRef = useRef(0);
  const mountedRef = useRef(true);
  const startInFlightRef = useRef(false);
  const sendInFlightRef = useRef(false);
  const activeSessionIdRef = useRef<number | null>(currentSession?.session_id ?? null);
  const activeUserIdRef = useRef<number | null>(userId ?? null);
  activeSessionIdRef.current = currentSession?.session_id ?? null;
  activeUserIdRef.current = userId ?? null;

  const stopStream = useCallback((stream: MediaStream) => {
    stream.getTracks().forEach((track) => track.stop());
  }, []);

  const releaseStream = useCallback(() => {
    if (streamRef.current) {
      stopStream(streamRef.current);
      streamRef.current = null;
    }
  }, [stopStream]);

  const startRecording = useCallback(async () => {
    if (!mountedRef.current || startInFlightRef.current || mediaRecorderRef.current) return;

    startInFlightRef.current = true;
    const generation = recordingGenerationRef.current + 1;
    recordingGenerationRef.current = generation;
    recordingSessionIdRef.current = currentSession?.session_id ?? null;
    recordingUserIdRef.current = userId ?? null;
    try {
      if (!currentSession && userId) {
        await startSession({
          topic: sessionTopic,
          purpose: 'voice',
          difficulty: sessionDifficulty,
        }, userId);
      }
      if (
        !mountedRef.current ||
        recordingGenerationRef.current !== generation ||
        activeUserIdRef.current !== (userId ?? null) ||
        (currentSession && activeSessionIdRef.current !== currentSession.session_id)
      ) return;

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (
        !mountedRef.current ||
        recordingGenerationRef.current !== generation ||
        activeUserIdRef.current !== (userId ?? null) ||
        (currentSession && activeSessionIdRef.current !== currentSession.session_id)
      ) {
        stopStream(stream);
        return;
      }
      streamRef.current = stream;
      const mediaRecorder = new MediaRecorder(stream);
      recordingMimeTypeRef.current = mediaRecorder.mimeType || 'audio/wav';
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        // A discarded recorder can deliver data after a new recording starts.
        // Keep stale chunks out of the current recording.
        if (generation === recordingGenerationRef.current && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        // Discard/unmount can stop a recorder asynchronously. Do not let that
        // late callback resurrect a recording or clean up a newer recording.
        if (generation !== recordingGenerationRef.current) {
          return;
        }
        setHasRecording(chunksRef.current.length > 0);
        if (streamRef.current === stream) {
          releaseStream();
        } else {
          stopStream(stream);
        }
        if (mediaRecorderRef.current === mediaRecorder) {
          mediaRecorderRef.current = null;
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (error) {
      console.warn('Microphone access was denied or unavailable:', error);
      if (
        !mountedRef.current ||
        recordingGenerationRef.current !== generation ||
        activeUserIdRef.current !== (userId ?? null)
      ) return;
      setIsRecording(false);
      mediaRecorderRef.current = null;
      chunksRef.current = [];
      releaseStream();
      addToast(microphoneAccessMessage, 'error');
    } finally {
      startInFlightRef.current = false;
    }
  }, [
    addToast,
    currentSession,
    microphoneAccessMessage,
    releaseStream,
    stopStream,
    sessionDifficulty,
    sessionTopic,
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
    recordingMimeTypeRef.current = 'audio/wav';
    recordingSessionIdRef.current = null;
    recordingUserIdRef.current = null;
    setHasRecording(false);
    releaseStream();
  }, [releaseStream]);

  const sendRecording = useCallback(async () => {
    if (
      !mountedRef.current ||
      sendInFlightRef.current ||
      !currentSession ||
      chunksRef.current.length === 0 ||
      isLoading ||
      (recordingSessionIdRef.current !== null &&
        recordingSessionIdRef.current !== currentSession.session_id) ||
      recordingUserIdRef.current !== (userId ?? null)
    ) {
      return;
    }

    sendInFlightRef.current = true;
    const sendGeneration = recordingGenerationRef.current;
    const sendSessionId = currentSession.session_id;
    const sendUserId = userId ?? null;
    const audioBlob = new Blob(chunksRef.current, { type: recordingMimeTypeRef.current });
    try {
      await submitVoiceAnswer(sendSessionId, audioBlob);
      if (
        mountedRef.current &&
        recordingGenerationRef.current === sendGeneration &&
        activeSessionIdRef.current === sendSessionId &&
        activeUserIdRef.current === sendUserId
      ) {
        chunksRef.current = [];
        recordingMimeTypeRef.current = 'audio/wav';
        recordingSessionIdRef.current = null;
        recordingUserIdRef.current = null;
        setHasRecording(false);
      }
    } finally {
      sendInFlightRef.current = false;
    }
  }, [currentSession, isLoading, submitVoiceAnswer, userId]);

  useEffect(() => {
    if (
      (mediaRecorderRef.current || hasRecording) &&
      ((recordingSessionIdRef.current !== null &&
        recordingSessionIdRef.current !== currentSession?.session_id) ||
        recordingUserIdRef.current !== (userId ?? null))
    ) {
      discardRecording();
    } else if ((mediaRecorderRef.current || hasRecording) && recordingSessionIdRef.current === null) {
      recordingSessionIdRef.current = currentSession?.session_id ?? null;
    }
  }, [currentSession?.session_id, discardRecording, hasRecording, userId]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      recordingGenerationRef.current += 1;
      if (mediaRecorderRef.current?.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
      mediaRecorderRef.current = null;
      releaseStream();
      chunksRef.current = [];
      recordingMimeTypeRef.current = 'audio/wav';
      recordingSessionIdRef.current = null;
      recordingUserIdRef.current = null;
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
