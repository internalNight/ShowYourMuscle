// Verifies the one accessibility property the repository had explicitly not checked: text contrast.
//
// The a11y work so far proved behaviour (focus, keyboard, labels, aria state) but the write-up says in as
// many words that contrast and colour-blind checks were never done. This check closes the contrast half.
//
// It runs the production build in a real browser and measures the *effective* colours rather than reading
// the stylesheet: for every element that directly contains visible text it composites that element's
// colour over its ancestors' backgrounds (including translucent ones such as the research readout) and
// compares the result with the WCAG 2.1 AA thresholds — 4.5:1 for normal text, 3:1 for large text. A
// stylesheet-only audit would have to guess which background each text colour lands on; the browser
// already knows.
//
// What it deliberately does not cover is written down at the bottom of the file: disabled controls
// (WCAG exempts inactive components), text painted on the WebGL canvas, the form-control text that is not
// a DOM text node (it is measured separately from the control's own computed colours), placeholder text,
// and colour-blind distinguishability, which is a different property from contrast.
//
// A browser is required. Set ATLAS_BROWSER to an executable path when auto-detection fails.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const DIST = join(ROOT, 'dist');
const CANDIDATES = [
  process.env.ATLAS_BROWSER,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  '/usr/bin/microsoft-edge', '/usr/bin/google-chrome', '/usr/bin/chromium',
].filter(Boolean);

const browser = CANDIDATES.find(path => existsSync(path));
if (!browser) {
  console.log('SKIPPED: no Chromium-based browser found. Set ATLAS_BROWSER to an executable path ' +
    'to run this check; the other check scripts do not need a browser.');
  process.exit(0);
}
assert(existsSync(join(DIST, 'index.html')),
  'dist/index.html is missing. Run `npm run build` before this check.');

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

const debugPort = 9950 + (process.pid % 40);
const profile = mkdtempSync(join(tmpdir(), 'atlas-contrast-'));
const child = spawn(browser, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--enable-unsafe-swiftshader', `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${profile}`, `${origin}/`], { stdio: 'ignore' });
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// The measurement itself, sent to the page. Kept as one expression so it can be evaluated in each view.
const MEASURE = `(() => {
  const parse = (value) => {
    const match = /rgba?\\(([^)]+)\\)/.exec(value || '');
    if (!match) return null;
    const parts = match[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
  };
  const over = (front, back) => ({
    r: front.r * front.a + back.r * (1 - front.a),
    g: front.g * front.a + back.g * (1 - front.a),
    b: front.b * front.a + back.b * (1 - front.a),
    a: 1,
  });
  const channel = (value) => {
    const c = value / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  const luminance = (colour) =>
    0.2126 * channel(colour.r) + 0.7152 * channel(colour.g) + 0.0722 * channel(colour.b);
  const ratio = (a, b) => {
    const first = luminance(a);
    const second = luminance(b);
    return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
  };
  const backgroundOf = (element) => {
    const layers = [];
    for (let node = element; node; node = node.parentElement) {
      const colour = parse(getComputedStyle(node).backgroundColor);
      if (colour && colour.a > 0) {
        layers.push(colour);
        if (colour.a >= 1) break;
      }
    }
    if (!layers.length) return { r: 255, g: 255, b: 255, a: 1 };
    let result = layers[layers.length - 1];
    for (let index = layers.length - 2; index >= 0; index--) result = over(layers[index], result);
    return result;
  };
  const visible = (element, style, rect) => {
    if (!rect.width || !rect.height) return false;
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    if (Number(style.opacity) === 0) return false;
    if (element.closest('[hidden], [aria-hidden="true"]')) return false;
    // WCAG exempts text in an inactive component, and the app deliberately dims disabled controls.
    if (element.closest(':disabled') || element.matches(':disabled')) return false;
    return true;
  };
  const label = (element) => {
    const id = element.id ? '#' + element.id : '';
    const classes = typeof element.className === 'string' && element.className.trim()
      ? '.' + element.className.trim().split(/\\s+/).slice(0, 2).join('.') : '';
    return element.tagName.toLowerCase() + id + classes;
  };
  const samples = [];
  const failures = [];
  const record = (element, colour, background, fontSize, fontWeight, text) => {
    const large = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
    const threshold = large ? 3 : 4.5;
    const value = ratio(colour, background);
    const entry = {
      selector: label(element),
      text: text.slice(0, 24),
      colour: 'rgb(' + [colour.r, colour.g, colour.b].map(Math.round).join(',') + ')',
      background: 'rgb(' + [background.r, background.g, background.b].map(Math.round).join(',') + ')',
      fontSize: Math.round(fontSize * 10) / 10,
      ratio: Math.round(value * 100) / 100,
      threshold,
    };
    samples.push(entry);
    if (value + 1e-9 < threshold) failures.push(entry);
  };
  for (const element of document.querySelectorAll('*')) {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    if (!visible(element, style, rect)) continue;
    const own = [...element.childNodes].filter(node => node.nodeType === 3 &&
      node.textContent.trim().length).map(node => node.textContent.trim()).join(' ');
    if (own) {
      const colour = parse(style.color);
      if (colour) record(element, colour, backgroundOf(element), parseFloat(style.fontSize),
        Number(style.fontWeight) || 400, own);
      continue;
    }
    // Form controls hold their text in a value, not in a child node.
    if (element.matches('input:not([type=checkbox]):not([type=radio]), select, textarea')) {
      const colour = parse(style.color);
      const background = parse(style.backgroundColor);
      if (colour && style.backgroundColor && getComputedStyle(element).backgroundColor !== 'rgba(0, 0, 0, 0)') {
        record(element, colour, background && background.a >= 1 ? background : backgroundOf(element),
          parseFloat(style.fontSize), Number(style.fontWeight) || 400, element.value || element.tagName);
      }
    }
  }
  return { samples, failures, ratio };
})()`;

let socket;
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
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    }
    if (message.method === 'Runtime.exceptionThrown') {
      pageErrors.push(message.params.exceptionDetails.exception?.description ||
        message.params.exceptionDetails.text);
    }
  };
  const send = (method, params = {}) => {
    const id = nextId++;
    socket.send(JSON.stringify({ id, method, params }));
    return new Promise(resolve => pending.set(id, resolve));
  };
  const evaluate = async (expression) => {
    const reply = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (reply.result?.exceptionDetails) {
      throw new Error(`page evaluation failed: ${reply.result.exceptionDetails.text}`);
    }
    return reply.result?.result?.value;
  };

  const waitFor = async (expression, description, attempts = 120) => {
    for (let attempt = 0; attempt < attempts; attempt++) {
      if (await evaluate(expression)) return;
      await sleep(500);
    }
    throw new Error(`timed out waiting for ${description}`);
  };

  await send('Runtime.enable');
  await waitFor(`!!document.querySelector('canvas') &&
    (document.querySelector('#build-identity')?.textContent || '').includes('构建标识')`,
  'the app to finish booting');

  const verified = [];
  const check = async (name, fn) => {
    try {
      await fn();
    } catch (error) {
      throw new Error(`contrast check failed — ${name}: ${error.message}`);
    }
    verified.push(name);
  };

  // The formula itself is checked first: a measurement that cannot tell dark-on-light from light-on-dark
  // would pass everything below for the wrong reason.
  await check('the WCAG formula agrees with published reference pairs', async () => {
    const cases = await evaluate(`(() => {
      const channel = (value) => { const c = value / 255;
        return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
      const luminance = (colour) => 0.2126 * channel(colour.r) + 0.7152 * channel(colour.g) +
        0.0722 * channel(colour.b);
      const ratio = (a, b) => { const first = luminance(a); const second = luminance(b);
        return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05); };
      const at = (r, g, b) => ({ r, g, b, a: 1 });
      return {
        blackOnWhite: ratio(at(0, 0, 0), at(255, 255, 255)),
        whiteOnBlack: ratio(at(255, 255, 255), at(0, 0, 0)),
        blueOnWhite: ratio(at(0, 0, 255), at(255, 255, 255)),
        greyOnWhite: ratio(at(119, 119, 119), at(255, 255, 255)),
        sameColour: ratio(at(18, 32, 48), at(18, 32, 48)),
      };
    })()`);
    assert(Math.abs(cases.blackOnWhite - 21) < 0.01, `black on white should be 21: ${cases.blackOnWhite}`);
    assert(Math.abs(cases.whiteOnBlack - 21) < 0.01, `white on black should be 21: ${cases.whiteOnBlack}`);
    assert(Math.abs(cases.blueOnWhite - 8.59) < 0.01, `blue on white should be 8.59: ${cases.blueOnWhite}`);
    assert(Math.abs(cases.greyOnWhite - 4.48) < 0.01, `#777 on white should be 4.48: ${cases.greyOnWhite}`);
    assert.equal(cases.sameColour, 1, 'a colour against itself must be exactly 1');
    // The discriminating case: 4.48 misses AA for normal text while 4.5 passes, so a threshold that is
    // applied to the wrong side of the comparison shows up here.
    assert(cases.greyOnWhite < 4.5, 'the reference pair that fails AA must fail the threshold too');
  });

  await check('every visible text passes WCAG AA in the default view', async () => {
    const result = await evaluate(MEASURE);
    assert(result.samples.length >= 40,
      `only ${result.samples.length} text samples were measured — a nearly empty page must not pass`);
    assert.deepEqual(result.failures, [],
      `text below WCAG AA: ${JSON.stringify(result.failures.slice(0, 6))}`);
    const lowest = result.samples.slice().sort((left, right) => left.ratio - right.ratio)[0];
    console.log(`  default view: ${result.samples.length} text samples, lowest ${lowest.ratio}:1 ` +
      `(${lowest.selector} ${lowest.colour} on ${lowest.background})`);
  });

  await check('every visible text passes WCAG AA in the other views and panels', async () => {
    const views = await evaluate(`[...document.querySelectorAll('.exercise-tab, .view-tab')]
      .map(tab => ({ id: tab.dataset.exercise || tab.dataset.view || tab.textContent.trim() }))`);
    assert(views.length >= 6, `expected the exercise and view tabs, found ${views.length}`);
    for (const view of views) {
      await evaluate(`(() => { const tab = [...document.querySelectorAll('.exercise-tab, .view-tab')]
        .find(item => (item.dataset.exercise || item.dataset.view || item.textContent.trim()) === ${JSON.stringify(view.id)});
        tab.click(); return true; })()`);
      await sleep(220);
      const result = await evaluate(MEASURE);
      assert(result.samples.length >= 20,
        `${view.id}: only ${result.samples.length} text samples were measured`);
      assert.deepEqual(result.failures, [],
        `${view.id}: text below WCAG AA: ${JSON.stringify(result.failures.slice(0, 6))}`);
    }
  });

  await check('the page reported no errors while measuring', async () => {
    assert.deepEqual(pageErrors, [], `the page raised: ${pageErrors.join(' | ')}`);
  });

  console.log(`Text contrast matches WCAG 2.1 AA everywhere it was measured ` +
    `(${verified.length} behaviours, ${origin}).`);
} finally {
  try { socket?.close(); } catch {}
  child.kill();
  await sleep(300);
  server.close();
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
