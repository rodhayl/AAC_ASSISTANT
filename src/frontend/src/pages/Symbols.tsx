import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Plus, Search, Edit, Trash2, Image as ImageIcon, Globe, Download } from 'lucide-react';
import api from '../lib/api';
import { assetUrl } from '../lib/utils';
import { Button } from '../components/ui/Button';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import type { Symbol as SymbolType } from '../types';
import { useTranslation } from 'react-i18next';

type UsageFilter = 'all' | 'in_use' | 'unused';

interface ArasaacSymbol {
  id: number;
  label: string;
  description?: string;
  keywords?: string;
  image_url: string;
}

export function Symbols() {
  const [symbols, setSymbols] = useState<SymbolType[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [usage, setUsage] = useState<UsageFilter>('all');
  const [sort, setSort] = useState('default');
  const [category, setCategory] = useState('all');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({ label: '', description: '', category: 'general', keywords: '' });
  // const [uploadingId, setUploadingId] = useState<number | 'new' | null>(null);
  const [newFile, setNewFile] = useState<File | null>(null);
  const [newPreview, setNewPreview] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [page, setPage] = useState(0);
  const pageSize = 100;
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const formRef = useRef<HTMLDivElement>(null);

  const [deleteState, setDeleteState] = useState<{
    isOpen: boolean;
    mode: 'single' | 'batch';
    id?: number;
    force: boolean;
    title: string;
    description: string;
    isLoading: boolean;
  }>({
    isOpen: false,
    mode: 'single',
    force: false,
    title: '',
    description: '',
    isLoading: false
  });

  // ARASAAC State
  const [showArasaac, setShowArasaac] = useState(false);
  const [arasaacQuery, setArasaacQuery] = useState('');
  const [arasaacResults, setArasaacResults] = useState<ArasaacSymbol[]>([]);
  const [isSearchingArasaac, setIsSearchingArasaac] = useState(false);
  const [importingId, setImportingId] = useState<number | null>(null);
  const { t, i18n } = useTranslation('symbols');

  const fetchSymbols = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number> = { skip: page * pageSize, limit: pageSize };
      if (usage !== 'all') params.usage = usage;
      if (category !== 'all') params.category = category;
      if (search) params.search = search;
      if (sort !== 'default') params.sort = sort;
      const res = await api.get('/boards/symbols', { params });
      setSymbols(res.data);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err?.response?.data?.detail || 'Failed to load symbols');
    } finally {
      setIsLoading(false);
    }
  }, [usage, category, search, page, sort]);

  useEffect(() => {
    fetchSymbols();
  }, [fetchSymbols]);

  const categories = useMemo(() => {
    const set = new Set<string>([
      'general', 'action', 'feeling', 'person', 'social', 
      'food', 'object', 'place', 'question', 'time', 'adjective', 'core', 'ARASAAC'
    ]);
    symbols.forEach(s => s.category && set.add(s.category));
    return ['all', ...Array.from(set).sort()];
  }, [symbols]);

  const availableCategories = useMemo(() => {
    const set = new Set<string>([
      'general', 'action', 'feeling', 'person', 'social', 
      'food', 'object', 'place', 'question', 'time', 'adjective', 'core', 'ARASAAC'
    ]);
    symbols.forEach(s => s.category && set.add(s.category));
    return Array.from(set).sort();
  }, [symbols]);

  const resetForm = () => {
    setForm({ label: '', description: '', category: 'general', keywords: '' });
    setNewFile(null);
    setNewPreview(null);
    setEditingId(null);
    if (formRef.current) {
      formRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const startEdit = (sym: SymbolType) => {
    setEditingId(sym.id);
    setForm({
      label: sym.label,
      description: sym.description || '',
      category: sym.category || 'general',
      keywords: sym.keywords || ''
    });
    setNewFile(null);
    setNewPreview(null);
    if (formRef.current) {
      formRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const submitEdit = async () => {
    if (!editingId) return;
    setCreating(true);
    try {
      await api.put(`/boards/symbols/${editingId}`, {
        label: form.label,
        description: form.description,
        category: form.category,
        keywords: form.keywords
      });
      if (newFile) {
        const fd = new FormData();
        fd.append('file', newFile);
        await api.post(`/boards/symbols/${editingId}/image`, fd);
      }
      resetForm();
      await fetchSymbols();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err?.response?.data?.detail || 'Failed to update symbol');
    } finally {
      setCreating(false);
    }
  };

  const submitCreate = async () => {
    if (!form.label) return;
    setCreating(true);
    try {
      if (newFile) {
        const fd = new FormData();
        fd.append('file', newFile);
        fd.append('label', form.label);
        fd.append('description', form.description);
        fd.append('category', form.category);
        fd.append('keywords', form.keywords);
        await api.post('/boards/symbols/upload', fd);
      } else {
        await api.post('/boards/symbols', {
          label: form.label,
          description: form.description,
          category: form.category,
          keywords: form.keywords
        });
      }
      resetForm();
      await fetchSymbols();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err?.response?.data?.detail || 'Failed to create symbol');
    } finally {
      setCreating(false);
    }
  };

  const deleteSymbol = (id: number) => {
    setDeleteState({
      isOpen: true,
      mode: 'single',
      id,
      force: false,
      title: t('deleteSymbol') || 'Delete Symbol',
      description: t('deleteSymbolConfirm') || 'Delete this symbol?',
      isLoading: false
    });
  };

  const deleteSelected = () => {
    setDeleteState({
      isOpen: true,
      mode: 'batch',
      force: false,
      title: t('deleteSymbols') || 'Delete Symbols',
      description: t('deleteSelectedConfirm', { count: selectedIds.size }) || `Delete ${selectedIds.size} selected symbols?`,
      isLoading: false
    });
  };

  const confirmDelete = async () => {
    setDeleteState(prev => ({ ...prev, isLoading: true }));
    try {
      if (deleteState.mode === 'single' && deleteState.id) {
        const url = `/boards/symbols/${deleteState.id}${deleteState.force ? '?force=true' : ''}`;
        await api.delete(url);
        setSymbols(prev => prev.filter(s => s.id !== deleteState.id));
        setSelectedIds(prev => {
          const next = new Set(prev);
          next.delete(deleteState.id!);
          return next;
        });
        setDeleteState(prev => ({ ...prev, isOpen: false }));
      } else if (deleteState.mode === 'batch') {
        const ids = Array.from(selectedIds);
        const failures: string[] = [];
        const deletedIds: number[] = [];

        for (const id of ids) {
          try {
            await api.delete(`/boards/symbols/${id}`);
            deletedIds.push(id);
          } catch (e: unknown) {
            const err = e as { response?: { data?: { detail?: string }, status?: number } };
            const detail = err?.response?.data?.detail || 'Failed';
            if (err?.response?.status === 400 && detail.toLowerCase().includes('in use')) {
              try {
                await api.delete(`/boards/symbols/${id}?force=true`);
                deletedIds.push(id);
                continue;
              } catch (err2: unknown) {
                const errDetail = (err2 as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'force delete failed';
                failures.push(`ID ${id}: ${errDetail}`);
                continue;
              }
            }
            failures.push(`ID ${id}: ${detail}`);
          }
        }
        setSymbols(prev => prev.filter(s => !deletedIds.includes(s.id)));
        setSelectedIds(prev => {
          const next = new Set(prev);
          deletedIds.forEach(id => next.delete(id));
          return next;
        });
        
        if (failures.length) {
          setError(`Some deletions failed: ${failures.join('; ')}`);
        }
        setDeleteState(prev => ({ ...prev, isOpen: false }));
      }
    } catch (e: unknown) {
      if (deleteState.mode === 'single') {
        const err = e as { response?: { data?: { detail?: string }, status?: number } };
        const detail = err?.response?.data?.detail || 'Failed to delete symbol';
        if (err?.response?.status === 400 && detail.toLowerCase().includes('in use')) {
          setDeleteState(prev => ({
            ...prev,
            force: true,
            isLoading: false,
            description: t('symbolInUseForceDelete') || 'Symbol is in use on boards. Remove it from all boards and delete?'
          }));
          return;
        }
        setError(detail);
        setDeleteState(prev => ({ ...prev, isOpen: false }));
      } else {
        setError('Batch delete failed unexpectedly');
        setDeleteState(prev => ({ ...prev, isOpen: false }));
      }
    } finally {
      setDeleteState(prev => ({ ...prev, isLoading: false }));
    }
  };


  const handleFile = (file: File | null) => {
    if (!file) {
      setNewFile(null);
      setNewPreview(null);
      return;
    }
    const isImage = file.type.startsWith('image/');
    const maxSizeMb = 5;
    if (!isImage || file.size > maxSizeMb * 1024 * 1024) {
      setError(`Invalid file. Must be an image under ${maxSizeMb}MB.`);
      setNewFile(null);
      setNewPreview(null);
      return;
    }
    setError(null);
    setNewFile(file);
    setNewPreview(URL.createObjectURL(file));
  };

  const searchArasaac = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!arasaacQuery.trim()) return;
    setIsSearchingArasaac(true);
    setError(null);
    try {
      const locale = i18n.language?.split('-')[0] || 'es';
      const res = await api.get('/arasaac/search', { 
        params: { 
          q: arasaacQuery,
          locale: locale
        } 
      });
      setArasaacResults(res.data);
    } catch (e: unknown) {
      console.error(e);
      setError('Failed to search ARASAAC');
    } finally {
      setIsSearchingArasaac(false);
    }
  };

  const importArasaacSymbol = async (item: ArasaacSymbol) => {
    setImportingId(item.id);
    try {
      await api.post('/arasaac/import', {
        arasaac_id: item.id,
        label: item.label,
        description: item.description,
        keywords: item.keywords,
        category: 'ARASAAC'
      });
      await fetchSymbols();
      // Optional: Switch back to local view or show success
    } catch (e: unknown) {
      console.error(e);
      setError('Failed to import symbol');
    } finally {
      setImportingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <ConfirmDialog
        isOpen={deleteState.isOpen}
        onClose={() => setDeleteState(prev => ({ ...prev, isOpen: false }))}
        onConfirm={confirmDelete}
        title={deleteState.title}
        description={deleteState.description}
        confirmText={deleteState.force ? (t('forceDelete') || 'Force Delete') : (t('delete') || 'Delete')}
        cancelText={t('cancel')}
        variant="danger"
        isLoading={deleteState.isLoading}
      />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('title')}</h1>
          <p className="text-gray-500 dark:text-gray-400">{t('subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <Button 
            variant={showArasaac ? "primary" : "secondary"}
            onClick={() => setShowArasaac(!showArasaac)}
          >
            <Globe className="w-4 h-4 mr-2" /> 
            {showArasaac ? t('backToLibrary') : t('searchArasaac')}
          </Button>
          {!showArasaac && (
            <Button onClick={() => { resetForm(); setEditingId(null); }}>
              <Plus className="w-4 h-4 mr-2" /> {t('newSymbol')}
            </Button>
          )}
        </div>
      </div>

      {error && <div className="bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 p-3 rounded-lg">{error}</div>}

      {showArasaac ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 space-y-4">
          <div className="flex flex-col gap-2">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{t('searchArasaac')}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t('subtitle')}
            </p>
          </div>
          
          <form onSubmit={searchArasaac} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                value={arasaacQuery}
                onChange={(e) => setArasaacQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                placeholder={t('searchPlaceholder')}
                autoFocus
              />
            </div>
            <Button type="submit" loading={isSearchingArasaac} disabled={!arasaacQuery.trim()}>
              {t('search')}
            </Button>
          </form>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 mt-4">
            {arasaacResults.map((item) => (
              <div key={item.id} className="p-3 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900 flex flex-col gap-2 items-center text-center hover:border-indigo-500 transition-colors">
                <div className="w-24 h-24 bg-white rounded-lg p-2 flex items-center justify-center">
                  <img src={item.image_url} alt={item.label} className="max-w-full max-h-full object-contain" />
                </div>
                <div className="w-full">
                  <div className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate" title={item.label}>{item.label}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 truncate" title={item.keywords}>{item.keywords}</div>
                </div>
                <Button 
                  size="sm" 
                  className="w-full mt-1"
                  onClick={() => importArasaacSymbol(item)}
                  loading={importingId === item.id}
                  disabled={importingId !== null}
                >
                  <Download className="w-3 h-3 mr-1" /> {t('import')}
                </Button>
              </div>
            ))}
            {!isSearchingArasaac && arasaacResults.length === 0 && arasaacQuery && (
              <div className="col-span-full text-center py-8 text-gray-500">
                {t('noResults', { query: arasaacQuery })}
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
      <div ref={formRef} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('label')}</label>
            <input
              value={form.label}
              onChange={(e) => setForm(prev => ({ ...prev, label: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              placeholder="e.g., Hola"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('category')}</label>
            <select
              value={form.category}
              onChange={(e) => setForm(prev => ({ ...prev, category: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              {availableCategories.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('description')}</label>
            <input
              value={form.description}
              onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              placeholder={t('optionalDesc')}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('keywords')}</label>
            <input
              value={form.keywords}
              onChange={(e) => setForm(prev => ({ ...prev, keywords: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              placeholder={t('commaSeparated')}
            />
          </div>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
            <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700 dark:text-gray-300">
              <input
                type="file"
                accept="image/*"
                onChange={(e) => handleFile((e.target.files || [])[0] || null)}
              />
              <ImageIcon className="w-4 h-4" /> {newFile ? newFile.name : t('upload')}
            </label>
          {newPreview && <img src={newPreview} alt="preview" className="w-12 h-12 rounded object-cover border" />}
          <div className="flex gap-2">
            <Button
              variant="primary"
              onClick={editingId ? submitEdit : submitCreate}
              loading={creating}
              disabled={!form.label}
            >
              {editingId ? t('save') : t('create')}
            </Button>
            {editingId && (
              <Button variant="ghost" onClick={resetForm}>
                {t('cancel')}
              </Button>
            )}
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 space-y-4">
        <div className="flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[200px] md:min-w-[280px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              placeholder={t('searchSymbols')}
            />
          </div>
          <div className="flex gap-2">
            {['all', 'in_use', 'unused'].map(u => (
              <Button
                key={u}
                variant={usage === u ? 'primary' : 'secondary'}
                onClick={() => { setUsage(u as UsageFilter); setPage(0); }}
                size="sm"
              >
                {u === 'all' ? t('filters.all') : u === 'in_use' ? t('filters.inUse') : t('filters.unused')}
              </Button>
            ))}
          </div>
          <select
            value={sort}
            onChange={(e) => { setSort(e.target.value); setPage(0); }}
            className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          >
            <option value="default">{t('filters.default')}</option>
            <option value="newest">{t('filters.newest')}</option>
            <option value="oldest">{t('filters.oldest')}</option>
            <option value="alpha">{t('filters.alpha')}</option>
          </select>
          <select
            value={category}
            onChange={(e) => { setCategory(e.target.value); setPage(0); }}
            className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
          >
            {categories.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <Button
            variant="danger"
            size="sm"
            onClick={deleteSelected}
            disabled={selectedIds.size === 0}
            title={t('deleteSelected')}
          >
            <Trash2 className="w-4 h-4 mr-1" /> {t('deleteSelected')}
          </Button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
          </div>
        ) : symbols.length === 0 ? (
          <div className="text-center text-gray-500 dark:text-gray-400 py-12">
            {t('noSymbols')}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {symbols.map(sym => (
              <div key={sym.id} className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <div className="w-12 h-12 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center overflow-hidden">
                    {sym.image_path ? (
                      <img src={assetUrl(sym.image_path)} alt={sym.label} className="w-full h-full object-cover" />
                    ) : (
                      <ImageIcon className="w-6 h-6 text-gray-400" />
                    )}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(sym.id)}
                      onChange={(e) => {
                        setSelectedIds(prev => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(sym.id); else next.delete(sym.id);
                          return next;
                        });
                      }}
                    />
                    <Button variant="secondary" size="sm" onClick={() => startEdit(sym)}>
                      <Edit className="w-4 h-4 mr-1" /> Edit
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => deleteSymbol(sym.id)}>
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
        )}

        <div className="flex justify-center gap-2 mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
          <Button 
            variant="secondary" 
            disabled={page === 0} 
            onClick={() => setPage(p => Math.max(0, p - 1))}
          >
            {t('previous')}
          </Button>
          <span className="flex items-center px-2 text-sm text-gray-500">Page {page + 1}</span>
          <Button 
            variant="secondary" 
            disabled={symbols.length < pageSize} 
            onClick={() => setPage(p => p + 1)}
          >
            {t('next')}
          </Button>
        </div>
      </div>
      </>
      )}
    </div>
  );
}
