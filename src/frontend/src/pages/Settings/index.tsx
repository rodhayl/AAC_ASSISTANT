import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/authStore';
import { usePreferences } from './usePreferences';
import { AiProviderTab } from './AiProviderTab';
import { AppearanceTab } from './AppearanceTab';
import { DataManagementTab } from './DataManagementTab';
import { LearningModesTab } from './LearningModesTab';
import { ProfileTab } from './ProfileTab';
import { SecurityTab } from './SecurityTab';
import { VoiceTab } from './VoiceTab';

type SectionId = 'profile' | 'appearance' | 'security' | 'voice' | 'ai' | 'learning-modes' | 'data';

const sectionAnchors: Array<{ id: SectionId; labelKey: string; staffOnly?: boolean }> = [
  { id: 'profile', labelKey: 'tabs.profile' },
  { id: 'appearance', labelKey: 'tabs.appearance' },
  { id: 'security', labelKey: 'tabs.security' },
  { id: 'voice', labelKey: 'tabs.voice' },
  { id: 'ai', labelKey: 'tabs.ai' },
  { id: 'learning-modes', labelKey: 'tabs.learningModes', staffOnly: true },
  { id: 'data', labelKey: 'tabs.data' },
];

export function Settings() {
  const user = useAuthStore(state => state.user);
  const { t } = useTranslation('settings');
  const [activeSection, setActiveSection] = useState<SectionId>('profile');
  const preferences = usePreferences();
  const isAdmin = user?.user_type === 'admin';
  const isStaff = isAdmin || user?.user_type === 'teacher';
  const visibleSections = sectionAnchors.filter((section) => !section.staffOnly || isStaff);

  const navigateToSection = (section: SectionId) => {
    setActiveSection(section);
    document.getElementById(`settings-${section}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">{t('title')}</h1>
        <p className="text-muted-foreground">{t('subtitle')}</p>
      </div>

      <nav
        aria-label={t('tabs.sectionsLabel')}
        className="sticky top-0 z-10 flex flex-wrap gap-2 rounded-xl border border-border bg-surface/95 p-2 shadow-sm backdrop-blur border-border bg-surface/95"
      >
        {visibleSections.map((section) => (
          <button
            key={section.id}
            type="button"
            aria-current={activeSection === section.id ? 'page' : undefined}
            onClick={() => navigateToSection(section.id)}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              activeSection === section.id
                ? 'bg-brand text-white'
                : 'text-muted-foreground hover:bg-surface-hover hover:text-brand'
            }`}
          >
            {t(section.labelKey)}
          </button>
        ))}
      </nav>

      <ProfileTab />
      <AppearanceTab
        preferences={preferences.preferences}
        setPreferences={preferences.setPreferences}
        prefsLoading={preferences.prefsLoading}
        prefsSaveSuccess={preferences.prefsSaveSuccess}
        prefsSaveError={preferences.prefsSaveError}
        onSave={preferences.handleSavePreferences}
      />
      <SecurityTab />
      <VoiceTab
        preferences={preferences.preferences}
        setPreferences={preferences.setPreferences}
        filteredVoices={preferences.filteredVoices}
        showStatus={isAdmin}
        prefsLoading={preferences.prefsLoading}
        prefsSaveSuccess={preferences.prefsSaveSuccess}
        prefsSaveError={preferences.prefsSaveError}
        onSave={preferences.handleSavePreferences}
      />
      <AiProviderTab key={`${user?.id ?? 'anonymous'}:${user?.user_type ?? 'unknown'}`} />
      {isStaff && (
        <LearningModesTab
          preferences={preferences.preferences}
          setPreferences={preferences.setPreferences}
          onDefaultModeChange={preferences.saveDefaultLearningMode}
        />
      )}
      <DataManagementTab />
    </div>
  );
}
