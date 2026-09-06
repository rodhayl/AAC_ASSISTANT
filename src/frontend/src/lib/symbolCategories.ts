export const ARASAAC_CATEGORY = 'ARASAAC' as const;

// Two category vocabularies exist on purpose; they are NOT the same list and
// must not be merged blindly:
//
// - DEFAULT_SYMBOL_CATEGORIES feeds the Symbol management page (Symbols.tsx),
//   whose filter chips show the RAW server category strings (no i18n), so it
//   mirrors the values stored on Symbol rows ('person', 'question', 'time',
//   'adjective', ...).
// - LEARNING_SYMBOL_CATEGORY_IDS feeds the Learning symbol panel tabs
//   (LearningSymbolPanel.tsx), whose labels are localized via
//   `t('categories.<id>')` in pages/learning.json ('people', 'action', ...).
//
// A symbol whose category belongs to the other vocabulary (or to neither) is
// still reachable: the panel's 'all' tab lists every item and
// symbolCategoryStyle falls back to a neutral 'general' treatment, so no
// out-of-list category can orphan a symbol or crash a chip.
//
// Symbols.tsx adds every server category it discovers to its chips, so
// DEFAULT_SYMBOL_CATEGORIES is a seed, not a closed set.

export const DEFAULT_SYMBOL_CATEGORIES = [
  'general',
  'action',
  'feeling',
  'person',
  'social',
  'food',
  'object',
  'place',
  'question',
  'time',
  'adjective',
  'core',
  ARASAAC_CATEGORY,
] as const;

export const LEARNING_SYMBOL_CATEGORY_IDS = [
  'core',
  'people',
  'action',
  'feeling',
  'food',
  'object',
  'place',
  'social',
  ARASAAC_CATEGORY,
] as const;
