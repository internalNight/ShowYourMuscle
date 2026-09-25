import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { checkTsmBodyFrames } from './check-tsm-body-frames.mjs';

const data = JSON.parse(readFileSync('public/data/press_tsm_reference.json', 'utf8'));
assert.equal(data.schemaVersion, 2);
assert.equal(data.status, 'shoulder_research_kinematics_only');
assert.equal(data.frames.length, 101);
checkTsmBodyFrames(data);
const names = Object.keys(data.frames[0].muscles);
assert.equal(names.length, 33);
for (const name of ['PectoralisMajorThorax_M', 'DeltoideusClavicle_A',
  'SerratusAnterior_M', 'TrapeziusScapula_M', 'TRIlong']) {
  assert(names.includes(name), `missing ${name}`);
}
let maxError = 0;
let maxStep = 0;
for (const [index, frame] of data.frames.entries()) {
  assert(Math.abs(frame.phase - index / 100) < 1e-9);
  for (const joint of ['thorax', 'clavicle', 'scapula', 'shoulder', 'elbow', 'hand']) {
    assert(frame.viewerJointsM[joint].length === 3 && frame.viewerJointsM[joint].every(Number.isFinite));
  }
  assert(Math.abs(frame.viewerJointsM.shoulder[0] - 0.30) < 1e-9);
  assert(Math.abs(frame.viewerJointsM.shoulder[1] - 1.45) < 1e-9);
  for (const name of names) {
    const muscle = frame.muscles[name];
    assert(muscle.lengthM > 0 && Number.isFinite(muscle.lengthM));
    assert(muscle.viewerPathM.length >= 2);
    assert(muscle.viewerPathM.every(point => point.length === 3 && point.every(Number.isFinite)));
    const polyline = muscle.viewerPathM.slice(1).reduce((sum, point, segment) =>
      sum + Math.hypot(...point.map((value, axis) => value - muscle.viewerPathM[segment][axis])), 0);
    maxError = Math.max(maxError, Math.abs(polyline - muscle.lengthM));
    assert(Math.abs(muscle.ratioToStartingPose - muscle.lengthM /
      data.frames[0].muscles[name].lengthM) < 1e-8);
    assert(Object.values(muscle.momentArmsM).length === 3);
    assert(Object.values(muscle.momentArmsM).every(Number.isFinite));
    if (index) maxStep = Math.max(maxStep, Math.abs(muscle.lengthM - data.frames[index - 1].muscles[name].lengthM));
  }
}
assert(maxError < 0.005);
assert(maxStep < 0.010);
assert(Math.abs(maxError - data.maximumPolylineErrorM) < 1e-9);
assert(Math.abs(maxStep - data.maximumLengthStepM) < 1e-9);
for (const name of names) {
  assert(Math.abs(data.frames[0].muscles[name].lengthM -
    data.frames[100].muscles[name].lengthM) < 1e-8);
}
console.log(`101 frames × 33 TSM paths: max display error ${(maxError * 1000).toFixed(2)} mm, max length step ${(maxStep * 1000).toFixed(2)} mm.`);
