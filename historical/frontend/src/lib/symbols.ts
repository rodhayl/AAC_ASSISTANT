import type { BoardSymbol } from '../types';
import type { LearningSymbolItem } from '../types';

const normalized = (value: string | undefined | null): string =>
  (value || '').trim().toLowerCase();

/**
 * Deduplicate learning-library symbols by label.
 *
 * The category is not part of the key: the catalog can hold the same word
 * under different categories (e.g. an ARASAAC import's "beverage" next to a
 * seeded "drinks"), and showing both tiles would render duplicate labels in
 * the panel. Prefer the variant that has an image.
 */
export function dedupeLearningSymbols(items: LearningSymbolItem[]): LearningSymbolItem[] {
  const byLabel = new Map<string, LearningSymbolItem>();
  for (const item of items) {
    const label = normalized(item.label);
    if (!label) continue;
    const existing = byLabel.get(label);
    if (!existing || (!existing.image_path && item.image_path)) {
      byLabel.set(label, item);
    }
  }
  return Array.from(byLabel.values());
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
