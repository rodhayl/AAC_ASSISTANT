import { expect, type Page } from '@playwright/test';

/**
 * Runtime contrast audit shared by the visual smoke and the full-route spec.
 *
 * Walks every visible text-bearing element and fails on any computed
 * foreground/background pair below WCAG AA (4.5:1). The check runs inside the
 * browser so it sees exactly what the theme classes (dark / high-contrast)
 * produce, including the Tailwind palette remaps done in index.css.
 */
export async function auditContrast(page: Page, label = '') {
  const violations = await page.evaluate(() => {
    // Freeze the theme transition (`body` animates background/color over
    // 300ms) so measurements never land on an in-between color.
    const freeze = document.createElement('style');
    freeze.textContent =
      '*, *::before, *::after { transition: none !important; animation: none !important; }';
    document.head.appendChild(freeze);

    /** Parse any CSS color the browser reports (rgb(), oklch(), space-syntax,
        hex, ...) through the canvas so sRGB channels + alpha are exact. */
    const cnv = document.createElement('canvas');
    const cctx = cnv.getContext('2d', { willReadFrequently: true })!;
    const parse = (c: string) => {
      if (c === 'transparent') return { r: 0, g: 0, b: 0, a: 0 };
      cctx.clearRect(0, 0, 1, 1);
      cctx.fillStyle = c;
      cctx.fillRect(0, 0, 1, 1);
      const d = cctx.getImageData(0, 0, 1, 1).data;
      return { r: d[0], g: d[1], b: d[2], a: d[3] / 255 };
    };
    const alphaOf = (c: string) => parse(c).a;
    const isTransparent = (c: string) => alphaOf(c) === 0;
    const lum = (c: { r: number; g: number; b: number }) => {
      const f = (v: number) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      };
      return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
    };
    const failures: string[] = [];
    const skip = new Set(['SCRIPT', 'STYLE', 'SVG', 'PATH', 'NOSCRIPT']);
    const audited = new Set(['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA', 'LABEL', 'H1', 'H2', 'H3', 'H4', 'P', 'SPAN', 'OPTION', 'LI', 'TD', 'TH', 'DIV']);
    /** Nearest ancestor background, but never climb past a fully opaque
        surface (a dialog card, a sidebar, the page body). Semi-transparent
        overlays like modal scrims are intentionally skipped so the text that
        sits on the opaque card below is measured against that card. */
    const effectiveBg = (el: Element): string => {
      let node: Element | null = el;
      while (node) {
        const bg = getComputedStyle(node).backgroundColor;
        if (!isTransparent(bg) && alphaOf(bg) >= 1) return bg;
        node = node.parentElement;
      }
      return 'rgba(0, 0, 0, 0)';
    };
    /** Whether any ancestor (including the element) paints a background image
        (gradients) — those surfaces cannot be measured as a flat color, so
        the pair is skipped instead of producing a false positive. */
    const hasBgImage = (el: Element): boolean => {
      for (let node: Element | null = el; node; node = node.parentElement) {
        const bi = getComputedStyle(node).backgroundImage;
        if (bi && bi !== 'none') return true;
      }
      return false;
    };
    for (const el of Array.from(document.querySelectorAll('body *'))) {
      if (skip.has(el.tagName)) continue;
      const text = (el.textContent || '').trim();
      if (!text) continue;
      // Only audit elements that carry their own direct text. Containers whose
      // text lives entirely in descendants are measured at those descendants
      // (against their own surfaces), so a scrim or card wrapper is never
      // compared as if all its children's text were painted directly on it.
      const hasOwnText = Array.from(el.childNodes).some(
        (n) => n.nodeType === Node.TEXT_NODE && (n.textContent || '').trim()
      );
      if (!hasOwnText) continue;
      const cs = getComputedStyle(el);
      const color = cs.color;
      // WCAG 1.4.3 exempts text inside inactive (disabled) controls.
      if (el instanceof HTMLElement && el.disabled) continue;
      if (el.getAttribute('aria-hidden') === 'true') continue;
      if (hasBgImage(el)) continue;
      // Semi-transparent containers (modal scrims, blurred panels) aggregate
      // the text of their children; each child is audited against its own
      // opaque surface, so auditing the container would double-count.
      const ownBg = getComputedStyle(el).backgroundColor;
      const ownBgIsTranslucent = !isTransparent(ownBg) && alphaOf(ownBg) < 1;
      if (ownBgIsTranslucent && el.children.length > 0) continue;
      const bg = effectiveBg(el);
      if (isTransparent(bg) || isTransparent(color)) continue;
      const pc = parse(color);
      const pb = parse(bg);
      if (!pc || !pb) continue;
      // Audit leaves and interactive/text elements; skip containers whose
      // children are audited individually (they may span multiple surfaces).
      if (el.children.length && !audited.has(el.tagName)) continue;
      const l1 = lum(pc);
      const l2 = lum(pb);
      const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      if (ratio < 4.5 && pc.a === 1 && pb.a === 1) {
        failures.push(`${el.tagName.toLowerCase()} ${String(el.className || '').slice(0, 60)} ${ratio.toFixed(2)}:1 "${text.slice(0, 60)}"`);
      }
    }
    return failures;
  });

  expect(violations, `contrast violations ${label}: ${violations.join(' | ')}`).toEqual([]);
}