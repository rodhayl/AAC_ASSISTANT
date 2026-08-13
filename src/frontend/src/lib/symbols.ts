import type { BoardSymbol } from '../types';
import type { LearningSymbolItem } from '../types';

const normalized = (value: string | undefined | null): string =>
  (value || '').trim().toLowerCase();

/** Deduplicate learning-library symbols by label and category. */
export function dedupeLearningSymbols(items: LearningSymbolItem[]): LearningSymbolItem[] {
  const byKey = new Map<string, LearningSymbolItem>();
  for (const item of items) {
    const label = normalized(item.label);
    if (!label) continue;
    const key = `${label}|${normalized(item.category)}`;
    const existing = byKey.get(key);
    if (!existing || (!existing.image_path && item.image_path)) {
      byKey.set(key, item);
    }
  }
  return Array.from(byKey.values());
}

/**
 * Keep visible, labeled board symbols unique for Symbol Hunt rounds.
 * Labels are normalized so casing/whitespace variants do not become confusing
 * duplicate targets during play.
 */
export function getUniquePlayableSymbols(symbols: BoardSymbol[]): BoardSymbol[] {
  const byLabel = new Map<string, BoardSymbol>();
  for (const symbol of symbols) {
    if (!symbol.is_visible) continue;
    const label = symbol.custom_text || symbol.symbol?.label;
    const key = normalized(label);
    if (key && !byLabel.has(key)) {
      byLabel.set(key, symbol);
    }
  }
  return Array.from(byLabel.values());
}
