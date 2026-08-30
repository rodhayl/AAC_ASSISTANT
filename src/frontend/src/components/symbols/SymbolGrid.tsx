import { Edit, Image as ImageIcon, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Symbol as SymbolType } from '../../types';
import { SymbolImage } from '../common/SymbolImage';
import { Button } from '../ui/button';

type SymbolGridProps = {
  symbols: SymbolType[];
  selectedIds: Set<number>;
  onToggleSelection: (id: number, selected: boolean) => void;
  onEdit: (symbol: SymbolType) => void;
  onDelete: (id: number) => void;
  page: number;
  hasMore: boolean;
  onPreviousPage: () => void;
  onNextPage: () => void;
};

export function SymbolGrid({
  symbols,
  selectedIds,
  onToggleSelection,
  onEdit,
  onDelete,
  page,
  hasMore,
  onPreviousPage,
  onNextPage,
}: SymbolGridProps) {
  const { t } = useTranslation('symbols');

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {symbols.map(sym => (
          <div key={sym.id} className="p-4 border border-border rounded-lg bg-surface flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center overflow-hidden">
                {sym.image_path ? (
                  <SymbolImage imagePath={sym.image_path} alt={sym.label} className="w-full h-full object-cover" />
                ) : (
                  <ImageIcon className="w-6 h-6 text-muted-foreground" />
                )}
              </div>
              <div className="flex gap-2">
                <input
                  type="checkbox"
                  checked={selectedIds.has(sym.id)}
                  onChange={(e) => onToggleSelection(sym.id, e.target.checked)}
                />
                <Button variant="outline" size="sm" onClick={() => onEdit(sym)}>
                  <Edit className="w-4 h-4 mr-1" /> {t('edit')}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => onDelete(sym.id)} aria-label={t('deleteSymbol')}>
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>
            <div>
              <div className="font-semibold text-foreground">{sym.label}</div>
              <div className="text-xs text-muted-foreground">{sym.category}</div>
              {sym.is_in_use && <span className="text-xs text-green-700 dark:text-green-400">{t('inUse')}</span>}
            </div>
            <div className="text-sm text-muted-foreground line-clamp-2">{sym.description}</div>
          </div>
        ))}
      </div>

      <div className="flex justify-center gap-2 mt-4 border-t border-border pt-4">
        <Button
          variant="outline"
          disabled={page === 0}
          onClick={onPreviousPage}
        >
          {t('previous')}
        </Button>
        <span className="flex items-center px-2 text-sm text-muted-foreground">{t('page', { n: page + 1 })}</span>
        <Button
          variant="outline"
          disabled={!hasMore}
          onClick={onNextPage}
        >
          {t('next')}
        </Button>
      </div>
    </>
  );
}
