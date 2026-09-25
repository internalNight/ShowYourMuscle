import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { readFileSync, writeFileSync } from 'node:fs';

const fractions = JSON.parse(readFileSync('src/data/squat_mass_template.json', 'utf8')).fractions;
assert(Math.abs(fractions.torso + fractions.pelvis + 2 *
  (fractions.thighEach + fractions.shankEach + fractions.footEach) - 1) < 1e-8);
const bundled = await build({ entryPoints: ['src/mechanics.ts'], bundle: true, platform: 'node',
  format: 'esm', write: false });
const { squatBalanceEstimate } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const profiles = [
  { heightCm: 175, weightKg: 72 },
  { heightCm: 190, weightKg: 90, armSpanCm: 197, inseamCm: 90 },
  { heightCm: 150, weightKg: 46, armSpanCm: 146, inseamCm: 69 },
];
const rows = [];
for (const profile of profiles) {
  for (const loadKg of [0, 20, 60]) {
    for (const offsetCm of [-6, 0, 6]) {
      for (const phase of [0, 0.25, 0.5, 0.75, 1]) {
        const result = squatBalanceEstimate(profile, phase, loadKg, offsetCm);
        assert(Object.values(result).every(Number.isFinite));
        assert(Math.abs(result.totalGravityN - (profile.weightKg + loadKg) * 9.80665) < 1e-8);
        if (loadKg === 0) assert(Math.abs(result.combinedComRelativeAnkleCm - result.bodyComRelativeAnkleCm) < 1e-9);
        rows.push({ profile, phase, loadKg, offsetCm, ...result });
      }
    }
  }
}
const center = rows.find(row => row.profile.heightCm === 175 && row.loadKg === 20 && row.offsetCm === 0 && row.phase === 0.5);
assert(center && Math.abs(center.combinedComRelativeAnkleCm) < 5,
  'revised illustrative bottom pose should keep the coarse gravity center near the ankle');
const result = {
  status: 'revised_pose_research_balance_probe_not_personal_cop_or_joint_force',
  method: 'Mass fractions from the public scaled gait2354 template; approximate segment centers projected onto the illustrative squat pose. Zero-acceleration equilibrium would require vertical ground reaction under the combined center of mass. Actual foot CoP, acceleration and segment mass distribution are unknown.',
  centerBottom: center,
  rows,
};
writeFileSync('docs/data/squat_balance_probe.json', `${JSON.stringify(result, null, 2)}\n`);
console.log(`Squat balance probe: ${rows.length} scenarios; default 20 kg bottom combined center ${center.combinedComRelativeAnkleCm.toFixed(1)} cm relative to ankle.`);
