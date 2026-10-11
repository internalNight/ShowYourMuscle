// Guards the length-dependent capacity re-derivation of the deep-squat frames.
//
// docs/data/bilateral_deep_squat_length_capacity.json recomputes the repository's capacity audit with
// the active force-length relation and pennation included. Three things must stay true for the
// conclusions drawn from it to hold: it must still reproduce the audit it extends, adding length
// dependence must only ever lower capacity, and the axes that come out above the bound must be the
// ones the documents name. The provenance and source-data facts recorded alongside are asserted too,
// because the reading of the result depends on them.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = name => JSON.parse(readFileSync(`docs/data/${name}`, 'utf8'));
const audit = read('bilateral_deep_squat_joint_capacity.json');
const length = read('bilateral_deep_squat_length_capacity.json');
const auditByCoordinate = new Map(audit.coordinates.map(row => [row.coordinate, row]));

let checked = 0;
for (const [subject, data] of Object.entries(length.subjects)) {
  assert.equal(data.interval.knee_angle_r.frameCount, 21, `${subject} interval is not 21 frames`);
  for (const [coordinate, frame] of Object.entries(data.targetFrame)) {
    assert(frame.lengthBoundNm < frame.maximumBoundNm,
      `${subject} ${coordinate}: length dependence did not lower the bound`);
    assert(Math.abs(frame.demandToLengthBound - Math.abs(frame.demandNm) / frame.lengthBoundNm)
      < 2e-3, `${subject} ${coordinate}: demand to length bound is inconsistent`);
    const original = auditByCoordinate.get(coordinate);
    if (!original || subject !== audit.subject) continue;
    // The maximum-isometric bound and the demand must be bit-for-bit the audit's, so that the
    // difference between the two documents is exactly the force-length factor.
    assert(Math.abs(frame.maximumBoundNm - original.optimisticIndependentCapacityNm) < 1e-2,
      `${subject} ${coordinate}: the audit bound is not reproduced ` +
      `(${frame.maximumBoundNm} vs ${original.optimisticIndependentCapacityNm})`);
    assert(Math.abs(frame.demandNm - original.targetMomentNm) < 1e-2,
      `${subject} ${coordinate}: the audit demand is not reproduced`);
    checked++;
  }
}
assert(checked >= 7, `only ${checked} coordinates were compared with the audit`);

// Which axes survive the stricter bound, per subject and per demand source.
const exceeds = (subject, coordinate, key) => length.subjects[subject].interval[coordinate][key];
for (const subject of ['AB01', 'AB02']) {
  for (const control of ['hip_flexion_r', 'hip_adduction_r', 'ankle_angle_r']) {
    assert.equal(exceeds(subject, control, 'framesExceedingLengthBound'), 0,
      `${subject} ${control} is a control axis but exceeds the length-dependent bound`);
  }
  assert.equal(exceeds(subject, 'lumbar_extension', 'framesExceedingLengthBound'), 21,
    `${subject} lumbar extension is expected to exceed the bound in every frame`);
}
assert.equal(exceeds('AB01', 'knee_angle_r', 'framesExceedingLengthBound'), 21,
  'the AB01 right knee is expected to exceed the length-dependent bound in every frame');
assert.equal(exceeds('AB02', 'knee_angle_r', 'framesExceedingLengthBound'), 0,
  'the AB02 right knee is expected to stay inside the length-dependent bound');

// The published CSV covers only the lower-limb joints, so the lumbar result rests on the replay
// alone. If a CSV column ever appears, this assertion should be revisited deliberately.
for (const subject of ['AB01', 'AB02']) {
  assert.equal(exceeds(subject, 'lumbar_extension', 'medianSourceCsvDemandToLengthBound'), null,
    `${subject}: lumbar extension unexpectedly has a published CSV demand`);
  for (const covered of ['knee_angle_r', 'hip_flexion_r', 'ankle_angle_r']) {
    assert(typeof exceeds(subject, covered, 'medianSourceCsvDemandToLengthBound') === 'number',
      `${subject} ${covered} should have a published CSV demand`);
  }
}

// The knee-angle sweep is the evidence that the bound responds to length the way muscle does, and
// that part of the knee bound comes from a muscle group acting on the wrong side of the joint.
const sweep = Object.entries(length.subjects.AB01.kneeAngleSweep)
  .map(([key, value]) => [Number(key), value]).sort((left, right) => left[0] - right[0]);
const capacities = sweep.map(([, value]) => value.lengthCapacityNm);
const peakIndex = capacities.indexOf(Math.max(...capacities));
assert(peakIndex > 0 && peakIndex < capacities.length - 1,
  'the length-dependent knee capacity does not peak at an interior knee angle');
assert(sweep[0][1].lengthCapacityNm < sweep[sweep.length - 1][1].lengthCapacityNm,
  'the deep-flexed knee capacity is not below the extended one');
const hamstrings = sweep.map(([, value]) => value.hamstringsMomentArmCm.bifemlh_r);
assert(hamstrings[0] > 0 && hamstrings[hamstrings.length - 1] < 0,
  'the hamstring knee moment arm no longer changes sign across the sweep');

const provenance = length.subjects.AB01.modelProvenance;
assert(provenance.credits.includes('not intended to be used in research'),
  'the model credits no longer carry the reduced-muscle-set caveat');
assert.deepEqual(Object.keys(provenance.kneeExtensors).sort(),
  ['rect_fem_l', 'rect_fem_r', 'vas_int_l', 'vas_int_r'],
  'the model knee extensor set changed');
assert.deepEqual(Object.keys(provenance.trunkExtensors).filter(name => name.startsWith('ercspn')).sort(),
  ['ercspn_l', 'ercspn_r'], 'the trunk extensor set changed');

// The two knees of one subject move within a few degrees of each other, so a large left/right demand
// difference is a property of that subject's demand rather than of the model.
const symmetry = length.subjects.AB01.symmetryAtTargetFrame.knee_angle;
assert(symmetry.leftRightAngleGapDeg < 5, 'the AB01 knee angle gap is unexpectedly large');
assert(symmetry.rightToLeftDemandRatio > 2,
  'the AB01 knee demands are no longer strongly asymmetric');

console.log(`Length-dependent capacity verified for ${checked} audited coordinates; ` +
  `the deepest-frame bound drops from ${audit.coordinates.find(row =>
    row.coordinate === 'knee_angle_r').optimisticIndependentCapacityNm} to ` +
  `${length.subjects.AB01.targetFrame.knee_angle_r.lengthBoundNm} N m at the right knee, ` +
  `and lumbar extension exceeds it in every frame of both subjects.`);
