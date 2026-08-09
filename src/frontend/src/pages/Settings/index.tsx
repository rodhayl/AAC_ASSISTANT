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
        <h1 className="text-2xl font-bold text-gray-900">{t('title')}</h1>
        <p className="text-gray-500">{t('subtitle')}</p>
      </div>

      <nav
        aria-label="Settings sections"
        className="sticky top-0 z-10 flex flex-wrap gap-2 rounded-xl border border-gray-200 bg-white/95 p-2 shadow-sm backdrop-blur dark:border-gray-700 dark:bg-gray-800/95"
      >
        {visibleSections.map((section) => (
          <button
            key={section.id}
            type="button"
            aria-current={activeSection === section.id ? 'page' : undefined}
            onClick={() => navigateToSection(section.id)}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              activeSection === section.id
                ? 'bg-indigo-600 text-white'
                : 'text-gray-600 hover:bg-indigo-50 hover:text-indigo-700 dark:text-gray-300 dark:hover:bg-gray-700'
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
      />
      <AiProviderTab key={`${user?.id ?? 'anonymous'}:${user?.user_type ?? 'unknown'}`} />
      {isStaff && <LearningModesTab />}
      <DataManagementTab />
    </div>
  );
}
