import { readFileSync } from 'node:fs'
import path from 'node:path'

/**
 * Read the release version from its single source of truth.
 *
 * `[project].version` in the repository root `pyproject.toml` drives the
 * backend, the packaged installer, and this frontend build, so no layer keeps
 * a version literal that a release bump could leave behind.
 */
export function readProjectVersion(): string {
  const pyprojectPath = path.resolve(__dirname, '../../..', 'pyproject.toml')
  const contents = readFileSync(pyprojectPath, 'utf8')
  const projectSection = contents
    .split(/^\[/m)
    .find((section) => section.startsWith('project]'))
  const version = projectSection?.match(/^\s*version\s*=\s*"([^"]+)"/m)?.[1]
  if (!version) {
    throw new Error(`[project].version is missing from ${pyprojectPath}`)
  }
  return version
}
