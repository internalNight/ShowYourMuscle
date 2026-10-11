// Guards the cross-model lumbar-capacity result.
//
// docs/data/full_body_lumbar_capacity.json asks the deep-squat lumbar question on a research-purpose
// full-body model with a real trunk, after three rounds in which only the reduced two-erector-spinae
// model could be used. The result is a correction, so the things that make it trustworthy are
// asserted here: the flexion sign convention is calibrated from the model rather than assumed, the
// level being compared is the anatomically matching one, the demand and the reduced-model bound tie
// back to the previous round's audit, and the conclusion does not depend on the chosen muscle group
// or on the arm posture left at its default.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = name => JSON.parse(readFileSync(`docs/data/${name}`, 'utf8'));
const reduced = read('bilateral_deep_squat_length_capacity.json');
const full = read('full_body_lumbar_capacity.json');

// The model's own muscle lengths, not an assumption, define which way flexion turns the spine.
assert.equal(full.flexionCalibration.flexionIsNegative, true,
  'lumbar flexion is no longer the negative coordinate direction');
assert(full.flexionCalibration.extensorFiberLengthAtMinus5Deg >
  full.flexionCalibration.extensorFiberLengthAtPlus5Deg,
  'flexing the spine no longer stretches the erector spinae');
assert(full.flexionCalibration.erectorSpinaeCount > 100,
  'the trunk extensor set is suspiciously small for a full-body model');
assert(full.flexionCalibration.erectorSpinaePositiveArmMomentNm >
  full.flexionCalibration.erectorSpinaeNegativeArmMomentNm,
  'the erector spinae no longer pull mainly in the positive direction');

// The source model's single lumbar joint must sit near the level this model is compared at.
for (const [subject, height] of Object.entries(full.levelCorrespondence.source)) {
  assert(Math.abs(height - full.levelCorrespondence.fullBodyLowestLevelAboveHipM) < 0.04,
    `${subject}: the source lumbar joint is ${height} m above the hip, too far from the ` +
    `${full.levelCorrespondence.fullBodyLowestLevelAboveHipM} m of the compared level`);
}

const expected = { AB01: { demand: 157.798, reduced: 112.653 }, AB02: { demand: 133.486, reduced: 92.052 } };
for (const [subject, data] of Object.entries(full.subjects)) {
  // Same demand and same reduced-model bound as the length-dependent audit, so this file only adds
  // a second model rather than a second convention.
  assert(Math.abs(data.demandNm - expected[subject].demand) < 1e-2,
    `${subject}: the lumbar demand does not tie back to the audit`);
  assert(Math.abs(data.reducedModelLengthBoundNm - reduced.subjects[subject]
    .targetFrame.lumbar_extension.lengthBoundNm) < 1e-2,
    `${subject}: the reduced-model lumbar bound does not tie back to the audit`);
  const capacities = data.report.capacities;
  assert(capacities.erectorSpinaeOnlyNm > 3 * data.reducedModelLengthBoundNm,
    `${subject}: the full-body trunk is no longer several times stronger than the reduced model`);
  assert(data.demandToErectorSpinaeOnly < 0.5,
    `${subject}: the demand is no longer comfortably inside the full-body trunk capacity`);
  // The arm posture is left at the model default, so the bound must not hinge on it.
  assert(capacities.shoulderSpanningNm < 1,
    `${subject}: shoulder-spanning muscles now drive the trunk bound, so the arm posture matters`);
  // Muscles that flex the trunk but pull the other way at this posture are documented, not hidden.
  assert(data.report.flexorsActingAsExtensorsArmsCm.rect_abd_r > 0,
    `${subject}: the rectus abdominis sign flip is no longer recorded`);
  assert(capacities.flexorsActingAsExtensorsNm > 100,
    `${subject}: the flipped-flexor contribution is smaller than previously recorded`);
}

// The conclusion must not be a property of one flexion angle.
const sweep = Object.entries(full.sweep).map(([angle, entry]) =>
  [Number(angle), entry.capacities.erectorSpinaeOnlyNm]);
assert(sweep.length >= 5, 'the flexion sweep is too short to support the conclusion');
for (const [angle, capacity] of sweep) {
  assert(capacity > 400 && capacity < 600,
    `at ${angle} deg the erector spinae capacity left the expected band (${capacity} N m)`);
}
const deepest = sweep[sweep.length - 1][1];
assert(deepest > 1.5 * expected.AB01.reduced,
  'the deepest sweep point no longer exceeds the reduced model by the reported margin');

console.log(`Full-body lumbar capacity verified: a ${full.modelProvenance.muscleCount}-muscle ` +
  `model with a real trunk holds the L5/S1 level ${full.levelCorrespondence.fullBodyLowestLevelAboveHipM} m ` +
  `above the hip against ${full.levelCorrespondence.source.AB01} m for the source joint, and its ` +
  `erector spinae alone (${full.subjects.AB01.report.capacities.erectorSpinaeOnlyNm} N m at AB01's ` +
  `posture) exceed the reduced model's ${expected.AB01.reduced} N m by ` +
  `${(full.subjects.AB01.report.capacities.erectorSpinaeOnlyNm / expected.AB01.reduced).toFixed(1)}x, ` +
  `leaving the demand at ${full.subjects.AB01.demandToErectorSpinaeOnly} of capacity.`);
