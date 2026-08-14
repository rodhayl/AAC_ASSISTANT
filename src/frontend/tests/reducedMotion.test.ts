import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

describe('Reduced motion accessibility styling', () => {
  it('defines prefers-reduced-motion media query with zero/instant animation durations', () => {
    const cssPath = path.resolve(__dirname, '../src/index.css');
    const cssContent = fs.readFileSync(cssPath, 'utf-8');

    expect(cssContent).toContain('@media (prefers-reduced-motion: reduce)');
    expect(cssContent).toContain('animation-duration: 0.01ms !important;');
    expect(cssContent).toContain('transition-duration: 0.01ms !important;');
    expect(cssContent).toContain('scroll-behavior: auto !important;');
  });
});
