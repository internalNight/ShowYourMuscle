// Pins the startup and payload budgets measured by scripts/measure-web-startup.mjs.
//
// The roadmap lists "startup speed in a gym" as a product-acceptance item. The measurement script
// records where the time goes and how large the shipped payload is; this check keeps the
// machine-independent half honest — the payload on disk must still match the recorded one byte for
// byte — and keeps the machine-dependent half inside declared ceilings instead of letting it drift.
// It also pins the two structural properties the measurement revealed: the 10.7 MB anatomy model is
// not on the first-paint path, and a reload served by the service worker must not transfer anything.
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const budget = JSON.parse(readFileSync('docs/data/web_startup_budget.json', 'utf8'));
const doc = readFileSync('docs/网页启动与体积预算.md', 'utf8');
const serviceWorker = readFileSync('public/sw.js', 'utf8');
const main = readFileSync('src/main.ts', 'utf8');

assert.equal(budget.status, 'desktop_headless_measurement_not_phone_acceptance');
assert(budget.limitations.length >= 5, 'the measurement lost its limitations');
assert(budget.limitations.some(text => text.includes('桌面')),
  'the measurement must still say the timings are desktop, not a phone');
assert(budget.limitations.some(text => text.includes('真机') || text.includes('手机')),
  'the measurement must still name the missing device acceptance');
assert(budget.limitations.some(text => text.includes('机器无关') || text.includes('逐字节')),
  'the measurement must still separate the machine-independent payload from the timings');

// The payload recorded must be the payload on disk right now.
const files = [];
const walk = (directory) => {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) walk(path);
    else if (entry.isFile()) {
      files.push({ path: relative('dist', path).replace(/\\/g, '/'), bytes: statSync(path).size });
    }
  }
};
walk('dist');
files.sort((a, b) => b.bytes - a.bytes);
const total = files.reduce((sum, file) => sum + file.bytes, 0);
assert.equal(files.length, budget.payload.fileCount,
  `dist/ now holds ${files.length} files, the measurement recorded ${budget.payload.fileCount}`);
assert.equal(total, budget.payload.totalBytes,
  `dist/ now totals ${total} bytes, the measurement recorded ${budget.payload.totalBytes}`);
assert.deepEqual(files.slice(0, 12), budget.payload.largest,
  'the largest shipped files changed; re-run node scripts/measure-web-startup.mjs');
const inline = files.find(file => file.path === 'index.html');
assert.equal(inline.bytes, budget.payload.inlineIndexBytes, 'the recorded inline page size is stale');
assert.equal(budget.payload.inlineIndexBytes, budget.payload.largest
  .find(file => file.path === 'index.html')?.bytes ?? -1,
  'the inline page size disagrees with the payload table');
assert.equal(budget.payload.serviceWorkerBytes,
  files.find(file => file.path === 'sw.js')?.bytes ?? -1, 'the recorded sw.js size is stale');

// Declared ceilings. These are deliberately loose: they exist to catch a regression, not to certify
// a phone. Re-measure and lower them when the payload actually shrinks.
assert(budget.budgets.inlineIndexBytes <= 2_000_000, 'the inline page budget is not a budget');
assert(budget.payload.inlineIndexBytes <= budget.budgets.inlineIndexBytes,
  `the inline page (${budget.payload.inlineIndexBytes} bytes) exceeds its budget`);
assert(budget.payload.totalBytes <= budget.budgets.payloadTotalBytes,
  `the payload (${budget.payload.totalBytes} bytes) exceeds its budget`);

const [cold, warm] = budget.runs;
assert.equal(cold.label, 'cold');
assert.equal(warm.label, 'warm');
for (const run of [cold, warm]) {
  for (const field of ['firstContentfulPaintMs', 'canvasSizedMs', 'assetsReadyMs',
    'offlineBundleReadyMs', 'domContentLoadedMs', 'loadEventMs']) {
    assert(Number.isFinite(run[field]) && run[field] >= 0, `${run.label} has no usable ${field}`);
  }
  assert.equal(run.serviceWorkerControlled, true,
    `the ${run.label} run was not controlled by the service worker, so it does not test the offline path`);
  assert(run.firstContentfulPaintMs <= budget.budgets.coldFirstContentfulPaintMs,
    `the ${run.label} first contentful paint (${run.firstContentfulPaintMs} ms) exceeds its budget`);
  assert(run.assetsReadyMs <= budget.budgets.coldAssetsReadyMs,
    `the ${run.label} model readiness (${run.assetsReadyMs} ms) exceeds its budget`);
}
assert(warm.assetsReadyMs <= budget.budgets.warmAssetsReadyMs,
  `the warm reload (${warm.assetsReadyMs} ms) exceeds its budget`);
// A reload served from the cache must not go back to the network for anything.
assert.equal(warm.transferredBytes, 0,
  `the warm reload transferred ${warm.transferredBytes} bytes instead of serving from the cache`);
// The multi-megabyte anatomy model is a research layer, so it must not be needed for the first view.
// The rule is about the FIRST VIEW, not about everything the page ever fetches: a research layer may be
// prefetched once the first view is ready. Resources recorded before that boundary must not include it.
const firstViewBoundaryMs = cold.assetsReadyMs;
const coldHasStartTimes = cold.resources.every(item => Number.isFinite(item.startTime));
const beforeBoundary = coldHasStartTimes
  ? cold.resources.filter(item => item.startTime <= firstViewBoundaryMs)
  : cold.resources;
const prefetchedResearchLayer = cold.resources.some(item => item.path.includes('z_anatomy_reference.glb'));
console.log('first-view resources: ' + beforeBoundary.length + ' of ' + cold.resources.length
  + ' (boundary ' + firstViewBoundaryMs + ' ms), research layer prefetched later: ' + prefetchedResearchLayer);
assert.equal(beforeBoundary.some(item => item.path.includes('z_anatomy_reference.glb')), false,
  'the large anatomy model is needed for the first view (it appears among the first-view resources)');
assert.equal(beforeBoundary.some(item => item.path === '/models/prototype_parts.glb'), true,
  'the first view no longer loads the light prototype model');

assert.equal(warm.resources.length, 0,
  'the warm reload reported transferred resources even though it transferred nothing');

// The offline badge is only allowed to claim completion when the worker verified the cached list.
assert(serviceWorker.includes('PRECACHE_MANIFEST'),
  'the service worker no longer records a precache manifest');
assert(serviceWorker.includes('complete:'),
  'the service worker no longer reports whether the bundle is complete');
assert(!/postMessage\(\{ cache: CACHE \}\)/.test(serviceWorker),
  'the service worker is answering with the cache name alone again, which cannot be verified');
assert(main.includes('离线包未就绪 · 缺'),
  'the page no longer distinguishes an incomplete offline bundle from a complete one');
assert(main.includes("bundleState = '资源缓存已完成'"),
  'the page no longer reports a completed offline bundle');
// The badge reports the bundle state and the network state separately; keep both halves.
assert(main.includes('离线 · '),
  'the page no longer says the device is offline while still reporting the bundle state');
assert(main.includes("window.addEventListener('offline', renderOfflineStatus)"),
  'the page no longer reacts when the device loses its network');
assert(main.includes("window.addEventListener('online', renderOfflineStatus)"),
  'the page no longer reacts when the network comes back');

// The page that explains the numbers must keep the measurement, the budget and the caveats together.
for (const phrase of ['measure-web-startup.mjs', 'check-web-startup-budget', 'z_anatomy_reference.glb',
  '真机', '不']) {
  assert(doc.includes(phrase), `the startup page no longer states “${phrase}”`);
}

console.log(`Startup budget verified: payload ${budget.payload.totalBytes} bytes in ` +
  `${budget.payload.fileCount} files (largest ${budget.payload.largest[0].path}), ` +
  `cold paint ${cold.firstContentfulPaintMs} ms / models ${cold.assetsReadyMs} ms / ` +
  `offline bundle ${cold.offlineBundleReadyMs} ms transferring ${cold.transferredBytes} bytes, ` +
  `warm reload ${warm.assetsReadyMs} ms transferring ${warm.transferredBytes} bytes — ` +
  `desktop headless proxy, no phone acceptance.`);
