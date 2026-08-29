import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { BoardSymbol } from '../../types';
import { useBoardStore } from '../../store/boardStore';
import { Button } from '../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';

interface SymbolEditorDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (updates: Partial<BoardSymbol>) => void;
  symbol: BoardSymbol | null;
  currentBoardId: number;
}

const COLORS = [
  { key: 'white', name: 'White', value: '#ffffff' },
  { key: 'red', name: 'Red', value: '#fee2e2' },
  { key: 'orange', name: 'Orange', value: '#ffedd5' },
  { key: 'yellow', name: 'Yellow', value: '#fef9c3' },
  { key: 'green', name: 'Green', value: '#dcfce7' },
  { key: 'blue', name: 'Blue', value: '#dbeafe' },
  { key: 'purple', name: 'Purple', value: '#f3e8ff' },
  { key: 'pink', name: 'Pink', value: '#fce7f3' },
  { key: 'gray', name: 'Gray', value: '#f3f4f6' },
];

export function SymbolEditorDialog({
  isOpen,
  onClose,
  onSave,
  symbol,
  currentBoardId,
}: SymbolEditorDialogProps) {
  const { t } = useTranslation('boards');
  const boards = useBoardStore((state) => state.boards);
  const fetchBoards = useBoardStore((state) => state.fetchBoards);
  
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
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent showCloseButton={false} className="max-w-md p-6">
        <DialogHeader className="flex-row items-center justify-between">
          <DialogTitle className="text-xl font-bold text-gray-900 dark:text-white">{t('editSymbol')}</DialogTitle>
          <button
            onClick={onClose}
            className="rounded-lg p-2 hover:bg-gray-100 dark:hover:bg-gray-700"
            aria-label={t('close')}
          >
            <X className="h-5 w-5 text-gray-500 dark:text-gray-400" />
          </button>
        </DialogHeader>

        <div className="space-y-4">
          {/* Custom Text */}
          <div>
            <label htmlFor="symbol-editor-custom-text" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('customLabel')}
            </label>
            <input
              id="symbol-editor-custom-text"
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
                  className={`h-8 w-8 rounded-full border-2 ${
                    color === c.value
                      ? 'border-indigo-600 ring-2 ring-indigo-600 ring-offset-2 dark:ring-offset-gray-800'
                      : 'border-gray-200 dark:border-gray-600'
                  }`}
                  style={{ backgroundColor: c.value }}
                  aria-label={t(`colors.${c.key}`, c.name)}
                  title={t(`colors.${c.key}`, c.name)}
                />
              ))}
            </div>
          </div>

          {/* Linked Board */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('linkToBoard')}
            </label>
            <Select
              value={linkedBoardId != null ? String(linkedBoardId) : 'none'}
              onValueChange={(next) => {
                // Base UI Select cannot commit an empty-string item value, so
                // the "none" option uses a sentinel mapped back to null.
                setLinkedBoardId(next === 'none' || next == null ? null : Number(next));
              }}
              items={[
                { value: 'none', label: t('none') },
                ...boards
                  .filter((b) => b.id !== currentBoardId)
                  .map((board) => ({ value: String(board.id), label: board.name })),
              ]}
            >
              <SelectTrigger aria-label={t('linkToBoard')} className="w-full text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t('none')}</SelectItem>
                {boards
                  .filter((b) => b.id !== currentBoardId)
                  .map((board) => (
                    <SelectItem key={board.id} value={String(board.id)}>
                      {board.name}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {t('linkToBoardHelp')}
            </p>
          </div>

          <div className="flex justify-end gap-3">
            <button
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              {t('cancel')}
            </button>
            <Button
              onClick={handleSave}
            >
              {t('save')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
