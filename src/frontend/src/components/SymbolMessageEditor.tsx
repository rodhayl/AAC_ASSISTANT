import { useState } from 'react';
import { Edit, Check, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { SymbolImage } from './common/SymbolImage';
import { glossSymbolUtterance } from '../lib/gloss';
import { getCategoryStyle } from '../lib/symbolCategoryStyle';

interface SymbolItem {
  id: number;
  label: string;
  image_path?: string;
  category?: string;
}

interface SymbolMessageEditorProps {
  message: {
    content: string;
    symbolImages?: Array<SymbolItem>;
  };
  onUpdate: (newSymbols: Array<SymbolItem>, newText: string) => void;
  onCancel: () => void;
}

export function SymbolMessageEditor({ message, onUpdate, onCancel }: SymbolMessageEditorProps) {
  const { t } = useTranslation('common');
  const [editedSymbols, setEditedSymbols] = useState<SymbolItem[]>(message.symbolImages || []);

  const removeSymbol = (index: number) => {
    setEditedSymbols(prev => prev.filter((_, i) => i !== index));
  };

  const glossSymbols = (): string => {
    return glossSymbolUtterance(editedSymbols);
  };

  const handleSave = () => {
    const glossedText = glossSymbols();
    onUpdate(editedSymbols, glossedText);
  };

  return (
    <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-3 my-2">
      <div className="flex items-center gap-2 mb-2 text-sm text-gray-600 dark:text-gray-400">
        <Edit className="w-4 h-4" />
        <span>{t('symbolEditor.title', 'Editing symbol message')}</span>
      </div>

      {editedSymbols.length === 0 ? (
        <div className="text-sm text-gray-500 dark:text-gray-400 italic mb-3 p-2">
          {t('symbolEditor.emptyHint', 'No symbols remaining. Add symbols or cancel to restore original.')}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2 mb-3">
            {editedSymbols.map((sym, idx) => (
              <div
                key={`edit-${sym.id}-${idx}`}
                className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs border ${
                  getCategoryStyle(sym.category).badgeBg
                } ${getCategoryStyle(sym.category).badgeText} ${getCategoryStyle(sym.category).border}`}
              >
                {sym.image_path && (
                  <SymbolImage
                    imagePath={sym.image_path}
                    alt={sym.label}
                    className="w-5 h-5 object-contain"
                  />
                )}
                <span>{sym.label}</span>
                <button
                  onClick={() => removeSymbol(idx)}
                  className="ml-1 text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 transition-colors"
                  aria-label={`Remove ${sym.label}`}
                  title="Remove symbol"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>

          <div className="text-sm text-gray-700 dark:text-gray-300 mb-3 p-2 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700">
            <span className="text-xs text-gray-500 dark:text-gray-400 mr-2">{t('symbolEditor.preview', 'Preview:')}</span>
            {glossSymbols() || <span className="italic text-gray-400">{t('symbolEditor.emptyMessage', 'Empty message')}</span>}
          </div>
        </>
      )}

      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={editedSymbols.length === 0}
          className="px-3 py-1.5 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1 transition-colors"
          title="Save and resend message"
        >
          <Check className="w-4 h-4" />
          {t('symbolEditor.saveResend', 'Save & Resend')}
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded text-sm hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          title="Cancel editing"
        >
          {t('symbolEditor.cancel', 'Cancel')}
        </button>
      </div>
    </div>
  );
}
