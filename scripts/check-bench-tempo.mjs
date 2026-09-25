import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { build } from 'esbuild';

const bundle = await build({ entryPoints: ['src/tempo.ts'], bundle: true,
  platform: 'node', format: 'esm', write: false, logLevel: 'silent' });
const source = bundle.outputFiles[0].text;
const { benchPlaybackTiming, advanceBenchPhase } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

const close = (actual, expected, tolerance = 1e-9) =>
  assert(Math.abs(actual - expected) <= tolerance, `${actual} != ${expected}`);
const lookup = JSON.parse(readFileSync('public/data/bench_tsm_reference.json', 'utf8'));
const strokeM = lookup.frames[0].viewerJointsM.hand[1]
  - lookup.frames[50].viewerJointsM.hand[1];
const teaching = benchPlaybackTiming('teaching', 175, 2.8);
close(teaching.descentS, 1.4);
close(teaching.ascentS, 1.4);
close(teaching.meanAscentMPerS, strokeM / 1.4);
const fifty = benchPlaybackTiming('study50', 175, 2.8);
const seventyFive = benchPlaybackTiming('study75', 175, 2.8);
close(fifty.descentS, 1);
close(fifty.meanAscentMPerS, 0.8);
close(seventyFive.meanAscentMPerS, 0.55);
assert(fifty.ascentS < seventyFive.ascentS);
close(benchPlaybackTiming('study50', 190, 2.8).meanAscentMPerS, 0.8);
close(advanceBenchPhase(0.5, fifty.ascentS / 2, fifty), 0.75);
close(advanceBenchPhase(0.5, fifty.ascentS, fifty), 0);
close(advanceBenchPhase(0.49, fifty.descentS * 0.04, fifty),
  0.5 + fifty.descentS * 0.02 / (2 * fifty.ascentS));
console.log('Bench playback matches the published median ascent speeds and crosses phase boundaries.');
