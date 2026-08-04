import { useEffect, useState } from 'react';
import { AlertCircle, Check, Edit2, Plus, Trash2 } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import api, { extractError } from '../../lib/api';
import type { LearningMode } from './types';

export function LearningModesTab() {
  const { user } = useAuthStore();
  const [learningModes, setLearningModes] = useState<LearningMode[]>([]);
  const [editingModeId, setEditingModeId] = useState<number | null>(null);
  const [modeForm, setModeForm] = useState({
    name: '',
    key: '',
    description: '',
    prompt_instruction: '',
  });
  const [modeError, setModeError] = useState<string | null>(null);
  const [modeSuccess, setModeSuccess] = useState<string | null>(null);

  const fetchLearningModes = () => {
    api
      .get('/learning-modes/')
      .then((res) => setLearningModes(res.data))
      .catch((err) => console.error('Failed to fetch modes', err));
  };

  useEffect(() => {
    if (user?.user_type === 'admin' || user?.user_type === 'teacher') {
      fetchLearningModes();
    }
  }, [user]);

  const handleEditMode = (mode: LearningMode) => {
    setEditingModeId(mode.id);
    setModeForm({
      name: mode.name,
      key: mode.key,
      description: mode.description || '',
      prompt_instruction: mode.prompt_instruction,
    });
    setModeError(null);
    setModeSuccess(null);
  };

  const handleCancelModeEdit = () => {
    setEditingModeId(null);
    setModeForm({ name: '', key: '', description: '', prompt_instruction: '' });
  };

  const handleSaveMode = async () => {
    try {
      if (editingModeId && editingModeId !== -1) {
        await api.put(`/learning-modes/${editingModeId}`, {
          name: modeForm.name,
          description: modeForm.description,
          prompt_instruction: modeForm.prompt_instruction,
        });
        setModeSuccess('Mode updated successfully');
      } else {
        await api.post('/learning-modes/', modeForm);
        setModeSuccess('Mode created successfully');
      }
      fetchLearningModes();
      handleCancelModeEdit();
      setTimeout(() => setModeSuccess(null), 3000);
    } catch (err: unknown) {
      setModeError(extractError(err, 'Failed to save mode'));
    }
  };

  const handleDeleteMode = async (id: number) => {
    if (!confirm('Are you sure you want to delete this learning mode?')) return;
    try {
      await api.delete(`/learning-modes/${id}`);
      fetchLearningModes();
      setModeSuccess('Mode deleted');
      setTimeout(() => setModeSuccess(null), 3000);
    } catch (err: unknown) {
      setModeError(extractError(err, 'Failed to delete mode'));
    }
  };

  return (
    <section
      id="settings-learning-modes"
      aria-labelledby="settings-learning-modes-heading"
      className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div className="p-6 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h3
              id="settings-learning-modes-heading"
              className="text-lg font-semibold text-gray-900 dark:text-gray-100"
            >
              Learning Modes
            </h3>
            <p className="text-sm text-gray-500 mt-1">Configure smart learning modes and prompts</p>
          </div>
          {modeSuccess && (
            <div className="flex items-center text-green-600 text-sm font-medium">
              <Check className="w-4 h-4 mr-1" /> {modeSuccess}
            </div>
          )}
        </div>
      </div>

      <div className="p-6">
        {modeError && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center mb-4">
            <AlertCircle className="w-5 h-5 mr-2" />
            {modeError}
          </div>
        )}

        {!editingModeId ? (
          <div>
            <div className="space-y-2 mb-4">
              {learningModes.map((mode) => (
                <div key={mode.id} className="p-4 border border-gray-200 rounded-lg flex justify-between items-center">
                  <div>
                    <div className="font-semibold">{mode.name}</div>
                    <div className="text-sm text-gray-500">{mode.description}</div>
                    {!mode.is_custom && (
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">System Default</span>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleEditMode(mode)}
                      className="p-2 text-indigo-600 hover:bg-indigo-50 rounded"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    {mode.is_custom && (
                      <button
                        onClick={() => handleDeleteMode(mode.id)}
                        className="p-2 text-red-600 hover:bg-red-50 rounded"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <button
              onClick={() => {
                setEditingModeId(-1);
                setModeForm({ name: '', key: '', description: '', prompt_instruction: '' });
              }}
              className="w-full py-2 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 hover:border-indigo-500 hover:text-indigo-500 flex items-center justify-center"
            >
              <Plus className="w-4 h-4 mr-2" /> Add New Learning Mode
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <h4 className="font-medium text-gray-900">
              {editingModeId === -1 ? 'Create New Mode' : 'Edit Mode'}
            </h4>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                value={modeForm.name}
                onChange={(event) => setModeForm({ ...modeForm, name: event.target.value })}
                className="w-full p-2 border rounded-lg"
                placeholder="e.g. Daily Conversation"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Key (Internal ID)</label>
              <input
                value={modeForm.key}
                onChange={(event) => setModeForm({ ...modeForm, key: event.target.value })}
                className="w-full p-2 border rounded-lg"
                placeholder="e.g. daily_conversation"
                disabled={editingModeId !== -1}
              />
              <p className="text-xs text-gray-500 mt-1">Unique identifier for this mode.</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <input
                value={modeForm.description}
                onChange={(event) => setModeForm({ ...modeForm, description: event.target.value })}
                className="w-full p-2 border rounded-lg"
                placeholder="Brief description for the user"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">System Prompt Instruction</label>
              <textarea
                value={modeForm.prompt_instruction}
                onChange={(event) => setModeForm({ ...modeForm, prompt_instruction: event.target.value })}
                className="w-full p-2 border rounded-lg h-32 font-mono text-sm"
                placeholder="Instructions for the AI on how to behave in this mode..."
              />
              <p className="text-xs text-gray-500 mt-1">
                This text is appended to the AI system prompt. It is not visible to the student.
              </p>
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={handleCancelModeEdit}
                className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveMode}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
              >
                Save Mode
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
