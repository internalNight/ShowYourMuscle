// Every file under public/ is copied into the web build and therefore into the Android package.
// A file that neither the app nor the service worker references is dead weight that ships to users,
// and research data in particular must not travel with the app. This check keeps that boundary
// explicit: wire the asset up, move it to docs/data as a research artifact, or delete it.
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

function walk(directory, files = []) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) walk(path, files);
    else files.push(path);
  }
  return files;
}

const toPosix = (path) => path.split(sep).join('/');
const publicFiles = walk('public').map(toPosix);
const source = [...walk('src')]
  .filter(path => /\.(ts|json)$/.test(path))
  .map(path => readFileSync(path, 'utf8')).join('\n');
const serviceWorker = readFileSync('public/sw.js', 'utf8');
const indexHtml = readFileSync('index.html', 'utf8');

// Framework files that are reached by the browser or the platform, not by our own code.
const platformFiles = new Set(['manifest.webmanifest']);
const isPlatformFile = (path) => platformFiles.has(path) || path.startsWith('icons/') ||
  path === 'sw.js';

const unreferenced = [];
const referenced = [];
for (const path of publicFiles) {
  const asset = path.replace(/^public\//, '');
  const basename = asset.split('/').pop();
  const users = [];
  if (source.includes(basename)) users.push('src');
  if (serviceWorker.includes(asset) || serviceWorker.includes(basename)) users.push('sw.js');
  if (indexHtml.includes(asset) || indexHtml.includes(basename)) users.push('index.html');
  if (isPlatformFile(asset)) users.push('platform');
  if (users.length === 0) unreferenced.push(asset);
  else referenced.push({ asset, users });
}

assert.deepEqual(unreferenced, [],
  `Shipped but unreferenced assets: ${unreferenced.join(', ')}. Wire each one into the app or the ` +
  'service worker, move it to docs/data as a research artifact, or delete it.');

// The three runtime lookups and two models are the assets the offline experience depends on, and the
// service worker must precache every one of them.
const precached = ['data/squat_opensim_reference.json', 'data/press_tsm_reference.json',
  'data/bench_tsm_reference.json', 'models/prototype_parts.glb', 'models/z_anatomy_reference.glb'];
for (const asset of precached) {
  assert(publicFiles.includes(`public/${asset}`), `${asset} is missing from public/`);
  assert(referenced.some(item => item.asset === asset && item.users.includes('sw.js')),
    `${asset} is not precached by the service worker`);
}
assert(!publicFiles.some(path => /^public\/data\/.*(arm26|probe|screen|audit)/.test(path)),
  'Research data belongs in docs/data, not in the shipped bundle');

console.log(`${publicFiles.length} shipped assets: ${precached.length} precached runtime assets, ` +
  `${publicFiles.length - precached.length} platform or notice files, 0 unreferenced.`);
