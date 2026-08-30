import { useTranslation } from 'react-i18next';
import { Button } from '../ui/button';
import { StatusMessage } from '../ui/StatusMessage';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';

import { FormLabel } from '@/components/ui/FormLabel';
interface BoardSettingsDialogProps {
  isOpen: boolean;
  saveSuccess: boolean;
  boardName: string;
  boardDescription: string;
  boardCategory: string;
  aiEnabled: boolean;
  primaryReady: boolean;
  primaryProvider?: string;
  primaryModel?: string;
  aiConfigError: string | null;
  saving: boolean;
  onClose: () => void;
  onSave: () => void;
  onBoardNameChange: (value: string) => void;
  onBoardDescriptionChange: (value: string) => void;
  onBoardCategoryChange: (value: string) => void;
  onAiEnabledChange: (enabled: boolean) => void;
}

export function BoardSettingsDialog({
  isOpen,
  saveSuccess,
  boardName,
  boardDescription,
  boardCategory,
  aiEnabled,
  primaryReady,
  primaryProvider,
  primaryModel,
  aiConfigError,
  saving,
  onClose,
  onSave,
  onBoardNameChange,
  onBoardDescriptionChange,
  onBoardCategoryChange,
  onAiEnabledChange,
}: BoardSettingsDialogProps) {
  const { t } = useTranslation('boards');

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        className="max-w-2xl max-h-[90vh] overflow-y-auto"
      >
        <DialogHeader>
          <DialogTitle>{t('boardSettings')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {saveSuccess && (
            <StatusMessage variant="success">
              {t('settingsSaved')}
            </StatusMessage>
          )}

          <div>
            <FormLabel htmlFor="board-settings-name">
              {t('boardName')}
            </FormLabel>
            <input
              id="board-settings-name"
              name="board_name"
              type="text"
              value={boardName}
              onChange={(event) => onBoardNameChange(event.target.value)}
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
              placeholder={t('placeholderName')}
            />
          </div>

          <div>
            <FormLabel htmlFor="board-settings-description">
              {t('description')}
            </FormLabel>
            <textarea
              id="board-settings-description"
              name="board_description"
              value={boardDescription}
              onChange={(event) => onBoardDescriptionChange(event.target.value)}
              className="w-full px-3 py-2 border border-border rounded-lg focus:ring-brand focus:border-brand bg-surface text-foreground"
              placeholder={t('optionalDescription')}
              rows={3}
            />
          </div>

          <div>
            <FormLabel>
              {t('category')}
            </FormLabel>
            <Select value={boardCategory} onValueChange={(next) => { if (next != null) onBoardCategoryChange(next); }}>
              <SelectTrigger aria-label={t('category')} name="board_category" className="w-full text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="general">{t('categories.general')}</SelectItem>
                <SelectItem value="daily">{t('categories.daily')}</SelectItem>
                <SelectItem value="social">{t('categories.social')}</SelectItem>
                <SelectItem value="education">{t('categories.education')}</SelectItem>
                <SelectItem value="medical">{t('categories.medical')}</SelectItem>
                <SelectItem value="food">{t('categories.food')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="border-t border-border pt-4">
            <div className="flex items-center mb-3">
              <input
                type="checkbox"
                id="aiEnabledEdit"
                checked={aiEnabled}
                onChange={(event) => onAiEnabledChange(event.target.checked)}
                className="w-4 h-4 text-brand rounded focus:ring-brand"
              />
              <label htmlFor="aiEnabledEdit" className="ml-2 text-sm font-medium text-foreground">
                {t('enableAI')}
              </label>
            </div>

            {aiEnabled && (
              <div className="space-y-4 pl-6">
                <p className="text-sm text-muted-foreground">
                  {t('aiConfigDescription')}
                </p>
                <div className="grid grid-cols-1 gap-3">
                  <label
                    className={`relative block p-3 rounded-lg border transition-colors ${primaryReady ? '' : 'opacity-60'}`}
                  >
                    <div className="font-semibold text-foreground">{t('primaryAI')}</div>
                    <div className="text-sm text-muted-foreground capitalize">
                      {primaryReady ? `${primaryProvider} - ${primaryModel}` : t('notConfigured')}
                    </div>
                  </label>
                </div>
                {aiConfigError && (
                  <div className="text-sm text-red-600 dark:text-red-400">{aiConfigError}</div>
                )}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
          >
            {t('cancel')}
          </Button>
          <Button type="button" onClick={onSave} loading={saving}>
            {saving ? t('saving') : t('saveSettings')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
