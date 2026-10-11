// Verifies the stage-3 acceptance line “无网络可打开个人模型与已下载动作” in a real browser.
//
// The repository already proves the offline bundle in two weaker ways: check:offline-cache runs
// public/sw.js inside a sandbox with fake caches, and the desktop pass was written up by hand. Neither
// shows that the real service worker, the real cache and the real page survive a real offline reload.
// This check does: it loads the production build until the bundle reports complete, then makes the
// offline claim enforceable — the browser goes offline through the DevTools Protocol *and* the local
// server starts refusing (and recording) every request, because a service-worker fetch can bypass the
// browser's offline emulation. After that it reloads and walks the views a user would — the default
// model, all three exercises' reference data, and the static anatomy layer — failing if anything comes
// up empty, if the app falls back to the refusing server, if the status stops saying the bundle is
// usable offline, or if the page raises an error.
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
// The server is the enforcement point for the offline claim, not just the DevTools network switch: a
// service-worker `fetch()` can bypass the browser's offline emulation, so once the bundle reports
// itself complete this server starts refusing (and recording) every request. Anything the app still
// needs after that has to come from the worker's cache, or the check fails.
let refusing = false;
const refusedHits = [];
const server = createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  if (refusing) {
    refusedHits.push(pathname);
    response.writeHead(503, { 'Content-Type': 'text/plain' }).end('offline');
    return;
  }
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

const debugPort = 9800 + (process.pid % 150);
const profile = mkdtempSync(join(tmpdir(), 'atlas-offline-'));
const child = spawn(browser, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--enable-unsafe-swiftshader', `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${profile}`, `${origin}/`], { stdio: 'ignore' });
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

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
    if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
      pageErrors.push(message.params.args.map(argument => argument.value ?? argument.description).join(' '));
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
  const waitFor = async (expression, description, attempts = 90) => {
    for (let attempt = 0; attempt < attempts; attempt++) {
      if (await evaluate(expression)) return;
      await sleep(500);
    }
    throw new Error(`timed out waiting for ${description}`);
  };
  const setOffline = (offline) => send('Network.emulateNetworkConditions',
    { offline, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });

  await send('Runtime.enable');
  await send('Network.enable');

  const verified = [];
  const check = async (name, fn) => {
    try {
      await fn();
    } catch (error) {
      throw new Error(`offline acceptance failed — ${name}: ${error.message}`);
    }
    verified.push(name);
  };

  await check('the offline bundle reports itself complete while online', async () => {
    await waitFor(`!!document.querySelector('canvas')`, 'the canvas to exist');
    await waitFor(`document.querySelector('#offline-status').textContent.includes('资源缓存已完成')`,
      'the verified offline bundle', 120);
    const online = await evaluate(`navigator.onLine`);
    assert.equal(online, true, 'the browser was already offline before the test switched it');
    const status = await evaluate(`document.querySelector('#offline-status').textContent`);
    assert(!status.includes('离线 ·'), `the online badge already says it is offline: ${status}`);
    // From here on the server refuses everything, so the rest of the check can only pass on the
    // worker's cache. Chromium keeps probing for the site favicon, which is not part of the bundle.
    refusedHits.length = 0;
    refusing = true;
  });

  await check('reloading with the network switched off still opens the app', async () => {
    await setOffline(true);
    await sleep(500);
    await evaluate(`location.reload()`);
    await waitFor(`!!document.querySelector('canvas') && !!document.querySelector('#asset-tag')`,
      'the page to boot from the cache');
    const firstLoadErrors = pageErrors.slice();
    assert.deepEqual(firstLoadErrors, [], `the offline reload raised: ${firstLoadErrors.join(' | ')}`);
    await waitFor(`document.querySelector('#offline-status').textContent.includes('资源缓存已完成')`,
      'the offline bundle check to answer again');
    const state = await evaluate(`({
      online: navigator.onLine,
      status: document.querySelector('#offline-status').textContent,
      controlled: !!navigator.serviceWorker.controller,
    })`);
    assert.equal(state.online, false, 'the browser did not report the network as off');
    assert.equal(state.controlled, true,
      'the reload was not controlled by the service worker, so nothing was served from cache');
    assert(state.status.includes('离线'), `the badge does not say the device is offline: ${state.status}`);
    assert(state.status.includes('资源缓存已完成'),
      `the badge no longer says the bundle is usable: ${state.status}`);
  });

  await check('the default model renders offline', async () => {
    await waitFor(`!/加载中/.test(document.querySelector('#asset-tag').textContent)`,
      'the default model tag to leave the loading state');
    const tag = await evaluate(`document.querySelector('#asset-tag').textContent`);
    assert(!tag.includes('失败'), `the default model failed offline: ${tag}`);
    assert(tag.includes('Blender'), `the default view did not load its model offline: ${tag}`);
    const canvas = await evaluate(`(() => { const c = document.querySelector('canvas');
      return { width: c.width, height: c.height }; })()`);
    assert(canvas.width > 0 && canvas.height > 0, `the canvas has no size offline: ${JSON.stringify(canvas)}`);
  });

  await check('all three exercises load their reference data offline', async () => {
    // Each exercise has its own loaded-state wording, and that wording only appears when the
    // reference data actually arrived, so this is what proves the bundle covers all three.
    const loadedTag = {
      squat: tag => tag.includes('OpenSim') || tag.includes('研究叠加'),
      bench: tag => tag.includes('胸廓—肩胛模型') || tag.includes('研究网格'),
      press: tag => tag.includes('胸廓—肩胛模型') || tag.includes('研究网格'),
    };
    for (const exercise of ['bench', 'press', 'squat']) {
      await evaluate(`document.querySelector('[data-exercise="${exercise}"]').click()`);
      await evaluate(`document.querySelector('[data-view="opensim"]').click()`);
      await sleep(600);
      // The tag shows a loading state until the reference data arrives, and the failure wording if it
      // does not, so waiting for neither is the honest test.
      await waitFor(`!/加载中|失败/.test(document.querySelector('#asset-tag').textContent)`,
        `the ${exercise} reference data to load from the cache`, 90);
      const tag = await evaluate(`document.querySelector('#asset-tag').textContent`);
      assert(!tag.includes('失败'), `the ${exercise} reference data failed offline: ${tag}`);
      assert(loadedTag[exercise](tag),
        `the ${exercise} view did not reach its loaded state offline: ${tag}`);
      // The explanation is checked for the heading of the view that should be showing, not merely for
      // being long: this is what proves the right research view rendered from the cache.
      const heading = { squat: 'OpenSim 深蹲参考路径', bench: '胸廓—肩胛模型卧推路径研究',
        press: '胸廓—肩胛模型上举路径研究' }[exercise];
      const rendered = await evaluate(`(() => {
        const node = document.querySelector('#view-explanation');
        return node ? (node.textContent ?? '').replace(/\\s+/g, ' ').trim() : '';
      })()`);
      assert(rendered.includes(heading),
        `the ${exercise} view explanation does not describe its research model offline: ` +
        `${rendered.slice(0, 80)}`);
    }
  });

  await check('the anatomy research layer loads offline', async () => {
    // The 10.7 MB Z-Anatomy model is the largest cached asset, so it is the strongest offline claim.
    await evaluate(`document.querySelector('[data-exercise="squat"]').click()`);
    await evaluate(`document.querySelector('[data-view="opensim"]').click()`);
    const research = `document.querySelector('#registered-bones-toggle')`;
    await waitFor(`!!${research} && !${research}.disabled`, 'the research toggle to be enabled');
    await evaluate(`if (!${research}.checked) ${research}.click()`);
    // Scoped to the two elements that report it, not the whole page: the same wording appears in the
    // static page chrome, so a page-wide search could pass without the layer having loaded.
    await waitFor(`document.querySelector('#asset-tag').textContent.includes('研究叠加') && document.querySelector('#asset-tag').textContent.includes('八块肌肉')`,
      'the research layer to report a completed load from the cache', 120);
    const reported = await evaluate(`({
      status: document.querySelector('#model-status').textContent,
      explanation: document.querySelector('#view-explanation').textContent,
    })`);
    assert(!reported.status.includes('加载失败') && !reported.explanation.includes('解剖网格加载失败'),
      `the research layer reported a load failure while offline: ${reported.status}`);
  });

  await check('the three reference datasets are really in the offline cache', async () => {
    // The views above say they loaded; this reads the cache the page actually serves from, so a stale
    // or bundled copy cannot satisfy the walk above without the cache being complete.
    const cached = await evaluate(`(async () => {
      const paths = ['/data/squat_opensim_reference.json', '/data/press_tsm_reference.json',
        '/data/bench_tsm_reference.json'];
      const out = {};
      for (const path of paths) {
        const hit = await caches.match(path);
        out[path] = hit ? (await hit.json()).schemaVersion ?? -1 : 0;
      }
      return out;
    })()`);
    for (const [path, schema] of Object.entries(cached)) {
      assert(schema > 0, `${path} is not in the service-worker cache (saw ${schema})`);
    }
  });

  await check('no bundled asset was ever fetched from the server again', async () => {
    await evaluate(`document.querySelector('[data-view="demand"]').click()`);
    await sleep(2500);
    // Two kinds of request legitimately still reach the network while the app runs from cache: the
    // browser's service-worker update check for /sw.js, and the worker's own network-first navigation
    // attempt for /, which falls back to the cache. The site favicon is not in the bundle either.
    // Everything the app itself needs — data, models, icons, manifests — has to come from the cache.
    const expected = new Set(['/', '/sw.js', '/favicon.ico']);
    const assetHits = refusedHits.filter(path => !expected.has(path));
    assert.deepEqual(assetHits, [],
      `the app asked the refusing server for ${assetHits.join(', ')} after its bundle was verified, ` +
      `so the cache did not cover it`);
    const resources = await evaluate(`performance.getEntriesByType('resource')
      .filter(entry => (entry.transferSize ?? 0) > 0).length`);
    assert.equal(resources, 0,
      `${resources} resource(s) reported a non-zero transfer size while offline`);
  });

  await check('the badge returns to the plain wording once the network is back', async () => {
    refusing = false;
    await setOffline(false);
    await sleep(1500);
    await waitFor(`document.querySelector('#offline-status').textContent.includes('资源缓存已完成')`,
      'the badge to recover');
    const status = await evaluate(`document.querySelector('#offline-status').textContent`);
    assert(!status.includes('离线 ·'), `the badge still says it is offline: ${status}`);
  });

  await check('the page raised no uncaught error', () => {
    assert.deepEqual(pageErrors, [], `the page reported errors: ${pageErrors.join(' | ')}`);
  });

  console.log(`${verified.length} offline behaviours verified in ${browser.split(/[\\/]/).pop()} ` +
    `against the production build: the bundle is verified complete, the server then refuses (and ` +
    `records) every request, the page still reloads and reaches the default model, all three ` +
    `exercises' reference data and the 10.7 MB anatomy layer from the worker cache, no bundled asset ` +
    `was requested from the server again (${refusedHits.length} recorded hit(s), all of them the ` +
    `worker's network-first navigation, the browser's /sw.js update check or the favicon), and the ` +
    `badge goes back to “资源缓存已完成” when the network returns.`);
} finally {
  try { socket?.close(); } catch {}
  child.kill();
  await new Promise(resolve => { server.close(resolve); setTimeout(resolve, 1500); });
  if (process.platform === 'win32') {
    spawn('taskkill', ['/F', '/T', '/PID', String(child.pid)], { stdio: 'ignore' });
    await sleep(500);
  }
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
