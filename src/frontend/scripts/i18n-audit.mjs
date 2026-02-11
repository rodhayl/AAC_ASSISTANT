import { globby } from 'globby'
import fs from 'fs'

const files = await globby(['src/**/*.tsx', 'src/**/*.ts'], { cwd: new URL('../', import.meta.url).pathname })
const issues = []
for (const file of files) {
  const content = fs.readFileSync(new URL(`../${file}`, import.meta.url), 'utf-8')
  // Heuristic: find JSX text nodes with letters not inside {t('...')}
  const regex = />\s*([^<{][^<>{}]+)\s*</g
  let m
  while ((m = regex.exec(content))) {
    const text = m[1].trim()
    if (text && /[A-Za-zÁÉÍÓÚáéíóúñÑ]/.test(text) && !/\{\s*t\(/.test(content.slice(m.index - 50, m.index + 50))) {
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
