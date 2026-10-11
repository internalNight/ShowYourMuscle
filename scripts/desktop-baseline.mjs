// Desktop baseline: measures the built page at wide viewports and saves screenshots for human review.
//
// This is the first step of the desktop pass. It asserts almost nothing on purpose — it produces the
// facts the design tokens will be derived from (how wide the layout actually is on a 1920 screen, which
// font sizes and spacings are in use, which targets are too small, what overlaps) plus PNGs a person can
// look at, because the model driving this work cannot see images.
//
// Usage: node scripts/desktop-baseline.mjs [outputDir]
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const DIST = join(ROOT, 'dist');
const OUT = process.argv[2] || join('D:', 'DeepseekHarness', 'desktop-review');
const VIEWPORTS = [
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1280x800', width: 1280, height: 800 },
];
const CANDIDATES = [
  process.env.ATLAS_BROWSER,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  '/usr/bin/microsoft-edge', '/usr/bin/google-chrome', '/usr/bin/chromium',
].filter(Boolean);

const browser = CANDIDATES.find(path => existsSync(path));
assert(browser, 'no Chromium-based browser found; set ATLAS_BROWSER');
assert(existsSync(join(DIST, 'index.html')), 'dist/index.html is missing. Run `npm run build` first.');
mkdirSync(OUT, { recursive: true });

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json',
  '.glb': 'model/gltf-binary', '.png': 'image/png', '.webmanifest': 'application/manifest+json',
  '.txt': 'text/plain; charset=utf-8' };
const server = createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  const file = join(DIST, normalize(pathname === '/' ? 'index.html' : pathname).replace(/^(\.\.[/\\])+/, ''));
  try {
    if (!statSync(file).isFile()) throw new Error('not a file');
    response.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream' });
    response.end(readFileSync(file));
  } catch {
    response.writeHead(404).end('not found');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;

const debugPort = 9200 + (process.pid % 600);
const profile = mkdtempSync(join(tmpdir(), 'atlas-desktop-'));
const child = spawn(browser, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--enable-unsafe-swiftshader', '--force-device-scale-factor=1',
  `--remote-debugging-port=${debugPort}`, `--user-data-dir=${profile}`, `${origin}/`], { stdio: 'ignore' });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

const MEASURE = `(() => {
  const box = el => { const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; };
  const visible = el => { const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
  const interactive = [...document.querySelectorAll('button, a[href], input, select, textarea, [role="button"], [tabindex]:not([tabindex="-1"])')]
    .filter(visible)
    .map(el => ({ tag: el.tagName.toLowerCase(),
      label: (el.getAttribute('aria-label') || el.textContent || el.getAttribute('name') || '').trim().slice(0, 30),
      ...box(el) }));
  const small = interactive.filter(item => Math.min(item.w, item.h) < 24);
  const overlaps = [];
  for (let i = 0; i < interactive.length; i++) {
    for (let j = i + 1; j < interactive.length; j++) {
      const a = interactive[i], b = interactive[j];
      const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (ox > 2 && oy > 2) overlaps.push(a.tag + ':' + a.label + ' × ' + b.tag + ':' + b.label + ' (' + Math.round(ox) + 'x' + Math.round(oy) + ')');
    }
  }
  const census = map => Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 16);
  const fonts = {}, gaps = {}, textColors = {};
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    const hasText = [...el.childNodes].some(node => node.nodeType === 3 && node.textContent.trim());
    if (hasText) {
      fonts[cs.fontSize] = (fonts[cs.fontSize] || 0) + 1;
      textColors[cs.color] = (textColors[cs.color] || 0) + 1;
    }
    for (const prop of ['gap', 'paddingTop', 'marginTop', 'borderRadius']) {
      const key = prop + ':' + cs[prop];
      gaps[key] = (gaps[key] || 0) + 1;
    }
  }
  const regions = {};
  for (const selector of ['.site-header', '.layout', '.intro', '.workspace', '.viewer-panel', '.lower-grid', 'canvas']) {
    const el = document.querySelector(selector);
    if (el) regions[selector] = box(el);
  }
  const root = document.documentElement;
  return {
    viewport: { w: innerWidth, h: innerHeight },
    documentWidth: root.scrollWidth, documentHeight: root.scrollHeight,
    sidewaysScroll: root.scrollWidth - root.clientWidth,
    regions, interactiveCount: interactive.length,
    smallTargets: small, overlapCount: overlaps.length, overlaps: overlaps.slice(0, 12),
    fontCensus: census(fonts), boxPropertyCensus: census(gaps), textColorCensus: census(textColors),
    unusedWidth: innerWidth - (regions['.layout'] ? (regions['.layout'].x + regions['.layout'].w) : innerWidth),
  };
})()`;

const frameRate = `(async () => {
  let frames = 0;
  const start = performance.now();
  await new Promise(resolve => {
    const tick = () => { frames += 1; if (performance.now() - start < 1000) requestAnimationFrame(tick); else resolve(); };
    requestAnimationFrame(tick);
  });
  return Math.round(frames * 1000 / (performance.now() - start));
})()`;

let socket;
const report = { generatedFrom: 'dist/', viewports: [] };
try {
  const target = await (async () => {
    for (let attempt = 0; attempt < 40; attempt++) {
      try {
        const list = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
        const page = list.find(item => item.type === 'page' && item.url.startsWith(origin));
        if (page) return page.webSocketDebuggerUrl;
      } catch {}
      await sleep(500);
    }
    throw new Error('the browser never exposed the page over the DevTools Protocol');
  })();

  socket = new WebSocket(target);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let nextId = 1;
  const pending = new Map();
  const pageErrors = [];
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); }
    if (message.method === 'Runtime.exceptionThrown') {
      pageErrors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
    }
  };
  const send = (method, params = {}) => {
    const id = nextId++;
    socket.send(JSON.stringify({ id, method, params }));
    return new Promise(resolve => pending.set(id, resolve));
  };
  const evaluate = async expression => {
    const reply = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (reply.result?.exceptionDetails) throw new Error(`page evaluation failed: ${reply.result.exceptionDetails.text}`);
    return reply.result?.result?.value;
  };

  await send('Page.enable');
  await send('Runtime.enable');

  for (const viewport of VIEWPORTS) {
    await send('Emulation.setDeviceMetricsOverride',
      { width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: false });
    await send('Page.navigate', { url: `${origin}/` });
    await sleep(3500);
    const measured = await evaluate(MEASURE);
    const fps = await evaluate(frameRate);
    const shot = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(OUT, `desktop-${viewport.name}.png`), Buffer.from(shot.result.data, 'base64'));
    const full = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
    writeFileSync(join(OUT, `desktop-${viewport.name}-full.png`), Buffer.from(full.result.data, 'base64'));
    report.viewports.push({ ...viewport, fps, ...measured });
    console.log(`\n=== ${viewport.name} (fps ${fps})`);
    console.log(`  layout ${JSON.stringify(measured.regions['.layout'])}  unused right edge ${measured.unusedWidth}px`);
    console.log(`  viewer ${JSON.stringify(measured.regions['.viewer-panel'])}  canvas ${JSON.stringify(measured.regions['canvas'])}`);
    console.log(`  sideways scroll ${measured.sidewaysScroll}px  document height ${measured.documentHeight}px`);
    console.log(`  interactive ${measured.interactiveCount}, targets under 24px ${measured.smallTargets.length}, overlapping pairs ${measured.overlapCount}`);
    if (measured.smallTargets.length) console.log(`  small: ${measured.smallTargets.slice(0, 6).map(item => `${item.tag}:${item.label} ${item.w}x${item.h}`).join(' | ')}`);
    if (measured.overlaps.length) console.log(`  overlaps: ${measured.overlaps.slice(0, 4).join(' | ')}`);
    console.log(`  fonts: ${measured.fontCensus.map(([value, count]) => `${value}×${count}`).join(' ')}`);
    console.log(`  spacing: ${measured.boxPropertyCensus.slice(0, 8).map(([value, count]) => `${value}×${count}`).join(' ')}`);
  }

  report.pageErrors = pageErrors;
  writeFileSync(join(OUT, 'desktop-baseline.json'), JSON.stringify(report, null, 2));
  console.log(`\npage errors: ${pageErrors.length}`);
  console.log(`screenshots and desktop-baseline.json written to ${OUT}`);
} finally {
  try { socket?.close(); } catch {}
  child.kill();
  server.close();
  await sleep(300);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
