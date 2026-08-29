import { create } from 'zustand';
import { toast } from 'sonner';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

const DEFAULT_DURATION_MS = 3000;

interface ToastState {
  addToast: (message: string, type?: ToastType, duration?: number) => void;
}

/**
 * Thin facade over sonner so existing call sites keep `addToast(message, type)`.
 * Rendering, stacking, and dismissal are owned by sonner (mounted as
 * <AppToaster /> in App); the store only maps our `ToastType`/sticky-duration
 * contract onto sonner's API (`duration: Infinity` = sticky toast).
 */
export const useToastStore = create<ToastState>(() => ({
  addToast: (message, type = 'info', duration = DEFAULT_DURATION_MS) => {
    const emit = {
      success: toast.success,
      error: toast.error,
      warning: toast.warning,
      info: toast.info,
    }[type];

    emit(message, { duration: duration > 0 ? duration : Infinity });
  },
}));
