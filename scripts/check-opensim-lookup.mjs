import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const data = JSON.parse(readFileSync('public/data/squat_opensim_reference.json', 'utf8'));
assert.equal(data.schemaVersion, 3);
assert.equal(data.status, 'reference_model_kinematics_only');
assert.equal(data.frames.length, 101);
const names = Object.keys(data.frames[0].muscles);
assert.equal(names.length, 9);
const bodyNames = Object.keys(data.frames[0].blenderBodyFrames);
const finite = value => Number.isFinite(value);
const determinant = m => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
  m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
  m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
let largestDiscrepancy = 0;
for (const [index, frame] of data.frames.entries()) {
  assert.ok(Math.abs(frame.phase - index / 100) < 1e-9);
  // Same guard the TSM checks and the muscle list already have: the body list is part of the contract,
  // not something to discover from whichever frame happens to be first.
  assert.deepEqual(Object.keys(frame.blenderBodyFrames).sort(), bodyNames.slice().sort(),
    `frame ${index} changed the set of Blender body frames`);
  for (const name of ['hip', 'knee', 'ankle', 'back', 'foot']) {
    assert.equal(frame.viewerJointsM[name].length, 3);
    assert.ok(frame.viewerJointsM[name].every(finite));
  }
  for (const name of bodyNames) {
    const body = frame.blenderBodyFrames[name];
    assert.ok(body.translationM.length === 3 && body.translationM.every(finite));
    assert.ok(body.rotationRows.length === 3 && body.rotationRows.every(row => row.length === 3 && row.every(finite)));
    for (let row = 0; row < 3; row++) {
      for (let other = 0; other < 3; other++) {
        const dot = body.rotationRows[row].reduce((sum, value, col) => sum + value * body.rotationRows[other][col], 0);
        assert.ok(Math.abs(dot - (row === other ? 1 : 0)) < 1e-8);
      }
    }
    // Orthonormal is not enough: a mirrored basis is still orthonormal but has determinant -1, and a
    // mirrored limb frame would render backwards while every length-based assertion stayed green.
    assert.ok(Math.abs(determinant(body.rotationRows) - 1) < 1e-8,
      `frame ${index} ${name}: the rotation is a reflection, not a rotation`);
  }
  assert.deepEqual(Object.keys(frame.muscles).sort(), names.slice().sort());
  for (const name of names) {
    const muscle = frame.muscles[name];
    assert.ok(muscle.viewerPathM.length >= 2);
    assert.ok(muscle.viewerPathM.every(point => point.length === 3 && point.every(finite)));
    const polyline = muscle.viewerPathM.slice(1).reduce((sum, point, segment) =>
      sum + Math.hypot(...point.map((value, axis) => value - muscle.viewerPathM[segment][axis])), 0);
    largestDiscrepancy = Math.max(largestDiscrepancy, Math.abs(polyline - muscle.lengthM));
    assert.ok(Math.abs(muscle.ratioToStanding - muscle.lengthM / data.frames[0].muscles[name].lengthM) < 1e-8);
  }
}
assert.ok(largestDiscrepancy < 0.005);
assert.ok(Math.abs(largestDiscrepancy - data.maximumPolylineErrorM) < 1e-9);
console.log(`101 frames × 9 paths: coordinates finite; displayed polylines differ from OpenSim lengths by at most ${(largestDiscrepancy * 1000).toFixed(3)} mm.`);
