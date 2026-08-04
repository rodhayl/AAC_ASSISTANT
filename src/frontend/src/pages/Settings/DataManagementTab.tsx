import { useAuthStore } from '../../store/authStore';
import { useToastStore } from '../../store/toastStore';
import { useTranslation } from 'react-i18next';
import { Download, Upload } from 'lucide-react';
import api from '../../lib/api';

export function DataManagementTab() {
  const { user } = useAuthStore();
  const { addToast } = useToastStore();
  const { t } = useTranslation('settings');
  const isTeacherOrAdmin = user?.user_type === 'admin' || user?.user_type === 'teacher';

  const handleExportData = async () => {
    if (!user) return;
    try {
      const boardsRes = await api.get('/boards/', { params: { user_id: user.id } });
      const achievementsRes = await api.get(`/achievements/user/${user.id}`);
      const pointsRes = await api.get(`/achievements/user/${user.id}/points`);
      const historyRes = await api.get(`/learning/history/${user.id}`, { params: { limit: 100 } });
      const assignedRes =
        user.user_type === 'student'
          ? await api.get('/boards/assigned', { params: { student_id: user.id } })
          : { data: [] };
      const base = {
        meta: { exported_at: new Date().toISOString(), username: user.username },
        boards: boardsRes.data,
        assignedBoards: assignedRes.data,
        achievements: achievementsRes.data,
        totalPoints: pointsRes.data,
        learningHistory: historyRes.data,
      };
      const encoder = new TextEncoder();
      const raw = JSON.stringify(base);
      const digest = await crypto.subtle.digest('SHA-256', encoder.encode(raw));
      const hex = Array.from(new Uint8Array(digest))
        .map((byte) => byte.toString(16).padStart(2, '0'))
        .join('');
      const data = { ...base, meta: { ...base.meta, checksum_sha256: hex, schema_version: '1' } };
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
      const baseForChecksum = {
        meta: { exported_at: json.meta.exported_at, username: json.meta.username },
        boards: json.boards,
        assignedBoards: json.assignedBoards,
        achievements: json.achievements,
        totalPoints: json.totalPoints,
        learningHistory: json.learningHistory,
      };
      const encoder = new TextEncoder();
      const digest = await crypto.subtle.digest(
        'SHA-256',
        encoder.encode(JSON.stringify(baseForChecksum)),
      );
      const hex = Array.from(new Uint8Array(digest))
        .map((byte) => byte.toString(16).padStart(2, '0'))
        .join('');
      const expected = json.meta.checksum_sha256;
      if (!expected || typeof expected !== 'string' || expected !== hex) {
        throw new Error('Checksum mismatch: file may be tampered');
      }
      for (const board of json.boards) {
        const createRes = await api.post(
          '/boards/',
          {
            name: board.name,
            description: board.description,
            category: board.category,
            is_public: board.is_public,
            is_template: board.is_template,
            grid_rows: board.grid_rows ?? 4,
            grid_cols: board.grid_cols ?? 5,
          },
          { params: { user_id: user.id } },
        );
        const newBoard = createRes.data;
        for (const symbol of board.symbols || []) {
          await api.post(`/boards/${newBoard.id}/symbols`, {
            symbol_id: symbol.symbol?.id ?? symbol.symbol_id,
            position_x: symbol.position_x,
            position_y: symbol.position_y,
            size: symbol.size,
            is_visible: symbol.is_visible,
            custom_text: symbol.custom_text,
          });
        }
      }
      if (user.user_type === 'student' && Array.isArray(json.assignedBoards)) {
        for (const assignedBoard of json.assignedBoards) {
          try {
            await api.post(`/boards/${assignedBoard.id}/assign`, { student_id: user.id });
          } catch {
            // Assignment is optional during client-side import.
          }
        }
      }
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
