import { useEffect, useRef } from 'react';
import { tts } from '../lib/tts';
import { stripReasoning } from '../store/learningStore';

interface SpeakableMessage {
  role: string;
  content: string;
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
  const sessionKeyRef = useRef<string | number | null>(null);

  useEffect(() => {
    if (sessionKey !== sessionKeyRef.current) {
      sessionKeyRef.current = sessionKey;
      spokenCountRef.current = skipExistingOnSessionChange ? messages.length : 0;
    }
    if (!enabled) return;
    for (let index = spokenCountRef.current; index < messages.length; index += 1) {
      // Advance the cursor even for skipped entries so a filtered or
      // non-assistant message cannot block newer ones.
      spokenCountRef.current = index + 1;
      const message = messages[index];
      if (message.role !== 'assistant') continue;
      const text = resolveText(message.content);
      if (text) {
        tts.enqueue(text, { rate: 0.9 });
      }
    }
  }, [messages, sessionKey, enabled, resolveText, skipExistingOnSessionChange]);
}
