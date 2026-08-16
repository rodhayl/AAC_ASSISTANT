import { useTranslation } from 'react-i18next';
import { Portal } from '../ui/Portal';

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
  onClose,
  onSave,
  onBoardNameChange,
  onBoardDescriptionChange,
  onBoardCategoryChange,
  onAiEnabledChange,
}: BoardSettingsDialogProps) {
  const { t } = useTranslation('boards');

  if (!isOpen) return null;

  return (
    <Portal>
    <div className="fixed inset-0 bg-black bg-opacity-50 dark:bg-opacity-70 flex items-center justify-center z-50">
      <div
        className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="board-settings-title"
      >
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 id="board-settings-title" className="text-xl font-semibold text-gray-900 dark:text-gray-100">{t('boardSettings')}</h2>
        </div>

        <div className="p-6 space-y-4">
          {saveSuccess && (
            <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-400 px-4 py-3 rounded-lg">
              {t('settingsSaved')}
            </div>
          )}

          <div>
            <label htmlFor="board-settings-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('boardName')}
            </label>
            <input
              id="board-settings-name"
              name="board_name"
              type="text"
              value={boardName}
              onChange={(event) => onBoardNameChange(event.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              placeholder={t('placeholderName')}
            />
          </div>

          <div>
            <label htmlFor="board-settings-description" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('description')}
            </label>
            <textarea
              id="board-settings-description"
              name="board_description"
              value={boardDescription}
              onChange={(event) => onBoardDescriptionChange(event.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              placeholder={t('optionalDescription')}
              rows={3}
            />
          </div>

          <div>
            <label htmlFor="board-settings-category" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('category')}
            </label>
            <select
              id="board-settings-category"
              name="board_category"
              value={boardCategory}
              onChange={(event) => onBoardCategoryChange(event.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="general">{t('categories.general')}</option>
              <option value="daily">{t('categories.daily')}</option>
              <option value="social">{t('categories.social')}</option>
              <option value="education">{t('categories.education')}</option>
              <option value="medical">{t('categories.medical')}</option>
              <option value="food">{t('categories.food')}</option>
            </select>
          </div>

          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <div className="flex items-center mb-3">
              <input
                type="checkbox"
                id="aiEnabledEdit"
                checked={aiEnabled}
                onChange={(event) => onAiEnabledChange(event.target.checked)}
                className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
              />
              <label htmlFor="aiEnabledEdit" className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                {t('enableAI')}
              </label>
            </div>

            {aiEnabled && (
              <div className="space-y-4 pl-6">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {t('aiConfigDescription')}
                </p>
                <div className="grid grid-cols-1 gap-3">
                  <label
                    className={`relative block p-3 rounded-lg border transition-colors ${primaryReady ? '' : 'opacity-60'}`}
                  >
                    <div className="font-semibold text-gray-900 dark:text-gray-100">{t('primaryAI')}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400 capitalize">
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

        <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end space-x-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            {t('cancel')}
          </button>
          <button
            onClick={onSave}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
          >
            {t('saveSettings')}
          </button>
        </div>
      </div>
    </div>
    </Portal>
  );
}
