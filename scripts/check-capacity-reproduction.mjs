// Guards the independent re-derivation of the deep-squat capacity audit.
//
// docs/data/bilateral_deep_squat_joint_capacity.json is produced by the audit at one deep-squat
// frame; docs/data/bilateral_deep_squat_capacity_pose_check.json re-derives the same quantities from
// the same model, pose and moment sources through a separate script. If the capacity logic changes in
// one place only, this cross-check fails instead of leaving two documents that quietly disagree.
//
// It also re-computes the derived fields of the re-derivation (demand disagreement and its size
// relative to the bound) so a mistake in those new metrics cannot pass unnoticed.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const audit = JSON.parse(readFileSync('docs/data/bilateral_deep_squat_joint_capacity.json', 'utf8'));
const probe = JSON.parse(readFileSync('docs/data/bilateral_deep_squat_capacity_pose_check.json',
  'utf8'));
assert.equal(audit.subject, probe.subject, 'the two artifacts describe different subjects');
assert.equal(audit.timeS, probe.timeS, 'the two artifacts describe different frames');
assert.equal(audit.muscleCount, probe.muscleCount, 'the two artifacts use different muscle sets');

const auditByCoordinate = new Map(audit.coordinates.map(row => [row.coordinate, row]));
let compared = 0;
for (const [coordinate, derived] of Object.entries(probe.coordinates)) {
  const original = auditByCoordinate.get(coordinate);
  assert(original, `the audit does not cover ${coordinate}`);
  const close = (left, right, tolerance, field) => assert(
    Math.abs(left - right) < tolerance,
    `${coordinate} ${field}: audit ${left} vs re-derivation ${right}`);
  close(original.targetMomentNm, derived.replayedIdMomentNm, 1e-2, 'replayed demand');
  close(original.optimisticIndependentCapacityNm, derived.optimisticCapacityNm, 1e-2, 'capacity');
  close(original.sourceRawCsvMomentNmAssumingNmPerKg, derived.sourceCsvMomentNm, 1e-2,
    'source demand');
  close(original.demandToCapacity, derived.replayedDemandToCapacity, 1e-3, 'demand to capacity');
  // Derived quantities are recomputed from the artifact's own reported values.
  close(Math.abs(derived.replayedIdMomentNm - derived.sourceCsvMomentNm),
    derived.demandEstimateDisagreementNm, 2e-3, 'demand disagreement');
  close(derived.demandEstimateDisagreementNm / derived.optimisticCapacityNm,
    derived.disagreementToCapacity, 2e-3, 'disagreement to capacity');
  assert(derived.oppositeDirectionCapacityNm >= 0, `${coordinate} has a negative opposite bound`);
  compared++;
}

// The framing this re-derivation supports: only the hip-rotation comparisons are unusable, because
// there the two independent demand estimates differ by more than half the bound itself.
const undermined = Object.entries(probe.coordinates)
  .filter(([, item]) => item.disagreementToCapacity > 0.5).map(([name]) => name).sort();
assert.deepEqual(undermined, ['hip_rotation_l', 'hip_rotation_r'],
  `unexpected unusable comparisons: ${undermined.join(', ')}`);
for (const name of undermined) {
  assert(probe.coordinates[name].directionAsymmetryRatio > 10,
    `${name} is flagged as unusable but its bound is not strongly direction-asymmetric`);
}
// Every other axis must keep its demand uncertainty well below its own bound, otherwise the
// distinction above is not a real discriminator.
for (const [name, item] of Object.entries(probe.coordinates)) {
  if (undermined.includes(name)) continue;
  assert(item.disagreementToCapacity < 0.2,
    `${name} has demand uncertainty ${item.disagreementToCapacity} of its bound`);
}
assert(probe.comparisonsUnderminedByDemandUncertainty.length === undermined.length,
  'the artifact summary disagrees with the per-coordinate values');

// The pose context is what makes the hip-rotation comparison unusable, so its two signatures are
// asserted as well: a fixed capture-frame heading (near-constant, opposite in sign between subjects)
// and a hip-rotation coordinate that tracks hip flexion.
const contexts = Object.entries(probe.poseContext);
assert.equal(contexts.length, 2, 'expected both subjects in the pose context');
const headings = contexts.map(([name, context]) => [name, context.pelvis_rotation]);
for (const [name, rotation] of headings) {
  assert(rotation.spanDeg < 10,
    `${name} pelvis_rotation spans ${rotation.spanDeg} deg, so it is not a fixed heading`);
  assert(Math.abs(rotation.medianDeg) > 60,
    `${name} pelvis_rotation median is only ${rotation.medianDeg} deg`);
}
assert(Math.sign(headings[0][1].medianDeg) !== Math.sign(headings[1][1].medianDeg),
  'both subjects share the same pelvis heading sign, so the offset is not a capture convention');
for (const [name, context] of contexts) {
  const ratios = Object.values(context.hipRotationAtDeepestFrameRatio);
  assert(ratios.every(ratio => ratio > 0),
    `${name} has no hip rotation at its deepest knee frame`);
  assert(ratios.some(ratio => ratio > 0.15),
    `${name} hip rotation does not track hip flexion at depth`);
}

console.log(`Deep-squat capacity audit reproduced for ${compared} coordinates; ` +
  'hip rotation is the only axis whose demand disagreement exceeds half its own bound ' +
  `(${probe.coordinates.hip_rotation_r.disagreementToCapacity} and ` +
  `${probe.coordinates.hip_rotation_l.disagreementToCapacity}), and its bound is ` +
  `${probe.coordinates.hip_rotation_r.directionAsymmetryRatio}x direction-asymmetric.`);
