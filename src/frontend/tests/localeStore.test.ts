import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  language: 'en' as string,
  changeLanguage: vi.fn(async () => undefined),
  ensureLocale: vi.fn(async () => undefined),
}));

vi.mock('../src/i18n/index', () => ({
  default: { language: mocks.language, changeLanguage: mocks.changeLanguage },
  ensureLocale: mocks.ensureLocale,
}));

describe('localeStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.language = 'en';
    localStorage.removeItem('aac_assistant_locale');
  });

  it('switches the language and persists the choice', async () => {
    const { useLocaleStore } = await import('../src/store/localeStore');

    await useLocaleStore.getState().setLocale('es');

    expect(mocks.ensureLocale).toHaveBeenCalledWith('es');
    expect(mocks.changeLanguage).toHaveBeenCalledWith('es');
    expect(localStorage.getItem('aac_assistant_locale')).toBe('es');
    expect(useLocaleStore.getState().locale).toBe('es');
  });

});
