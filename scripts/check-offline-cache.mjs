import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { runInNewContext } from 'node:vm';

// The install handler caches one URL at a time on purpose. It used to call cache.addAll, and when the browser
// refused a single 10.7 MB research model the whole precache rejected: the registration was discarded,
// navigator.serviceWorker.ready never resolved and the offline badge stayed at "离线包准备中" forever, which
// took check:ui-offline, measure:web-startup and check:web-startup-budget down with it.
{
  const worker = await readFile(resolve('dist/sw.js'), 'utf8');
  assert(/const outcomes = await Promise\.all\(/.test(worker),
    'the install handler must cache one URL at a time and record each outcome');
  assert(!/cache\.addAll\(/.test(worker),
    'the install handler must not call cache.addAll: one refused asset would reject the whole offline bundle');
  console.log('OFFLINE_CACHE resilience: install caches per URL, records failures, never uses cache.addAll');
}

const origin = 'http://127.0.0.1:4175';
const handlers = new Map();
const stores = new Map();
let networkMode = 'online';

function keyOf(request) {
  return new URL(typeof request === 'string' ? request : request.url, origin).href;
}

async function localFetch(request) {
  if (networkMode === 'reject') throw new Error('network disconnected');
  if (networkMode === 'bad-gateway') return new Response('bad gateway', { status: 502 });
  const pathname = new URL(keyOf(request)).pathname;
  const file = resolve('dist', pathname === '/' ? 'index.html' : `.${pathname}`);
  return new Response(await readFile(file), { status: 200 });
}

const caches = {
  async open(name) {
    if (!stores.has(name)) stores.set(name, new Map());
    const store = stores.get(name);
    return {
      async put(request, response) { store.set(keyOf(request), response.clone()); },
      async addAll(requests) {
        for (const request of requests) {
          const response = await localFetch(request);
          assert(response.ok);
          store.set(keyOf(request), response.clone());
        }
      },
      async add(request) {
        const response = await localFetch(request);
        assert(response.ok);
        store.set(keyOf(request), response.clone());
      },
      async match(request) {
        const response = store.get(keyOf(request));
        return response ? response.clone() : undefined;
      },
      async keys() { return [...store.keys()]; },
    };
  },
  async match(request) {
    for (const store of stores.values()) {
      const response = store.get(keyOf(request));
      if (response) return response.clone();
    }
  },
  async keys() { return [...stores.keys()]; },
  async delete(name) { return stores.delete(name); },
};

const self = {
  location: { origin },
  addEventListener(type, handler) { handlers.set(type, handler); },
  skipWaiting() {},
  clients: { claim: async () => {} },
};
runInNewContext(await readFile('public/sw.js', 'utf8'),
  { self, caches, fetch: localFetch, URL, Promise, Response });

async function dispatchWaitable(type) {
  let task;
  handlers.get(type)({ waitUntil(value) { task = value; } });
  await task;
}
async function dispatchFetch(request) {
  let task;
  handlers.get('fetch')({ request, respondWith(value) { task = value; } });
  return await task;
}
// Mirrors how the page asks the worker whether the offline bundle is complete.
async function askCacheStatus() {
  const replies = [];
  let task;
  handlers.get('message')({
    data: { type: 'cache-status' },
    ports: [{ postMessage: value => replies.push(value) }],
    waitUntil(value) { task = value; },
  });
  await task;
  assert.equal(replies.length, 1, 'the worker did not answer the cache-status question');
  return replies[0];
}

await dispatchWaitable('install');
await dispatchWaitable('activate');
const names = await caches.keys();
assert.equal(names.length, 1);
const html = await (await caches.match('/')).text();
assert(html.includes(names[0]), `The app expects a different service-worker cache than ${names[0]}`);
const script = html.match(/<script type="module" data-bundle="inline">([\s\S]*?)<\/script>/);
const style = html.match(/<style data-bundle="inline">([\s\S]*?)<\/style>/);
assert(script && script[1].length > 100_000, 'Inline app script missing');
assert(style && style[1].length > 1_000, 'Inline stylesheet missing');
assert(script[1].includes('实验对照') && script[1].includes('Scherpereel') &&
  script[1].includes('预测验收') && script[1].includes('双腿模型验收'),
  'Offline build is missing the attributed squat lab-reference and held-out benchmark');
assert(!html.includes('src="/assets/'), 'The offline page still requires an external script');
// The badge in the header says “资源缓存已完成” only when the worker confirms a complete bundle, so
// the worker has to answer that question honestly in both directions.
const complete = await askCacheStatus();
assert.equal(complete.cache, names[0]);
assert.equal(complete.complete, true, 'the worker did not confirm a complete bundle after install');
// The reply crosses a sandbox boundary, so compare a host-side copy rather than the worker's array.
assert.deepEqual([...complete.missing], [],
  `the worker reported missing assets: ${[...complete.missing].join(', ')}`);
assert(complete.entries >= 10, `the cache holds only ${complete.entries} entries`);
assert(complete.expected >= complete.entries - 1,
  `the manifest lists ${complete.expected} urls but the cache holds ${complete.entries} entries`);
// Simulate an interrupted precache: drop one asset and the worker must say so rather than claim the
// bundle is ready.
const damaged = '/models/z_anatomy_reference.glb';
stores.get(names[0]).delete(`${origin}${damaged}`);
const afterDamage = await askCacheStatus();
assert.equal(afterDamage.complete, false,
  'the worker still claimed a complete offline bundle after an asset went missing');
assert(afterDamage.missing.includes(damaged),
  `the worker did not name the missing asset: ${JSON.stringify(afterDamage.missing)}`);
stores.get(names[0]).delete(`${origin}/__precache-manifest.json`);
const withoutManifest = await askCacheStatus();
assert.equal(withoutManifest.complete, false,
  'the worker claimed completion without the precache manifest');
assert(withoutManifest.missing.includes('/__precache-manifest.json'),
  'the worker did not report the missing precache manifest');
// Restore the two entries so the rest of the check still exercises a complete bundle.
await dispatchWaitable('install');
networkMode = 'reject';
const navigation = await dispatchFetch({ url: `${origin}/`, method: 'GET', mode: 'navigate' });
assert.equal(await navigation.text(), html);
networkMode = 'bad-gateway';
const gatewayFailure = await dispatchFetch({ url: `${origin}/`, method: 'GET', mode: 'navigate' });
assert.equal(await gatewayFailure.text(), html);
for (const path of ['/data/squat_opensim_reference.json', '/data/press_tsm_reference.json',
  '/data/bench_tsm_reference.json',
  '/models/prototype_parts.glb', '/models/z_anatomy_reference.glb']) {
  const response = await dispatchFetch({ url: `${origin}${path}`, method: 'GET', mode: 'same-origin' });
  assert(response.ok, `${path} was not cached`);
  if (path === '/data/squat_opensim_reference.json') {
    const lookup = await response.json();
    assert.equal(lookup.schemaVersion, 3);
    assert.equal(lookup.frames.length, 101);
    for (const body of ['pelvis', 'femur_r', 'tibia_r']) {
      assert.equal(lookup.frames[50].blenderBodyFrames[body].translationM.length, 3);
    }
  }
  if (path === '/data/press_tsm_reference.json') {
    const lookup = await response.json();
    assert.equal(lookup.schemaVersion, 2);
    assert.equal(lookup.status, 'shoulder_research_kinematics_only');
    assert.equal(lookup.frames.length, 101);
    assert.equal(Object.keys(lookup.frames[50].muscles).length, 33);
    assert.equal(Object.keys(lookup.frames[50].blenderBodyFrames).length, 7);
  }
  if (path === '/data/bench_tsm_reference.json') {
    const lookup = await response.json();
    assert.equal(lookup.schemaVersion, 2);
    assert.equal(lookup.status, 'bench_research_kinematics_only');
    assert.equal(lookup.frames.length, 101);
    assert.equal(Object.keys(lookup.frames[50].muscles).length, 33);
    assert.equal(Object.keys(lookup.frames[50].blenderBodyFrames).length, 7);
  }
}
console.log(`${names[0]}: offline page with inline app, three OpenSim lookups and both GLB models available.`);
