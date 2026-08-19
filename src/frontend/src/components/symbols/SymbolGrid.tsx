import { Edit, Image as ImageIcon, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Symbol as SymbolType } from '../../types';
import { SymbolImage } from '../common/SymbolImage';
import { Button } from '../ui/Button';

type SymbolGridProps = {
  symbols: SymbolType[];
  selectedIds: Set<number>;
  onToggleSelection: (id: number, selected: boolean) => void;
  onEdit: (symbol: SymbolType) => void;
  onDelete: (id: number) => void;
  page: number;
  pageSize: number;
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
  pageSize,
  onPreviousPage,
  onNextPage,
}: SymbolGridProps) {
  const { t } = useTranslation('symbols');

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {symbols.map(sym => (
          <div key={sym.id} className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="w-12 h-12 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center overflow-hidden">
                {sym.image_path ? (
                  <SymbolImage imagePath={sym.image_path} alt={sym.label} className="w-full h-full object-cover" />
                ) : (
                  <ImageIcon className="w-6 h-6 text-gray-400" />
                )}
              </div>
              <div className="flex gap-2">
                <input
                  type="checkbox"
                  checked={selectedIds.has(sym.id)}
                  onChange={(e) => onToggleSelection(sym.id, e.target.checked)}
                />
                <Button variant="secondary" size="sm" onClick={() => onEdit(sym)}>
                  <Edit className="w-4 h-4 mr-1" /> {t('edit', 'Edit')}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => onDelete(sym.id)} aria-label={t('deleteSymbol', 'Delete Symbol')}>
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>
            <div>
              <div className="font-semibold text-gray-900 dark:text-gray-100">{sym.label}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">{sym.category}</div>
              {sym.is_in_use && <span className="text-xs text-green-600">{t('inUse')}</span>}
            </div>
            <div className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2">{sym.description}</div>
          </div>
        ))}
      </div>

      <div className="flex justify-center gap-2 mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
        <Button
          variant="secondary"
          disabled={page === 0}
          onClick={onPreviousPage}
        >
          {t('previous')}
        </Button>
        <span className="flex items-center px-2 text-sm text-gray-500">{t('page', 'Page {{n}}', { n: page + 1 })}</span>
        <Button
          variant="secondary"
          disabled={symbols.length < pageSize}
          onClick={onNextPage}
        >
          {t('next')}
        </Button>
      </div>
    </>
  );
}
