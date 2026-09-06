import { describe, expect, it } from 'vitest';

import enLearning from '../src/locales/en/pages/learning.json';
import esLearning from '../src/locales/es/pages/learning.json';
import {
  DEFAULT_SYMBOL_CATEGORIES,
  LEARNING_SYMBOL_CATEGORY_IDS,
} from '../src/lib/symbolCategories';
import { getCategoryStyle } from '../src/lib/symbolCategoryStyle';

describe('symbol category vocabularies (PROMPT_13 D10)', () => {
  it('keeps the two vocabularies distinct by design', () => {
    // Symbols.tsx chips show raw server strings; Learning tabs are localized
    // ids. They intentionally differ ('person' vs 'people'), which is why
    // learning.json localizes 'people' and Symbols.tsx never localizes chips.
    expect(DEFAULT_SYMBOL_CATEGORIES).toContain('person');
    expect(DEFAULT_SYMBOL_CATEGORIES).toContain('question');
    expect(DEFAULT_SYMBOL_CATEGORIES).toContain('time');
    expect(LEARNING_SYMBOL_CATEGORY_IDS).toContain('people');
    expect(LEARNING_SYMBOL_CATEGORY_IDS).not.toContain('person');
    expect(new Set(LEARNING_SYMBOL_CATEGORY_IDS).size).toBe(
      LEARNING_SYMBOL_CATEGORY_IDS.length,
    );
  });

  it('localizes every learning tab id in both locales (categories.* keys)', () => {
    // Cited keys, en and es identical: all/action/people/core/feeling/food/
    // object/place/social/ARASAAC — see pages/learning.json `categories`.
    const tabIds = [...LEARNING_SYMBOL_CATEGORY_IDS, 'all'];
    for (const id of tabIds) {
      expect(typeof enLearning.categories[id]).toBe('string');
      expect(typeof esLearning.categories[id]).toBe('string');
      expect(enLearning.categories[id]).toBeTruthy();
      expect(esLearning.categories[id]).toBeTruthy();
    }
  });

  it('falls back gracefully for categories outside the learning tab list', () => {
    // A 'person'-vocabulary (or any unknown) symbol never orphanes: the
    // 'all' tab exists for it and chips get the neutral 'general' style.
    expect(LEARNING_SYMBOL_CATEGORY_IDS).not.toContain('general');
    expect(getCategoryStyle('person').kind).toBe('pronouns'); // alias handling
    expect(getCategoryStyle('people').kind).toBe('pronouns');
    expect(getCategoryStyle('question').kind).toBe('general');
    expect(getCategoryStyle('time').kind).toBe('general');
    expect(getCategoryStyle(undefined).kind).toBe('general');
  });
});
