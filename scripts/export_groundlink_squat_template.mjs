// Export the existing phone physics formula for an independent lab comparison.
import { build } from 'esbuild';
import { mkdirSync, writeFileSync } from 'node:fs';

const bundled = await build({ entryPoints: ['src/mechanics.ts'], bundle: true,
  platform: 'node', format: 'esm', write: false });
const { squatVerticalSupportScenario } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const profiles = {
  s001: [168, 69.86], s002: [170, 66.68], s003: [159, 53.07],
  s004: [182, 71.67], s005: [195, 90.7], s006: [153, 48.99],
  s007: [175, 63.96],
};
const phases = Array.from({ length: 99 }, (_, i) => (i + 1) / 100);
const rows = Object.entries(profiles).map(([subject, [heightCm, weightKg]]) => {
  const profile = { heightCm, weightKg };
  return { subject, heightCm, weightKg,
    supportRatio: phases.map(phase => squatVerticalSupportScenario(
      profile, phase, 0, 2.8, 0).ratioToStaticWeight),
  };
});
const out = '.cache/groundlink/template_predictions.json';
mkdirSync('.cache/groundlink', { recursive: true });
writeFileSync(out, JSON.stringify({ durationS: 2.8, loadKg: 0,
  phases, rows, status: 'research_only_viewer_formula_not_personal_validation' }, null, 2) + '\n');
console.log(`Saved ${out} for ${rows.length} subjects`);
