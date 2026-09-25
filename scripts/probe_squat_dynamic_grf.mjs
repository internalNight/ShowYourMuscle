// Check whether the teaching trajectory can support a dynamic GRF scenario.
// This computes only m(g+a_COM), not net joint or muscle forces.
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { readFileSync, writeFileSync } from 'node:fs';

const bundled = await build({ entryPoints: ['src/mechanics.ts'], bundle: true, platform: 'node',
  format: 'esm', write: false });
const { squatBalanceEstimate, squatVerticalSupportScenario } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const args = process.argv.slice(2);
const option = name => { const index = args.indexOf(name); return index < 0 ? undefined : args[index + 1]; };
const squatDepthDeg = option('--depth-deg') === undefined ? undefined : Number(option('--depth-deg'));
const durationS = Number(option('--duration-s') ?? JSON.parse(readFileSync('src/data/demo_motion_protocol.json', 'utf8')).cycleDurationS);
const output = option('--out') ?? 'docs/data/squat_dynamic_grf_probe.json';
if (args.some(arg => arg.startsWith('--') && !['--depth-deg', '--duration-s', '--out'].includes(arg)) ||
    ['--depth-deg', '--duration-s', '--out'].some(name => args.includes(name) && !option(name)) ||
    !Number.isFinite(durationS) || durationS < 1.5 || durationS > 6 ||
    (squatDepthDeg !== undefined && (!Number.isFinite(squatDepthDeg) || squatDepthDeg < 60 || squatDepthDeg > 135))) {
  throw new Error('Usage: node scripts/probe_squat_dynamic_grf.mjs [--depth-deg 60..135] [--duration-s 1.5..6] [--out result.json]');
}
const profiles = [
  { heightCm: 175, weightKg: 72 },
  { heightCm: 190, weightKg: 90, armSpanCm: 197, inseamCm: 90 },
  { heightCm: 150, weightKg: 46, armSpanCm: 146, inseamCm: 69 },
];
const rows = [];
for (const profile of profiles) {
  for (const loadKg of [0, 20, 60]) {
    const frames = [];
    for (let i = 1; i < 100; i++) {
      const phase = i / 100;
      const current = squatBalanceEstimate(profile, phase, loadKg, 0, squatDepthDeg);
      const scenario = squatVerticalSupportScenario(profile, phase, loadKg, durationS, 0, squatDepthDeg);
      const { accelerationMs2, verticalSupportN: forceN } = scenario;
      assert(Number.isFinite(forceN) && forceN > 0,
        'illustrative squat trajectory must have finite, positive vertical support');
      frames.push({ phase, accelerationMs2, forceN,
        bodyComHeightM: current.bodyComHeightM, combinedComHeightM: current.combinedComHeightM });
    }
    const minForceN = Math.min(...frames.map(frame => frame.forceN));
    const maxForceN = Math.max(...frames.map(frame => frame.forceN));
    rows.push({ profile, loadKg, minForceN, maxForceN,
      minimumRatioToStaticWeight: minForceN / ((profile.weightKg + loadKg) * 9.80665),
      maximumRatioToStaticWeight: maxForceN / ((profile.weightKg + loadKg) * 9.80665),
      deepest: frames[49], frames: profile.heightCm === 175 && (loadKg === 0 || loadKg === 20)
        ? frames : undefined });
  }
}
const result = {
  status: 'illustrative_trajectory_dynamic_force_probe_not_validated_personal_prediction',
  method: `0.01-phase central second derivative of template segment COM plus barbell height, with the prescribed ${durationS} s squat animation. Total vertical support scenario is (body + bar mass) times (g + COM vertical acceleration). No measured motion, foot contact, net joint moments or muscle forces.`,
  durationS, squatDepthDeg: squatDepthDeg ?? null, rows,
};
writeFileSync(output, `${JSON.stringify(result, null, 2)}\n`);
for (const row of rows) {
  console.log(`${row.profile.heightCm} cm/${row.profile.weightKg} kg + ${row.loadKg} kg: ${row.minForceN.toFixed(0)}–${row.maxForceN.toFixed(0)} N (${row.minimumRatioToStaticWeight.toFixed(2)}–${row.maximumRatioToStaticWeight.toFixed(2)} × static weight)`);
}
