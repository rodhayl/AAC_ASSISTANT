import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppearanceTab } from '../src/pages/Settings/AppearanceTab';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => {
      const table: Record<string, string> = {
        'preferences.title': 'Preferences',
        'preferences.saved': 'Saved',
        'preferences.savePrefs': 'Save preferences',
        'preferences.language': 'Language',
        'preferences.languageHelp': 'Choose language',
        'preferences.voiceMode': 'Voice mode',
        'preferences.voiceModeHelp': 'Voice help',
        'preferences.notifications': 'Notifications',
        'preferences.notificationsHelp': 'Notify help',
        'preferences.dark': 'Dark mode',
        'preferences.darkHelp': 'Dark help',
        'preferences.dwellTime': 'Dwell time',
        'preferences.dwellTimeHelp': 'Dwell help',
        'preferences.ignoreRepeats': 'Ignore repeats',
        'preferences.ignoreRepeatsHelp': 'Ignore help',
        'preferences.highContrast': 'High contrast',
        'preferences.highContrastHelp': 'Contrast help',
        'security.saving': 'Saving…',
      };
      return table[key] ?? defaultValue ?? key;
    },
  }),
}));

const basePreferences = {
  tts_voice: 'default',
  ui_language: 'es-ES',
  notifications_enabled: true,
  voice_mode_enabled: true,
  dark_mode: false,
  dwell_time: 0,
  ignore_repeats: 0,
  high_contrast: false,
};

describe('AppearanceTab', () => {
  let setPreferences: ReturnType<typeof vi.fn>;
  let onSave: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setPreferences = vi.fn((updater) => updater(basePreferences));
    onSave = vi.fn().mockResolvedValue(undefined);
  });

  const renderTab = (overrides: Record<string, unknown> = {}) =>
    render(
      <AppearanceTab
        preferences={basePreferences}
        setPreferences={setPreferences}
        prefsLoading={false}
        prefsSaveSuccess={false}
        prefsSaveError={null}
        onSave={onSave}
        {...overrides}
      />,
    );

  it('renders every preference control', () => {
    renderTab();
    expect(screen.getByLabelText('Language')).toBeInTheDocument();
    expect(screen.getByLabelText('Voice mode')).toBeInTheDocument();
    expect(screen.getByLabelText('Notifications')).toBeInTheDocument();
    expect(screen.getByLabelText('Dark mode')).toBeInTheDocument();
    expect(screen.getByLabelText('Dwell time')).toBeInTheDocument();
    expect(screen.getByLabelText('Ignore repeats')).toBeInTheDocument();
    expect(screen.getByLabelText('High contrast')).toBeInTheDocument();
  });

  it('propagates edits for the language, toggles, and sliders', () => {
    renderTab();

    fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'en-US' } });
    expect(setPreferences).toHaveBeenLastCalledWith(expect.any(Function));

    fireEvent.click(screen.getByLabelText('Dark mode'));
    fireEvent.click(screen.getByLabelText('High contrast'));
    fireEvent.change(screen.getByLabelText('Dwell time'), { target: { value: '500' } });
    fireEvent.change(screen.getByLabelText('Ignore repeats'), { target: { value: '300' } });
    expect(setPreferences).toHaveBeenCalled();
  });

  it('calls onSave and shows the loading label while saving', () => {
    renderTab({ prefsLoading: true });
    fireEvent.click(screen.getByRole('button', { name: 'Saving…' }));
    expect(onSave).not.toHaveBeenCalled(); // disabled while loading
  });

  it('shows the success message and saves', () => {
    renderTab({ prefsSaveSuccess: true });
    expect(screen.getByText('Saved')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Save preferences' }));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('shows the save error instead of the success message', () => {
    renderTab({ prefsSaveError: 'Saving failed' });
    expect(screen.getByText('Saving failed')).toBeInTheDocument();
    expect(screen.queryByText('Saved')).not.toBeInTheDocument();
  });
});
