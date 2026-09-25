import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';

const bundled = await build({ entryPoints: ['src/mechanics.ts'], bundle: true, platform: 'node',
  format: 'esm', write: false });
const { barbellGravityMoments, benchBarbellMomentScenarios, squatBalanceEstimate, squatVerticalSupportScenario } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const profiles = [
  { heightCm: 175, weightKg: 72 },
  { heightCm: 190, weightKg: 90, armSpanCm: 197, inseamCm: 90 },
  { heightCm: 150, weightKg: 46, armSpanCm: 146, inseamCm: 69 },
];
for (const profile of profiles) {
  for (const exercise of ['squat', 'bench', 'press']) {
    for (const phase of [0, 0.25, 0.5, 0.75, 1]) {
      const light = barbellGravityMoments(profile, exercise, phase, 20);
      const heavy = barbellGravityMoments(profile, exercise, phase, 40);
      assert.equal(light.length, exercise === 'squat' ? 3 : 2);
      for (let index = 0; index < light.length; index++) {
        const a = light[index], b = heavy[index];
        assert(Number.isFinite(a.leverArmCm) && a.leverArmCm >= 0);
        assert(Number.isFinite(a.momentNm) && a.momentNm >= 0);
        assert(Math.abs(a.momentNm * 2 - b.momentNm) < 1e-9);
        assert(Math.abs(a.leverArmCm - b.leverArmCm) < 1e-9);
        assert(Math.abs(a.momentNm - 20 * 9.80665 / 2 * a.leverArmCm / 100) < 1e-9);
      }
    }
  }
}
const squatTop = barbellGravityMoments(profiles[0], 'squat', 0, 60);
const squatBottom = barbellGravityMoments(profiles[0], 'squat', 0.5, 60);
assert(squatBottom[0].momentNm > squatTop[0].momentNm, 'bar moment about hip should grow with bottom position');
const deeperMoments = barbellGravityMoments(profiles[0], 'squat', 0.5, 60, 0, 117);
const deeperBalance = squatBalanceEstimate(profiles[0], 0.5, 60, 0, 117);
assert(Math.abs(deeperMoments[1].leverArmCm - squatBottom[1].leverArmCm) > 0.1,
  'selected squat depth must change knee geometry in the load calculation');
assert(Math.abs(deeperBalance.combinedComRelativeAnkleCm
  - squatBalanceEstimate(profiles[0], 0.5, 60).combinedComRelativeAnkleCm) > 0.1,
  'selected squat depth must change the static body balance estimate');
for (const profile of profiles) {
  for (const phase of [0, 0.25, 0.5, 0.75, 1]) {
    const bodyOnly = squatBalanceEstimate(profile, phase, 0);
    const centered = squatBalanceEstimate(profile, phase, 60);
    const barForward = squatBalanceEstimate(profile, phase, 60, 6);
    assert(Math.abs(bodyOnly.combinedComRelativeAnkleCm - bodyOnly.bodyComRelativeAnkleCm) < 1e-9);
    assert(Math.abs(centered.totalGravityN - (profile.weightKg + 60) * 9.80665) < 1e-8);
    assert(Math.abs(barForward.combinedComRelativeAnkleCm - centered.combinedComRelativeAnkleCm
      - 6 * 60 / (profile.weightKg + 60)) < 1e-8,
    'moving only the bar forward must shift the combined gravity line by its mass-weighted displacement');
  }
}
for (const depth of [75, undefined, 117]) {
  for (const profile of profiles) {
    for (const phase of [0.01, 0.25, 0.5, 0.75, 0.99]) {
      const fast = squatVerticalSupportScenario(profile, phase, 20, 2, 0, depth);
      const slow = squatVerticalSupportScenario(profile, phase, 20, 4, 0, depth);
      assert.equal(fast.staticWeightN, slow.staticWeightN);
      assert(Math.abs(fast.accelerationMs2 - slow.accelerationMs2 * 4) < 1e-8);
      assert(Number.isFinite(fast.verticalSupportN) && fast.verticalSupportN > 0);
      assert(Number.isFinite(slow.verticalSupportN) && slow.verticalSupportN > 0);
    }
  }
}
const bottomSupport = squatVerticalSupportScenario(profiles[0], 0.5, 20, 2.8);
assert(bottomSupport.accelerationMs2 > 0 && bottomSupport.verticalSupportN > bottomSupport.staticWeightN);
const probe = JSON.parse(readFileSync('docs/data/squat_dynamic_grf_probe.json', 'utf8'));
const reference = probe.rows.find(row => row.profile.heightCm === 175 && row.loadKg === 20).deepest;
assert(Math.abs(bottomSupport.verticalSupportN - reference.forceN) < 1e-7);
for (const phase of [0, 0.25, 0.5, 0.75, 1]) {
  const back = barbellGravityMoments(profiles[0], 'squat', phase, 60, -6);
  const center = barbellGravityMoments(profiles[0], 'squat', phase, 60, 0);
  const front = barbellGravityMoments(profiles[0], 'squat', phase, 60, 6);
  assert.notDeepEqual(back.map(item => item.leverArmCm), front.map(item => item.leverArmCm),
    'changing the bar line must change at least one displayed joint lever arm');
  for (let index = 0; index < 3; index++) {
    const distances = [back[index].leverArmCm, center[index].leverArmCm, front[index].leverArmCm];
    assert(Math.abs(distances[0] - distances[1]) <= 6 + 1e-9);
    assert(Math.abs(distances[2] - distances[1]) <= 6 + 1e-9);
    assert(distances[0] + distances[2] >= 12 - 1e-9,
      'two load lines 12 cm apart must have a combined lever arm of at least 12 cm');
    assert(distances[0] + distances[2] >= 2 * distances[1] - 1e-9,
      'absolute lever arms must be convex around the default load line');
  }
}
const benchFrames = JSON.parse(readFileSync('public/data/bench_tsm_reference.json', 'utf8')).frames;
const benchStudy = JSON.parse(readFileSync('src/data/bench_lateral_force_study.json', 'utf8'));
assert.equal(benchStudy.subjectMeanLateralPercentOfAssumedVertical.length, 10);
assert.equal(benchStudy.subjectMeanHorizontalForceN.length, 10);
assert.equal(benchStudy.assumedVerticalForcePerHandN, 78.48);
for (let index = 0; index < 10; index++) {
  const observedPercent = 100 * benchStudy.subjectMeanHorizontalForceN[index] / 78.48;
  assert(Math.abs(observedPercent - benchStudy.subjectMeanLateralPercentOfAssumedVertical[index]) < 0.1,
    'published horizontal force and published percentage should agree to their rounding precision');
}
const empiricalPercent = [...benchStudy.subjectMeanLateralPercentOfAssumedVertical].sort((a, b) => a - b);
assert.equal(empiricalPercent[0], -62.4);
assert.equal(empiricalPercent.at(-1), 115.8);
const empiricalMedian = (empiricalPercent[4] + empiricalPercent[5]) / 2;
assert(Math.abs(empiricalMedian - 18.05) < 1e-9);
for (const phase of [0, 25, 50, 75, 100]) {
  const frame = benchFrames[phase];
  const scenarios = benchBarbellMomentScenarios(frame, 175, 20);
  const doubleLoad = benchBarbellMomentScenarios(frame, 175, 40);
  const tall = benchBarbellMomentScenarios(frame, 190, 20);
  assert.deepEqual(scenarios.map(item => item.handEffortLateralRatio), [-0.1, 0, 0.4]);
  for (let index = 0; index < scenarios.length; index++) {
    for (const key of ['shoulderMomentNm', 'elbowMomentNm']) {
      assert(Number.isFinite(scenarios[index][key]) && scenarios[index][key] >= 0);
      assert(Math.abs(scenarios[index][key] * 2 - doubleLoad[index][key]) < 1e-9);
      assert(Math.abs(scenarios[index][key] * 190 / 175 - tall[index][key]) < 1e-9);
    }
  }
  const vertical = 20 * 9.80665 / 2;
  const hand = frame.viewerJointsM.hand;
  for (const [jointName, key] of [['shoulder', 'shoulderMomentNm'], ['elbow', 'elbowMomentNm']]) {
    const joint = frame.viewerJointsM[jointName];
    const expected = vertical * Math.hypot(hand[0] - joint[0], hand[2] - joint[2]);
    assert(Math.abs(scenarios[1][key] - expected) < 1e-9);
  }
  assert(benchBarbellMomentScenarios(frame, 175, 0).every(item =>
    item.shoulderMomentNm === 0 && item.elbowMomentNm === 0));
  assert(Math.abs(scenarios[0].shoulderMomentNm - scenarios[2].shoulderMomentNm) > 0.1);
  const empirical = benchBarbellMomentScenarios(frame, 175, 20,
    [empiricalPercent[0], empiricalMedian, empiricalPercent.at(-1)].map(percent => percent / 100));
  assert.equal(empirical.length, 3);
  assert(empirical.every(item => Number.isFinite(item.shoulderMomentNm) && Number.isFinite(item.elbowMomentNm)));
  assert(Math.max(...empirical.map(item => item.shoulderMomentNm))
    - Math.min(...empirical.map(item => item.shoulderMomentNm)) > 0.1);
}
console.log('Bar-only moments and illustrative squat vertical support: geometry, tempo scaling, and research probe consistency verified.');
