import { useState, useEffect, useCallback, useRef } from 'react';
import { X, Search, ArrowUp, ArrowDown, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useToastStore } from '../../store/toastStore';
import api, { extractError } from '../../lib/api';
import { walkPages } from '../../lib/pagination';
import { SymbolImage } from '../common/SymbolImage';
import { Button } from '../ui/button';
import { IconButton } from '../ui/icon-button';
import type { Symbol } from '../../types';
import { getCategoryStyle } from '../../lib/symbolCategoryStyle';
import { isValidImageFile } from '../../lib/download';
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '../ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

interface SymbolPickerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (symbolId: number) => void;
  position: { x: number; y: number };
}

const SYMBOL_PICKER_PAGE_SIZE = 1000;

export function SymbolPicker({ isOpen, onClose, onSelect, position }: SymbolPickerProps) {
  const { t } = useTranslation('boards');
  const addToast = useToastStore((state) => state.addToast);
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [isLoading, setIsLoading] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadLabel, setUploadLabel] = useState('');
  const [uploadCategory, setUploadCategory] = useState('general');
  const [isUploading, setIsUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [reorderMode, setReorderMode] = useState(false);
  const [reorderedSymbols, setReorderedSymbols] = useState<Symbol[]>([]);
  const [isSavingOrder, setIsSavingOrder] = useState(false);
  const symbolRequestIdRef = useRef(0);

  useEffect(() => {
    if (!isOpen && (previewUrl || uploadFile)) {
      setPreviewUrl(null);
      setUploadFile(null);
    }
  }, [isOpen, previewUrl, uploadFile]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  // Fetch categories once on open
  useEffect(() => {
    if (isOpen) {
      api.get<string[]>('/boards/symbols/categories').then(res => {
        setCategories(['all', ...res.data]);
      }).catch(err => console.error("Failed to fetch categories", err));
    }
  }, [isOpen]);

  const fetchSymbols = useCallback(async () => {
    const requestId = ++symbolRequestIdRef.current;
    setIsLoading(true);
    try {
      const params: Record<string, string> = {};
      if (selectedCategory !== 'all') {
        params.category = selectedCategory;
      }
      if (searchTerm) {
        params.search = searchTerm;
      }

      // Walk every page: the backend caps a single request at `limit`
      // (default 100, max 1000), so one fetch silently truncated catalogs
      // with more symbols than the page size.
      const symbols = await walkPages<Symbol>({
        pageSize: SYMBOL_PICKER_PAGE_SIZE,
        fetchPage: async (skip) => {
          const response = await api.get('/boards/symbols', {
            params: { ...params, skip, limit: SYMBOL_PICKER_PAGE_SIZE },
          });
          return response.data;
        },
        isCancelled: () => requestId !== symbolRequestIdRef.current,
      });
      if (requestId !== symbolRequestIdRef.current) return;
      setSymbols(symbols);
    } catch (error) {
      if (requestId === symbolRequestIdRef.current) {
        console.error('Failed to fetch symbols:', error);
      }
    } finally {
      if (requestId === symbolRequestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [selectedCategory, searchTerm]);

  useEffect(() => {
    if (isOpen) {
      const timeoutId = setTimeout(() => {
        void fetchSymbols();
      }, 300);
      return () => {
        clearTimeout(timeoutId);
        symbolRequestIdRef.current += 1;
      };
    }
    symbolRequestIdRef.current += 1;
    return undefined;
  }, [isOpen, fetchSymbols]);

  const toggleReorderMode = useCallback(() => {
    if (!reorderMode) {
      setReorderedSymbols([...symbols]);
    }
    setReorderMode(!reorderMode);
  }, [reorderMode, symbols]);

  const moveSymbol = useCallback((index: number, direction: 'up' | 'down') => {
    const newSymbols = [...reorderedSymbols];
    const targetIndex = direction === 'up' ? index - 1 : index + 1;

    if (targetIndex < 0 || targetIndex >= newSymbols.length) return;

    [newSymbols[index], newSymbols[targetIndex]] = [newSymbols[targetIndex], newSymbols[index]];
    setReorderedSymbols(newSymbols);
  }, [reorderedSymbols]);

  const saveOrder = useCallback(async () => {
    setIsSavingOrder(true);
    try {
      const updates = reorderedSymbols.map((symbol, index) => ({
        id: symbol.id,
        order_index: index * 10
      }));

      await api.put('/boards/symbols/reorder', updates);

      setSymbols(reorderedSymbols);
      setReorderMode(false);

      addToast(t('symbolPicker.orderSaved'), 'success');
    } catch (error) {
      console.error('Failed to save symbol order:', error);
      addToast(t('symbolPicker.orderSaveFailed'), 'error');
    } finally {
      setIsSavingOrder(false);
    }
  }, [reorderedSymbols, t, addToast]);

  const handleSelect = useCallback((symbolId: number) => {
    if (reorderMode) return;
    onSelect(symbolId);
    onClose();
    setSearchTerm('');
  }, [reorderMode, onSelect, onClose]);

  const handleUpload = useCallback(async () => {
    if (!uploadFile || !uploadLabel) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      const fd = new FormData();
      fd.append('file', uploadFile);
      fd.append('label', uploadLabel);
      fd.append('category', uploadCategory);
      const res = await api.post('/boards/symbols/upload', fd);
      const created: Symbol = res.data;

      // Refresh symbols
      fetchSymbols();

      setUploadFile(null);
      setUploadLabel('');
      setUploadCategory('general');
      setPreviewUrl(null);
      onSelect(created.id);
      onClose();
    } catch (e: unknown) {
      console.error('Failed to upload symbol:', e);
      const detail = extractError(e, t('symbolPicker.uploadFailed'));
      setUploadError(detail);
    } finally {
      setIsUploading(false);
    }
  }, [uploadFile, uploadLabel, uploadCategory, onSelect, onClose, fetchSymbols, t]);

  const handleMultiUpload = useCallback(async (files: File[]) => {
    const valid = files.filter((file) => isValidImageFile(file))
    if (valid.length === 0) return
    setIsUploading(true)
    try {
      // A batch of files must not all inherit the single-upload label field:
      // each file gets its own name-based label (extension stripped), while a
      // lone file still honors an explicitly typed label.
      const labelForFile = (file: File) =>
        (file.name || '').replace(/\.[^.]+$/, '') || 'symbol';
      for (const f of valid) {
        const fd = new FormData()
        fd.append('file', f)
        fd.append('label', valid.length === 1 ? (uploadLabel || labelForFile(f)) : labelForFile(f))
        fd.append('category', uploadCategory)
        await api.post('/boards/symbols/upload', fd)
      }
      fetchSymbols();
      setUploadFile(null)
      setUploadLabel('')
      setUploadCategory('general')
    } catch (e) {
      console.error('Failed to upload symbols:', e)
      setUploadError(t('symbolPicker.uploadFailed'))
    } finally {
      setIsUploading(false)
    }
  }, [uploadLabel, uploadCategory, fetchSymbols, t]);

  if (!isOpen) return null;

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        showCloseButton={false}
        className="max-w-4xl max-h-[80vh] flex flex-col p-0"
      >
        <div className="p-6 border-b border-border">
          <div className="flex justify-between items-center mb-4">
            <div>
              <DialogTitle className="text-2xl font-bold text-foreground">
                {reorderMode ? t('symbolPicker.reorderTitle') : t('symbolPicker.title')}
              </DialogTitle>
              <p className="text-sm text-muted-foreground mt-1">
                {reorderMode
                  ? t('symbolPicker.reorderInstructions')
                  : t('symbolPicker.position', { x: position.x, y: position.y })
                }
              </p>
            </div>
            <div className="flex items-center gap-2">
              {reorderMode && (
                <Button
                  variant="success"
                  onClick={saveOrder}
                  loading={isSavingOrder}
                  title={t('symbolPicker.saveOrder')}
                >
                  <Save />
                  {isSavingOrder ? t('symbolPicker.saving') : t('symbolPicker.saveOrder')}
                </Button>
              )}
              <button
                onClick={toggleReorderMode}
                disabled={selectedCategory === 'core'}
                className={`px-4 py-2 rounded-lg flex items-center gap-2 ${reorderMode
                    ? 'bg-muted-foreground text-white hover:bg-surface-hover'
                    : 'bg-brand text-white hover:bg-brand/80'
                  } ${selectedCategory === 'core' ? 'opacity-50 cursor-not-allowed' : ''}`}
                title={selectedCategory === 'core' ? t('symbolPicker.reorderDisabledCore') : (reorderMode ? t('symbolPicker.cancelReorder') : t('symbolPicker.reorder'))}
              >
                {reorderMode ? t('symbolPicker.cancelReorder') : t('symbolPicker.reorder')}
              </button>
              <button
                onClick={onClose}
                className="p-2 text-muted-foreground hover:text-foreground hover:bg-surface-hover rounded-lg transition-colors"
                aria-label={t('symbolPicker.cancel')}
              >
                <X className="w-6 h-6" />
              </button>
            </div>
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
            <input
              id="symbol-picker-search"
              name="symbol_picker_search"
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={t('symbolPicker.searchPlaceholder')}
              aria-label={t('symbolPicker.searchPlaceholder')}
              className="w-full pl-10 pr-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-brand focus:border-transparent bg-surface text-foreground"
            />
          </div>

          <div className="flex gap-2 mt-4 overflow-x-auto pb-2">
            {categories.map((category) => (
              <button
                key={category}
                onClick={() => setSelectedCategory(category)}
                className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${selectedCategory === category
                    ? 'bg-brand text-white'
                    : 'bg-muted text-foreground hover:bg-surface-hover'
                  }`}
              >
                {t(`categories.${category}`)}
              </button>
            ))}
          </div>

          <div
            className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3"
            onDragOver={(e) => { e.preventDefault() }}
            onDrop={async (e) => {
              e.preventDefault()
              setUploadError(null)
              const files = Array.from(e.dataTransfer.files || [])
              await handleMultiUpload(files)
            }}
          >
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={(e) => {
                const files = Array.from(e.target.files || [])
                const f = files[0] || null
                setUploadError(null)
                setPreviewUrl(null)
                if (f) {
                  const maxSizeMb = 5
                  const isImage = f.type.startsWith('image/')
                  const tooLarge = !isValidImageFile(f)
                  if (!isImage) {
                    setUploadError(t('symbolPicker.invalidFileType'))
                    setUploadFile(null)
                    return
                  }
                  if (tooLarge) {
                    setUploadError(t('symbolPicker.fileTooLarge', { size: maxSizeMb }))
                    setUploadFile(null)
                    return
                  }
                  setUploadFile(f)
                  const reader = new FileReader()
                  reader.onload = () => {
                    if (typeof reader.result === 'string' && reader.result.startsWith('data:image/')) {
                      setPreviewUrl(reader.result)
                    }
                  }
                  reader.readAsDataURL(f)
                  if (files.length > 1) {
                    handleMultiUpload(files)
                  }
                } else {
                  setUploadFile(null)
                }
              }}
              className="border border-border rounded-lg px-3 py-2 bg-surface text-foreground"
            />
            <input
              type="text"
              value={uploadLabel}
              onChange={(e) => setUploadLabel(e.target.value)}
              placeholder={t('symbolPicker.label')}
              className="border border-border rounded-lg px-3 py-2 bg-surface text-foreground"
            />
            <Select
              value={uploadCategory}
              onValueChange={(value) => setUploadCategory(value ?? uploadCategory)}
              items={[
                ...categories.filter(c => c !== 'all').map((c) => ({ value: c, label: c })),
                ...(!categories.includes(uploadCategory)
                  ? [{ value: uploadCategory, label: uploadCategory }]
                  : []),
              ]}
            >
              <SelectTrigger aria-label={t('category')} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {categories.filter(c => c !== 'all').map(c => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
                {!categories.includes(uploadCategory) && (
                  <SelectItem value={uploadCategory}>{uploadCategory}</SelectItem>
                )}
              </SelectContent>
            </Select>
            {previewUrl && previewUrl.startsWith('data:image/') && (
              <div className="md:col-span-3 mt-2 flex items-center gap-3">
                <img src={previewUrl} alt={t('symbolPicker.preview')} className="w-16 h-16 object-cover rounded" />
                <span className="text-xs text-muted-foreground">{t('symbolPicker.preview')}</span>
              </div>
            )}
            {uploadError && (
              <div className="md:col-span-3 mt-2 text-sm text-red-600 dark:text-red-400">{uploadError}</div>
            )}
            <button
              onClick={handleUpload}
              disabled={!uploadFile || !uploadLabel || !!uploadError || isUploading}
              className={`md:col-span-3 mt-2 px-4 py-2 rounded-lg ${!uploadFile || !uploadLabel || !!uploadError || isUploading
                  ? 'bg-muted text-foreground hover:bg-surface-hover'
                  : 'bg-brand text-white hover:bg-brand/80'
                }`}
            >
              {isUploading ? t('symbolPicker.uploading') : t('symbolPicker.uploadNew')}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand"></div>
            </div>
          ) : symbols.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <p>{t('symbolPicker.noSymbolsFound')}</p>
              {searchTerm && (
                <button
                  onClick={() => setSearchTerm('')}
                  className="mt-2 text-brand hover:text-brand"
                >
                  {t('symbolPicker.clearSearch')}
                </button>
              )}
            </div>
          ) : (
            <div
              className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4"
              /* ~3 rows at lg */
            >
              {(reorderMode ? reorderedSymbols : symbols).map((symbol, index) => (
                (() => {
                  const categoryStyle = getCategoryStyle(symbol.category);
                  return (
                    <div
                      key={symbol.id}
                      className={`relative group p-4 border-2 ${categoryStyle.border} rounded-xl ${categoryStyle.hoverBorder} hover:shadow-md transition-all duration-200 flex flex-col items-center bg-surface`}
                    >
                      <div className={`absolute top-2 left-2 w-2.5 h-2.5 rounded-full ${categoryStyle.dot} opacity-80`} aria-hidden="true" />
                      {reorderMode && (
                        <div className="absolute top-2 right-2 flex flex-col gap-1">
                          <IconButton
                            label={t('symbolPicker.moveUp')}
                            onClick={() => moveSymbol(index, 'up')}
                            disabled={index === 0}
                            className={`p-1 rounded bg-surface shadow-sm border border-border ${index === 0
                                ? 'text-muted-foreground cursor-not-allowed'
                                : 'text-brand hover:bg-brand/20'
                              }`}
                          >
                            <ArrowUp className="w-4 h-4" />
                          </IconButton>
                          <IconButton
                            label={t('symbolPicker.moveDown')}
                            onClick={() => moveSymbol(index, 'down')}
                            disabled={index === (reorderMode ? reorderedSymbols : symbols).length - 1}
                            className={`p-1 rounded bg-surface shadow-sm border border-border ${index === (reorderMode ? reorderedSymbols : symbols).length - 1
                                ? 'text-muted-foreground cursor-not-allowed'
                                : 'text-brand hover:bg-brand/20'
                              }`}
                          >
                            <ArrowDown className="w-4 h-4" />
                          </IconButton>
                        </div>
                      )}
                      <button
                        onClick={() => handleSelect(symbol.id)}
                        disabled={reorderMode}
                        className={`w-full flex flex-col items-center ${reorderMode ? 'cursor-default' : 'cursor-pointer'}`}
                      >
                        <div className="w-16 h-16 bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-900/30 dark:to-purple-900/30 rounded-lg flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                          <SymbolImage
                            imagePath={symbol.image_path}
                            alt={symbol.label}
                            className="w-12 h-12 object-contain"
                          />
                        </div>
                        <span className="text-sm font-medium text-foreground text-center line-clamp-2">
                          {symbol.label}
                        </span>
                        <span className="text-xs text-muted-foreground mt-1">
                          {symbol.category}
                        </span>
                      </button>
                    </div>
                  )
                })()
              ))}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-border bg-background rounded-b-xl">
          <div className="flex justify-between items-center text-sm text-muted-foreground">
            <span>{t('symbolPicker.symbolsAvailable', { count: symbols.length })}</span>
            <button
              onClick={onClose}
              className="px-4 py-2 text-foreground hover:bg-surface-hover rounded-lg transition-colors"
            >
              {t('symbolPicker.cancel')}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
