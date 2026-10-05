#!/usr/bin/env node
// Export SVG elements by id to PNG (Inkscape replacement, uses Chromium via Playwright).
// Usage: node tools/render.mjs <file.svg> <dpi> <outdir> [id...]
//        without ids, reads one id per line from stdin.
// Requires the `playwright` module (NODE_PATH if installed globally).
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)('playwright');

const [svgPath, dpi, outDir, ...ids] = process.argv.slice(2);
if (!svgPath || !dpi || !outDir) {
  console.error('Usage: render.mjs <file.svg> <dpi> <outdir> [id...]');
  process.exit(1);
}
if (!ids.length)
  ids.push(
    ...readFileSync(0, 'utf8')
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
  );

mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: Number(dpi) / 96 });
let failed = 0;

for (const id of ids) {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto('file://' + resolve(svgPath));
  const box = await page.evaluate((id) => {
    const svg = document.documentElement;
    const target = svg.getElementById(id);
    if (!target) return null;
    // keeps visible only the branch containing the element
    const keep = new Set();
    for (let n = target; n && n !== svg; n = n.parentNode) keep.add(n);
    for (const n of keep) {
      for (const c of n.parentNode.children) {
        if (keep.has(c) || ['defs', 'style', 'metadata', 'namedview'].includes(c.localName))
          continue;
        c.style.display = 'none';
      }
    }
    const r = target.getBoundingClientRect();
    // frames only the element: viewBox and dimensions match its bounding box
    svg.setAttribute('viewBox', `${r.x} ${r.y} ${r.width} ${r.height}`);
    svg.setAttribute('width', r.width);
    svg.setAttribute('height', r.height);
    return { width: r.width, height: r.height };
  }, id);
  if (!box) {
    console.error('id not found:', id);
    failed++;
    continue;
  }
  await page.setViewportSize({ width: Math.ceil(box.width), height: Math.ceil(box.height) });
  await page.screenshot({
    path: `${outDir}/${id}.png`,
    omitBackground: true,
    clip: { x: 0, y: 0, width: box.width, height: box.height },
  });
}
await browser.close();
process.exit(failed ? 1 : 0);
