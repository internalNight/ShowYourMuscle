import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { runInNewContext } from 'node:vm';

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
runInNewContext(await readFile('public/sw.js', 'utf8'), { self, caches, fetch: localFetch, URL, Promise });

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
