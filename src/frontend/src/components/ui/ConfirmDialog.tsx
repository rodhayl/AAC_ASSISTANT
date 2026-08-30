import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from './alert-dialog';

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
  const { t } = useTranslation('common');

  return (
    <AlertDialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <AlertDialogContent className="max-w-md" data-mobile-dialog="true">
        <AlertDialogHeader>
          <div className="mb-4 flex items-center justify-between">
            <AlertDialogTitle className="text-xl font-bold text-foreground">{title}</AlertDialogTitle>
            <AlertDialogCancel
              className="modal-close rounded-lg p-2 text-muted-foreground hover:bg-surface-hover transition-colors"
              aria-label={t('close')}
              disabled={isLoading}
            >
              <X className="h-5 w-5" />
            </AlertDialogCancel>
          </div>
        </AlertDialogHeader>

        <AlertDialogDescription className="text-muted-foreground mb-8">
          {description}
        </AlertDialogDescription>

        <AlertDialogFooter>
          <AlertDialogCancel
            variant="ghost"
            disabled={isLoading}
          >
            {cancelText}
          </AlertDialogCancel>
          <AlertDialogAction
            variant={variant === 'danger' ? 'danger' : 'default'}
            onClick={onConfirm}
            loading={isLoading}
          >
            {confirmText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
