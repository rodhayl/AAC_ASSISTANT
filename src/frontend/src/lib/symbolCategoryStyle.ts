export type CategoryKind =
  | 'pronouns'
  | 'verbs'
  | 'articles'
  | 'nouns'
  | 'emotions'
  | 'punctuation'
  | 'general'

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
    dot: 'bg-indigo-500',
  },
  verbs: {
    border: 'border-emerald-200 dark:border-emerald-800/70',
    hoverBorder: 'hover:border-emerald-400 dark:hover:border-emerald-500',
    badgeBg: 'bg-emerald-100 dark:bg-emerald-900/60',
    badgeText: 'text-emerald-700 dark:text-emerald-200',
    dot: 'bg-emerald-500',
  },
  articles: {
    border: 'border-rose-200 dark:border-rose-800/70',
    hoverBorder: 'hover:border-rose-400 dark:hover:border-rose-500',
    badgeBg: 'bg-rose-100 dark:bg-rose-900/60',
    badgeText: 'text-rose-700 dark:text-rose-200',
    dot: 'bg-rose-500',
  },
  nouns: {
    border: 'border-amber-200 dark:border-amber-800/70',
    hoverBorder: 'hover:border-amber-400 dark:hover:border-amber-500',
    badgeBg: 'bg-amber-100 dark:bg-amber-900/60',
    badgeText: 'text-amber-700 dark:text-amber-200',
    dot: 'bg-amber-500',
  },
  emotions: {
    border: 'border-purple-200 dark:border-purple-800/70',
    hoverBorder: 'hover:border-purple-400 dark:hover:border-purple-500',
    badgeBg: 'bg-purple-100 dark:bg-purple-900/60',
    badgeText: 'text-purple-700 dark:text-purple-200',
    dot: 'bg-purple-500',
  },
  punctuation: {
    border: 'border-gray-200 dark:border-gray-700',
    hoverBorder: 'hover:border-gray-400 dark:hover:border-gray-500',
    badgeBg: 'bg-gray-100 dark:bg-gray-800',
    badgeText: 'text-gray-700 dark:text-gray-200',
    dot: 'bg-gray-500',
  },
  general: {
    border: 'border-slate-200 dark:border-slate-800/70',
    hoverBorder: 'hover:border-slate-400 dark:hover:border-slate-500',
    badgeBg: 'bg-slate-100 dark:bg-slate-900/60',
    badgeText: 'text-slate-700 dark:text-slate-200',
    dot: 'bg-slate-500',
  },
}

export function getCategoryStyle(category?: string): CategoryStyle {
  const kind = classifyCategory(category)
  return { kind, ...STYLES[kind] }
}

