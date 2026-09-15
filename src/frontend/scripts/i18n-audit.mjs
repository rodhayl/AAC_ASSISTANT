import { globby } from 'globby'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

// JSX text nodes can appear in .tsx components and, after a refactor, in .ts
// modules that build renderable nodes or user-facing markup — the old
// .tsx-only glob silently missed those. Locale bundles are the translations
// themselves and are never audited.
const files = await globby(['src/**/*.{ts,tsx}'], {
  cwd: frontendRoot,
  ignore: ['src/locales/**', 'src/**/*.d.ts'],
})

// Strip comments before matching: a comment containing ">" ... "<" is not a
// JSX text node.
function withoutComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1')
}

const HAS_LETTER = /[A-Za-zÀ-ÖØ-öø-ÿ]/
// Prose only: letters, digits, spaces and ordinary sentence punctuation.
// Parentheses, quotes, `:`, `?`, `&`, `|`, `=`, `<`, `>`, backticks or braces
// mean this is code (ternary branch, generic type argument, comparison), not a
// JSX text node.
const PROSE_ONLY = /^[A-Za-zÀ-ÖØ-öø-ÿ0-9\s.,!;\-–—/%+*#]*$/
const CODE_MARKERS = /\b(import|return|const|function|export)\b|\bnew\b/

// A JSX text node: prose between a tag-closing '>' and the next '<', possibly
// spanning lines (a wrapped sentence is the same defect as an inline one).
const TEXT_NODE = /(?<![=<>\-])>\s*([^<>{}]+?)\s*</g

const issues = []
for (const file of files) {
  const content = withoutComments(fs.readFileSync(path.join(frontendRoot, file), 'utf-8'))
  let m
  while ((m = TEXT_NODE.exec(content))) {
    const text = m[1].trim()
    if (!text || !HAS_LETTER.test(text)) continue
    if (!PROSE_ONLY.test(text)) continue
    if (CODE_MARKERS.test(text)) continue
    // A node already calling t()/i18n is translated, not hardcoded.
    if (/\{\s*t\(|\bi18n\.t\(/.test(content.slice(m.index - 60, m.index + 60))) continue
    issues.push({ file, text: text.replace(/\s+/g, ' ') })
  }
}

if (issues.length) {
  console.log(`Found ${issues.length} potential hardcoded strings:`)
  for (const i of issues) console.log(`- ${i.file}: "${i.text}"`)
  process.exitCode = 1
} else {
  console.log('No obvious hardcoded strings found.')
}
