import React, { useState } from 'react';
import { X, BookOpen } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useLearningStore } from '../../store/learningStore';
import { useAuthStore } from '../../store/authStore';

interface ContextModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ContextModal({ isOpen, onClose }: ContextModalProps) {
  const { t } = useTranslation('boards');
  const { startSession, isLoading } = useLearningStore();
  const { user } = useAuthStore();
  
  const [topic, setTopic] = useState('');
  const [purpose, setPurpose] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !topic.trim()) return;

    await startSession({
      topic: topic.trim(),
      purpose: purpose.trim() || 'general communication',
      difficulty: 'adaptive'
    }, user.id);
    
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {t('setContext', 'Set Conversation Context')}
            </h2>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('topic', 'Topic')}
            </label>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g., Dinosaurs, Lunch, Weekend Plans"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              autoFocus
              required
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {t('topicHint', 'What do you want to talk about? The AI will adapt its suggestions.')}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('purpose', 'Purpose (Optional)')}
            </label>
            <input
              type="text"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="e.g., School, Social, Requesting"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
            >
              {t('cancel', 'Cancel')}
            </button>
            <button
              type="submit"
              disabled={isLoading || !topic.trim()}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {isLoading ? t('setting', 'Setting...') : t('setContextBtn', 'Set Context')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
