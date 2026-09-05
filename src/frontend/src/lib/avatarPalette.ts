/**
 * Shared saturated solid palette. Used by teacher avatars and symbol-category
 * dots so both surfaces speak the same visual language. Every class here is
 * a saturated solid with white content, readable on light and dark themes
 * (see the dark-mode guard allowlist in tests/styleTokens.test.ts).
 */
export const AVATAR_BG_COLORS = [
  'bg-indigo-500',
  'bg-sky-500',
  'bg-emerald-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-violet-500',
  'bg-teal-500',
  'bg-orange-500',
] as const;
