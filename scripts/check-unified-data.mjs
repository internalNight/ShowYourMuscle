import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const data = JSON.parse(readFileSync('public/data/unified_opensim_reference.json', 'utf8'));
const audit = JSON.parse(readFileSync('docs/data/unified_opensim_geometry.json', 'utf8'));
assert.equal(data.model, audit.model);
assert.equal(data.bodyNames.length, 80);
assert.equal(data.muscleNames.length, 520);
assert.equal(new Set(data.bodyNames).size, 80);
assert.equal(new Set(data.muscleNames).size, 520);
assert.equal(audit.present.length + audit.missing.length + audit.excluded.length, 132);

for (const [action, frames] of Object.entries({ neutral: [data.neutral], ...data.actions })) {
  assert.equal(frames.length, action === 'neutral' ? 1 : 101);
  for (const [index, frame] of frames.entries()) {
    assert.equal(frame.bodies.length, 80, `${action} frame ${index} bodies`);
    assert.equal(frame.paths.length, 520, `${action} frame ${index} paths`);
    assert.equal(frame.lengthsM.length, 520, `${action} frame ${index} lengths`);
    assert(frame.coordinates && typeof frame.coordinates === 'object');
    for (let muscle = 0; muscle < 520; muscle++) {
      assert(frame.paths[muscle].length >= 2, `${action} frame ${index} ${muscle} path`);
      assert(Number.isFinite(frame.lengthsM[muscle]) && frame.lengthsM[muscle] > 0);
    }
  }
  if (action !== 'neutral') {
    const mid = frames[50];
    assert(Object.keys(mid.coordinates).length >= 2, `${action} has no joint coordinates`);
    assert(mid.bodies.some((body, index) => JSON.stringify(body) !== JSON.stringify(data.neutral.bodies[index])),
      `${action} did not change model pose`);
    assert(mid.lengthsM.some((length, index) => Math.abs(length - data.neutral.lengthsM[index]) > 0.001),
      `${action} did not change muscle lengths`);
  }
}
console.log('One OpenSim model: 80 bodies, 520 paths, 304 complete frames, changing poses and lengths.');
