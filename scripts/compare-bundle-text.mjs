// Compare the rendered Chinese wording of two production builds.
//
// The page text is written in template literals, so after editing wording the only cheap way to prove
// that nothing else changed is to diff the wording itself. This script extracts every Chinese text run
// from both inlined bundles and reports the differences; it also writes a report file, because a
// cp936 console cannot print CJK reliably.
//
// Usage:
//   node scripts/compare-bundle-text.mjs <previous-index.html> [--strict]
// `--strict` makes a difference fail the run (useful when only a known wording change is expected).

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const TEXT_RUN = /[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef·「」“”％≈↗×°／＋－]{3,}/g;

function textRuns(file) {
  const runs = new Set();
  for (const match of readFileSync(file, 'utf8').matchAll(TEXT_RUN)) runs.add(match[0]);
  return runs;
}

const [previous, ...flags] = process.argv.slice(2);
if (!previous) {
  console.error('usage: node scripts/compare-bundle-text.mjs <previous-index.html> [--strict]');
  process.exit(2);
}
const strict = flags.includes('--strict');
const previousPath = resolve(previous);
const currentPath = resolve('dist/index.html');

const before = textRuns(previousPath);
const after = textRuns(currentPath);
const onlyBefore = [...before].filter(run => !after.has(run));
const onlyAfter = [...after].filter(run => !before.has(run));

const report = [
  '# production wording comparison',
  '',
  `previous: ${previousPath} (${before.size} text runs)`,
  `current : ${currentPath} (${after.size} text runs)`,
  '',
  `## only in the previous build (${onlyBefore.length})`,
  ...onlyBefore.map(run => `- ${run}`),
  '',
  `## only in the current build (${onlyAfter.length})`,
  ...onlyAfter.map(run => `- ${run}`),
  '',
];
writeFileSync('bundle-text-diff.md', report.join('\n'), 'utf8');

console.log(`previous build: ${before.size} Chinese text runs`);
console.log(`current build : ${after.size} Chinese text runs`);
console.log(`only in previous: ${onlyBefore.length}, only in current: ${onlyAfter.length}`);
console.log('full report written to bundle-text-diff.md');
if (onlyBefore.length || onlyAfter.length) {
  console.log(strict
    ? 'differences found and --strict was requested: failing'
    : 'review the report and confirm every difference is intentional');
  process.exitCode = strict ? 1 : 0;
}
