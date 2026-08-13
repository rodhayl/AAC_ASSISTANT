import { describe, expect, it } from 'vitest';
import { dedupeLearningSymbols, getUniquePlayableSymbols } from '../src/lib/symbols';

const boardSymbol = (id: number, label: string, overrides: Record<string, unknown> = {}) => ({
  id,
  symbol_id: id,
  position_x: 0,
  position_y: 0,
  size: 1,
  is_visible: true,
  symbol: {
    id,
    label,
    category: 'general',
    language: 'en',
    is_builtin: true,
    created_at: '2026-01-01T00:00:00Z',
  },
  ...overrides,
});

describe('symbol deduplication helpers', () => {
  it('keeps the first learning symbol unless a duplicate adds an image', () => {
    const result = dedupeLearningSymbols([
      { id: 1, label: ' Water ', category: 'drink' },
      { id: 2, label: 'water', category: 'drink', image_path: '/water.png' },
      { id: 3, label: 'water', category: 'food' },
      { id: 4, label: ' ', category: 'food' },
    ]);

    expect(result).toEqual([
      { id: 2, label: 'water', category: 'drink', image_path: '/water.png' },
      { id: 3, label: 'water', category: 'food' },
    ]);
  });

  it('returns visible board symbols uniquely by custom or source label', () => {
    const result = getUniquePlayableSymbols([
      boardSymbol(1, 'Cat'),
      boardSymbol(2, 'cat'),
      boardSymbol(3, 'Dog', { is_visible: false }),
      boardSymbol(4, 'Dog', { custom_text: ' Puppy ' }),
    ]);

    expect(result.map((symbol) => symbol.id)).toEqual([1, 4]);
  });
});
