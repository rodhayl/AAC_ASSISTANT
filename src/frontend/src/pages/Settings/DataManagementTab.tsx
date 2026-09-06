import { useAuthStore } from '../../store/authStore';
import { useToastStore } from '../../store/toastStore';
import { useTranslation } from 'react-i18next';
import { Download, Upload } from 'lucide-react';
import api from '../../lib/api';
import { downloadJson } from '../../lib/download';
import { isStaffUser } from '../../lib/roles';
import { Button } from '../../components/ui/button';

export function DataManagementTab() {
  const user = useAuthStore(state => state.user);
  const addToast = useToastStore((state) => state.addToast);
  const { t } = useTranslation('settings');
  const isTeacherOrAdmin = isStaffUser(user);

  const handleExportData = async (serverExport = false) => {
    if (!user) return;
    try {
      const response = await api.get('/data/export', { params: { username: user.username } });
      const suffix = serverExport ? '-server' : '';
      downloadJson(response.data, `aac-data-${user.username}${suffix}.json`);
    } catch (error) {
      console.error(serverExport ? 'Server export failed:' : 'Failed to export data:', error);
      if (serverExport) {
        addToast(t('data.exportServerFailed'), 'error');
      }
    }
  };

  const handleImportData = async (file: File) => {
    if (!user) return;
    try {
      const text = await file.text();
      const json = JSON.parse(text);
      if (!json.meta || typeof json.meta !== 'object') throw new Error(t('data.invalidExportMeta'));
      if (!Array.isArray(json.boards)) throw new Error(t('data.invalidExportBoards'));
      if (!Array.isArray(json.assignedBoards)) throw new Error(t('data.invalidExportAssignedBoards'));
      if (!Array.isArray(json.achievements)) throw new Error(t('data.invalidExportAchievements'));
      await api.post('/data/import', json);
      addToast(t('data.importSuccess'), 'success');
    } catch (error) {
      console.error('Failed to import data:', error);
      const errorMessage = error instanceof Error ? error.message : t('errors.unknownError');
      addToast(t('data.importFailed') + errorMessage, 'error');
    }
  };

  return (
    <section
      id="settings-data"
      aria-labelledby="settings-data-heading"
      className="bg-surface rounded-xl shadow-sm border border-border overflow-hidden"
    >
      <div className="p-6 border-b border-border">
        <h3 id="settings-data-heading" className="text-lg font-semibold text-foreground">
          {t('data.title')}
        </h3>
        <p className="text-sm text-muted-foreground mt-1">{t('data.subtitle')}</p>
      </div>
      <div className="p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Button
            onClick={() => void handleExportData()}
            title={t('data.exportClientTitle')}
          >
            <Download />
            {t('data.exportClient')}
          </Button>
          {isTeacherOrAdmin && (
            <button
              onClick={() => void handleExportData(true)}
              className="px-4 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 flex items-center justify-center"
              title={t('data.exportServerTitle')}
            >
              <Download className="w-4 h-4 mr-2" />
              {t('data.exportServer')}
            </button>
          )}
        </div>
        {isTeacherOrAdmin && (
          <label className="flex items-center justify-center px-4 py-2 bg-muted text-foreground rounded-lg cursor-pointer hover:bg-muted w-full">
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
