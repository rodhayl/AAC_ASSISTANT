import { useState } from 'react';
import { Edit, Check, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { SymbolImage } from './common/SymbolImage';
import { glossSymbolUtterance } from '../lib/gloss';
import { getCategoryStyle } from '../lib/symbolCategoryStyle';
import { Button } from './ui/button';

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
    <div className="bg-background border border-border rounded-lg p-3 my-2">
      <div className="flex items-center gap-2 mb-2 text-sm text-muted-foreground">
        <Edit className="w-4 h-4" />
        <span>{t('symbolEditor.title')}</span>
      </div>

      {editedSymbols.length === 0 ? (
        <div className="text-sm text-muted-foreground italic mb-3 p-2">
          {t('symbolEditor.emptyHint')}
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
                  className="ml-1 text-destructive hover:text-destructive/80 transition-colors"
                  aria-label={t('symbolEditor.removeSymbol', { label: sym.label })}
                  title={t('symbolEditor.removeSymbolTitle')}
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>

          <div className="text-sm text-foreground mb-3 p-2 bg-surface rounded border border-border">
            <span className="text-xs text-muted-foreground mr-2">{t('symbolEditor.preview')}</span>
            {glossSymbols() || <span className="italic text-muted-foreground">{t('symbolEditor.emptyMessage')}</span>}
          </div>
        </>
      )}

      <div className="flex gap-2">
        <Button onClick={handleSave} disabled={editedSymbols.length === 0} className="flex items-center gap-1 transition-colors" title={t('symbolEditor.saveResendTitle')} >
          <Check className="w-4 h-4" />
          {t('symbolEditor.saveResend')}
        </Button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 bg-muted text-foreground rounded text-sm hover:bg-surface-hover transition-colors"
          title={t('symbolEditor.cancelTitle')}
        >
          {t('symbolEditor.cancel')}
        </button>
      </div>
    </div>
  );
}
