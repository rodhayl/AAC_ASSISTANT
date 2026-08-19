import { describe, expect, it } from 'vitest';
import i18n from '../src/i18n/index';

// The settings components use `useTranslation('settings')`, so error fallbacks
// live in the settings namespace. These must resolve to real text in the
// bundled Spanish locale; a missing key would render the raw key itself
// (e.g. "errors.saveFailed") in the UI.
describe('settings i18n keys resolve', () => {
  it('resolves the preference save-failure fallback used by usePreferences', () => {
    const value = i18n.t('settings:errors.saveFailed');
    expect(value).not.toBe('errors.saveFailed');
    expect(value).not.toBe('settings:errors.saveFailed');
    expect(value.length).toBeGreaterThan(0);
  });

  it('resolves the unknown-error fallback used by DataManagementTab', () => {
    const value = i18n.t('settings:errors.unknownError');
    expect(value).not.toBe('errors.unknownError');
    expect(value.length).toBeGreaterThan(0);
  });

  it('resolves all settings-store AI failure fallbacks', () => {
    for (const key of [
      'settings:ai.fetchFailed',
      'settings:ai.updateFailed',
      'settings:ai.fetchOllamaFailed',
      'settings:ai.fetchOpenRouterFailed',
      'settings:ai.fetchLmStudioFailed',
    ]) {
      const value = i18n.t(key);
      expect(value).not.toBe(key.split(':')[1]);
      expect(value.length).toBeGreaterThan(0);
    }
  });

  it('resolves the profile/security/ai load fallbacks and data import errors', () => {
    for (const key of [
      'settings:profile.saveFailed',
      'settings:security.changeFailed',
      'settings:ai.loadFailed',
      'settings:data.invalidExportMeta',
      'settings:data.invalidExportBoards',
      'settings:data.invalidExportAssignedBoards',
      'settings:data.invalidExportAchievements',
      'settings:tabs.sectionsLabel',
    ]) {
      const value = i18n.t(key);
      expect(value).not.toBe(key.split(':')[1]);
      expect(value.length).toBeGreaterThan(0);
    }
  });
});
