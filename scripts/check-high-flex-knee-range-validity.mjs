// Guards where the candidate model's knee-capacity claim is valid.
//
// docs/data/high_flex_knee_range_validity.json answers why the candidate's knee capacity bumps at
// 120 deg and whether the AB01 right-knee shortfall survives inside the range where the candidate's
// patellofemoral geometry is data-backed. Four things must stay true: the model's patellofemoral
// splines must be the only angle-limited geometry, the moment-arm peak must sit exactly on their last
// knot, the frame-by-frame comparison must reproduce the previously reported deepest-frame ratios, and
// the split at 120 deg must keep showing that the shortfall is confined beyond it.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = name => JSON.parse(readFileSync(`docs/data/${name}`, 'utf8'));
const validity = read('high_flex_knee_range_validity.json');
const cross = read('high_flex_length_capacity.json');

const limit = validity.patellofemoralSplineLimitDeg;
assert(Math.abs(limit - 120) < 0.01, `the patellofemoral spline limit moved to ${limit} deg`);

// Only the patellofemoral joint is spline-driven, so only it can end the model's data range.
const ranges = validity.patellofemoralTransformRanges;
const splines = Object.entries(ranges).filter(([, info]) => info.function === 'SimmSpline');
assert.equal(splines.length, 3,
  `expected three patellofemoral splines, found ${splines.length}`);
for (const [axis, info] of splines) {
  assert.equal(info.knotCount, 13, `${axis}: knot count changed to ${info.knotCount}`);
  assert.equal(info.rangeDeg[0], 0, `${axis}: the spline no longer starts at 0 deg`);
  assert(Math.abs(info.rangeDeg[1] - limit) < 1e-6,
    `${axis}: the spline ends at ${info.rangeDeg[1]} deg instead of ${limit}`);
}

let worstInsideCandidate = 0;
let worstInsideSource = 0;
for (const [subject, data] of Object.entries(validity.subjects)) {
  // The candidate can be posed deeper than its patellofemoral data, which is the whole problem.
  assert(data.candidateMaximumFlexionDeg > limit,
    `${subject}: the knee range no longer extends past the spline limit`);
  assert.equal(data.frames.length, 101, `${subject}: frame count changed`);

  // The moment-arm curve must peak exactly on the last knot, with the slope changing sign there.
  const profile = data.momentArmProfile;
  const peak = profile.maximumAbsoluteArm;
  assert(Math.abs(peak.appliedFlexionDeg - limit) < 0.01,
    `${subject}: the ${profile.muscle} peak sits at ${peak.appliedFlexionDeg} deg, not at the ` +
    `spline limit`);
  const slope = profile.slopeAtBoundaryCmPerDeg;
  assert.equal(slope.signFlip, true, `${subject}: the moment-arm slope no longer flips at the limit`);
  assert(slope.before > 0.03 && slope.after < -0.02,
    `${subject}: the boundary slopes changed (${slope.before} then ${slope.after} cm/deg)`);
  const boundary = profile.samples.filter(sample =>
    Math.abs(sample.appliedFlexionDeg - limit) < 1e-6);
  assert.equal(boundary.length, 1, `${subject}: the fine grid no longer lands on the limit`);

  // Inside the data-backed range nothing exceeds either model's bound.
  const inside = data.summary.within;
  assert(inside.frames > 0, `${subject}: no frames inside the patellofemoral data range`);
  assert(inside.maximumFlexionDeg <= limit, `${subject}: the inside split is above the limit`);
  assert.equal(inside.sourceFramesOverOne, 0,
    `${subject}: ${inside.sourceFramesOverOne} frames inside the range now exceed the reduced bound`);
  assert.equal(inside.candidateFramesOverOne, 0,
    `${subject}: ${inside.candidateFramesOverOne} frames inside the range now exceed the candidate`);
  assert(inside.sourceMaximumRatio < 1 && inside.candidateMaximumRatio < 1,
    `${subject}: the inside-range maximum ratio reached 1`);
  worstInsideCandidate = Math.max(worstInsideCandidate, inside.candidateMaximumRatio);
  worstInsideSource = Math.max(worstInsideSource, inside.sourceMaximumRatio);
  for (const frame of data.frames) {
    if (frame.flexionDeg > limit) continue;
    assert(frame.candidateRatio < 1 && frame.sourceRatio < 1,
      `${subject} ${frame.timeS}s: an inside-range frame exceeds a bound`);
  }

  // Beyond it, only AB01 shows a shortfall, in both models.
  const beyond = data.summary.beyond;
  assert(beyond.frames > 0, `${subject}: no frames beyond the patellofemoral data range`);
  assert.equal(beyond.sourceFramesOverOne > 0, subject === 'AB01',
    `${subject}: the reduced-model deep-flexion result changed`);
  assert.equal(beyond.candidateFramesOverOne > 0, subject === 'AB01',
    `${subject}: the candidate deep-flexion result changed`);
  assert.equal(beyond.sourceMaximumRatio > 1, subject === 'AB01',
    `${subject}: the reduced-model deep-flexion maximum changed`);

  // The deepest frame must still reproduce the numbers reported by the cross-model comparison.
  const knee = cross.subjects[subject].targetFrame.knee_angle_r;
  const deepest = data.frames.reduce((best, frame) =>
    Math.abs(frame.timeS - data.deepestFrameTimeS) < Math.abs(best.timeS - data.deepestFrameTimeS)
      ? frame : best);
  assert(Math.abs(deepest.timeS - data.deepestFrameTimeS) < 1e-9,
    `${subject}: the deepest frame is missing from the frame list`);
  assert(Math.abs(deepest.sourceRatio - knee.source.demandToLengthBound) < 0.01,
    `${subject}: the deepest-frame reduced-model ratio no longer matches ` +
    `(${deepest.sourceRatio} vs ${knee.source.demandToLengthBound})`);
  assert(Math.abs(deepest.candidateRatio - knee.candidate.demandToLengthBound) < 0.01,
    `${subject}: the deepest-frame candidate ratio no longer matches ` +
    `(${deepest.candidateRatio} vs ${knee.candidate.demandToLengthBound})`);
  // For AB01 the clamped deepest frame is also the worst frame beyond the data range; for AB02 the
  // worst frame is shallower, so only that one is tied here.
  if (subject === 'AB01') {
    assert(Math.abs(beyond.candidateMaximumRatio - knee.candidate.demandToLengthBound) < 0.01,
      `${subject}: the candidate maximum is no longer the clamped deepest frame`);
  } else {
    assert(beyond.candidateMaximumRatio > knee.candidate.demandToLengthBound,
      `${subject}: the worst frame beyond the data range should be shallower than the deepest one`);
  }
}

const ab01 = validity.subjects.AB01;
const ab02 = validity.subjects.AB02;
console.log(`Knee validity range verified: the candidate's three patellofemoral splines end at ` +
  `${limit} deg, the knee extensor moment arm peaks exactly there ` +
  `(${ab01.momentArmProfile.maximumAbsoluteArm.momentArmCm} cm, slope ` +
  `${ab01.momentArmProfile.slopeAtBoundaryCmPerDeg.before} to ` +
  `${ab01.momentArmProfile.slopeAtBoundaryCmPerDeg.after} cm/deg). Inside that range no frame ` +
  `exceeds either model's bound (reduced model ${ab01.summary.within.sourceMaximumRatio} / ` +
  `${ab02.summary.within.sourceMaximumRatio}, candidate ${ab01.summary.within.candidateMaximumRatio}` +
  ` / ${ab02.summary.within.candidateMaximumRatio}), and the AB01 shortfall appears only in the ` +
  `${ab01.summary.beyond.frames} frames beyond it (${ab01.summary.beyond.sourceFramesOverOne} frames ` +
  `over the reduced bound, ${ab01.summary.beyond.candidateFramesOverOne} over the candidate); ` +
  `AB02 never exceeds either bound.`);
