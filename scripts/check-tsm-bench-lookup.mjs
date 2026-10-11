import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { checkTsmBodyFrames } from './tsm-body-frames.mjs';

const data = JSON.parse(readFileSync('public/data/bench_tsm_reference.json', 'utf8'));
assert.equal(data.schemaVersion, 2);
assert.equal(data.status, 'bench_research_kinematics_only');
assert.equal(data.frames.length, 101);
checkTsmBodyFrames(data);
const names = Object.keys(data.frames[0].muscles);
assert.equal(names.length, 33);
for (const name of ['PectoralisMajorThorax_M', 'DeltoideusClavicle_A', 'TRIlong']) {
  assert(names.includes(name));
}
const top = data.frames[0].viewerJointsM.hand;
const bottom = data.frames[50].viewerJointsM.hand;
let maxPolylineError = 0;
let maxLengthStep = 0;
let maxHandPathError = 0;
for (const [index, frame] of data.frames.entries()) {
  assert(Math.abs(frame.phase - index / 100) < 1e-9);
  for (const joint of ['thorax', 'clavicle', 'scapula', 'shoulder', 'elbow', 'hand']) {
    assert(frame.viewerJointsM[joint].length === 3 && frame.viewerJointsM[joint].every(Number.isFinite));
  }
  assert(Math.abs(frame.viewerJointsM.shoulder[0] - 0.27) < 1e-9);
  assert(Math.abs(frame.viewerJointsM.shoulder[1] - 0.75) < 1e-9);
  // Same contract as the squat and press references: every frame must carry the whole muscle list.
  assert.deepEqual(Object.keys(frame.muscles).sort(), names.slice().sort(),
    `frame ${index} (phase ${frame.phase}) changed the set of muscles`);
  const lowered = Math.sin(Math.PI * frame.phase) ** 2;
  const target = top.map((value, axis) => value + (bottom[axis] - value) * lowered);
  maxHandPathError = Math.max(maxHandPathError,
    Math.hypot(...target.map((value, axis) => value - frame.viewerJointsM.hand[axis])));
  for (const name of names) {
    const muscle = frame.muscles[name];
    assert(muscle.lengthM > 0 && Number.isFinite(muscle.lengthM));
    assert(muscle.viewerPathM.length >= 2);
    assert(muscle.viewerPathM.every(point => point.length === 3 && point.every(Number.isFinite)));
    const polyline = muscle.viewerPathM.slice(1).reduce((sum, point, segment) =>
      sum + Math.hypot(...point.map((value, axis) => value - muscle.viewerPathM[segment][axis])), 0);
    maxPolylineError = Math.max(maxPolylineError, Math.abs(polyline - muscle.lengthM));
    assert(Math.abs(muscle.ratioToStartingPose - muscle.lengthM /
      data.frames[0].muscles[name].lengthM) < 1e-8);
    assert.deepEqual(Object.keys(muscle.momentArmsM),
      ['plane_elv', 'shoulder_elv', 'axial_rot', 'elbow_flexion']);
    assert(Object.values(muscle.momentArmsM).every(Number.isFinite));
    if (index) maxLengthStep = Math.max(maxLengthStep,
      Math.abs(muscle.lengthM - data.frames[index - 1].muscles[name].lengthM));
  }
}
assert(maxPolylineError < 0.005);
assert(maxLengthStep < 0.010);
assert(maxHandPathError < 0.015);
assert(Math.abs(maxPolylineError - data.maximumPolylineErrorM) < 1e-9);
assert(Math.abs(maxLengthStep - data.maximumLengthStepM) < 1e-9);
assert(Math.abs(maxHandPathError - data.maximumHandPathErrorM) < 1e-9);
assert(data.handDropM > 0.15 && data.handDropM < 0.35);
assert(data.handLateralDriftM < 0.04);
assert(data.elbowLateralChangeM > 0.12);
for (const name of names) {
  assert(Math.abs(data.frames[0].muscles[name].lengthM -
    data.frames[100].muscles[name].lengthM) < 1e-8);
}
console.log(`101 bench frames × 33 TSM paths: hand path error ${(maxHandPathError * 1000).toFixed(1)} mm, path error ${(maxPolylineError * 1000).toFixed(2)} mm, length step ${(maxLengthStep * 1000).toFixed(2)} mm.`);
