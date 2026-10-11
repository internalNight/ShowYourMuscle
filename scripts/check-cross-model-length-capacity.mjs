// Guards the cross-model knee-capacity comparison.
//
// docs/data/high_flex_length_capacity.json puts the reduced gait2354-family model and the
// research-purpose RajagopalLaiUhlrich2023 candidate under one pose convention. Three things make
// its conclusions trustworthy: the reduced-model side must reproduce the previous round's
// length-dependent audit exactly, the candidate must not reproduce the reduced model's
// hamstring-as-knee-extensor artifact, and the pose clamp at the candidate's knee range must stay
// visible rather than being silently compared as if it were the requested angle.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = name => JSON.parse(readFileSync(`docs/data/${name}`, 'utf8'));
const reduced = read('bilateral_deep_squat_length_capacity.json');
const cross = read('high_flex_length_capacity.json');

let compared = 0;
for (const [subject, data] of Object.entries(cross.subjects)) {
  const sweep = Object.entries(data.sweep).map(([key, value]) => [Number(key), value]);
  const previous = new Map(Object.entries(reduced.subjects[subject].kneeAngleSweep)
    .map(([key, value]) => [Number(key), value]));
  for (const [angle, entry] of sweep) {
    assert.equal(entry.source.poseClamped, false,
      `${subject} ${angle}: the reduced model was clamped during the sweep`);
    assert(entry.source.appliedFlexionDeg === angle,
      `${subject} ${angle}: the reduced model holds a different angle than requested`);
    const earlier = previous.get(angle);
    if (!earlier) continue;
    // Same definition, same pose, same moment-arm timing, so this tie must be exact.
    assert(Math.abs(entry.source.lengthCapacityNm - earlier.lengthCapacityNm) < 0.15,
      `${subject} ${angle}: the reduced model does not reproduce the length audit ` +
      `(${entry.source.lengthCapacityNm} vs ${earlier.lengthCapacityNm})`);
    compared++;
  }
  assert(compared >= 7, `only ${compared} sweep angles were tied to the previous round`);

  // The artifact under test: the reduced model puts knee flexors into the extension direction
  // beyond about 125 deg of flexion, the research-purpose candidate does not.
  const deep = sweep.filter(([angle]) => angle <= -130);
  assert(deep.length >= 3, `${subject}: no deep-flexion sweep angles`);
  for (const [angle, entry] of deep) {
    assert(entry.source.flexorsActingAsExtensorsMaximumNm > 20,
      `${subject} ${angle}: the reduced model no longer shows flexors acting as knee extensors`);
    assert(entry.candidate.flexorsActingAsExtensorsMaximumNm < 1,
      `${subject} ${angle}: the candidate now also puts flexors into the extension direction`);
  }
  const shallow = sweep.filter(([angle]) => angle >= -120);
  assert(shallow.length >= 7, `${subject}: no shallow sweep angles`);
  for (const [angle, entry] of shallow) {
    assert(entry.source.flexorsActingAsExtensorsMaximumNm < 1,
      `${subject} ${angle}: flexors should not extend the knee before 125 deg of flexion`);
    assert.equal(entry.candidate.flexorsActingAsExtensorsMaximumNm, 0,
      `${subject} ${angle}: the candidate shows flexors extending the knee`);
  }

  // The candidate's knee extensor capacity is substantially larger at the deepest shared angle.
  const deepest = sweep[sweep.length - 1][1];
  assert(deepest.candidate.extensorsOnlyLengthNm > 1.5 * deepest.source.extensorsOnlyLengthNm,
    `${subject}: the candidate is not stronger than the reduced model at deep flexion`);

  const knee = data.targetFrame.knee_angle_r;
  assert.equal(knee.source.demandToLengthBound > 1, subject === 'AB01',
    `${subject}: the reduced-model right knee result changed`);
  assert.equal(knee.candidate.demandToLengthBound > 1, subject === 'AB01',
    `${subject}: the cross-model right knee result changed`);
  assert.equal(data.candidatePoseClampedCoordinates.includes('knee_angle_r'), subject === 'AB01',
    `${subject}: the candidate pose clamp on the right knee changed`);
  if (subject === 'AB01') {
    // A clamped pose means the candidate number is its range limit, never the requested angle.
    assert(knee.candidate.poseClamped && Math.abs(knee.candidate.appliedPoseDeg + 140) < 0.01,
      'the AB01 candidate right knee is no longer reported at its range limit');
  } else {
    assert.equal(knee.candidate.poseClamped, false,
      'the AB02 candidate right knee should be inside its coordinate range');
    assert(knee.candidate.demandToLengthBound < 1,
      'the AB02 right knee is expected to stay within the candidate bound');
  }
}

// The candidate must be the research-purpose model, not a scaled copy of the reduced one.
assert.equal(cross.subjects.AB01.muscleCount.source, 54);
assert.equal(cross.subjects.AB01.muscleCount.candidate, 80);
assert.equal(cross.subjects.AB01.targetFrame.knee_angle_l.candidate.demandSign, -1,
  'the candidate knee demand sign convention changed');

console.log(`Cross-model length capacity verified: ${compared} sweep angles tie back to the ` +
  `reduced-model audit; the candidate removes the hamstring-as-knee-extensor artifact ` +
  `(0 vs ${cross.subjects.AB01.sweep['-140.0'].source.flexorsActingAsExtensorsMaximumNm} N m at ` +
  `140 deg) and is 1.5x stronger there, yet the AB01 right knee still exceeds its bound ` +
  `(${cross.subjects.AB01.targetFrame.knee_angle_r.candidate.demandToLengthBound}) while AB02 ` +
  `does not (${cross.subjects.AB02.targetFrame.knee_angle_r.candidate.demandToLengthBound}).`);
