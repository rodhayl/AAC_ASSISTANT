import { AVATAR_BG_COLORS } from './avatarPalette'

export type CategoryKind =
  | 'pronouns'
  | 'verbs'
  | 'articles'
  | 'nouns'
  | 'emotions'
  | 'punctuation'
  | 'general'

// Category dots reuse the shared avatar palette so symbol dots and teacher
// avatars share one saturated solid visual language. (Emotions uses violet,
// matching the palette, instead of a near-duplicate purple.)
// Palette order: indigo, sky, emerald, amber, rose, violet, teal, orange.
const [DOT_PRONOUNS, , DOT_VERBS, DOT_NOUNS, DOT_ARTICLES, DOT_EMOTIONS] = AVATAR_BG_COLORS

export interface CategoryStyle {
  kind: CategoryKind
  border: string
  hoverBorder: string
  badgeBg: string
  badgeText: string
  dot: string
}

function normalizeCategory(category?: string): string {
  return (category || 'general').toLowerCase().trim()
}

function classifyCategory(category?: string): CategoryKind {
  const c = normalizeCategory(category)

  if (c === 'punctuation') return 'punctuation'

  if (
    c.includes('pronoun') ||
    c.includes('people') ||
    c.includes('person') ||
    c.includes('social') ||
    c.includes('core')
  ) {
    return 'pronouns'
  }

  if (c.includes('verb') || c.includes('action') || c.includes('actions')) {
    return 'verbs'
  }

  if (c.includes('article') || c.includes('determiner')) {
    return 'articles'
  }

  if (c.includes('emotion') || c.includes('feeling')) {
    return 'emotions'
  }

  if (
    c.includes('noun') ||
    c.includes('object') ||
    c.includes('objects') ||
    c.includes('place') ||
    c.includes('places') ||
    c.includes('animal') ||
    c.includes('food')
  ) {
    return 'nouns'
  }

  return 'general'
}

const STYLES: Record<CategoryKind, Omit<CategoryStyle, 'kind'>> = {
  pronouns: {
    border: 'border-indigo-200 dark:border-indigo-800/70',
    hoverBorder: 'hover:border-indigo-400 dark:hover:border-indigo-500',
    badgeBg: 'bg-indigo-100 dark:bg-indigo-900/60',
    badgeText: 'text-indigo-700 dark:text-indigo-200',
    dot: DOT_PRONOUNS,
  },
  verbs: {
    border: 'border-emerald-200 dark:border-emerald-800/70',
    hoverBorder: 'hover:border-emerald-400 dark:hover:border-emerald-500',
    badgeBg: 'bg-emerald-100 dark:bg-emerald-900/60',
    badgeText: 'text-emerald-700 dark:text-emerald-200',
    dot: DOT_VERBS,
  },
  articles: {
    border: 'border-rose-200 dark:border-rose-800/70',
    hoverBorder: 'hover:border-rose-400 dark:hover:border-rose-500',
    badgeBg: 'bg-rose-100 dark:bg-rose-900/60',
    badgeText: 'text-rose-700 dark:text-rose-200',
    dot: DOT_ARTICLES,
  },
  nouns: {
    border: 'border-amber-200 dark:border-amber-800/70',
    hoverBorder: 'hover:border-amber-400 dark:hover:border-amber-500',
    badgeBg: 'bg-amber-100 dark:bg-amber-900/60',
    badgeText: 'text-amber-700 dark:text-amber-200',
    dot: DOT_NOUNS,
  },
  emotions: {
    border: 'border-purple-200 dark:border-purple-800/70',
    hoverBorder: 'hover:border-purple-400 dark:hover:border-purple-500',
    badgeBg: 'bg-purple-100 dark:bg-purple-900/60',
    badgeText: 'text-purple-700 dark:text-purple-200',
    dot: DOT_EMOTIONS,
  },
  punctuation: {
    border: 'border-border',
    hoverBorder: 'hover:border-muted-foreground',
    badgeBg: 'bg-muted',
    badgeText: 'text-muted-foreground',
    dot: 'bg-muted-foreground',
  },
  general: {
    border: 'border-border',
    hoverBorder: 'hover:border-muted-foreground',
    badgeBg: 'bg-muted',
    badgeText: 'text-muted-foreground',
    dot: 'bg-muted-foreground',
  },
}

export function getCategoryStyle(category?: string): CategoryStyle {
  const kind = classifyCategory(category)
  return { kind, ...STYLES[kind] }
}

