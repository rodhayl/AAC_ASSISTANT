import { useId, useRef } from 'react';
import { X } from 'lucide-react';
import { useModalFocusTrap } from '../../hooks/useModalFocusTrap';
import { Button } from './Button';

interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'primary' | 'danger';
  isLoading?: boolean;
}

export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'primary',
  isLoading = false,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  useModalFocusTrap(dialogRef, isOpen, onClose);

  if (!isOpen) return null;

  return (
    <div
      ref={dialogRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div className="w-full max-w-md rounded-xl glass-card p-6 shadow-xl animate-in zoom-in-95 duration-200" data-mobile-dialog="true">
        <div className="mb-4 flex items-center justify-between">
          <h2 id={titleId} className="text-xl font-bold text-primary">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="modal-close rounded-lg p-2 text-secondary hover:bg-surface-hover transition-colors"
            aria-label="Close dialog"
            disabled={isLoading}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="text-secondary mb-8">
          {description}
        </p>

        <div className="flex justify-end gap-3">
          <Button
            variant="ghost"
            onClick={onClose}
            disabled={isLoading}
          >
            {cancelText}
          </Button>
          <Button
            variant={variant}
            onClick={onConfirm}
            loading={isLoading}
          >
            {confirmText}
          </Button>
        </div>
      </div>
    </div>
  );
}
