import { useState } from 'react';
import { Edit, Check, X } from 'lucide-react';
import { assetUrl } from '../lib/utils';

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
  const [editedSymbols, setEditedSymbols] = useState<SymbolItem[]>(message.symbolImages || []);

  const removeSymbol = (index: number) => {
    setEditedSymbols(prev => prev.filter((_, i) => i !== index));
  };

  const glossSymbols = (): string => {
    if (editedSymbols.length === 0) return '';
    
    // Use same glossing logic as main Learning.tsx
    const joined = editedSymbols.map(s => s.label).join(' ');
    if (!joined) return '';
    
    const capped = joined.charAt(0).toUpperCase() + joined.slice(1);
    const needsPeriod = !/[.!?]$/.test(capped);
    return needsPeriod ? `${capped}.` : capped;
  };

  const handleSave = () => {
    const glossedText = glossSymbols();
    onUpdate(editedSymbols, glossedText);
  };

  const getCategoryColor = (category?: string): string => {
    const colors: Record<string, string> = {
      'action': 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-700',
      'object': 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-200 dark:border-green-700',
      'person': 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-700',
      'feeling': 'bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300 border-pink-200 dark:border-pink-700',
      'place': 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border-yellow-200 dark:border-yellow-700',
      'question': 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border-orange-200 dark:border-orange-700',
    };
    return colors[category || ''] || 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border-indigo-100 dark:border-indigo-700';
  };

  return (
    <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-3 my-2">
      <div className="flex items-center gap-2 mb-2 text-sm text-gray-600 dark:text-gray-400">
        <Edit className="w-4 h-4" />
        <span>Editing symbol message</span>
      </div>

      {editedSymbols.length === 0 ? (
        <div className="text-sm text-gray-500 dark:text-gray-400 italic mb-3 p-2">
          No symbols remaining. Add symbols or cancel to restore original.
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2 mb-3">
            {editedSymbols.map((sym, idx) => (
              <div
                key={`edit-${sym.id}-${idx}`}
                className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs border ${getCategoryColor(sym.category)}`}
              >
                {sym.image_path && (
                  <img
                    src={assetUrl(sym.image_path)}
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
            <span className="text-xs text-gray-500 dark:text-gray-400 mr-2">Preview:</span>
            {glossSymbols() || <span className="italic text-gray-400">Empty message</span>}
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
          Save & Resend
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded text-sm hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          title="Cancel editing"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
