import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const sourceRoot = resolve(__dirname, '../src');

function productionSources(): string[] {
  const files = [
    'components',
    'pages',
    'hooks',
    'lib',
    'store',
  ];
  return files.flatMap((directory) => {
    const output: string[] = [];
    const visit = (path: string) => {
      for (const entry of readdirSync(path, { withFileTypes: true })) {
        const fullPath = resolve(path, entry.name);
        if (entry.isDirectory()) visit(fullPath);
        else if (entry.name.endsWith('.tsx')) output.push(readFileSync(fullPath, 'utf8'));
      }
    };
    visit(resolve(sourceRoot, directory));
    return output;
  });
}

describe('standardized frontend style tokens', () => {
  it('does not reintroduce generic gray application utilities', () => {
    const source = productionSources().join('\n');
    expect(source).not.toMatch(/(?:^|["' ])(?:dark:)?(?:bg|text|border|ring)-(?:gray|slate|zinc)-\d+/);
  });

  it('does not use collided semantic text tokens', () => {
    const source = productionSources().join('\n');
    expect(source).not.toMatch(/(?:^|["' ])text-(?:primary|secondary|muted)(?:["' /]|$)/);
  });
});
