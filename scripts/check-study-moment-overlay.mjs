import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';

const evidence = JSON.parse(readFileSync('src/data/squat_evidence.json', 'utf8'));
const curves = evidence.phaseJointMomentStudyCurves;
assert.equal(curves.rightHip.median.length, 99);
assert.equal(curves.rightKnee.median.length, 99);
const bundled = await build({ entryPoints: ['src/study-moments.ts'], bundle: true,
  platform: 'node', format: 'esm', write: false });
const { squatStudyJointMoments } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);

for (const [phase, index] of [[0, 0], [0.01, 0], [0.25, 24], [0.5, 49], [0.75, 74], [0.99, 98], [1, 98]]) {
  const values = squatStudyJointMoments(phase);
  assert.deepEqual(values.map(item => item.joint), ['髋', '膝']);
  assert.equal(values[0].momentNmPerKg, curves.rightHip.median[index]);
  assert.equal(values[1].momentNmPerKg, curves.rightKnee.median[index]);
}
const halfway = squatStudyJointMoments(0.255);
assert(Math.abs(halfway[0].momentNmPerKg
  - (curves.rightHip.median[24] + curves.rightHip.median[25]) / 2) < 1e-12);
assert(Math.abs(halfway[1].momentNmPerKg
  - (curves.rightKnee.median[24] + curves.rightKnee.median[25]) / 2) < 1e-12);
assert.throws(() => squatStudyJointMoments(Number.NaN));
console.log('Study overlay matches both source net-joint-moment curves at endpoints and five interior phases.');
