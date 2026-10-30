import { useState, useEffect, useCallback } from 'react';
import { X, Search, ArrowUp, ArrowDown, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useToastStore } from '../../store/toastStore';
import api from '../../lib/api';
import { SymbolImage } from '../common/SymbolImage';
import type { Symbol } from '../../types';
import { getCategoryStyle } from '../../lib/symbolCategoryStyle';

interface SymbolPickerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (symbolId: number) => void;
  position: { x: number; y: number };
}

export function SymbolPicker({ isOpen, onClose, onSelect, position }: SymbolPickerProps) {
  const { t } = useTranslation('boards');
  const { addToast } = useToastStore();
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

  // Fetch categories once on open
  useEffect(() => {
    if (isOpen) {
      // Fetch enough symbols to likely cover all categories
      api.get('/boards/symbols', { params: { limit: 1000 } }).then(res => {
        const uniqueCats = Array.from(new Set(res.data.map((s: Symbol) => s.category))).sort();
        // Ensure 'core' is present if it exists in DB, or just rely on the fetch
        // We also want 'core' to be near the top if possible, but alphabetical is fine for now
        setCategories(['all', ...uniqueCats] as string[]);
      }).catch(err => console.error("Failed to fetch categories", err));
    }
  }, [isOpen]);

  const fetchSymbols = useCallback(async () => {
    setIsLoading(true);
    try {
      const params: Record<string, string> = {};
      if (selectedCategory !== 'all') {
        params.category = selectedCategory;
      }
      if (searchTerm) {
        params.search = searchTerm;
      }

      const response = await api.get('/boards/symbols', { params });
      setSymbols(response.data);
    } catch (error) {
      console.error('Failed to fetch symbols:', error);
    } finally {
      setIsLoading(false);
    }
  }, [selectedCategory, searchTerm]);

  useEffect(() => {
    if (isOpen) {
      const timeoutId = setTimeout(() => {
        fetchSymbols();
      }, 300);
      return () => clearTimeout(timeoutId);
    }
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
      const err = e as { response?: { data?: { detail?: string } } };
      const detail = err?.response?.data?.detail || t('symbolPicker.uploadFailed');
      setUploadError(detail);
    } finally {
      setIsUploading(false);
    }
  }, [uploadFile, uploadLabel, uploadCategory, onSelect, onClose, fetchSymbols, t]);

  const handleMultiUpload = useCallback(async (files: File[]) => {
    const valid = files.filter(f => f.type.startsWith('image/') && f.size <= 5 * 1024 * 1024)
    if (valid.length === 0) return
    setIsUploading(true)
    try {
      for (const f of valid) {
        const fd = new FormData()
        fd.append('file', f)
        fd.append('label', uploadLabel || f.name)
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
    <div className="fixed inset-0 bg-black bg-opacity-50 dark:bg-opacity-70 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-900/90 backdrop-blur-xl border border-border dark:border-white/10 rounded-xl shadow-2xl w-full max-w-4xl max-h-[80vh] flex flex-col">
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                {reorderMode ? t('symbolPicker.reorderTitle') : t('symbolPicker.title')}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {reorderMode
                  ? t('symbolPicker.reorderInstructions')
                  : t('symbolPicker.position', { x: position.x, y: position.y })
                }
              </p>
            </div>
            <div className="flex items-center gap-2">
              {reorderMode && (
                <button
                  onClick={saveOrder}
                  disabled={isSavingOrder}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 flex items-center gap-2"
                  title={t('symbolPicker.saveOrder')}
                >
                  <Save className="w-4 h-4" />
                  {isSavingOrder ? t('symbolPicker.saving') : t('symbolPicker.saveOrder')}
                </button>
              )}
              <button
                onClick={toggleReorderMode}
                disabled={selectedCategory === 'core'}
                className={`px-4 py-2 rounded-lg flex items-center gap-2 ${reorderMode
                    ? 'bg-gray-600 text-white hover:bg-gray-700'
                    : 'bg-indigo-600 text-white hover:bg-indigo-700'
                  } ${selectedCategory === 'core' ? 'opacity-50 cursor-not-allowed' : ''}`}
                title={selectedCategory === 'core' ? t('symbolPicker.reorderDisabledCore') : (reorderMode ? t('symbolPicker.cancelReorder') : t('symbolPicker.reorder'))}
              >
                {reorderMode ? t('symbolPicker.cancelReorder') : t('symbolPicker.reorder')}
              </button>
              <button
                onClick={onClose}
                className="p-2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                aria-label={t('symbolPicker.cancel')}
              >
                <X className="w-6 h-6" />
              </button>
            </div>
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 dark:text-gray-500 w-5 h-5" />
            <input
              id="symbol-picker-search"
              name="symbol_picker_search"
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder={t('symbolPicker.searchPlaceholder')}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
          </div>

          <div className="flex gap-2 mt-4 overflow-x-auto pb-2">
            {categories.map((category) => (
              <button
                key={category}
                onClick={() => setSelectedCategory(category)}
                className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${selectedCategory === category
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
              >
                {t(`categories.${category}`, category.replace('_', ' ').toUpperCase())}
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
                  const isImage = f.type.startsWith('image/')
                  const maxSizeMb = 5
                  const tooLarge = f.size > maxSizeMb * 1024 * 1024
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
                  setPreviewUrl(URL.createObjectURL(f))
                  if (files.length > 1) {
                    handleMultiUpload(files)
                  }
                } else {
                  setUploadFile(null)
                }
              }}
              className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
            <input
              type="text"
              value={uploadLabel}
              onChange={(e) => setUploadLabel(e.target.value)}
              placeholder={t('symbolPicker.label')}
              className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            />
            <select
              value={uploadCategory}
              onChange={(e) => setUploadCategory(e.target.value)}
              className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              {categories.filter(c => c !== 'all').map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
              {!categories.includes(uploadCategory) && (
                <option value={uploadCategory}>{uploadCategory}</option>
              )}
            </select>
            {previewUrl && (
              <div className="md:col-span-3 mt-2 flex items-center gap-3">
                <img src={previewUrl} alt="Preview" className="w-16 h-16 object-cover rounded" />
                <span className="text-xs text-gray-500 dark:text-gray-400">{t('symbolPicker.preview')}</span>
              </div>
            )}
            {uploadError && (
              <div className="md:col-span-3 mt-2 text-sm text-red-600 dark:text-red-400">{uploadError}</div>
            )}
            <button
              onClick={handleUpload}
              disabled={!uploadFile || !uploadLabel || !!uploadError || isUploading}
              className={`md:col-span-3 mt-2 px-4 py-2 rounded-lg ${!uploadFile || !uploadLabel || !!uploadError || isUploading
                  ? 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400'
                  : 'bg-indigo-600 text-white hover:bg-indigo-700'
                }`}
            >
              {isUploading ? t('symbolPicker.uploading') : t('symbolPicker.uploadNew')}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
            </div>
          ) : symbols.length === 0 ? (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <p>{t('symbolPicker.noSymbolsFound')}</p>
              {searchTerm && (
                <button
                  onClick={() => setSearchTerm('')}
                  className="mt-2 text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300"
                >
                  {t('symbolPicker.clearSearch')}
                </button>
              )}
            </div>
          ) : (
            <div
              className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4"
              style={{ minHeight: '360px' }} // ~3 rows at lg
            >
              {(reorderMode ? reorderedSymbols : symbols).map((symbol, index) => (
                (() => {
                  const categoryStyle = getCategoryStyle(symbol.category);
                  return (
                    <div
                      key={symbol.id}
                      className={`relative group p-4 border-2 ${categoryStyle.border} rounded-xl ${categoryStyle.hoverBorder} hover:shadow-md transition-all duration-200 flex flex-col items-center bg-white dark:bg-gray-800`}
                    >
                      <div className={`absolute top-2 left-2 w-2.5 h-2.5 rounded-full ${categoryStyle.dot} opacity-80`} aria-hidden="true" />
                      {reorderMode && (
                        <div className="absolute top-2 right-2 flex flex-col gap-1">
                          <button
                            onClick={() => moveSymbol(index, 'up')}
                            disabled={index === 0}
                            className={`p-1 rounded bg-white dark:bg-gray-700 shadow-sm border border-gray-200 dark:border-gray-600 ${index === 0
                                ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                                : 'text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30'
                              }`}
                            title={t('symbolPicker.moveUp')}
                          >
                            <ArrowUp className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => moveSymbol(index, 'down')}
                            disabled={index === (reorderMode ? reorderedSymbols : symbols).length - 1}
                            className={`p-1 rounded bg-white dark:bg-gray-700 shadow-sm border border-gray-200 dark:border-gray-600 ${index === (reorderMode ? reorderedSymbols : symbols).length - 1
                                ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                                : 'text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30'
                              }`}
                            title={t('symbolPicker.moveDown')}
                          >
                            <ArrowDown className="w-4 h-4" />
                          </button>
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
                        <span className="text-sm font-medium text-gray-900 dark:text-gray-100 text-center line-clamp-2">
                          {symbol.label}
                        </span>
                        <span className="text-xs text-gray-500 dark:text-gray-400 mt-1">
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

        <div className="p-4 border-t border-border dark:border-white/5 bg-gray-50 dark:bg-white/5 rounded-b-xl">
          <div className="flex justify-between items-center text-sm text-gray-600 dark:text-gray-400">
            <span>{t('symbolPicker.symbolsAvailable', { count: symbols.length })}</span>
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              {t('symbolPicker.cancel')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
