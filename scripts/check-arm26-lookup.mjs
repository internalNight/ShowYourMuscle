import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// Research-only artifact: the shipping app no longer fetches this lookup, so it lives with the other
// research data instead of inside the web bundle. `check:bundle-assets` keeps that separation.
const data = JSON.parse(readFileSync('docs/data/press_arm26_reference.json', 'utf8'));
assert.equal(data.schemaVersion, 1);
assert.equal(data.status, 'planar_research_kinematics_only');
assert.equal(data.frames.length, 101);
const names = Object.keys(data.frames[0].muscles);
assert.deepEqual(names.sort(), ['BRA', 'BIClong', 'BICshort', 'TRIlat', 'TRIlong', 'TRImed'].sort());
let largestDiscrepancy = 0;
for (const [index, frame] of data.frames.entries()) {
  assert.ok(Math.abs(frame.phase - index / 100) < 1e-9);
  for (const name of ['shoulder', 'elbow', 'distalForearm']) {
    assert.ok(frame.viewerJointsM[name].length === 3 && frame.viewerJointsM[name].every(Number.isFinite));
  }
  for (const name of names) {
    const muscle = frame.muscles[name];
    assert.ok(muscle.viewerPathM.length >= 2);
    assert.ok(muscle.viewerPathM.every(point => point.length === 3 && point.every(Number.isFinite)));
    const polyline = muscle.viewerPathM.slice(1).reduce((sum, point, segment) =>
      sum + Math.hypot(...point.map((value, axis) => value - muscle.viewerPathM[segment][axis])), 0);
    largestDiscrepancy = Math.max(largestDiscrepancy, Math.abs(polyline - muscle.lengthM));
    assert.ok(Math.abs(muscle.ratioToStartingPose - muscle.lengthM / data.frames[0].muscles[name].lengthM) < 1e-8);
    assert.ok(Object.values(muscle.momentArmsM).every(Number.isFinite));
  }
}
assert.ok(largestDiscrepancy < 0.005);
assert.ok(Math.abs(largestDiscrepancy - data.maximumPolylineErrorM) < 1e-9);
console.log(`101 frames × 6 Arm26 paths: max displayed-path discrepancy ${(largestDiscrepancy * 1000).toFixed(3)} mm.`);
