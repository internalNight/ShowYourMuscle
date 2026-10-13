import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

function walk(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? walk(path) : [relative('dist', path).split(sep).join('/')];
  });
}

const expected = [
  'data/unified_anatomy_bones.json',
  'data/unified_muscle_skin.json',
  'data/unified_muscle_weights.bin',
  'data/unified_opensim_reference.json',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'index.html',
  'manifest.webmanifest',
  'models/NOTICE-unified-opensim.txt',
  'models/NOTICE-z-anatomy.txt',
  'models/unified_anatomy_bones.glb',
  'models/unified_muscle_surfaces.glb',
  'models/unified_opensim_skeleton.glb',
  'sw.js',
].sort();
assert.deepEqual(walk('dist').sort(), expected, 'distribution asset list differs from the unified OpenSim viewer');
const html = readFileSync('dist/index.html', 'utf8');
assert(html.includes('data-bundle="inline"') && html.includes('unified-app'));
for (const forbidden of ['prototype_parts.glb', 'z_anatomy_reference.glb',
  'full_body_skeleton.glb', 'squat_opensim_reference.json',
  'press_tsm_reference.json', 'bench_tsm_reference.json']) {
  assert(!html.includes(forbidden), `the current app still references ${forbidden}`);
}
console.log(`${expected.length} distribution files; one OpenSim rig with registered anatomy surfaces.`);
