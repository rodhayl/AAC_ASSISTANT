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

  // A single export path: the server assembles and returns the full data
  // export, which the browser saves as a JSON file. (An earlier UI offered
  // "client" vs "server" exports, but both buttons called the same endpoint
  // and only differed by a filename suffix; the labels were removed.)
  const handleExportData = async () => {
    if (!user) return;
    try {
      const response = await api.get('/data/export', { params: { username: user.username } });
      downloadJson(response.data, `aac-data-${user.username}.json`);
    } catch (error) {
      console.error('Failed to export data:', error);
      // A failed export must not be silent: the server /data/export endpoint
      // can be down even when the rest of the app responds (the old "server
      // export" button surfaced this with a toast before the two buttons were
      // collapsed into one).
      addToast(t('data.exportFailed'), 'error');
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
      const result = await api.post('/data/import', json);
      const body = (result.data ?? {}) as Record<string, unknown>;
      // D7: surface whether the import's source export was truncated (100-session cap)
      if (body.truncated) {
        const total = body.total_learning_sessions;
        const shown = body.learning_history;
        addToast(t('data.importTruncated', { shown, total }), 'warning');
      } else {
        addToast(t('data.importSuccess'), 'success');
      }
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
        <Button onClick={() => void handleExportData()} title={t('data.exportClientTitle')}>
          <Download />
          {t('data.exportClient')}
        </Button>
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
                // Reset the input value after every selection (success or
                // failure): an uncontrolled file input keeps the previous
                // value, so choosing the SAME file twice would not re-fire
                // onChange and the second import would be impossible.
                event.target.value = '';
                if (file) void handleImportData(file);
              }}
            />
          </label>
        )}
      </div>
    </section>
  );
}
