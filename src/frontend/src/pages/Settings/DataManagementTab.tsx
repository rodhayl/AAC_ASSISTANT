import { useAuthStore } from '../../store/authStore';
import { useToastStore } from '../../store/toastStore';
import { useTranslation } from 'react-i18next';
import { Download, Upload } from 'lucide-react';
import api from '../../lib/api';

export function DataManagementTab() {
  const user = useAuthStore(state => state.user);
  const addToast = useToastStore((state) => state.addToast);
  const { t } = useTranslation('settings');
  const isTeacherOrAdmin = user?.user_type === 'admin' || user?.user_type === 'teacher';

  const handleExportData = async () => {
    if (!user) return;
    try {
      const response = await api.get('/data/export', { params: { username: user.username } });
      const data = response.data;
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `aac-data-${user.username}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to export data:', error);
    }
  };

  const handleServerExport = async () => {
    if (!user) return;
    try {
      const response = await api.get('/data/export', { params: { username: user.username } });
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `aac-data-${user.username}-server.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Server export failed:', error);
      addToast(t('data.exportServerFailed'), 'error');
    }
  };

  const handleImportData = async (file: File) => {
    if (!user) return;
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      if (!json.meta || typeof json.meta !== 'object') throw new Error('Invalid export: missing meta');
      if (!Array.isArray(json.boards)) throw new Error('Invalid export: boards must be array');
      if (!Array.isArray(json.assignedBoards)) throw new Error('Invalid export: assignedBoards must be array');
      if (!Array.isArray(json.achievements)) throw new Error('Invalid export: achievements must be array');
      await api.post('/data/import', json);
      addToast(t('data.importSuccess'), 'success');
    } catch (error) {
      console.error('Failed to import data:', error);
      const errorMessage = error instanceof Error ? error.message : t('errors.unknownError', 'Unknown error');
      addToast(t('data.importFailed') + errorMessage, 'error');
    }
  };

  return (
    <section
      id="settings-data"
      aria-labelledby="settings-data-heading"
      className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div className="p-6 border-b border-gray-200 dark:border-gray-700">
        <h3 id="settings-data-heading" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          {t('data.title')}
        </h3>
        <p className="text-sm text-gray-500 mt-1">{t('data.subtitle')}</p>
      </div>
      <div className="p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <button
            onClick={handleExportData}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 flex items-center justify-center"
            title={t('data.exportClientTitle')}
          >
            <Download className="w-4 h-4 mr-2" />
            {t('data.exportClient')}
          </button>
          {isTeacherOrAdmin && (
            <button
              onClick={handleServerExport}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center justify-center"
              title={t('data.exportServerTitle')}
            >
              <Download className="w-4 h-4 mr-2" />
              {t('data.exportServer')}
            </button>
          )}
        </div>
        {isTeacherOrAdmin && (
          <label className="flex items-center justify-center px-4 py-2 bg-gray-100 text-gray-700 rounded-lg cursor-pointer hover:bg-gray-200 w-full">
            <Upload className="w-4 h-4 mr-2" />
            {t('data.importBoards')}
            <input
              id="import-boards-file"
              name="import_boards_file"
              type="file"
              accept="application/json"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) handleImportData(file);
              }}
            />
          </label>
        )}
      </div>
    </section>
  );
}
