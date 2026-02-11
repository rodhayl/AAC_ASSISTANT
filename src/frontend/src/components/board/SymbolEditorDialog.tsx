import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { BoardSymbol } from '../../types';
import { useBoardStore } from '../../store/boardStore';

interface SymbolEditorDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (updates: Partial<BoardSymbol>) => void;
  symbol: BoardSymbol | null;
}

const COLORS = [
  { name: 'White', value: '#ffffff', class: 'bg-white' },
  { name: 'Red', value: '#fee2e2', class: 'bg-red-100' },
  { name: 'Orange', value: '#ffedd5', class: 'bg-orange-100' },
  { name: 'Yellow', value: '#fef9c3', class: 'bg-yellow-100' },
  { name: 'Green', value: '#dcfce7', class: 'bg-green-100' },
  { name: 'Blue', value: '#dbeafe', class: 'bg-blue-100' },
  { name: 'Purple', value: '#f3e8ff', class: 'bg-purple-100' },
  { name: 'Pink', value: '#fce7f3', class: 'bg-pink-100' },
  { name: 'Gray', value: '#f3f4f6', class: 'bg-gray-100' },
];

export function SymbolEditorDialog({ isOpen, onClose, onSave, symbol }: SymbolEditorDialogProps) {
  const { t } = useTranslation('boards');
  const { boards, fetchBoards } = useBoardStore();
  
  const [customText, setCustomText] = useState(symbol?.custom_text || symbol?.symbol.label || '');
  const [color, setColor] = useState(symbol?.color || '#ffffff');
  const [linkedBoardId, setLinkedBoardId] = useState<number | null | undefined>(symbol?.linked_board_id);

  useEffect(() => {
    if (isOpen) {
      fetchBoards();
    }
  }, [isOpen, fetchBoards]);

  if (!isOpen || !symbol) return null;

  const handleSave = () => {
    onSave({
      custom_text: customText,
      color: color,
      linked_board_id: linkedBoardId
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl dark:bg-gray-800">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">{t('editSymbol')}</h2>
          <button onClick={onClose} className="rounded-lg p-2 hover:bg-gray-100 dark:hover:bg-gray-700">
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        <div className="space-y-4">
          {/* Custom Text */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('customLabel')}
            </label>
            <input
              type="text"
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              className="w-full rounded-lg border border-gray-300 p-2 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              placeholder={symbol.symbol.label}
            />
          </div>

          {/* Background Color */}
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('backgroundColor')}
            </label>
            <div className="grid grid-cols-5 gap-2">
              {COLORS.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setColor(c.value)}
                  className={`h-8 w-8 rounded-full border-2 ${c.class} ${
                    color === c.value
                      ? 'border-indigo-600 ring-2 ring-indigo-600 ring-offset-2 dark:ring-offset-gray-800'
                      : 'border-gray-200 dark:border-gray-600'
                  }`}
                  title={c.name}
                />
              ))}
            </div>
          </div>

          {/* Linked Board */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('linkToBoard')}
            </label>
            <select
              value={linkedBoardId || ''}
              onChange={(e) => setLinkedBoardId(e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-lg border border-gray-300 p-2 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
            >
              <option value="">{t('none')}</option>
              {boards
                .filter((b) => b.id !== symbol.id) // Prevent self-linking loop (basic check)
                .map((board) => (
                  <option key={board.id} value={board.id}>
                    {board.name}
                  </option>
                ))}
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {t('linkToBoardHelp')}
            </p>
          </div>

          <div className="mt-6 flex justify-end gap-3">
            <button
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              {t('cancel')}
            </button>
            <button
              onClick={handleSave}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              {t('save')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
