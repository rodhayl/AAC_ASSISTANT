import type { TFunction } from 'i18next'

// Shared localization helpers for system achievements.
//
// The backend stores system achievements under their canonical English names
// (the seeded catalog), so the UI maps a canonical name to its stable catalog
// key to localize name/description. Custom or renamed achievements keep their
// stored text. This module is shared by the Achievements page and the
// notifications panel so both surfaces translate identically.

// Maps the canonical English name of a seeded system achievement to its stable
// catalog key so the name/description can be localized without a database
// migration.
export const SYSTEM_ACHIEVEMENT_KEYS: Record<string, string> = {
  'First Steps': 'first_steps',
  'Vocabulary Explorer': 'vocabulary_explorer',
  'Quick Learner': 'quick_learner',
  'Comprehension Champion': 'comprehension_champion',
  'Streak Master': 'streak_master',
  'Dedicated Learner': 'dedicated_learner',
  'Topic Expert': 'topic_expert',
  'Voice Pioneer': 'voice_pioneer',
};

export function localizeAchievementName(name: string, t: TFunction): string {
  const key = SYSTEM_ACHIEVEMENT_KEYS[name];
  return key ? t(`systemAchievements.${key}.name`, name) : name;
}

export function localizeAchievementDescription(
  name: string,
  description: string,
  t: TFunction,
): string {
  const key = SYSTEM_ACHIEVEMENT_KEYS[name];
  return key ? t(`systemAchievements.${key}.description`, description) : description;
}

// Backend achievement notifications use the canonical English name and an
// English "(+N pts)" suffix. Rewrite any known system-achievement name inside
// the message so Spanish/other users see the localized name; the point total
// and any custom-achievement names pass through unchanged.
export function localizeAchievementMessage(message: string, t: TFunction): string {
  let localized = message;
  for (const [name, key] of Object.entries(SYSTEM_ACHIEVEMENT_KEYS)) {
    if (localized.includes(name)) {
      localized = localized.replace(name, t(`systemAchievements.${key}.name`, name));
    }
  }
  return localized;
}
