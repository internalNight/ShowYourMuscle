import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';

// The full-body scaling artifact is produced offline by `scripts/probe_full_body_scaling.py` against the
// local OpenSim build; Node cannot run OpenSim, so this check re-derives every ratio and every aggregate
// from the recorded raw numbers. A summary that drifts away from its own measurements fails here, and so
// does a recording that scaled nothing.
const data = JSON.parse(readFileSync('docs/data/full_body_scaling_probe.json', 'utf8'));
assert.equal(data.status, 'full_body_scaling_probe_geometry_only');
assert.equal(data.probe, 'scripts/probe_full_body_scaling.py');
assert.ok(existsSync(data.probe), `the recorded producer is missing: ${data.probe}`);
assert.equal(data.model.path, '.cache/model-candidates/opensim-models/Models/Rajagopal/RajagopalLaiUhlrich2023.osim');
assert.match(data.model.sha256, /^[0-9A-F]{64}$/);
assert.ok(data.openSimVersion.startsWith('4.'), `unexpected OpenSim version: ${data.openSimVersion}`);
assert.ok(data.tolerance > 0 && data.tolerance < 1e-2);

// "Full body" is a count here, not an adjective.
const inventory = data.inventory;
assert.ok(inventory.bodies >= 20 && inventory.joints >= 20,
  `the recorded model is not a full body: ${inventory.bodies} bodies, ${inventory.joints} joints`);
assert.ok(inventory.muscles >= 70, `expected a whole-body muscle set, found ${inventory.muscles}`);
assert.ok(inventory.markers >= 50 && inventory.coordinates >= 30,
  `too few markers or coordinates for a scalable model: ${inventory.markers}, ${inventory.coordinates}`);
assert.equal(inventory.hasLowerLimb && inventory.hasUpperLimb && inventory.hasTrunk, true,
  'the inventory does not claim lower limb, upper limb and trunk together');
assert.ok(inventory.totalMassKg > 40 && inventory.totalMassKg < 120,
  `implausible model mass: ${inventory.totalMassKg} kg`);
assert.equal(inventory.sampleBodies.length, Math.min(12, inventory.bodies));
assert.equal(inventory.sampleMuscles.length, Math.min(12, inventory.muscles));
assert.ok(inventory.sampleMuscles.every(name => typeof name === 'string' && name.length > 0));
// The probe picks the measured muscle from the model's own muscle set instead of hard-coding one.
assert.ok(inventory.sampleMuscles.length > 0 && typeof data.probeMuscle === 'string' && data.probeMuscle.length > 0);

const baseline = data.baseline;
for (const key of ['pathLengthM', 'thighLengthM', 'shankLengthM', 'upperArmLengthM', 'totalMassKg']) {
  assert.ok(Number.isFinite(baseline[key]) && baseline[key] > 0, `baseline ${key} is not a positive number`);
}

// Stature and body-mass scaling. Segment lengths must follow the height factor exactly; the muscle path
// length and the moment arm only approximately, because OpenSim scales optimal fibre lengths and tendon
// slack lengths on top of the body scaling. The requested total mass must be hit exactly.
const uniform = Object.entries(data.uniformScaling);
assert.equal(uniform.length, 3, 'the probe must cover more than one stature');
let sawTaller = false;
let sawShorter = false;
for (const [label, entry] of uniform) {
  const factor = entry.heightCm / data.baselineHeightCm;
  assert.ok(Math.abs(entry.heightFactor - factor) < 1e-12, `${label}: heightFactor does not match heightCm`);
  assert.deepEqual(entry.scaleFactors.map(value => Math.abs(value - factor) < 1e-12), [true, true, true],
    `${label}: the recorded scale factors are not the uniform height factor`);
  for (const key of ['thighLengthM', 'shankLengthM', 'upperArmLengthM']) {
    const ratio = entry[key] / baseline[key];
    assert.ok(Math.abs(ratio - entry.ratiosToBaseline[key]) < 1e-9,
      `${label}: the recorded ${key} ratio does not match the recorded lengths`);
    assert.ok(Math.abs(ratio - factor) < 1e-12,
      `${label}: ${key} did not follow the height factor exactly (${ratio} vs ${factor})`);
  }
  const pathRatio = entry.pathLengthM / baseline.pathLengthM;
  assert.ok(Math.abs(pathRatio - entry.ratiosToBaseline.pathLengthM) < 1e-9,
    `${label}: the recorded muscle path ratio does not match the recorded lengths`);
  assert.ok(Math.abs(pathRatio - factor) <= data.tolerance,
    `${label}: the muscle path length left the scaled skeleton by ${Math.abs(pathRatio / factor - 1)}`);
  assert.ok(pathRatio !== 1 || factor === 1,
    `${label}: the muscle path length did not move while the skeleton did`);
  assert.ok(Math.abs(entry.totalMassKg - entry.targetMassKg) < 1e-6,
    `${label}: the scaled model missed its target mass by ${entry.totalMassKg - entry.targetMassKg} kg`);
  const armRatio = entry.momentArmsM.knee_angle_r / baseline.momentArmsM.knee_angle_r;
  assert.ok(Math.abs(armRatio / factor - 1) < 1e-3,
    `${label}: the knee moment arm did not follow the scaled skeleton (${armRatio} vs ${factor})`);
  if (entry.heightCm > data.baselineHeightCm) sawTaller = true;
  if (entry.heightCm < data.baselineHeightCm) sawShorter = true;
}
assert.ok(sawTaller && sawShorter, 'the probe must scale both above and below its baseline stature');

// A circumference input is a whole-segment scale. It must move the muscle path and the moment arm, it must
// leave the other segments and the total mass alone, and it must not be a length change in disguise.
const girth = Object.entries(data.girthScaling);
assert.equal(girth.length, 2, 'the probe must show more than one girth step');
let previousArm = baseline.momentArmsM.knee_angle_r;
for (const [label, entry] of girth) {
  const expected = Number(/(\d+)%/.exec(label)?.[1]) / 100 + 1;
  assert.ok(Number.isFinite(expected) && Math.abs(entry.scaleFactors[0] - expected) < 1e-12,
    `${label}: the recorded factor ${entry.scaleFactors[0]} does not match the label`);
  assert.equal(entry.scaleFactors[1], 1, `${label}: a girth change may not lengthen the segment`);
  assert.equal(entry.scaleFactors[0], entry.scaleFactors[2], `${label}: a girth change must widen both transverse axes`);
  assert.equal(entry.scaledBody, 'femur_r');
  assert.ok(Math.abs(entry.shankLengthM - baseline.shankLengthM) < 1e-12,
    `${label}: widening the thigh moved the shank length`);
  assert.ok(Math.abs(entry.upperArmLengthM - baseline.upperArmLengthM) < 1e-12,
    `${label}: widening the thigh moved the upper arm length`);
  assert.ok(Math.abs(entry.thighLengthM / baseline.thighLengthM - 1) < 1e-4,
    `${label}: a girth change moved the thigh length by more than a hundredth of a percent`);
  assert.ok(Math.abs(entry.totalMassKg - baseline.totalMassKg) < 1e-9,
    `${label}: a girth change moved the total mass`);
  const pathRatio = entry.pathLengthM / baseline.pathLengthM;
  assert.ok(pathRatio !== 1 && Math.abs(pathRatio - 1) < 0.01,
    `${label}: the muscle path length should move only slightly, found a ratio of ${pathRatio}`);
  const arm = entry.momentArmsM.knee_angle_r;
  assert.ok(arm > previousArm * 1.01,
    `${label}: the knee moment arm did not widen: ${previousArm} -> ${arm}`);
  previousArm = arm;
}

// The runtime has to reproduce OpenSim's scaled skeleton by scaling the parent-relative node translations of
// the exported skeleton, so those two are compared here: walk the shipped GLB tree, compose each body's
// recorded scale factors down the chain, and require the resulting positions to be OpenSim's own.
const skeletonGlb = readFileSync('public/models/full_body_skeleton.glb');
const skeletonJson = JSON.parse(skeletonGlb.subarray(20, 20 + skeletonGlb.readUInt32LE(12)).toString('utf8'));
const nodeOf = new Map(skeletonJson.nodes.map((node, index) => [node.name, { node, index }]));
const childOf = new Map();
for (const { node, index } of nodeOf.values()) {
  for (const child of node.children ?? []) {
    childOf.set(skeletonJson.nodes[child].name, node.name);
  }
}
const rootName = skeletonJson.scenes[0].nodes.map(index => skeletonJson.nodes[index].name)[0];

function reproducePositions(profile) {
  // Start from the root at the model's own ground position. Each child sits at its parent's position plus its
  // recorded translation re-expressed through **that parent's** scale factors — which is exactly what setting
  // `node.scale` on the parent does to a child in three.js, and which the probe's recorded hops confirm is
  // what OpenSim does: a uniform stature factor scales every hop, while widening one segment's girth leaves
  // the joint positions of every body untouched.
  const positions = { [rootName]: data.baselineBodyPositionsM[rootName].slice() };
  const queue = [rootName];
  while (queue.length > 0) {
    const parent = queue.shift();
    for (const [name, owner] of childOf.entries()) {
      if (owner !== parent) continue;
      const translation = nodeOf.get(name).node.translation;
      const factors = profile.appliedScaleFactors[parent];
      positions[name] = positions[parent].map((value, axis) => value + translation[axis] * factors[axis]);
      queue.push(name);
    }
  }
  return positions;
}

let comparedPositions = 0;
let worstPositionError = 0;
for (const [label, profile] of Object.entries({ ...data.uniformScaling, ...data.girthScaling })) {
  // A stature factor moves every joint, and the runtime reproduction has to match OpenSim to rounding.
  // A girth factor is a mesh change: the probe shows it leaves OpenSim's joint positions within a millimetre,
  // so girth is treated as mesh-only and the residual is allowed up to 5 mm — the measured worst case is
  // reported in the summary line rather than hidden behind the bound.
  const isGirth = Object.keys(data.girthScaling).includes(label);
  const tolerance = isGirth ? 5e-3 : 1e-6;
  const reproduced = reproducePositions(profile);
  for (const [name, expected] of Object.entries(profile.bodyPositionsInGroundM)) {
    const actual = reproduced[name];
    assert.ok(actual, `${label}: ${name} is not reachable in the exported skeleton tree`);
    const error = Math.max(...expected.map((value, axis) => Math.abs(value - actual[axis])));
    assert.ok(error <= tolerance,
      `${label}: scaling the exported skeleton puts ${name} ${error} m away from OpenSim's own position ` +
      `(tolerance ${tolerance} m)`);
    worstPositionError = Math.max(worstPositionError, error);
    comparedPositions += 1;
  }
}

// The two statements that must never be dropped from the artifact: body fat does not drive muscle geometry,
// and a circumference scales a whole segment rather than one muscle.
const limitations = data.limitations.join('\n');
for (const phrase of ['体脂', '整段', '单块肌肉', '运行时缩放']) {
  assert.ok(limitations.includes(phrase), `the limitations no longer mention ${phrase}`);
}

// The model file lives in a local cache that is not part of the repository, so the recorded hash is
// re-checked only when that cache is present; the absence is reported instead of silently passing.
let hashNote = 'model file not present, the recorded SHA-256 was checked for shape only';
if (existsSync(data.model.path)) {
  const actual = createHash('sha256').update(readFileSync(data.model.path)).digest('hex').toUpperCase();
  assert.equal(actual, data.model.sha256, 'the recorded model SHA-256 does not match the file on disk');
  hashNote = `model SHA-256 matches the file on disk (${actual.slice(0, 8)}…)`;
}

console.log(`FULL_BODY_SCALING {"bodies":${inventory.bodies},"joints":${inventory.joints},"muscles":${inventory.muscles},"markers":${inventory.markers},"probeMuscle":"${data.probeMuscle}","tallestThighRatio":${data.uniformScaling['190cm/95kg'].ratiosToBaseline.thighLengthM},"kneeMomentArmAtThighPlus20Pct":${data.girthScaling['thigh+20%'].momentArmsM.knee_angle_r},"baselineKneeMomentArmM":${baseline.momentArmsM.knee_angle_r},"reproducedBodyPositions":${comparedPositions},"worstBodyPositionErrorM":${worstPositionError}}`);
console.log(`Stature and girth scaling re-derived from the recorded numbers; ${hashNote}.`);
