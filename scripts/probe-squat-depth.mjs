// Evaluate whether simple knee-depth presets remain geometrically feasible.
// This is a teaching-model screen, not a measured athlete or force validation.
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { writeFileSync } from 'node:fs';

const bundled = await build({ stdin: { contents:
  "export { createPose, squatKneeFlexionDeg, profileSegmentDimensions } from './src/model.ts'; export { squatBalanceEstimate } from './src/mechanics.ts';",
  resolveDir: process.cwd(), loader: 'ts' }, bundle: true, platform: 'node', format: 'esm', write: false });
const { createPose, squatKneeFlexionDeg, profileSegmentDimensions, squatBalanceEstimate } =
  await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const profiles = [
  { heightCm: 175, weightKg: 72, armSpanCm: 175, inseamCm: 80 },
  { heightCm: 150, weightKg: 46, armSpanCm: 146, inseamCm: 69 },
  { heightCm: 190, weightKg: 90, armSpanCm: 197, inseamCm: 90 },
];
const choices = [null, 75, 117, 130];
const rows = [];
for (const profile of profiles) {
  const segments = profileSegmentDimensions(profile);
  for (const target of choices) {
    const phases = Array.from({ length: 101 }, (_, index) => index / 100);
    const values = phases.map(phase => {
      const pose = createPose(profile, 'squat', phase, 0, target ?? undefined);
      const balance = squatBalanceEstimate(profile, phase, 20, 0, target ?? undefined);
      const femurErrorM = Math.abs(pose.hipR.distanceTo(pose.kneeR) - segments.femurM);
      const tibiaErrorM = Math.abs(pose.kneeR.distanceTo(pose.ankleR) - segments.tibiaM);
      assert(femurErrorM < 1e-6 && tibiaErrorM < 1e-6);
      assert(Number.isFinite(balance.combinedComRelativeAnkleCm) && pose.pelvis.y > 0.3 * profile.heightCm / 175);
      return { kneeFlexionDeg: squatKneeFlexionDeg(pose),
        pelvisHeightM: pose.pelvis.y,
        combinedComRelativeAnkleCm: balance.combinedComRelativeAnkleCm,
        kneeForwardRelativeAnkleCm: (pose.kneeR.z - pose.ankleR.z) * 100 };
    });
    const bottom = values[50];
    if (target !== null) assert(Math.abs(bottom.kneeFlexionDeg - target) < 1e-6,
      `requested ${target}°, got ${bottom.kneeFlexionDeg}°`);
    rows.push({ profile, targetDepthDeg: target, startingKneeFlexionDeg: values[0].kneeFlexionDeg,
      bottomKneeFlexionDeg: bottom.kneeFlexionDeg,
      bottomPelvisHeightM: bottom.pelvisHeightM,
      bottomKneeForwardRelativeAnkleCm: bottom.kneeForwardRelativeAnkleCm,
      bottomCombinedComRelativeAnkleCm: bottom.combinedComRelativeAnkleCm,
      maximumAbsoluteComRelativeAnkleCm: Math.max(...values.map(value => Math.abs(value.combinedComRelativeAnkleCm))) });
  }
}
const result = { status: 'illustrative_depth_geometry_not_validated_squat_technique_or_force',
  description: 'Knee target changes the bottom hip height with fixed femur and tibia lengths; posterior hip offset and torso lean remain the illustrative defaults. 20 kg barbell COM is a static gravity probe only.',
  rows };
writeFileSync('docs/data/squat_depth_probe.json', `${JSON.stringify(result, null, 2)}\n`);
for (const row of rows) console.log(`${row.profile.heightCm}cm target=${row.targetDepthDeg ?? 'old'}: knee=${row.bottomKneeFlexionDeg.toFixed(1)}°, bottom pelvis=${row.bottomPelvisHeightM.toFixed(2)}m, COM vs ankle=${row.bottomCombinedComRelativeAnkleCm.toFixed(1)}cm`);
