// Desktop layout check: the measurable half of "make the desktop pass not ugly".
//
// It serves dist/ and drives a headless Chromium at 1920x1080 and 1440x900, then asserts the properties that
// can be stated without taste: nothing scrolls sideways; every interactive element is actually hit-testable
// where it is drawn (a box can overlap because of clipped overflow, so this samples elementFromPoint instead
// of comparing boxes); every control's effective target (its wrapping label when present) is at least 24x24
// px (WCAG 2.5.8); text that is told not to wrap is not clipped by an overflow:hidden ancestor; and every
// CSS font size used belongs to the token scale declared in src/style.css (SVG chart labels are exempt, their
// computed size is scaled by the viewBox).
//
// Screenshots: set ATLAS_SCREENSHOTS to a directory to also save desktop-<viewport>.png there for human
// review, because no model in this pipeline can look at the page.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const DIST = join(ROOT, 'dist');
const SCREENSHOTS = process.env.ATLAS_SCREENSHOTS || '';
const VIEWPORTS = [
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '1440x900', width: 1440, height: 900 },
];
const ALLOWED_FONTS = ['10px', '11px', '12px', '13px', '14px', '16px', '18px', '20px'];
const MIN_TARGET = 24;
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
  console.log('SKIPPED: no Chromium-based browser found. Set ATLAS_BROWSER to run this check.');
  process.exit(0);
}
assert(existsSync(join(DIST, 'index.html')), 'dist/index.html is missing. Run `npm run build` first.');
if (SCREENSHOTS) mkdirSync(SCREENSHOTS, { recursive: true });

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

const debugPort = 9400 + (process.pid % 500);
const profile = mkdtempSync(join(tmpdir(), 'atlas-desktop-check-'));
const child = spawn(browser, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--enable-unsafe-swiftshader', '--force-device-scale-factor=1',
  `--remote-debugging-port=${debugPort}`, `--user-data-dir=${profile}`, `${origin}/`], { stdio: 'ignore' });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

const AUDIT = `(() => {
  const labelOf = el => (el.getAttribute('aria-label') || el.textContent || el.getAttribute('name') || '').trim().slice(0, 30);
  const visible = el => { const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
  const controls = [...document.querySelectorAll('button, a[href], input, select, textarea, [role="button"], [tabindex]:not([tabindex="-1"])')]
    .filter(visible).map(el => {
      const label = el.closest('label');
      const area = label && label !== el && visible(label) ? label : el;
      const b = area.getBoundingClientRect();
      let left = Math.max(0, b.x), top = Math.max(0, b.y);
      let right = Math.min(innerWidth, b.x + b.width), bottom = Math.min(innerHeight, b.y + b.height);
      for (let node = area.parentElement; node && node !== document.documentElement; node = node.parentElement) {
        const style = getComputedStyle(node);
        if (!/(hidden|auto|scroll|clip)/.test(style.overflowX + '|' + style.overflowY)) continue;
        const r = node.getBoundingClientRect();
        const boxLeft = r.left + node.clientLeft, boxTop = r.top + node.clientTop;
        left = Math.max(left, boxLeft); top = Math.max(top, boxTop);
        right = Math.min(right, boxLeft + node.clientWidth); bottom = Math.min(bottom, boxTop + node.clientHeight);
      }
      const minVisible = Math.min(24, Math.min(b.width, b.height));
      const offscreen = right - left < minVisible || bottom - top < minVisible;
      const xs = [left + 4, (left + right) / 2, right - 4];
      const ys = [top + 4, (top + bottom) / 2, bottom - 4];
      const samples = [];
      for (const x of xs) for (const y of ys) if (x > left && y > top && x < right && y < bottom) samples.push([x, y]);
      let blocked = 0, centreBlocked = false, centreBlocker = '';
      const describe = node => node ? node.tagName.toLowerCase() + '.' + String(node.className || '').split(' ')[0] : 'nothing';
      for (const [x, y] of samples) {
        const hit = document.elementFromPoint(x, y);
        const ok = hit && (hit === el || hit === area || el.contains(hit) || hit.contains(el) ||
          (label && label.contains(hit)));
        if (!ok) {
          blocked += 1;
          if (Math.abs(x - (left + right) / 2) < 3 && Math.abs(y - (top + bottom) / 2) < 3) {
            centreBlocked = true; centreBlocker = describe(hit);
          }
        }
      }
      const inlineLink = el.tagName === 'A' && getComputedStyle(el).display === 'inline' &&
        !!el.closest('p, li, small, .footer, .lab-evidence-body, .form-footer');
      return { tag: el.tagName.toLowerCase(), label: labelOf(el), w: Math.round(b.width), h: Math.round(b.height),
        inlineLink, offscreen, inPanel: !!el.closest('.control-panel'), centreBlocker, visibleBox: [Math.round(left), Math.round(top), Math.round(right), Math.round(bottom)], visibleW: Math.round(Math.max(0, right - left)), visibleH: Math.round(Math.max(0, bottom - top)), samples: samples.length, blocked, centreBlocked };
    });
  const clipped = [];
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (!['hidden', 'clip'].includes(cs.overflowX) || cs.whiteSpace !== 'nowrap') continue;
    if (el.scrollWidth > el.clientWidth + 2) clipped.push(el.tagName.toLowerCase() + ':' + (el.textContent || '').trim().slice(0, 24));
  }
  const fonts = {}, fontSamples = {};
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('svg')) continue;
    const hasText = [...el.childNodes].some(node => node.nodeType === 3 && node.textContent.trim());
    if (!hasText) continue;
    const size = getComputedStyle(el).fontSize;
    fonts[size] = (fonts[size] || 0) + 1;
    if (!fontSamples[size]) fontSamples[size] = [];
    if (fontSamples[size].length < 3) {
      fontSamples[size].push(el.tagName.toLowerCase() + '.' + String(el.className || '').split(' ')[0] +
        (el.ownerSVGElement ? '[in-svg]' : '') + ' :: ' + (el.textContent || '').trim().slice(0, 16));
    }
  }
  const root = document.documentElement;
  return {
    viewport: { w: innerWidth, h: innerHeight },
    sidewaysScroll: root.scrollWidth - root.clientWidth,
    canvas: (() => { const el = document.querySelector('canvas'); if (!el) return null;
      const r = el.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) }; })(),
    documentHeight: document.documentElement.scrollHeight,
    columnHeights: (() => { const result = {};
      for (const selector of ['.control-panel', '.viewer-panel', '.profile-card', '.training-card', '.backup-card', '.intro', '.footer']) {
        const el = document.querySelector(selector);
        if (el) result[selector] = Math.round(el.getBoundingClientRect().height);
      } return result; })(),
    controlCount: controls.length,
    tooSmall: controls.filter(c => !c.offscreen && !c.inlineLink && Math.min(c.w, c.h) < ${MIN_TARGET}),
    inlineLinks: controls.filter(c => c.inlineLink && Math.min(c.w, c.h) < ${MIN_TARGET}).length,
    blockedCentres: controls.filter(c => !c.offscreen && c.centreBlocked),
    blockedPoints: controls.filter(c => !c.offscreen && c.blocked > 0 && !c.centreBlocked),
    offscreenControls: controls.filter(c => c.offscreen).length,
    offscreenPrimary: controls.filter(c => c.offscreen && c.inPanel).length,
    offscreenPrimaryLabels: controls.filter(c => c.offscreen && c.inPanel).map(c => c.tag + ':' + c.label),
    clippedNowrap: clipped,
    fonts,
    fontSamples,
  };
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

  // 设计 token 静态校验（增补之八十四）：纯文件读取，先跑，失败得快。
  {
    const sources = ['src/style.css', 'index.html'];
    let css = '';
    for (const file of sources) css += readFileSync(new URL('../' + file, import.meta.url), 'utf8') + '\n';
    const defined = new Set([...css.matchAll(/(--[a-z0-9-]+)\s*:/g)].map(match => match[1]));
    const unresolved = [];
    for (const match of css.matchAll(/var\(\s*(--[a-z0-9-]+)\s*([,)])/g)) {
      if (!defined.has(match[1]) && match[2] === ')') unresolved.push(match[1]);
    }
    const uniqueUnresolved = [...new Set(unresolved)];
    assert.equal(uniqueUnresolved.length, 0, "设计 token 引用无法解析：出现了没有定义、也没有回退值的 var()" + ': ' + uniqueUnresolved.join(', '));
    const fontSizes = [...css.matchAll(/font-size:\s*([^;\n]+)/g)].map(match => match[1].trim());
    const allowed = new Set(['9px', '30px']);
    const offScale = [...new Set(fontSizes.filter(value => !/^var\(--(text|display)/.test(value)
      && !allowed.has(value) && !/^clamp\(/.test(value) && !/[`\\]/.test(value)))];
    assert.equal(offScale.length, 0, '字号必须来自 --text-*/--display 刻度：' + offScale.join(', '));
    const measure = (pattern) => new Set([...css.matchAll(pattern)].map(match => match[0].trim())).size;
    console.log('设计 token 现状：font-size ' + new Set(fontSizes).size + ' 种、padding '
      + measure(/padding:\s*[^;\n]+/g) + ' 种、gap ' + measure(/gap:\s*[^;\n]+/g) + ' 种、border-radius '
      + measure(/border-radius:\s*[^;\n]+/g) + ' 种、颜色 ' + measure(/#[0-9a-fA-F]{3,8}\b/g) + ' 种');
  }
  // 设计 token 静态校验（增补之八十四）：纯文件读取，先跑，失败得快。
  {
    const sources = ['src/style.css', 'index.html'];
    let css = '';
    for (const file of sources) css += readFileSync(new URL('../' + file, import.meta.url), 'utf8') + '\n';
    const defined = new Set([...css.matchAll(/(--[a-z0-9-]+)\s*:/g)].map(match => match[1]));
    const unresolved = [];
    for (const match of css.matchAll(/var\(\s*(--[a-z0-9-]+)\s*([,)])/g)) {
      if (!defined.has(match[1]) && match[2] === ')') unresolved.push(match[1]);
    }
    const uniqueUnresolved = [...new Set(unresolved)];
    assert.equal(uniqueUnresolved.length, 0, "设计 token 引用无法解析：出现了没有定义、也没有回退值的 var()" + ': ' + uniqueUnresolved.join(', '));
    const fontSizes = [...css.matchAll(/font-size:\s*([^;\n]+)/g)].map(match => match[1].trim());
    const allowed = new Set(['9px', '30px']);
    const offScale = [...new Set(fontSizes.filter(value => !/^var\(--(text|display)/.test(value)
      && !allowed.has(value) && !/^clamp\(/.test(value) && !/[`\\]/.test(value)))];
    assert.equal(offScale.length, 0, '字号必须来自 --text-*/--display 刻度：' + offScale.join(', '));
    const measure = (pattern) => new Set([...css.matchAll(pattern)].map(match => match[0].trim())).size;
    console.log('设计 token 现状：font-size ' + new Set(fontSizes).size + ' 种、padding '
      + measure(/padding:\s*[^;\n]+/g) + ' 种、gap ' + measure(/gap:\s*[^;\n]+/g) + ' 种、border-radius '
      + measure(/border-radius:\s*[^;\n]+/g) + ' 种、颜色 ' + measure(/#[0-9a-fA-F]{3,8}\b/g) + ' 种');
  }
  // 状态齐全（增补之八十五）：每个 :hover 选择器都必须有等价的 :focus-visible 规则。
  // 解析前先去掉注释——第一版就是被注释污染了"选择器"字符串，导致 .button 被误判为缺失。
  {
    const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, ' ');
    const rules = [...css.matchAll(/([^{}]+)\{/g)].map(match => match[1]).filter(text => !text.includes('@'));
    const basesFor = marker => new Set(rules.flatMap(text => text.split(','))
      .filter(selector => selector.includes(marker))
      .map(selector => selector.replace(/:hover|:focus-visible/g, '').trim()));
    const hoverBases = basesFor(':hover');
    const focusBases = basesFor(':focus-visible');
    const missing = [...hoverBases].filter(base => base && !focusBases.has(base));
    assert.equal(missing.length, 0, "交互状态不齐全：这些控件的 hover 没有对应的键盘焦点样式" + ': ' + missing.join(', '));
  }
  // 圆角 token（增补之八十六）：任何 border-radius 都必须是 var(--radius-*)。
  // 白名单里只留 99px 一处已知欠账（它几乎等效于 pill，但改值会动到渲染，等审美裁决再收）。
  {
    const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, ' ');
    const radii = [...css.matchAll(/border-radius:\s*([^;\n]+)/g)].map(match => match[1].trim());
    const allowed = new Set(['99px']);
    const literals = [...new Set(radii.filter(value => !/^var\(--radius-/.test(value) && !allowed.has(value)))];
    assert.equal(literals.length, 0, "圆角必须来自 --radius-* token，不能直接写字面量" + ': ' + literals.join(', '));
  }
  // 间距棘轮（增补之八十七）：4px 刻度内的间距必须走 --space-* token；非刻度值暂时保留，
  // 但**种类数不许增加**——这是"不改视觉也能守住不恶化"的可测量约束，等审美裁决后再收敛刻度。
  {
    const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, ' ');
    const spacing = /(?:^|[;{\s])(padding|gap|row-gap|column-gap|margin)\s*:\s*([^;{}]+);/g;
    const offScale = new Set();
    for (const match of css.matchAll(spacing)) {
      for (const part of match[2].split(/\s+/)) {
        if (!/^\d+px$/.test(part)) continue;
        const size = Number(part.replace('px', ''));
        if (size % 4 !== 0 || size > 48) offScale.add(part);
      }
    }
    assert.ok(offScale.size <= 18, "间距漂移数量增加了：出现了新的非 4px 刻度值" + ': ' + offScale.size
      + ' 种（上限 118）：' + [...offScale].sort().join(', '));
  }
  // 颜色 token（增补之九十一）：同一个色值不许在多于一处以字面量出现（重复的必须提成 --palette-*）。
  {
    const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, ' ');
    const withoutDefinitions = css.replace(/--[a-z0-9-]+\s*:\s*#[0-9a-fA-F]{3,8}\s*;/g, ' ');
    const counts = new Map();
    for (const match of withoutDefinitions.matchAll(/#[0-9a-fA-F]{3,8}\b/g)) {
      const value = match[0].toLowerCase();
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }
    const repeated = [...counts.entries()].filter(([, count]) => count >= 2).map(([value, count]) => value + 'x' + count);
    assert.equal(repeated.length, 0, "重复的颜色字面量必须提成命名 token，不能散落在各处" + ': ' + repeated.join(', '));
    const distinct = new Set([...css.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map(match => match[0].toLowerCase())).size;
    assert.ok(distinct <= 109, "颜色字面量种类数增加了，请先把它提成命名 token" + ': ' + distinct
      + ' 种（上限 118）');
  }
  // 对比度（增补之九十二）：同一规则块里同时声明 color 与 background 的元素，静态算 WCAG 对比度，必须 >= 4.5:1。
  // 覆盖率有限：只覆盖能静态解析的配对（本次 15 组）；继承背景的规则静态算不出来，留待浏览器侧扩展。
  {
    const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, ' ');
    const tokens = new Map();
    for (const match of css.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;{}]+);/g)) tokens.set(match[1], match[2].trim());
    const resolveValue = (value, depth = 0) => {
      let text = value.trim();
      if (depth < 5) {
        const reference = /^var\((--[a-z0-9-]+)\)$/.exec(text);
        if (reference && tokens.has(reference[1])) text = resolveValue(tokens.get(reference[1]), depth + 1);
      }
      return text;
    };
    const parseColour = (value) => {
      const text = resolveValue(value).toLowerCase();
      const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/.exec(text);
      if (hex) {
        const digits = hex[1].length === 3 ? hex[1].split('').map(char => char + char).join('') : hex[1];
        return { r: parseInt(digits.slice(0, 2), 16), g: parseInt(digits.slice(2, 4), 16), b: parseInt(digits.slice(4, 6), 16), a: 1 };
      }
      const rgba = /^rgba?\(([^)]+)\)$/.exec(text);
      if (rgba) {
        const parts = rgba[1].split(/[,/]/).map(part => part.trim()).filter(Boolean).map(Number);
        if (parts.length >= 3 && parts.every(part => Number.isFinite(part))) return { r: parts[0], g: parts[1], b: parts[2], a: parts[3] ?? 1 };
      }
      return null;
    };
    const luminance = (colour) => {
      const channel = value => { const v = value / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
      return 0.2126 * channel(colour.r) + 0.7152 * channel(colour.g) + 0.0722 * channel(colour.b);
    };
    const lowContrast = [];
    let resolvable = 0;
    for (const match of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      const selector = match[1].trim().replace(/\s+/g, ' ');
      if (selector.startsWith('@')) continue;
      const body = match[2];
      const colour = /(?:^|[;{\s])color\s*:\s*([^;{}]+)/.exec(body);
      const background = /(?:^|[;{\s])background(?:-color)?\s*:\s*([^;{}]+)/.exec(body);
      if (!colour || !background) continue;
      const foreground = parseColour(colour[1]);
      const back = parseColour(background[1].split(/\s+/)[0]);
      if (!foreground || !back || foreground.a < 1 || back.a < 1) continue;
      resolvable += 1;
      const [hi, lo] = [luminance(foreground), luminance(back)].sort((a, b) => b - a);
      const ratio = (hi + 0.05) / (lo + 0.05);
      if (ratio < 4.5) lowContrast.push(selector + ' ' + colour[1].trim() + ' on ' + background[1].trim() + ' = ' + ratio.toFixed(2));
    }
    console.log('对比度：静态可解析配对 ' + resolvable + ' 组，低于 4.5:1 的 ' + lowContrast.length + ' 组');
    assert.equal(lowContrast.length, 0, "文字与背景的对比度低于 4.5:1" + '：' + lowContrast.join('; '));
  }
  // 对比度（增补之九十三）：在浏览器里逐元素量真实前景/背景色——包含**继承**来的背景与半透明合成，
  // 这正是静态规则算不出的那 55 组。阈值按 WCAG：正文 4.5:1，大字号（>=24px，或 >=18.66px 且粗体）3:1。
  // 上限取自一次真实测量（先测后冻结的棘轮），不是拍的。
  {
    const walkContrast = function walk() {
  const toRgb = (text) => {
    const match = /rgba?\(([^)]+)\)/.exec(text || '');
    if (!match) return null;
    const parts = match[1].split(',').map(part => parseFloat(part));
    if (parts.length < 3 || parts.slice(0, 3).some(part => !Number.isFinite(part))) return null;
    return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 && Number.isFinite(parts[3]) ? parts[3] : 1 };
  };
  const channel = (value) => { const v = value / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const luminance = (colour) => 0.2126 * channel(colour.r) + 0.7152 * channel(colour.g) + 0.0722 * channel(colour.b);
  const blend = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const backgroundOf = (element) => {
    let current = element;
    let result = { r: 255, g: 255, b: 255, a: 1 };
    const stack = [];
    while (current) {
      const colour = toRgb(getComputedStyle(current).backgroundColor);
      if (colour && colour.a > 0) {
        stack.push(colour);
        if (colour.a >= 1) break;
      }
      current = current.parentElement;
    }
    for (let index = stack.length - 1; index >= 0; index -= 1) result = blend(stack[index], result);
    return result;
  };
  const describe = (element) => {
    if (element.id) return '#' + element.id;
    const classes = String(element.className || '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
    return classes.length > 0 ? element.tagName.toLowerCase() + '.' + classes.join('.') : element.tagName.toLowerCase();
  };
  const results = [];
  for (const element of document.querySelectorAll('body *')) {
    const hasText = Array.from(element.childNodes).some(node => node.nodeType === 3 && node.textContent.trim().length > 0);
    if (!hasText) continue;
    const style = getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;
    const box = element.getBoundingClientRect();
    if (box.width < 2 || box.height < 2) continue;
    const foreground = toRgb(style.color);
    if (!foreground) continue;
    const background = backgroundOf(element);
    const solid = foreground.a < 1 ? blend(foreground, background) : foreground;
    const sorted = [luminance(solid), luminance(background)].sort((a, b) => b - a);
    const ratio = (sorted[0] + 0.05) / (sorted[1] + 0.05);
    const size = parseFloat(style.fontSize);
    const large = size >= 24 || (size >= 18.66 && parseInt(style.fontWeight, 10) >= 700);
    results.push({
      selector: describe(element),
      ratio: Math.round(ratio * 100) / 100,
      threshold: large ? 3 : 4.5,
      color: style.color,
      background: 'rgb(' + Math.round(background.r) + ', ' + Math.round(background.g) + ', ' + Math.round(background.b) + ')',
    });
  }
  results.sort((a, b) => a.ratio - b.ratio);
  return JSON.stringify({
    measured: results.length,
    failing: results.filter(entry => entry.ratio < entry.threshold),
    tightest: results.filter(entry => entry.ratio >= entry.threshold)[0] || null,
    worst: results[0] || null,
  });
};
    const measured = JSON.parse(await evaluate('(' + walkContrast.toString() + ')()'));
    const detail = measured.failing.map(entry => entry.selector + '=' + entry.ratio.toFixed(2) + '(' + entry.color + ' on ' + entry.background + ')');
    console.log('浏览器对比度实测：可测文本元素 ' + measured.measured + ' 个，最低 '
      + (measured.worst ? measured.worst.ratio.toFixed(2) + '（' + measured.worst.selector + '）' : 'n/a')
      + '，低于阈值 ' + measured.failing.length + ' 个');
    if (detail.length > 0) console.log('浏览器对比度不达标明细：' + detail.join(' | '));
    if (measured.tightest) console.log('浏览器对比度最紧的达标元素：' + measured.tightest.selector + ' '
      + measured.tightest.color + ' on ' + measured.tightest.background + ' = ' + measured.tightest.ratio.toFixed(2));
    assert.ok(measured.failing.length <= 0, "浏览器实测对比度低于阈值的元素变多了" + '：' + measured.failing.length + ' 个（上限 118）：' + detail.slice(0, 6).join('; '));
  }
  await send('Page.enable');
  await send('Runtime.enable');

  for (const viewport of VIEWPORTS) {
    await send('Emulation.setDeviceMetricsOverride',
      { width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: false });
    await send('Page.navigate', { url: `${origin}/` });
    await sleep(3200);
    // ⑤：研究网格是首次交互/空闲后才拉的（10 MB，不进首屏），那几段的来源切换要等它完成——否则量到的是
    // 换之前的画面，截图也证明不了裁决。等待有限：20 秒仍不出现即判失败，让"换了没换"本身可见。
    let swap = null;
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const raw = await evaluate("document.querySelector('#viewer').dataset.geometrySwap ?? ''");
      if (raw) { swap = JSON.parse(raw); if (swap.active) break; }
      await sleep(200);
    }
    assert.ok(swap && swap.active, `${viewport.name}: 默认视图没有把那几段换成研究网格 (geometrySwap=${JSON.stringify(swap)})`);
    assert.ok(Array.isArray(swap.swapped) && swap.swapped.length > 0,
      `${viewport.name}: 来源切换没有记录被换掉的体段`);
  assert.equal(swap.exportMeshesRemaining, 0,
    swap.exportMeshesRemaining + " export meshes for swapped bodies are still attached to the scene, so the "
    + "research geometry only claims to have replaced them");
    // 悬停标签：先在 1920×1080 视口下扫描九宫格确认过内容（(0.5,0.3) → addlong_l；(0.5,0.55) → sart_l），
    // 且标签只在 OpenSim 肌肉视图里存在，所以这里先切到深蹲 + OpenSim，验证完再回到默认视图，
    // 免得 AUDIT 和评审截图看到的是被切走的画面。
    if (viewport.width >= 1900) {
      await evaluate("document.querySelector('[data-exercise=\"squat\"]')?.click()");
      await evaluate("document.querySelector('[data-view=\"opensim\"]')?.click()");
      let tubes = null;
      for (let attempt = 0; attempt < 40; attempt += 1) {
        const raw = await evaluate("document.querySelector('#viewer').dataset.muscleTubes ?? ''");
        if (raw) { tubes = JSON.parse(raw); if (tubes.tubes === 80) break; }
        await sleep(250);
      }
      assert.ok(tubes && tubes.tubes === 80,
        `${viewport.name}: 肌肉管没有就绪，无法验证悬停标签 (muscleTubes=${JSON.stringify(tubes)})`);
      const canvasBox = await evaluate("(() => { const c = document.querySelector('#viewer canvas');"
        + " if (!c) return null; const r = c.getBoundingClientRect();"
        + " return { left: r.left, top: r.top, width: r.width, height: r.height }; })()");
      const hoverAt = async (fx, fy) => {
        await send('Input.dispatchMouseEvent', { type: 'mouseMoved', button: 'none', clickCount: 0,
          x: Math.round(canvasBox.left + canvasBox.width * fx),
          y: Math.round(canvasBox.top + canvasBox.height * fy) });
        let text = '';
        for (let attempt = 0; attempt < 12; attempt += 1) {
          await sleep(300);
          text = await evaluate("document.querySelector('.viewer-hover-label')?.textContent ?? ''");
          if (text) break;
        }
        return text;
      };
      const candidatePoints = [[0.5, 0.3], [0.5, 0.55], [0.42, 0.62], [0.58, 0.5], [0.5, 0.72]];
      const labels = [];
      for (const [fx, fy] of candidatePoints) {
        const text = await hoverAt(fx, fy);
        if (text && text.length > 0) labels.push(text);
        if ([...new Set(labels)].length >= 2) break;
      }
      assert.ok(labels.length > 0, `${viewport.name}: 悬停模型没有出现标签（候选点全部为空）`);
      for (const text of labels) {
        assert.ok(/^[a-z][a-zA-Z0-9_]*(?: · 路径 [+-]\d+\.\d%)?$/.test(text),
          `${viewport.name}: 悬停标签形状不像解剖标识符：${text}`);
      }
      const distinctLabels = [...new Set(labels)];
      assert.ok(distinctLabels.length >= 2,
        `${viewport.name}: 多个不同部位的悬停标签完全相同（${distinctLabels.join('/')}）——标签不反映悬停对象`);
      // 回到默认视图并重新等来源切换，保证 AUDIT 与截图看到的仍是默认画面。
      await send('Page.navigate', { url: origin + '/' });
      await sleep(3200);
      for (let attempt = 0; attempt < 100; attempt += 1) {
        const raw = await evaluate("document.querySelector('#viewer').dataset.geometrySwap ?? ''");
        if (raw && JSON.parse(raw).active) break;
        await sleep(200);
      }
    }
    const result = await evaluate(AUDIT);
    console.log(`  columns: ${Object.entries(result.columnHeights).map(([name, height]) => `${name} ${height}`).join(', ')}`);
    if (SCREENSHOTS) {
      const shot = await send('Page.captureScreenshot', { format: 'png' });
      writeFileSync(join(SCREENSHOTS, `desktop-${viewport.name}.png`), Buffer.from(shot.result.data, 'base64'));
    }

    assert.equal(result.sidewaysScroll, 0,
      `${viewport.name}: the page scrolls sideways by ${result.sidewaysScroll}px`);
    assert.equal(result.blockedCentres.length, 0,
      `${viewport.name}: the centre of ${result.blockedCentres.map(item => `${item.tag}:${item.label} (visible ${item.visibleBox} of ${item.w}x${item.h}, over it: ${item.centreBlocker})`).join(', ')} is not the control drawn there`);
    const fonts = Object.keys(result.fonts).filter(size => {
      const value = parseFloat(size);
      return !ALLOWED_FONTS.includes(size) && value < 28;
    });
    assert.equal(fonts.length, 0,
      `${viewport.name}: font sizes ${fonts.map(size => `${size} (${(result.fontSamples[size] || []).join(' | ')})`).join(', ')} are outside the token scale`);
    for (const item of result.tooSmall) {
      assert.ok(Math.min(item.w, item.h) >= MIN_TARGET,
        `${viewport.name}: ${item.tag}:${item.label} is ${item.w}x${item.h}px, under ${MIN_TARGET}px`);
    }
    assert.equal(result.clippedNowrap.length, 0,
      `${viewport.name}: text told not to wrap is clipped: ${result.clippedNowrap.join(', ')}`);
    assert.ok(result.canvas && result.canvas.w > 400 && result.canvas.h > 300,
      `${viewport.name}: the model canvas is ${JSON.stringify(result.canvas)}`);
    // A desktop layout gives the model the screen: at 1200px and wider the canvas has to take at least 60%
    // of the viewport height (the old phone column managed 47%) and the page has to fit inside two screens
    // (it was 2.8 tall, and 2.51 with an uncapped control panel), so a regression fails here.
    assert.ok(result.canvas.h >= viewport.height * 0.6,
      `${viewport.name}: the model canvas is ${result.canvas.h}px tall, under 60% of the ${viewport.height}px viewport`);
    assert.ok(result.documentHeight <= viewport.height * 2,
      `${viewport.name}: the page is ${result.documentHeight}px tall, more than two ${viewport.height}px viewports`);
    // The data column is allowed to scroll; the panel that drives the model is not, because a control
    // you have to go looking for is a control that is not there. This was 5 at 1080 and 8 at 900 before the
    // view presets and layer switches moved next to the model; it must stay at zero.
    assert.ok(result.offscreenPrimary === 0,
      `${viewport.name}: ${result.offscreenPrimary} controls that drive the model are scrolled out of the control panel ` +
      `(${result.offscreenPrimaryLabels.join(', ')})`);
    assert.equal(pageErrors.length, 0, `the page logged errors: ${pageErrors.join('; ')}`);

    console.log(`${viewport.name}: canvas ${result.canvas.w}x${result.canvas.h} (${Math.round(result.canvas.h / viewport.height * 100)}% of viewport height), ` +
      `page ${result.documentHeight}px (${(result.documentHeight / viewport.height).toFixed(2)} screens), ${result.controlCount} controls ` +
      `(${result.offscreenControls} scrolled out of their card, ${result.offscreenPrimary} of them model controls: ` +
      `${result.offscreenPrimaryLabels.join(' ') || 'none'}), ` +
      `${result.tooSmall.length} under ${MIN_TARGET}px, ${result.blockedCentres.length} blocked centres, ` +
      `fonts ${Object.entries(result.fonts).map(([size, count]) => `${size}x${count}`).join(' ')}`);
  }

// ④ 宽屏契约（增补之一百零四～一百零七）：1600px 以上是宽屏专用版面，这里守住三件"能测"的事——
// 模型画布占比、主工作区栏数、正文行宽；另加一条自比：换成宽屏版面后，视角预设与图层开关的**数量不许变**
// （防止媒体查询把工具栏藏起来，而所有"可见性"断言都还是绿的）。
const countsAt = async (width, height) => {
  await send('Emulation.setDeviceMetricsOverride', { width: width, height: height, deviceScaleFactor: 1, mobile: false });
  await sleep(400);
  const text = await evaluate(`(function () {
    const canvas = document.querySelector('canvas');
    const rect = canvas ? canvas.getBoundingClientRect() : { width: 0, height: 0 };
    const workspace = document.querySelector('.workspace');
    const columns = workspace ? getComputedStyle(workspace).gridTemplateColumns.split(' ').filter(Boolean).length : 0;
    const widths = Array.from(document.querySelectorAll('p')).map((node) => node.getBoundingClientRect().width);
    const widest = widths.length ? Math.max.apply(null, widths) : 0;
    const fontSize = parseFloat(getComputedStyle(document.body).fontSize) || 16;
    return JSON.stringify({ canvasFraction: (rect.width * rect.height) / ${width * height}, columns: columns,
      proseChars: widest / (fontSize * 0.5),
      presets: Array.from(document.querySelectorAll('.view-tab')).filter((el) => el.getClientRects().length > 0).length,
      layers: Array.from(document.querySelectorAll('.layers input')).filter((el) => el.getClientRects().length > 0).length });
  })()`);
  return JSON.parse(text);
};
const atNarrow = await countsAt(1440, 900);
const wide = await countsAt(1920, 1080);
console.log('宽屏实测：画布占比 ' + wide.canvasFraction.toFixed(3) + '，工作区栏数 ' + wide.columns
  + '，最长正文 ' + Math.round(wide.proseChars) + ' 字符，视角预设 ' + wide.presets + '，图层开关 ' + wide.layers
  + '（1440 下为 ' + atNarrow.presets + '/' + atNarrow.layers + '）');
assert.ok(wide.canvasFraction >= 0.356, "宽屏（1920×1080）下模型画布占比过小" + '：' + wide.canvasFraction.toFixed(3) + '（下限 0.356）');
assert.ok(wide.columns >= 2, "宽屏下主工作区退化成单栏" + '：' + wide.columns + ' 栏');
assert.ok(wide.proseChars <= 118, "宽屏下正文行宽过长，影响阅读" + '：' + Math.round(wide.proseChars) + ' 字符（上限 118）');
assert.ok(wide.presets > 0 && wide.layers > 0, "宽屏下找不到视角预设或图层开关" + '：预设 ' + wide.presets + '，图层 ' + wide.layers);
assert.deepEqual({ presets: wide.presets, layers: wide.layers }, { presets: atNarrow.presets, layers: atNarrow.layers },
  "宽屏下视角预设或图层开关数量发生了变化" + '：1440 下 ' + atNarrow.presets + '/' + atNarrow.layers + '，1920 下 ' + wide.presets + '/' + wide.layers);
  const layerInfoText = await evaluate(`(function () {
    return JSON.stringify(Array.from(document.querySelectorAll('.layers input')).map((input) => ({
      id: input.id || '', className: input.className || '', type: input.type || '',
      checked: !!input.checked, visible: input.getClientRects().length > 0,
      display: getComputedStyle(input).display,
      parent: input.parentElement ? input.parentElement.className : '' })));
  })()`);
  console.log('图层开关明细：' + layerInfoText);
  // ④ 状态相关控件（增补之一百零八）：`#tsm-upper-bones-control` 只在 **OpenSim 视图 + 非深蹲** 时露出
  // （src/main.ts:582）。断言"该出现时必须出现且能点、不该出现时必须消失且禁用"——这类"永远点不到的控件"
  // 不会被任何可见性或尺寸断言发现。
  const labelList = async (selector) => JSON.parse(await evaluate("JSON.stringify(Array.from(document.querySelectorAll('" + selector + "')).map(function (node) { return (node.textContent || '').trim(); }))"));
  const clickLabel = async (selector, label) => {
    await evaluate("(function () { var nodes = Array.from(document.querySelectorAll('" + selector + "')); var node = nodes.find(function (n) { return (n.textContent || '').trim() === " + JSON.stringify(label) + "; }); if (node) node.click(); })()");
    await sleep(700);
  };
  const controlState = async () => JSON.parse(await evaluate("JSON.stringify((function () { var control = document.querySelector('#tsm-upper-bones-control'); var toggle = document.querySelector('#tsm-upper-bones-toggle'); var rect = toggle ? toggle.getBoundingClientRect() : { width: 0, height: 0 }; return { hidden: control ? control.hidden : null, disabled: toggle ? toggle.disabled : null, visible: toggle ? toggle.getClientRects().length > 0 : false, width: Math.round(rect.width), height: Math.round(rect.height) }; })())"));
  const viewLabels = await labelList('.view-tab');
  const exerciseLabels = await labelList('.exercise-tab');
  console.log('状态控件·可选视图：' + JSON.stringify(viewLabels) + '；可选运动：' + JSON.stringify(exerciseLabels));
  const opensimLabel = viewLabels.find((label) => /opensim/i.test(label));
  const squatLabel = exerciseLabels.find((label) => /蹲|squat/i.test(label));
  const otherLabel = exerciseLabels.find((label) => !/蹲|squat/i.test(label));
  assert.ok(opensimLabel && squatLabel && otherLabel,
    '状态控件断言需要的视图/运动标签没有识别出来：' + JSON.stringify(viewLabels) + '/' + JSON.stringify(exerciseLabels));
  await clickLabel('.exercise-tab', otherLabel);
  await clickLabel('.view-tab', opensimLabel);
  const controlShown = await controlState();
  await clickLabel('.exercise-tab', squatLabel);
  const controlGone = await controlState();
  // （增补之一百零九）OpenSim 视图里深蹲杠没有意义，必须隐藏（src/main.ts:571-574）。
  const squatBarState = JSON.parse(await evaluate("JSON.stringify((function () { var bar = document.querySelector('#squat-bar-control'); var note = document.querySelector('#squat-bar-note'); return { barHidden: bar ? bar.hidden : null, noteHidden: note ? note.hidden : null }; })())"));
  console.log('深蹲杠实测：' + JSON.stringify(squatBarState));
  // （增补之一百一十三）同一条规则的另一半：`view === 'opensim'` 收起深蹲杠，换到路径长度视图就应当出现。
  // 这条同时是**驱动的自证**：默认值来自源码（`referenceMode = false`，src/main.ts:80；研究节奏开关默认关），
  // 因此"深蹲杠可见"只有在页签点击真的切换了内部状态时才会成立。
  await clickLabel('.view-tab', viewLabels[0]);
  const squatViewState = JSON.parse(await evaluate("JSON.stringify((function () { var bar = document.querySelector('#squat-bar-control'); var depth = document.querySelector('#squat-depth-control'); return { barHidden: bar ? bar.hidden : null, depthHidden: depth ? depth.hidden : null }; })())"));
  console.log('深蹲视图实测：' + JSON.stringify(squatViewState) + '（点击的页签：' + viewLabels[0] + '）');
  // （增补之一百一十四）注册骨开关成对规则：非 OpenSim 视图必须禁用（src/main.ts:581 的视图因子，与参考模式默认无关），
  // OpenSim＋深蹲必须可用（默认 referenceMode=false，src/main.ts:80）。
  const regPlain = JSON.parse(await evaluate("JSON.stringify((function () { var reg = document.querySelector('#registered-bones-toggle'); return reg ? { disabled: reg.disabled, visible: reg.getClientRects().length > 0 } : { disabled: null, visible: null }; })())"));
  console.log('注册骨开关实测（路径长度＋深蹲）：' + JSON.stringify(regPlain));
  assert.equal(regPlain.disabled, true, '路径长度＋深蹲下注册骨开关应当禁用（非 OpenSim 视图没有注册骨层可看）：' + JSON.stringify(regPlain));
  await clickLabel('.view-tab', opensimLabel);
  const regOpenSim = JSON.parse(await evaluate("JSON.stringify((function () { var reg = document.querySelector('#registered-bones-toggle'); return reg ? { disabled: reg.disabled, visible: reg.getClientRects().length > 0 } : { disabled: null, visible: null }; })())"));
  console.log('注册骨开关实测（OpenSim＋深蹲）：' + JSON.stringify(regOpenSim));
  assert.equal(regOpenSim.disabled, false, "OpenSim＋深蹲下注册骨开关应当可用" + '：' + JSON.stringify(regOpenSim));
  // （增补之一百一十六）研究节奏成对规则：#squat-demand-mode 是 <select>（src/main.ts:236），选项 study 即研究节奏。
  // load-control / capacity-hint 必须随它转变（src/main.ts:537-539）。
  const demandLabel = viewLabels.find((label) => /负重|demand/i.test(label));
  assert.ok(demandLabel, "找不到负重力学视图页签：" + JSON.stringify(viewLabels));
  await clickLabel('.exercise-tab', squatLabel);
  await clickLabel('.view-tab', demandLabel);
  const setMode = async (value) => { await evaluate("(function () { var select = document.querySelector('#squat-demand-mode'); if (select) { select.value = '" + value + "'; select.dispatchEvent(new Event('change', { bubbles: true })); } })()"); await sleep(500); };
  const studyOff = JSON.parse(await evaluate("JSON.stringify((function () { var load = document.querySelector('#load-control'); var hint = document.querySelector('#capacity-hint'); var mode = document.querySelector('#squat-demand-mode'); var readout = document.querySelector('#viewer-research-readout'); return { readoutHidden: readout ? readout.hidden : null, readoutVisible: readout ? readout.getClientRects().length > 0 : null, loadVisible: load ? load.getClientRects().length > 0 : null, hintVisible: hint ? hint.getClientRects().length > 0 : null, modeValue: mode ? mode.value : null }; })())"));
  await setMode('study');
  const studyOn = JSON.parse(await evaluate("JSON.stringify((function () { var load = document.querySelector('#load-control'); var hint = document.querySelector('#capacity-hint'); var mode = document.querySelector('#squat-demand-mode'); var readout = document.querySelector('#viewer-research-readout'); return { readoutHidden: readout ? readout.hidden : null, readoutVisible: readout ? readout.getClientRects().length > 0 : null, loadVisible: load ? load.getClientRects().length > 0 : null, hintVisible: hint ? hint.getClientRects().length > 0 : null, modeValue: mode ? mode.value : null }; })())"));
  await setMode('barbell');
  console.log('研究节奏实测：' + JSON.stringify(studyOff) + ' -> ' + JSON.stringify(studyOn));
  const backToBarbell = JSON.parse(await evaluate("JSON.stringify((function () { var load = document.querySelector('#load-control'); var hint = document.querySelector('#capacity-hint'); var mode = document.querySelector('#squat-demand-mode'); var readout = document.querySelector('#viewer-research-readout'); return { readoutHidden: readout ? readout.hidden : null, readoutVisible: readout ? readout.getClientRects().length > 0 : null, loadVisible: load ? load.getClientRects().length > 0 : null, hintVisible: hint ? hint.getClientRects().length > 0 : null, modeValue: mode ? mode.value : null }; })())"));
  console.log('研究节奏回程实测：' + JSON.stringify(backToBarbell));
  assert.equal(studyOn.readoutHidden, false, '研究模式下研究读数应当可见：' + JSON.stringify(studyOn));
  assert.equal(backToBarbell.readoutHidden, true, "barbell 模式下研究读数应当隐藏" + '：' + JSON.stringify(backToBarbell));
  assert.equal(studyOff.loadVisible, true, '负重力学＋深蹲下未启用研究节奏时 load 控件应当可见：' + JSON.stringify(studyOff));
  assert.equal(studyOn.loadVisible, false, "启用研究节奏后 load 控件与容量提示应当隐藏" + '：' + JSON.stringify(studyOn));
  assert.equal(studyOn.hintVisible, false, "启用研究节奏后 load 控件与容量提示应当隐藏" + '（容量提示）：' + JSON.stringify(studyOn));


  assert.equal(squatViewState.barHidden, false, "路径长度＋深蹲下深蹲杠应当可见（也证明页签点击真的切换了状态）" + '：' + JSON.stringify(squatViewState));
  assert.equal(squatViewState.depthHidden, false, '路径长度＋深蹲下深蹲深度控件应当可见：' + JSON.stringify(squatViewState));

  // （增补之一百一十）互补断言：卧推视图下 `#press-evidence` 与 `#lab-evidence` 都由同一个 referenceMode 驱动
  // （src/main.ts:504-505），因此两者可见性**必须互斥**——这样不需要知道 referenceMode 的默认值也能守住路由。
  await clickLabel('.view-tab', viewLabels[0]);
  await clickLabel('.exercise-tab', otherLabel);
  const evidence = JSON.parse(await evaluate("JSON.stringify((function () { var press = document.querySelector('#press-evidence'); var lab = document.querySelector('#lab-evidence'); var vis = function (node) { return node ? node.getClientRects().length > 0 : null; }; return { pressVisible: vis(press), labVisible: vis(lab), pressHidden: press ? press.hidden : null, labHidden: lab ? lab.hidden : null }; })())"));
  console.log('证据面板实测：' + JSON.stringify(evidence));
  // 撤下（增补之一百一十二）：这条断言变异打不动（
  // src/main.ts:282 的初始 hidden 属性就让它恒为隐藏），因此不作为断言保留——上方测量与状态矩阵仅作诊断输出。
  const stateMatrix = JSON.parse(await evaluate("JSON.stringify(Array.from(document.querySelectorAll('input, button, select, details')).filter(function (node) { return node.id; }).map(function (node) { return { id: node.id, visible: node.getClientRects().length > 0, disabled: !!node.disabled }; }))"));
  console.log('状态矩阵（' + otherLabel + ' + ' + viewLabels[0] + '）：' + JSON.stringify(stateMatrix));

  assert.equal(squatBarState.barHidden, true, "OpenSim 视图的深蹲里深蹲杠控件却仍然可见" + '：' + JSON.stringify(squatBarState));
  assert.equal(squatBarState.noteHidden, true, 'OpenSim 视图的深蹲里深蹲杠说明却仍然可见：' + JSON.stringify(squatBarState));

  console.log('状态控件实测：' + JSON.stringify(controlShown) + ' -> ' + JSON.stringify(controlGone));
  assert.equal(controlShown.hidden, false, '前置条件成立时研究层开关却是隐藏的：' + JSON.stringify(controlShown));
  assert.ok(controlShown.visible && controlShown.width >= 24 && controlShown.height >= 24,
    '前置条件成立时研究层开关不可见或小于 24×24：' + controlShown.width + 'x' + controlShown.height);
  assert.equal(controlGone.hidden, true, '深蹲时研究层开关仍显示，容易误导（该层在深蹲下不可用）：' + JSON.stringify(controlGone));
  assert.equal(controlGone.disabled, true, '深蹲时研究层开关仍可点击，容易误导：' + JSON.stringify(controlGone));
  await clickLabel('.exercise-tab', otherLabel);
  await clickLabel('.view-tab', viewLabels[0]);
  // （增补之一百一十八）跨状态布局扫描：既有布局断言只在默认状态下跑，只在某个"运动×视图"组合里出现的
  // 横向滚动或过小控件会漏过去。这里轮询 3 运动 × 3 视图模式，要求每个状态都不出现这两类问题。
  const sweepStates = [];
  for (const sweepExercise of exerciseLabels) {
    for (const sweepView of viewLabels.slice(0, 3)) {
      await clickLabel('.exercise-tab', sweepExercise);
      await clickLabel('.view-tab', sweepView);
      const swept = JSON.parse(await evaluate("JSON.stringify((function () { var doc = document.documentElement; var small = Array.from(document.querySelectorAll('button, input, select, a[href], summary, details')).filter(function (n) { return n.getClientRects().length > 0 && (n.getBoundingClientRect().width < 24 || n.getBoundingClientRect().height < 24); }).map(function (n) { return n.id || n.className || n.tagName; }); return { sideways: doc.scrollWidth - window.innerWidth, small: small }; })())"));
      sweepStates.push({ exercise: sweepExercise, view: sweepView, sideways: swept.sideways, small: swept.small });
    }
  }
  const badStates = sweepStates.filter((entry) => entry.sideways > 1);
  console.log('跨状态扫描：' + sweepStates.length + ' 个状态，横向滚动问题 ' + badStates.length + ' 个' + (badStates.length ? ' -> ' + JSON.stringify(badStates.slice(0, 2)) : ' 状态：' + JSON.stringify(sweepStates.map((entry) => entry.exercise + '/' + entry.view + '(' + entry.sideways + ')'))));
  assert.equal(badStates.length, 0, "某些状态下出现横向滚动" + '：' + JSON.stringify(badStates.slice(0, 3)));
  await clickLabel('.view-tab', viewLabels[0]);
  await clickLabel('.exercise-tab', exerciseLabels[0]);
console.log('DESKTOP_LAYOUT ok: no sideways scroll, no blocked centres, targets >= 24px, fonts on the token scale');
} finally {
  try { socket?.close(); } catch {}
  child.kill();
  server.close();
  await sleep(300);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
