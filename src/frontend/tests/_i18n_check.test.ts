import { describe, it, expect } from 'vitest';
import i18n from '../src/i18n/index';

describe('i18n t before init', () => {
  it('shows what t returns', () => {
    const value = i18n.t('learning:audioMessage', 'Audio message');
    console.log('RESULT:', JSON.stringify(value), 'isInitialized:', i18n.isInitialized, 'lang:', i18n.language);
    expect(true).toBe(true);
  });
});
