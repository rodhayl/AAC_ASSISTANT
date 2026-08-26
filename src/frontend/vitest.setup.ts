import '@testing-library/jest-dom'
import common from './src/locales/en/common.json'
import dashboard from './src/locales/en/pages/dashboard.json'
import learning from './src/locales/en/pages/learning.json'
import achievements from './src/locales/en/pages/achievements.json'
import boards from './src/locales/en/pages/boards.json'
import login from './src/locales/en/pages/login.json'
import register from './src/locales/en/pages/register.json'
import settings from './src/locales/en/pages/settings.json'
import students from './src/locales/en/pages/students.json'
import symbols from './src/locales/en/pages/symbols.json'
import sidebar from './src/locales/en/pages/sidebar.json'
import layout from './src/locales/en/pages/layout.json'
import error from './src/locales/en/pages/error.json'
import games from './src/locales/en/pages/games.json'
import teachers from './src/locales/en/pages/teachers.json'
import admins from './src/locales/en/pages/admins.json'
import setup from './src/locales/en/pages/setup.json'

type TranslationValue = string | Record<string, unknown>

const resources: Record<string, Record<string, TranslationValue>> = {
  common,
  dashboard,
  learning,
  achievements,
  boards,
  login,
  register,
  settings,
  students,
  symbols,
  sidebar,
  layout,
  error,
  games,
  teachers,
  admins,
  setup,
}

function lookup(namespace: string, key: string): string | undefined {
  const value = key.split('.').reduce<unknown>((current, part) => {
    if (!current || typeof current !== 'object') return undefined
    return (current as Record<string, unknown>)[part]
  }, resources[namespace])
  return typeof value === 'string' ? value : undefined
}

export function testTranslation(
  namespace: string,
  key: string,
  arg2?: string | Record<string, unknown>,
  arg3?: Record<string, unknown>,
): string {
  const options = typeof arg2 === 'object' ? arg2 : arg3
  const defaultValue = typeof arg2 === 'string' ? arg2 : undefined
  const requestedNamespace = typeof options?.ns === 'string' ? options.ns : namespace
  let value = lookup(requestedNamespace, key) ?? lookup(namespace, key) ?? lookup('common', key) ?? defaultValue ?? key
  for (const [name, replacement] of Object.entries(options ?? {})) {
    if (name !== 'defaultValue') value = value.replace(`{{${name}}}`, String(replacement))
  }
  return value
}

;(globalThis as typeof globalThis & {
  __aacTestTranslation?: typeof testTranslation
}).__aacTestTranslation = testTranslation

afterEach(() => {
  document.body.innerHTML = ''
})
