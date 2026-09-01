import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const sourceRoot = resolve(__dirname, '../src');

function productionSources(): Array<{ file: string; src: string }> {
  const files = [
    'components',
    'pages',
    'hooks',
    'lib',
    'store',
  ];
  return files.flatMap((directory) => {
    const output: Array<{ file: string; src: string }> = [];
    const visit = (path: string) => {
      for (const entry of readdirSync(path, { withFileTypes: true })) {
        const fullPath = resolve(path, entry.name);
        if (entry.isDirectory()) visit(fullPath);
        else if (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')) {
          // Only production sources: skip tests and type declarations.
          if (/\.test\.(ts|tsx)$/.test(entry.name) || entry.name.endsWith('.d.ts')) continue;
          output.push({ file: fullPath, src: readFileSync(fullPath, 'utf8') });
        }
      }
    };
    visit(resolve(sourceRoot, directory));
    return output;
  });
}

describe('standardized frontend style tokens', () => {
  it('does not reintroduce generic gray application utilities', () => {
    const source = productionSources().map(({ src }) => src).join('\n');
    expect(source).not.toMatch(/(?:^|["' ])(?:dark:)?(?:bg|text|border|ring)-(?:gray|slate|zinc)-\d+/);
  });

  it('does not use collided semantic text tokens', () => {
    const source = productionSources().map(({ src }) => src).join('\n');
    expect(source).not.toMatch(/(?:^|["' ])text-(?:primary|secondary|muted)(?:["' /]|$)/);
  });
});

/**
 * Dark-mode pair guard.
 *
 * Every raw Tailwind color utility (bg-red-500, text-amber-700, border-x-*,
 * gradient from/to/via, ...) used in a class pool must have a matching
 * `dark:` variant in the SAME class pool, otherwise that element renders with
 * light-theme colors on the near-black dark background.
 *
 * Class pools are whole template literals / quoted strings, with ${...}
 * interpolations replaced by a space so conditional branches stay in the same
 * pool as the rest of the class list.
 *
 * Intentional exceptions (verified readable on both themes) live in
 * ALLOWLIST below — each entry must carry a reason. Do not grow it casually.
 */
describe('dark-mode color pair guard', () => {
  const COLOR =
    /\b(bg|text|border|from|to|via|ring|divide|fill|stroke|outline|decoration|accent|caret|placeholder)-(red|green|blue|amber|purple|yellow|orange|emerald|pink|rose|indigo|slate|gray|zinc|neutral|stone|lime|teal|cyan|sky|violet|fuchsia)-(\d{2,3})(?:\/\d+)?\b/;

  /** Saturated solids / mid-tone accents that are readable on both themes. */
  const ALLOWED_BASE_CLASSES = new Set([
    // Solid accent buttons with white text (ui/button.tsx variants)
    'bg-green-700', 'bg-green-800', 'bg-purple-600', 'bg-purple-700',
    'bg-red-600', 'bg-red-700', 'bg-amber-600', 'bg-amber-700',
    // Status/solid buttons in feature pages (white text, readable on dark)
    'bg-emerald-700', 'bg-emerald-800',
    // Notification dots / recording badges (saturated, white icon or dot)
    'bg-red-500', 'bg-purple-500', 'bg-orange-500',
    'bg-orange-600', // hover of the recording badge (same saturated solid)
    // Category dots (symbolCategoryStyle.ts) — saturated on both themes
    'bg-indigo-500', 'bg-emerald-500', 'bg-rose-500', 'bg-amber-500', 'bg-purple-500',
    // Correct-answer / solid state buttons (white text)
    'bg-green-700',
    // Mid-tone icons readable on near-black (icons, not text)
    'text-indigo-500', 'text-orange-500', 'text-yellow-500', 'text-green-500', 'text-red-500',
    // Amber progress gradients on dark tracks (saturated mid-tones)
    'from-amber-400', 'to-amber-600',
    // Hero gradient banner (white text on saturated brand colors)
    'from-indigo-600', 'to-purple-600',
    // Board icon gradient (white icon on saturated brand colors)
    'from-indigo-500', 'via-blue-500', 'to-purple-500',
    // Playable board gradient (white icon on saturated colors)
    'from-indigo-500', 'via-blue-500', 'to-purple-500',
    // Correct/incorrect game overlays (saturated fill + border, has dark:/30 pair)
    'border-green-500', 'border-red-500',
    // TeacherAvatar initials (tiny saturated solid + white text, readable on both themes)
    'bg-sky-500', 'bg-teal-500', 'bg-violet-500',
  ]);

  function classPools(src: string): string[] {
    const pools: string[] = [];
    const re = /`(?:[^`\\]|\\.)*`|'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(src)) !== null) {
      // Replace ${...} interpolations with a space so both conditional
      // branches stay in the same pool as the rest of the class list.
      const s = m[0].slice(1, -1).replace(/\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/g, ' ');
      if (s.includes('-')) pools.push(s);
    }
    return pools;
  }

  it('every raw color class has a dark: pair (or is allowlisted)', () => {
    const offenders: string[] = [];

    for (const { file, src } of productionSources()) {
      for (const pool of classPools(src)) {
        const classes = pool.split(/\s+/).filter(Boolean);
        for (const cls of classes) {
          const m = cls.match(COLOR);
          if (!m) continue;
          const base = m[0]; // e.g. bg-red-900/30 -> strip opacity for matching
          const noShade = base.replace(/\/\d+$/, '');
          const parts = noShade.split('-');
          const colorName = parts[parts.length - 2];
          const prop = parts.slice(0, -2).join('-'); // may include hover: etc.
          const innerProp = prop.replace(/^[a-z]+:/, ''); // strip variant prefix

          // Allowlisted saturated solids / mid-tones: readable on both themes.
          if (ALLOWED_BASE_CLASSES.has(noShade)) continue;

          // Must have a dark: pair in the same pool. Accept any variant
          // prefix on the dark side (dark:hover:bg-..., dark:focus:...).
          const wantedExact = new RegExp(
            `^dark:(?:[a-z]+:)*${prop}-${colorName}-\\d{2,3}`,
          );
          const wantedInner = new RegExp(
            `^dark:(?:[a-z]+:)*${innerProp}-${colorName}-\\d{2,3}`,
          );
          const hasDark = classes.some((c) => wantedExact.test(c) || wantedInner.test(c));
          if (!hasDark) {
            const rel = file.slice(sourceRoot.length + 1);
            offenders.push(`${rel}: ${base}   [pool: ${pool.trim().replace(/\s+/g, ' ').slice(0, 120)}]`);
          }
        }
      }
    }

    expect(
      offenders,
      `\nRaw color classes without a dark: pair found.\n` +
      `Add "dark:<prop>-<color>-<shade>" next to the light class, or if the\n` +
      `class is intentionally readable on both themes (saturated solid + white\n` +
      `text, mid-tone icon), add it to ALLOWED_BASE_CLASSES with a reason.\n\n` +
      offenders.join('\n'),
    ).toEqual([]);
  });
});
