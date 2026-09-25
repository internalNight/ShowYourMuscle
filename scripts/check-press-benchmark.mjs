import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';

const bundled = await build({
  entryPoints: ['src/model.ts'], bundle: true, platform: 'node', format: 'esm', write: false,
});
const { createPose } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);

// An et al. (2025), Korean Journal of Applied Biomechanics 35(2), Table 5.
// DOI: 10.5103/KJAB.2025.35.2.76. These are group-level standing barbell
// observations, not subject-level validation or complete press dynamics.
const study = JSON.parse(readFileSync('src/data/standing_press_study.json', 'utf8'));
assert.equal(study.status, 'published_group_summary_not_individual_validation');
assert.equal(study.participants, 14);
const measured = {
  heightCm: study.meanHeightCm,
  verticalRangeCm: study.barbellAscentVerticalRangeCm,
  apRangeCm: study.barbellAscentAnteriorPosteriorRangeCm,
};
const profile = { heightCm: measured.heightCm, weightKg: 68.07 };
const samples = Array.from({ length: 101 }, (_, index) => createPose(profile, 'press', index / 200));
const start = samples[0];
const end = samples.at(-1);
const verticalRangeCm = (end.wristR.y - start.wristR.y) * 100;
const startApCm = (start.wristR.z - start.shoulderR.z) * 100;
const endApCm = (end.wristR.z - end.shoulderR.z) * 100;
const apSamplesCm = samples.map(pose => (pose.wristR.z - pose.shoulderR.z) * 100);
const maxApCm = Math.max(...apSamplesCm);
const minApCm = Math.min(...apSamplesCm);
const peakIndex = apSamplesCm.indexOf(maxApCm);
const apRangeCm = maxApCm - minApCm;

assert.ok(Math.abs(verticalRangeCm - measured.verticalRangeCm.mean) <= measured.verticalRangeCm.sd,
  `Vertical bar range ${verticalRangeCm} cm outside the study's mean ± SD`);
assert.ok(Math.abs(apRangeCm - measured.apRangeCm.mean) <= measured.apRangeCm.sd,
  `AP bar range ${apRangeCm} cm outside the study's mean ± SD`);
assert.ok(Math.abs(maxApCm - study.barbellAscentAnteriorMaxCm.mean) <= study.barbellAscentAnteriorMaxCm.sd,
  `Maximum anterior shoulder-to-bar distance ${maxApCm} cm outside the study's mean ± SD`);
assert.ok(Math.abs(minApCm - study.barbellAscentAnteriorMinCm.mean) <= study.barbellAscentAnteriorMinCm.sd,
  `Minimum anterior shoulder-to-bar distance ${minApCm} cm outside the study's mean ± SD`);
assert.ok(peakIndex > 0 && peakIndex < samples.length / 2 && maxApCm > startApCm &&
  endApCm < startApCm && endApCm > 0,
  'Illustrative bar should move forward early, then back toward the shoulder while staying anterior');
console.log(JSON.stringify({ measured, illustration: {
  verticalRangeCm, apRangeCm, startApCm, maxApCm, endApCm, peakAscentFraction: peakIndex / 100,
}}, null, 2));
