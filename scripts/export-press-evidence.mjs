// Export a small, clearly labeled seated-press EMG research reference.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const audit = JSON.parse(readFileSync(resolve(root,
  'docs/data/seated_overhead_press_emg_audit.json'), 'utf8'));
const keys = ['pectoralis_clavicular', 'deltoid_anterior', 'deltoid_middle',
  'deltoid_posterior', 'triceps_lateral', 'trapezius_upper'];
if (audit.status !== 'research_seated_press_phase_mean_emg_not_standing_press_or_muscle_force_validation' ||
    audit.sourceWorkbookMd5 !== 'e8b6c718179c993b0817208341e84130' ||
    audit.sourceLicense !== 'CC BY 4.0 per Zenodo API record 5744051' ||
    Object.keys(audit.muscles).length !== 6 || keys.some(key => {
      const row = audit.muscles[key];
      return row?.participants !== 8 ||
        !Number.isFinite(row.frontBarbellConcentricMeanPctReference) ||
        !Number.isFinite(row.frontBarbellEccentricMeanPctReference) ||
        row.frontConcentricMinusEccentric.peopleHigher +
          row.frontConcentricMinusEccentric.peopleLower +
          row.frontConcentricMinusEccentric.peopleTied !== 8;
    })) {
  throw new Error('The seated press source audit is missing or inconsistent.');
}
const muscles = Object.fromEntries(keys.map(key => [key, {
  concentricMeanPctReference: audit.muscles[key].frontBarbellConcentricMeanPctReference,
  eccentricMeanPctReference: audit.muscles[key].frontBarbellEccentricMeanPctReference,
  participantsConcentricHigher: audit.muscles[key].frontConcentricMinusEccentric.peopleHigher,
}]));
const output = {
  schemaVersion: 1,
  status: audit.status,
  participants: 8,
  muscles,
  sourceUrl: 'https://doi.org/10.3389/fphys.2022.825880',
  dataUrl: 'https://zenodo.org/records/5744051',
  licenseUrl: 'https://creativecommons.org/licenses/by/4.0/',
};
const path = resolve(root, 'src/data/press_emg_study.json');
writeFileSync(path, JSON.stringify(output, null, 2) + '\n');
console.log(`Wrote ${path}`);
