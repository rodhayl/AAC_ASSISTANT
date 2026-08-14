import { globby } from 'globby'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

// Only JSX-capable files carry text nodes; .ts files produced only code false
// positives (arrow functions, comparisons) under the old heuristic.
const files = await globby(['src/**/*.tsx'], { cwd: frontendRoot })

const issues = []
for (const file of files) {
  const content = fs.readFileSync(path.join(frontendRoot, file), 'utf-8')
  // Heuristic: a JSX text node is prose between a tag-closing '>' and the next
  // '<'. Exclude '>' that closes an arrow function or comparison (=>, >=, <=,
  // ->, -->). Multi-line nodes are skipped (they are usually code or prose that
  // needs `t()` interpolation anyway), and code operators (`;`, `=`, `&&`, `||`)
  // disqualify a match.
  const regex = /(?<![=<>\-])>\s*([^<>{}\n]+?)\s*</g
  let m
  while ((m = regex.exec(content))) {
    const text = m[1].trim()
    if (
      text &&
      /[A-Za-zÁÉÍÓÚáéíóúñÑ]/.test(text) &&
      !/[;=]/.test(text) &&
      !/\?/.test(text) &&
      !/&&|\|\|/.test(text) &&
      !/\{\s*t\(/.test(content.slice(m.index - 50, m.index + 50))
    ) {
      issues.push({ file, text })
    }
  }
}

if (issues.length) {
  console.log(`Found ${issues.length} potential hardcoded strings:`)
  for (const i of issues) console.log(`- ${i.file}: "${i.text}"`)
  process.exitCode = 1
} else {
  console.log('No obvious hardcoded strings found.')
}
