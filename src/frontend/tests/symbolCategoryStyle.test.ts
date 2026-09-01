import { describe, expect, it } from 'vitest';
import { getCategoryStyle } from '../src/lib/symbolCategoryStyle';
import { AVATAR_BG_COLORS } from '../src/lib/avatarPalette';

describe('symbol category styles', () => {
  it('maps each category dot onto the shared avatar palette', () => {
    const cases: Array<[string, string]> = [
      ['pronouns', 'bg-indigo-500'],
      ['verbs', 'bg-emerald-500'],
      ['articles', 'bg-rose-500'],
      ['nouns', 'bg-amber-500'],
      ['emotions', 'bg-violet-500'],
    ];
    for (const [category, expected] of cases) {
      expect(getCategoryStyle(category).dot).toBe(expected);
      // The dot must come from the shared palette, not a one-off class.
      expect(AVATAR_BG_COLORS).toContain(expected);
    }
  });

  it('keeps punctuation and general dots neutral', () => {
    expect(getCategoryStyle('punctuation').dot).toBe('bg-muted-foreground');
    expect(getCategoryStyle('general').dot).toBe('bg-muted-foreground');
    expect(getCategoryStyle(undefined).dot).toBe('bg-muted-foreground');
  });
});
