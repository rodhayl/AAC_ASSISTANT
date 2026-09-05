import { useEffect, useRef } from 'react';
import { tts } from '../lib/tts';
import { stripReasoning } from '../store/learningStore';

interface SpeakableMessage {
  role: string;
  content: string;
}

let activeSpeechSurfaceCount = 0;
const INITIAL_SESSION_KEY = Symbol('initial-session-key');
type SpeechSessionKey = string | number | null;
const handledMessages = new WeakMap<SpeakableMessage, Set<SpeechSessionKey>>();

function markMessageHandled(message: SpeakableMessage, sessionKey: SpeechSessionKey): void {
  const sessionKeys = handledMessages.get(message) ?? new Set<SpeechSessionKey>();
  sessionKeys.add(sessionKey);
  handledMessages.set(message, sessionKeys);
}

function wasMessageHandled(message: SpeakableMessage, sessionKey: SpeechSessionKey): boolean {
  return handledMessages.get(message)?.has(sessionKey) ?? false;
}

interface AssistantSpeechOptions {
  messages: SpeakableMessage[];
  sessionKey: string | number | null;
  enabled: boolean;
  resolveText?: (content: string) => string;
  skipExistingOnSessionChange?: boolean;
}

/**
 * Single speech mechanism for assistant chat surfaces: every assistant
 * message appended to the store is enqueued into the shared TTS queue, in
 * order. The messages array is the only source of truth; callers never
 * enqueue chat messages directly.
 */
export function useAssistantMessageSpeech({
  messages,
  sessionKey,
  enabled,
  resolveText = stripReasoning,
  skipExistingOnSessionChange = false,
}: AssistantSpeechOptions) {
  const spokenCountRef = useRef(0);
  const sessionKeyRef = useRef<string | number | null | typeof INITIAL_SESSION_KEY>(INITIAL_SESSION_KEY);
  const skipExistingRef = useRef(false);
  const enabledRef = useRef(enabled);

  // Keep the singleton queue scoped to the active conversation. The store
  // cancels before request-time transitions; this also covers route changes
  // and components that receive a new session without going through the
  // page-level handlers.
  useEffect(() => {
    const isInitialRender = sessionKeyRef.current === INITIAL_SESSION_KEY;
    const sessionChanged = !isInitialRender && sessionKey !== sessionKeyRef.current;
    const historyWasLoaded = skipExistingOnSessionChange && !skipExistingRef.current;
    const voiceWasDisabled = !enabled && enabledRef.current;
    const messagesReset = !isInitialRender && !sessionChanged && messages.length < spokenCountRef.current;
    const initialIdleSurface = isInitialRender && (!enabled || sessionKey === null);
    const markMessagesHandled = () => {
      messages.forEach((message) => markMessageHandled(message, sessionKey));
    };

    // The TTS queue is a singleton, so every session transition must stop
    // speech belonging to the previous context before any new messages are
    // considered. An initial idle surface also clears audio left by a route
    // that disappeared before its cleanup ran.
    if (sessionChanged || initialIdleSurface || historyWasLoaded || voiceWasDisabled || messagesReset) {
      tts.cancelAll();
    }
    if (isInitialRender || sessionChanged || messagesReset) {
      sessionKeyRef.current = sessionKey;
      // Messages received while voice is disabled, while no session is
      // active, or from loaded history are already historical from speech's
      // perspective. Do not replay them when voice/session state changes.
      const skipMessages =
        !enabled || sessionKey === null || skipExistingOnSessionChange;
      spokenCountRef.current = skipMessages ? messages.length : 0;
      if (skipMessages) markMessagesHandled();
    } else if (historyWasLoaded) {
      // Loading the same session again must not speak its reconstructed
      // history as if it were newly generated assistant output.
      spokenCountRef.current = messages.length;
      markMessagesHandled();
    }
    skipExistingRef.current = skipExistingOnSessionChange;
    enabledRef.current = enabled;

    // A null session is an idle surface, never a speakable conversation.
    if (!enabled || sessionKey === null) {
      spokenCountRef.current = messages.length;
      markMessagesHandled();
      return;
    }
    for (let index = spokenCountRef.current; index < messages.length; index += 1) {
      // Advance the cursor even for skipped entries so a filtered or
      // non-assistant message cannot block newer ones.
      spokenCountRef.current = index + 1;
      const message = messages[index];
      if (wasMessageHandled(message, sessionKey)) continue;
      markMessageHandled(message, sessionKey);
      if (message.role !== 'assistant') continue;
      const text = resolveText(message.content);
      if (text) {
        tts.enqueue(text, { rate: 0.9 });
      }
    }
  }, [messages, sessionKey, enabled, resolveText, skipExistingOnSessionChange]);

  // A page can unmount while a session remains in the shared store. Cancel
  // only when the last speech surface has gone away, so a route transition
  // does not interrupt a replacement surface during React StrictMode or a
  // same-commit mount/unmount.
  useEffect(() => {
    activeSpeechSurfaceCount += 1;
    return () => {
      activeSpeechSurfaceCount = Math.max(0, activeSpeechSurfaceCount - 1);
      Promise.resolve().then(() => {
        if (activeSpeechSurfaceCount === 0) tts.cancelAll();
      });
    };
  }, []);
}
