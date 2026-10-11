// Measures how long the built page takes to become usable and how large the shipped payload is.
//
// The roadmap lists "startup speed in a gym" as a product-acceptance item and nothing measured it.
// This script is the measurement half of that: it serves dist/, opens the production build in a
// headless Chromium browser over the DevTools Protocol, records milestones for a cold first load and
// for a reload served by the service worker, lists every byte that was transferred, and writes the
// result to docs/data/web_startup_budget.json. scripts/check-web-startup-budget.mjs then pins the
// machine-independent half (the payload on disk) and keeps the numbers from silently regressing.
//
// The timings are desktop, headless and therefore a proxy: they say nothing about a phone in a gym.
// A browser is required. Set ATLAS_BROWSER to an executable path when auto-detection fails.
import { createServer } from 'node:http';
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync }
  from 'node:fs';
import { spawn } from 'node:child_process';
import { cpus, tmpdir } from 'node:os';
import { extname, join, normalize, relative } from 'node:path';

const ROOT = process.cwd();
const DIST = join(ROOT, 'dist');
const OUT = join(ROOT, 'docs', 'data', 'web_startup_budget.json');
const CANDIDATES = [
  process.env.ATLAS_BROWSER,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  '/usr/bin/microsoft-edge', '/usr/bin/google-chrome', '/usr/bin/chromium',
].filter(Boolean);

if (!existsSync(join(DIST, 'index.html'))) {
  console.error('dist/index.html is missing. Run `npm run build` before measuring.');
  process.exit(1);
}
const browser = CANDIDATES.find(path => existsSync(path));
if (!browser) {
  console.log('SKIPPED: no Chromium-based browser found. Set ATLAS_BROWSER to an executable path.');
  process.exit(0);
}

// Payload on disk. This half is machine-independent, so the check asserts it exactly.
const payloadFiles = [];
const walk = (directory) => {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) walk(path);
    else if (entry.isFile()) {
      payloadFiles.push({ path: relative(DIST, path).replace(/\\/g, '/'), bytes: statSync(path).size });
    }
  }
};
walk(DIST);
payloadFiles.sort((a, b) => b.bytes - a.bytes);
const payloadTotal = payloadFiles.reduce((sum, file) => sum + file.bytes, 0);

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json',
  '.glb': 'model/gltf-binary', '.png': 'image/png', '.webmanifest': 'application/manifest+json',
  '.txt': 'text/plain; charset=utf-8', '.svg': 'image/svg+xml' };
const served = new Map();
const server = createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  const file = join(DIST, normalize(pathname === '/' ? 'index.html' : pathname).replace(/^(\.\.[/\\])+/, ''));
  try {
    if (!statSync(file).isFile()) throw new Error('not a file');
    const body = readFileSync(file);
    served.set(pathname === '/' ? '/index.html' : pathname, body.length);
    response.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream' });
    response.end(body);
  } catch {
    response.writeHead(404).end('not found');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;

// Marks are read in the page and are all relative to performance.timeOrigin, i.e. to the navigation
// that started them, so a reload restarts the clock exactly like a cold load.
const COLLECTOR = `
  window.__atlasStartup = { marks: {}, observerErrors: [] };
  const record = (name) => {
    if (!(name in window.__atlasStartup.marks)) window.__atlasStartup.marks[name] = performance.now();
  };
  try {
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) record('paint:' + entry.name);
    }).observe({ type: 'paint', buffered: true });
  } catch (error) { window.__atlasStartup.observerErrors.push(String(error)); }
  document.addEventListener('DOMContentLoaded', () => record('domContentLoaded'));
  window.addEventListener('load', () => record('load'));
  const watch = () => {
    const canvas = document.querySelector('canvas');
    if (canvas && canvas.width > 0) record('canvasSized');
    const tag = document.querySelector('#asset-tag');
    if (tag && !(tag.textContent || '').includes('加载中')) record('modelsReady');
    const offline = document.querySelector('#offline-status');
    if (offline && (offline.textContent || '').includes('资源缓存已完成')) record('offlineBundleReady');
    requestAnimationFrame(watch);
  };
  requestAnimationFrame(watch);
`;

const debugPort = 9600 + (process.pid % 300);
const profile = mkdtempSync(join(tmpdir(), 'atlas-startup-'));
const child = spawn(browser, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--enable-unsafe-swiftshader', `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

let socket;
let result;
try {
  const target = await (async () => {
    for (let attempt = 0; attempt < 40; attempt++) {
      try {
        const list = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
        const page = list.find(item => item.type === 'page');
        if (page) return page.webSocketDebuggerUrl;
      } catch {}
      await sleep(500);
    }
    throw new Error('the browser never exposed a page over the DevTools Protocol');
  })();

  socket = new WebSocket(target);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let nextId = 1;
  const pending = new Map();
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
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
      throw new Error(`page evaluation failed: ${reply.result.exceptionDetails.text} ${expression}`);
    }
    return reply.result?.result?.value;
  };
  await send('Runtime.enable');
  await send('Page.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', { source: COLLECTOR });

  const version = (await send('Browser.getVersion')).result ?? {};

  const measure = async (label) => {
    const deadline = Date.now() + 60_000;
    let marks = {};
    while (Date.now() < deadline) {
      await sleep(250);
      const snapshot = await evaluate(`(() => {
        const state = window.__atlasStartup;
        if (!state) return null;
        const offline = document.querySelector('#offline-status');
        return {
          marks: { ...state.marks },
          offline: offline ? (offline.textContent || '') : '',
          controlled: !!navigator.serviceWorker?.controller,
        };
      })()`);
      if (!snapshot) continue;
      marks = snapshot.marks;
      if (snapshot.offline.includes('资源缓存已完成')) {
        // Give the last paint a moment to land, then take the final reading.
        await sleep(500);
        const final = await evaluate(`(() => {
          const state = window.__atlasStartup;
          return {
            marks: { ...state.marks },
            controlled: !!navigator.serviceWorker?.controller,
            resources: performance.getEntriesByType('resource').map(entry => ({
              startTime: entry.startTime,
              path: entry.name.replace(${JSON.stringify(origin)}, ''),
              transferSize: entry.transferSize ?? 0,
              durationMs: Math.round(entry.duration),
            })),
            observerErrors: state.observerErrors,
          };
        })()`);
        const transferred = final.resources.reduce((sum, item) => sum + item.transferSize, 0);
        return {
          label,
          marks: final.marks,
          assetsReadyMs: Math.round(final.marks.modelsReady ?? -1),
          offlineBundleReadyMs: Math.round(final.marks.offlineBundleReady ?? -1),
          firstPaintMs: Math.round(final.marks['paint:first-paint'] ?? -1),
          firstContentfulPaintMs: Math.round(final.marks['paint:first-contentful-paint'] ?? -1),
          domContentLoadedMs: Math.round(final.marks.domContentLoaded ?? -1),
          loadEventMs: Math.round(final.marks.load ?? -1),
          canvasSizedMs: Math.round(final.marks.canvasSized ?? -1),
          serviceWorkerControlled: final.controlled,
          requestedResources: final.resources.length,
          transferredBytes: transferred,
          resources: final.resources.filter(item => item.transferSize > 0)
            .sort((a, b) => b.transferSize - a.transferSize).slice(0, 12),
          observerErrors: final.observerErrors,
        };
      }
    }
    return { label, marks, timedOut: true };
  };

  await send('Page.navigate', { url: `${origin}/` });
  const cold = await measure('cold');
  if (cold.timedOut) throw new Error('the cold load never reported a completed offline bundle');
  await send('Page.reload', { ignoreCache: false });
  const warm = await measure('warm');
  if (warm.timedOut) throw new Error('the reload never reported a completed offline bundle');

  result = {
    status: 'desktop_headless_measurement_not_phone_acceptance',
    measuredAt: new Date().toISOString(),
    measuredOn: '本轮开发机（Windows，无头 Chromium，单次采样）',
    command: 'node scripts/measure-web-startup.mjs',
    environment: {
      browser: browser.split(/[\\/]/).pop(),
      product: version.product,
      revision: version.revision,
      platform: process.platform,
      headless: true,
      cpuCount: cpus().length,
      deviceScaleFactor: 1,
      network: '同机 localhost，无网络延迟',
    },
    payload: {
      totalBytes: payloadTotal,
      fileCount: payloadFiles.length,
      largest: payloadFiles.slice(0, 12),
      inlineIndexBytes: payloadFiles.find(file => file.path === 'index.html')?.bytes ?? 0,
      serviceWorkerBytes: payloadFiles.find(file => file.path === 'sw.js')?.bytes ?? 0,
    },
    budgets: {
      inlineIndexBytes: 1_600_000,
      payloadTotalBytes: 40_000_000,
      coldFirstContentfulPaintMs: 3_000,
      coldAssetsReadyMs: 30_000,
      warmAssetsReadyMs: 10_000,
    },
    runs: [cold, warm],
    limitations: [
      '这是**桌面无头浏览器**在同机 localhost 上的单次采样，不是手机、不是健身房现场，也不是多次统计；它只能排除“明显变慢”这类回归，不能当作启动速度验收。',
      '计时包含本机文件读取与无头浏览器启动后的首次渲染，绝对值受机器负载影响；比较不同版本时应在同一台机器、同一次运行里对照。',
      'payload（磁盘上的发布包体积）与机器无关，这部分由 npm run check-web-startup-budget 逐字节固定。',
      '“modelsReady”以界面上的模型标签不再显示“加载中”为准，它表示骨骼／肌肉网格已经挂上，不表示首帧已经绘制完成。',
      '冷启动的 transferredBytes 由同机 localhost 提供，不含网络往返、TLS、CDN 或移动网络开销；真机首装体积还要加上 APK 自身。',
      '只测量默认深蹲视图；切到卧推、实力举或研究叠加层会另外加载参考数据，这里没有覆盖。',
    ],
  };
} finally {
  try { socket?.close(); } catch {}
  child.kill();
  await new Promise(resolve => { server.close(resolve); setTimeout(resolve, 1200); });
  if (process.platform === 'win32') {
    spawn('taskkill', ['/F', '/T', '/PID', String(child.pid)], { stdio: 'ignore' });
    await sleep(400);
  }
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}

writeFileSync(OUT, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
const [cold, warm] = result.runs;
console.log(`WEB_STARTUP_BUDGET ${JSON.stringify({
  payloadBytes: result.payload.totalBytes,
  files: result.payload.fileCount,
  inlineIndexBytes: result.payload.inlineIndexBytes,
  cold: {
    firstPaintMs: cold.firstPaintMs, firstContentfulPaintMs: cold.firstContentfulPaintMs,
    canvasSizedMs: cold.canvasSizedMs, assetsReadyMs: cold.assetsReadyMs,
    offlineBundleReadyMs: cold.offlineBundleReadyMs, transferredBytes: cold.transferredBytes,
    serviceWorkerControlled: cold.serviceWorkerControlled,
  },
  warm: {
    firstPaintMs: warm.firstPaintMs, firstContentfulPaintMs: warm.firstContentfulPaintMs,
    canvasSizedMs: warm.canvasSizedMs, assetsReadyMs: warm.assetsReadyMs,
    offlineBundleReadyMs: warm.offlineBundleReadyMs, transferredBytes: warm.transferredBytes,
    serviceWorkerControlled: warm.serviceWorkerControlled,
  },
  served: served.size,
})}`);
