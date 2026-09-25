// Export the exact phone support-force formula for the public 0/25-lb study.
import { build } from 'esbuild';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const bundled = await build({
  entryPoints: [fileURLToPath(new URL('../src/mechanics.ts', import.meta.url))],
  bundle: true, platform: 'node', format: 'esm', write: false,
});
const { squatVerticalSupportScenario } = await import(
  `data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const massCsv = readFileSync(new URL('../.cache/lower-limb-raw/Subject_masses.csv', import.meta.url), 'utf8');
const subjects = massCsv.trim().split(/\r?\n/).slice(1).map(line => {
  const [subject, weightKg] = line.split(',');
  return { subject, weightKg: Number(weightKg) };
});
const phases = Array.from({ length: 99 }, (_, i) => (i + 1) / 100);
const loadKg = 25 * 0.45359237;
const durationS = 2.8;
const heightCm = 175; // Source archive does not provide measured subject heights.
const rows = subjects.flatMap(({ subject, weightKg }) =>
  [0, loadKg].map(extraLoadKg => ({
    subject, weightKg, extraLoadKg,
    ratioToStaticTotalWeight: phases.map(phase =>
      squatVerticalSupportScenario({ heightCm, weightKg }, phase,
        extraLoadKg, durationS, 0).ratioToStaticWeight),
  })));
const out = new URL('../.cache/lower-limb/loaded_squat_template_predictions.json', import.meta.url);
mkdirSync(new URL('../.cache/lower-limb/', import.meta.url), { recursive: true });
writeFileSync(out, JSON.stringify({ heightCm, durationS, loadKg, phases, rows,
  status: 'research_only_fixed_phone_template_not_personal_prediction',
  assumption: 'The additional 25 lb travels according to the app squat load path; actual placement is unreported.'
}, null, 2) + '\n');
console.log(`Saved ${fileURLToPath(out)} for ${subjects.length} subjects and two loads`);
