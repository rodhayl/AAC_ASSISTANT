import { useCallback, useEffect, useRef } from 'react';
import { useAuthStore } from '../store/authStore';
import { tts } from '../lib/tts';

export interface HoverSpeakProps {
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onMouseDown: () => void;
}

/**
 * Hover-to-speak for symbol suggestions.
 *
 * When the user enables it in Settings (Voice), resting the pointer on a
 * suggestion for `hover_speak_delay_ms` speaks its label through the
 * configured TTS engine. Moving within the same element does not restart
 * the timer (mouseenter only fires once per entry); leaving the element or
 * pressing it cancels a pending utterance so a click never double-speaks.
 */
export function useHoverSpeak() {
  const enabled = useAuthStore(
    (state) => state.user?.settings?.hover_speak_enabled ?? false,
  );
  const delayMs = useAuthStore(
    (state) => state.user?.settings?.hover_speak_delay_ms ?? 1000,
  );
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancel = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Never leave a pending utterance behind when the component unmounts.
  useEffect(() => cancel, [cancel]);

  const getHoverSpeakProps = useCallback(
    (text: string): HoverSpeakProps | Record<string, never> => {
      if (!enabled || !text.trim()) return {};
      return {
        onMouseEnter: () => {
          cancel();
          timerRef.current = setTimeout(() => {
            timerRef.current = null;
            tts.enqueue(text, { key: `hover-speak:${text.trim().toLowerCase()}` });
          }, delayMs);
        },
        onMouseLeave: cancel,
        onMouseDown: cancel,
      };
    },
    [enabled, delayMs, cancel],
  );

  return { hoverSpeakEnabled: enabled, getHoverSpeakProps };
}
