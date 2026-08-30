import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Plus, Search, Trash2, Image as ImageIcon, Globe, Download } from 'lucide-react';
import api, { extractError } from '../lib/api';
import { Button } from '../components/ui/button';
import { StatusMessage } from '../components/ui/StatusMessage';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { SymbolGrid } from '../components/symbols/SymbolGrid';
import type { Symbol as SymbolType } from '../types';
import { useTranslation } from 'react-i18next';
import { ARASAAC_CATEGORY, DEFAULT_SYMBOL_CATEGORIES } from '../lib/symbolCategories';
import { isValidImageFile, MAX_IMAGE_FILE_BYTES } from '../lib/download';
import { SymbolImage } from '../components/common/SymbolImage';
import { useToastStore } from '../store/toastStore';

import { SectionTitle } from '@/components/ui/SectionTitle';

import { FormLabel } from '@/components/ui/FormLabel';

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
  const [newFile, setNewFile] = useState<File | null>(null);
  const [newPreview, setNewPreview] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [page, setPage] = useState(0);
  const pageSize = 100;
  const [hasMore, setHasMore] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [serverCategories, setServerCategories] = useState<string[]>([]);
  const formRef = useRef<HTMLDivElement>(null);
  // Latest-request-wins guard so a slow response cannot overwrite a newer one
  // when filters/search/sort change in quick succession.
  const fetchSeqRef = useRef(0);
  const arasaacSearchSeqRef = useRef(0);

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
  const addToast = useToastStore((state) => state.addToast);

  const fetchSymbols = useCallback(async () => {
    const seq = ++fetchSeqRef.current;
    setIsLoading(true);
    setError(null);
    try {
      // Request one extra item so we can detect whether a next page exists
      // without relying on the brittle "items < pageSize" heuristic.
      const params: Record<string, string | number> = { skip: page * pageSize, limit: pageSize + 1 };
      if (usage !== 'all') params.usage = usage;
      if (category !== 'all') params.category = category;
      if (search) params.search = search;
      if (sort !== 'default') params.sort = sort;
      const res = await api.get('/boards/symbols', { params });
      if (seq !== fetchSeqRef.current) return;
      const items: SymbolType[] = Array.isArray(res.data) ? res.data : [];
      setHasMore(items.length > pageSize);
      setSymbols(items.slice(0, pageSize));
    } catch (e: unknown) {
      if (seq !== fetchSeqRef.current) return;
      setError(extractError(e, t('loadFailed')));
    } finally {
      if (seq === fetchSeqRef.current) setIsLoading(false);
    }
  }, [usage, category, search, page, sort, t]);

  useEffect(() => {
    fetchSymbols();
  }, [fetchSymbols]);

  // The library can hold hundreds of ARASAAC categories, far more than the
  // current page's symbols can reveal; fetch the full category list so the
  // filter dropdown covers every imported category, not just the visible ones.
  useEffect(() => {
    let cancelled = false;
    api
      .get('/boards/symbols/categories')
      .then((res) => {
        if (!cancelled) {
          const list = Array.isArray(res.data) ? res.data : [];
          // The endpoint contract is list[str]; drop anything else so the
          // filter dropdown never tries to render a non-string option.
          setServerCategories(list.filter((c): c is string => typeof c === 'string'));
        }
      })
      .catch(() => {
        // Non-fatal: fall back to defaults plus the current page's categories.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const availableCategories = useMemo(() => {
    const categories = new Set<string>(DEFAULT_SYMBOL_CATEGORIES);
    serverCategories.forEach(c => c && categories.add(c));
    symbols.forEach(s => s.category && categories.add(s.category));
    return Array.from(categories).sort();
  }, [serverCategories, symbols]);

  const categories = useMemo(
    () => ['all', ...availableCategories],
    [availableCategories],
  );

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
      setError(extractError(e, t('updateFailed')));
    } finally {
      setCreating(false);
    }
  };

  const submitCreate = async () => {
    setCreating(true);
    try {
      const language = i18n.language?.split('-')[0] || 'en';
      if (newFile) {
        const fd = new FormData();
        fd.append('file', newFile);
        fd.append('label', form.label);
        fd.append('description', form.description);
        fd.append('category', form.category);
        fd.append('keywords', form.keywords);
        fd.append('language', language);
        await api.post('/boards/symbols/upload', fd);
      } else {
        await api.post('/boards/symbols', {
          label: form.label,
          description: form.description,
          category: form.category,
          keywords: form.keywords,
          language
        });
      }
      resetForm();
      await fetchSymbols();
    } catch (e: unknown) {
      setError(extractError(e, t('createFailed')));
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
      title: t('deleteSymbol'),
      description: t('deleteSymbolConfirm'),
      isLoading: false
    });
  };

  const deleteSelected = () => {
    setDeleteState({
      isOpen: true,
      mode: 'batch',
      force: false,
      title: t('deleteSymbols'),
      description: t('deleteSelectedConfirm', { count: selectedIds.size }),
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
        const inUseCount: string[] = [];

        for (const id of ids) {
          try {
            await api.delete(`/boards/symbols/${id}`);
            deletedIds.push(id);
          } catch (e: unknown) {
            const err = e as { response?: { status?: number } };
            const detail = extractError(e, t('failed'));
            // The backend error text is localized, but always mentions the
            // force=true escape hatch, so that marker is the stable signal
            // that the symbol is in use on boards. Never force-delete in a
            // batch: that would silently strip symbols from boards without
            // the explicit confirmation the single-delete flow provides.
            if (err?.response?.status === 400 && detail.includes('force=true')) {
              inUseCount.push(`#${id}`);
            } else {
              failures.push(`#${id}: ${detail}`);
            }
          }
        }
        setSymbols(prev => prev.filter(s => !deletedIds.includes(s.id)));
        setSelectedIds(prev => {
          const next = new Set(prev);
          deletedIds.forEach(id => next.delete(id));
          return next;
        });

        if (inUseCount.length) {
          setError(t('batchDeleteInUseSkipped', { count: inUseCount.length }));
        } else if (failures.length) {
          setError(t('someDeletionsFailed', { details: failures.join('; ') }));
        }
        setDeleteState(prev => ({ ...prev, isOpen: false }));
      }
    } catch (e: unknown) {
      if (deleteState.mode === 'single') {
        const err = e as { response?: { status?: number } };
        const detail = extractError(e, t('deleteFailed'));
        // Backend error text is localized but always mentions force=true when
        // the symbol is in use on boards (e.g. en: "...use force=true",
        // es: "...use force=true"), so that is the language-independent signal.
        if (err?.response?.status === 400 && detail.includes('force=true')) {
          setDeleteState(prev => ({
            ...prev,
            force: true,
            isLoading: false,
            description: t('symbolInUseForceDelete')
          }));
          return;
        }
        setError(detail);
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
    const maxSizeMb = MAX_IMAGE_FILE_BYTES / (1024 * 1024);
    if (!isValidImageFile(file)) {
      setError(t('invalidFile', { size: maxSizeMb }));
      setNewFile(null);
      setNewPreview(null);
      return;
    }
    setError(null);
    setNewFile(file);
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string' && reader.result.startsWith('data:image/')) {
        setNewPreview(reader.result);
      }
    };
    reader.readAsDataURL(file);
  };

  const searchArasaac = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const query = arasaacQuery.trim();
    if (!query) return;
    const searchSeq = ++arasaacSearchSeqRef.current;
    setIsSearchingArasaac(true);
    setError(null);
    try {
      const locale = i18n.language?.split('-')[0] || 'es';
      const res = await api.get('/arasaac/search', { 
        params: { 
          q: query,
          locale: locale
        } 
      });
      if (searchSeq === arasaacSearchSeqRef.current) {
        setArasaacResults(Array.isArray(res.data) ? res.data : []);
      }
    } catch (e: unknown) {
      if (searchSeq === arasaacSearchSeqRef.current) {
        console.error(e);
        setError(t('arasaacSearchFailed'));
      }
    } finally {
      if (searchSeq === arasaacSearchSeqRef.current) setIsSearchingArasaac(false);
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
        category: ARASAAC_CATEGORY
      });
      await fetchSymbols();
      // Confirm the import so the user isn't left guessing whether the click
      // did anything (the library is behind this view).
      addToast(t('importSuccess'), 'success');
    } catch (e: unknown) {
      console.error(e);
      setError(t('importFailed'));
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
        confirmText={deleteState.force ? t('forceDelete') : t('delete')}
        cancelText={t('cancel')}
        variant="danger"
        isLoading={deleteState.isLoading}
      />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{t('title')}</h1>
          <p className="text-muted-foreground">{t('subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <Button 
            variant={showArasaac ? "default" : "outline"}
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

      {error && <StatusMessage variant="error">{error}</StatusMessage>}

      {showArasaac ? (
        <div className="bg-surface rounded-xl shadow-sm border border-border p-4 space-y-4">
          <div className="flex flex-col gap-2">
            <SectionTitle>{t('searchArasaac')}</SectionTitle>
            <p className="text-sm text-muted-foreground">
              {t('subtitle')}
            </p>
          </div>
          
          <form onSubmit={searchArasaac} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                value={arasaacQuery}
                onChange={(e) => setArasaacQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 border border-border rounded-lg bg-surface text-foreground"
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
              <div key={item.id} className="p-3 border border-border rounded-lg bg-background flex flex-col gap-2 items-center text-center hover:border-brand transition-colors">
                <div className="w-24 h-24 bg-surface rounded-lg p-2 flex items-center justify-center">
                  <SymbolImage imagePath={item.image_url} alt={item.label} className="max-w-full max-h-full object-contain" />
                </div>
                <div className="w-full">
                  <div className="font-medium text-sm text-foreground truncate" title={item.label}>{item.label}</div>
                  <div className="text-xs text-muted-foreground truncate" title={item.keywords}>{item.keywords}</div>
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
              <div className="col-span-full text-center py-8 text-muted-foreground">
                {t('noResults', { query: arasaacQuery })}
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
      <div ref={formRef} className="bg-surface rounded-xl shadow-sm border border-border p-4 space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <FormLabel htmlFor="symbol-label" className="block text-sm font-medium text-foreground mb-1">{t('label')}</FormLabel>
            <input
              id="symbol-label"
              value={form.label}
              onChange={(e) => setForm(prev => ({ ...prev, label: e.target.value }))}
              className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground"
              placeholder={t('labelPlaceholder')}
            />
          </div>
          <div>
            <FormLabel>{t('category')}</FormLabel>
            <Select value={form.category} onValueChange={(next) => { if (next != null) setForm(prev => ({ ...prev, category: next })); }}>
              <SelectTrigger aria-label={t('category')} className="w-full text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {availableCategories.map(c => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <FormLabel>{t('description')}</FormLabel>
            <input
              value={form.description}
              onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))}
              className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground"
              placeholder={t('optionalDesc')}
            />
          </div>
          <div>
            <FormLabel>{t('keywords')}</FormLabel>
            <input
              value={form.keywords}
              onChange={(e) => setForm(prev => ({ ...prev, keywords: e.target.value }))}
              className="w-full px-3 py-2 border border-border rounded-lg bg-surface text-foreground"
              placeholder={t('commaSeparated')}
            />
          </div>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
            <label className="flex items-center gap-2 cursor-pointer text-sm text-foreground">
              <input
                type="file"
                accept="image/*"
                onChange={(e) => handleFile((e.target.files || [])[0] || null)}
              />
              <ImageIcon className="w-4 h-4" /> {newFile ? newFile.name : t('upload')}
            </label>
          {newPreview && newPreview.startsWith('data:image/') && (
            <img src={newPreview} alt={t('previewAlt')} className="w-12 h-12 rounded object-cover border" />
          )}
          <div className="flex gap-2">
            <Button
              variant="default"
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

      <div className="bg-surface rounded-xl shadow-sm border border-border p-4 space-y-4">
        <div className="flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[200px] md:min-w-[280px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
              className="w-full pl-9 pr-3 py-2 border border-border rounded-lg bg-surface text-foreground"
              placeholder={t('searchSymbols')}
            />
          </div>
          <div className="flex gap-2">
            {['all', 'in_use', 'unused'].map(u => (
              <Button
                key={u}
                variant={usage === u ? 'default' : 'outline'}
                onClick={() => { setUsage(u as UsageFilter); setPage(0); }}
                size="sm"
              >
                {u === 'all' ? t('filters.all') : u === 'in_use' ? t('filters.inUse') : t('filters.unused')}
              </Button>
            ))}
          </div>
          <Select
            value={sort}
            onValueChange={(next) => { if (next != null) { setSort(next); setPage(0); } }}
            items={[
              { value: 'default', label: t('filters.default') },
              { value: 'newest', label: t('filters.newest') },
              { value: 'oldest', label: t('filters.oldest') },
              { value: 'alpha', label: t('filters.alpha') },
            ]}
          >
            <SelectTrigger aria-label={t('filters.sort')} className="w-36 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">{t('filters.default')}</SelectItem>
              <SelectItem value="newest">{t('filters.newest')}</SelectItem>
              <SelectItem value="oldest">{t('filters.oldest')}</SelectItem>
              <SelectItem value="alpha">{t('filters.alpha')}</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={category}
            onValueChange={(next) => { if (next != null) { setCategory(next); setPage(0); } }}
            items={categories.map(c => ({ value: c, label: c === 'all' ? t('filters.all') : c }))}
          >
            <SelectTrigger aria-label={t('filters.category')} className="w-36 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {categories.map(c => (
                <SelectItem key={c} value={c}>{c === 'all' ? t('filters.all') : c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="destructive"
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
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
          </div>
        ) : symbols.length === 0 ? (
          <div className="text-center text-muted-foreground py-12">
            {t('noSymbols')}
          </div>
        ) : (
          <SymbolGrid
            symbols={symbols}
            selectedIds={selectedIds}
            onToggleSelection={(id, selected) => {
              setSelectedIds(prev => {
                const next = new Set(prev);
                if (selected) next.add(id); else next.delete(id);
                return next;
              });
            }}
            onEdit={startEdit}
            onDelete={deleteSymbol}
            page={page}
            hasMore={hasMore}
            onPreviousPage={() => setPage(p => Math.max(0, p - 1))}
            onNextPage={() => setPage(p => p + 1)}
          />
        )}
      </div>
      </>
      )}
    </div>
  );
}
