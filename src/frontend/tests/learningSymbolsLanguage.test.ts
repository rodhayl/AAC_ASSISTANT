import { describe, expect, it } from 'vitest';
import { dedupeLearningSymbols } from '../src/lib/symbols';

describe('learning symbol localization', () => {
  it('keeps localized labels with their own symbol records', () => {
    const symbols = dedupeLearningSymbols([
      { id: 1, label: 'Hi', category: 'social', image_path: '/car.png', language: 'en' },
      { id: 2, label: 'Hola', category: 'social', image_path: '/hello.png', language: 'es' },
    ]);

    expect(symbols.find((symbol) => symbol.label === 'Hola')).toEqual(
      expect.objectContaining({ id: 2, image_path: '/hello.png', language: 'es' }),
    );
    expect(symbols.find((symbol) => symbol.label === 'Hi')).toEqual(
      expect.objectContaining({ id: 1, image_path: '/car.png', language: 'en' }),
    );
  });
});
