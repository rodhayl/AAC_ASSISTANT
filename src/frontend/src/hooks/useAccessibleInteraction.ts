import { useCallback, useRef } from 'react';
import { useAuthStore } from '../store/authStore';

interface UseAccessibleInteractionProps {
  onClick: (e?: React.MouseEvent | React.TouchEvent) => void;
  disabled?: boolean;
}

export function useAccessibleInteraction({ onClick, disabled }: UseAccessibleInteractionProps) {
  const { user } = useAuthStore();
  const dwellTime = user?.settings?.dwell_time || 0;
  const ignoreRepeats = user?.settings?.ignore_repeats || 0;

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastClickTimeRef = useRef<number>(0);
  const isDwellingRef = useRef(false);

  // Helper to trigger the actual click logic with repeat check
  const triggerClick = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    const now = Date.now();
    if (ignoreRepeats > 0) {
      if (now - lastClickTimeRef.current < ignoreRepeats) {
        return;
      }
    }
    lastClickTimeRef.current = now;
    onClick(e);
  }, [ignoreRepeats, onClick]);

  const handlePointerDown = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    if (disabled) return;

    if (dwellTime > 0) {
      isDwellingRef.current = true;
      // Persist event if needed, though usually we just pass it
      // e.persist(); 
      
      timerRef.current = setTimeout(() => {
        if (isDwellingRef.current) {
          triggerClick(e);
          isDwellingRef.current = false;
        }
      }, dwellTime);
    }
  }, [dwellTime, disabled, triggerClick]);

  const handlePointerUp = useCallback(() => {
    if (dwellTime > 0) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      isDwellingRef.current = false;
    }
  }, [dwellTime]);

  const handlePointerLeave = useCallback(() => {
    if (dwellTime > 0) {
        if (timerRef.current) {
            clearTimeout(timerRef.current);
            timerRef.current = null;
        }
        isDwellingRef.current = false;
    }
  }, [dwellTime]);

  const handleClick = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    if (disabled) return;
    
    // Check if it's a keyboard click (detail === 0)
    // For MouseEvent, detail is click count. For keyboard on button, it is 0.
    const isKeyboard = 'detail' in e && e.detail === 0;

    // If dwell time is enabled, we ignore normal pointer clicks (as they are handled by timer)
    // But we MUST allow keyboard clicks.
    if (dwellTime === 0 || isKeyboard) {
       triggerClick(e);
    }
  }, [dwellTime, disabled, triggerClick]);

  return {
    onMouseDown: handlePointerDown,
    onMouseUp: handlePointerUp,
    onMouseLeave: handlePointerLeave,
    onTouchStart: handlePointerDown,
    onTouchEnd: handlePointerUp,
    onClick: handleClick
  };
}
