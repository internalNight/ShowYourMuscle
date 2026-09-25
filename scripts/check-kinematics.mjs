import assert from 'node:assert/strict';
import { build } from 'esbuild';

const bundled = await build({
  entryPoints: ['src/model.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
});
const source = bundled.outputFiles[0].text;
const { createPose, profileSegmentDimensions, squatBarSagittalZ, squatKneeFlexionDeg } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

const segments = [
  ['hipL', 'kneeL'], ['kneeL', 'ankleL'], ['hipR', 'kneeR'], ['kneeR', 'ankleR'],
  ['shoulderL', 'elbowL'], ['elbowL', 'wristL'], ['shoulderR', 'elbowR'], ['elbowR', 'wristR'],
];
for (const profile of [
  { heightCm: 175, weightKg: 72, armSpanCm: 175, inseamCm: 80 },
  { heightCm: 195, weightKg: 95, armSpanCm: 210, inseamCm: 94 },
  { heightCm: 150, weightKg: 45, armSpanCm: 140, inseamCm: 67 },
]) {
  for (const target of [75, 117]) {
    const standing = createPose(profile, 'squat', 0, 0, target);
    const bottom = createPose(profile, 'squat', 0.5, 0, target);
    const dimensions = profileSegmentDimensions(profile);
    assert.ok(Math.abs(squatKneeFlexionDeg(bottom) - target) < 1e-6,
      `requested bottom knee flexion ${target}° was not reached`);
    assert.ok(Math.abs(standing.pelvis.y - createPose(profile, 'squat', 0).pelvis.y) < 1e-9,
      'depth selection must not change the starting pose');
    for (let step = 0; step <= 20; step++) {
      const pose = createPose(profile, 'squat', step / 20, 0, target);
      assert.ok(Math.abs(pose.hipR.distanceTo(pose.kneeR) - dimensions.femurM) < 1e-6);
      assert.ok(Math.abs(pose.kneeR.distanceTo(pose.ankleR) - dimensions.tibiaM) < 1e-6);
      assert.ok(Math.abs(pose.wristR.z - squatBarSagittalZ(pose.shoulderR.z)) < 1e-9);
    }
  }
  for (const exercise of ['squat', 'bench', 'press']) {
    const base = createPose(profile, exercise, 0);
    for (let step = 0; step <= 20; step++) {
      const pose = createPose(profile, exercise, step / 20);
      for (const [a, b] of segments) {
        const expected = base[a].distanceTo(base[b]);
        const actual = pose[a].distanceTo(pose[b]);
        assert.ok(Number.isFinite(actual) && Math.abs(expected - actual) < 0.001,
          `${exercise} phase=${step / 20} ${a}-${b}: ${actual} vs ${expected}`);
      }
      if (exercise === 'press' || exercise === 'bench') {
        const baseGrip = base.wristL.distanceTo(base.wristR);
        const grip = pose.wristL.distanceTo(pose.wristR);
        assert.ok(Math.abs(grip - baseGrip) < 1e-9,
          `${exercise} phase=${step / 20}: rigid bar grip width changed`);
        assert.ok(Math.abs(pose.wristL.y - pose.wristR.y) < 1e-9 &&
          Math.abs(pose.wristL.z - pose.wristR.z) < 1e-9,
        `${exercise} phase=${step / 20}: hands separated along bar travel direction`);
      }
      assert.ok(Math.abs(pose.pelvis.distanceTo(pose.chest) - profileSegmentDimensions(profile).torsoM) < 0.001,
        `${exercise} phase=${step / 20} torso length changed`);
      if (exercise === 'squat') {
        assert.ok(Math.abs(pose.wristR.z - squatBarSagittalZ(pose.shoulderR.z)) < 1e-9 &&
          Math.abs(pose.wristR.y - pose.shoulderR.y - 0.09) < 1e-9,
        'squat hand should coincide with the illustrative bar line');
        for (const offset of [-6, 6]) {
          const shifted = createPose(profile, exercise, step / 20, offset);
          assert.ok(Math.abs(shifted.wristR.z - squatBarSagittalZ(shifted.shoulderR.z, offset)) < 1e-9);
          assert.ok(Math.abs(shifted.shoulderR.z - pose.shoulderR.z) < 1e-9,
            'changing the bar location must leave the core squat pose unchanged');
        }
      }
    }
  }
}
const shortLeg = { heightCm: 175, weightKg: 72, inseamCm: 72, armSpanCm: 160 };
const longLeg = { heightCm: 175, weightKg: 72, inseamCm: 88, armSpanCm: 190 };
const short = profileSegmentDimensions(shortLeg);
const long = profileSegmentDimensions(longLeg);
assert.ok(long.femurM > short.femurM && long.tibiaM > short.tibiaM,
  'longer inseam should lengthen both leg segments');
assert.ok(long.torsoM < short.torsoM,
  'torso must compensate so height is preserved');
assert.ok(Math.abs((0.54 + 2 * (short.upperArmM + short.forearmM)) * 100 - 160) < 1e-9,
  '160 cm input arm span should equal calibrated shoulder plus arms');
assert.ok(Math.abs((0.54 + 2 * (long.upperArmM + long.forearmM)) * 100 - 190) < 1e-9,
  '190 cm input arm span should equal calibrated shoulder plus arms');
assert.ok(Math.abs(createPose(shortLeg, 'squat', 0).head.y -
  createPose(longLeg, 'squat', 0).head.y) < 1e-9,
  'changing inseam at fixed height must preserve standing head position');
const tallSameInseam = profileSegmentDimensions({ heightCm: 190, weightKg: 80, inseamCm: 80 });
assert.ok(Math.abs(tallSameInseam.appliedInseamCm - 80) < 1e-9,
  'absolute inseam must not be multiplied by height again');
const capped = profileSegmentDimensions({ heightCm: 175, weightKg: 72,
  inseamCm: 120, armSpanCm: 250 });
assert.ok(capped.inseamClamped && capped.armSpanClamped,
  'outlier proportions must be flagged when the teaching geometry caps them');
console.log('3 exercises × 3 body profiles × 21 poses: limb lengths, two selectable squat depths and pressing grip width stable; stature, inseam and arm span calibration checked.');
