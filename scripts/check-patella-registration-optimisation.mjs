// Guards the measured patella registration offset and everything that consumes it.
//
// docs/data/patella_registration_optimisation.json is produced by
// blender/optimise_patella_registration.py. It is not just a report: the offset it found is now part
// of the shipped registration, read by the Blender animator, the attachment screen and the phone
// layer. This check keeps the search honest (the offset must still be the one that removed the
// overlap), keeps every consumer reading the same number, and keeps the card's claim tied to it.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { assertHeadlineCopy, RESEARCH_HEADING } from './card-text.mjs';

const read = name => JSON.parse(readFileSync(`docs/data/${name}`, 'utf8'));
const search = read('patella_registration_optimisation.json');
const audit = read('registered_mesh_integrity_audit.json');
const clearance = read('bone_joint_clearance_probe.json');
const attachment = read('attachment_surface_screen.json');
const main = readFileSync('src/main.ts', 'utf8');

assert.equal(search.status, 'research_only_patella_registration_search');
assert.equal(search.framesChecked, 101);
assert.equal(search.searchedObject, 'atlas_Patella.r');
assert.equal(search.searchedBody, 'patella_r');
assert.equal(search.evaluations >= 20, true, 'the search recorded suspiciously few evaluations');
assert(search.trace.length >= 3, 'the search lost its improvement trace');
assert(search.limitations.length >= 5, 'the search lost its limitations');
assert(search.limitations.some(text => text.includes('single constant')),
  'the search must still say the offset cannot follow the patella');
assert(search.limitations.some(text => text.includes('not an attachment')),
  'the search must still say the offset is not an attachment or joint model');

// The search must have found what it claims to have found.
const { baseline, optimised } = search;
assert.equal(baseline.femurPatellaFrames, 87, 'the recorded baseline overlap changed');
assert.equal(baseline.patellaTibiaFrames, 73, 'the recorded baseline patella-to-tibia overlap changed');
assert(baseline.maximumFemurDepthM > 0.01, 'the baseline patellofemoral penetration shrank');
assert(optimised.femurPatellaFrames < baseline.femurPatellaFrames / 10,
  'the searched offset no longer removes most of the patellofemoral overlap');
assert(optimised.femurPatellaFrames <= 5, 'the searched offset leaves more than grazing frames');
assert.equal(optimised.maximumFemurDepthM, 0, 'the searched offset still leaves measurable depth');
assert.equal(optimised.patellaTibiaFrames, 0, 'the searched offset no longer clears the tibia');
// The patella must stay against the femur: a large gap would mean the search cheated by flying off.
assert(optimised.medianFemurDistanceM > 0.002 && optimised.medianFemurDistanceM < 0.012,
  `the patella now sits ${optimised.medianFemurDistanceM} m from the femur`);
assert(optimised.maximumFemurDistanceM < 0.02,
  'the patella drifted too far from the femur for this to be a registration');
const offset = optimised.offsetM;
assert.equal(offset.length, 3, 'the offset is no longer a three-vector');
assert(Math.abs(optimised.offsetMagnitudeM - Math.hypot(...offset)) < 1e-4,
  'the recorded offset magnitude does not match its components');
assert(optimised.offsetMagnitudeM > 0.02 && optimised.offsetMagnitudeM < 0.04,
  `the searched offset magnitude is now ${optimised.offsetMagnitudeM} m`);

// Every consumer must read this report, and the shipped scenes must agree with it.
const animator = readFileSync('blender/animate_registered_bones.py', 'utf8');
assert(animator.includes('patella_registration_optimisation.json'),
  'the bone animator no longer reads the search report');
assert(animator.includes('Matrix.Translation(offset)'),
  'the bone animator no longer applies a per-bone offset');
const screen = readFileSync('blender/probe_attachment_surfaces.py', 'utf8');
assert(screen.includes('patella_registration_optimisation.json'),
  'the attachment screen no longer reads the search report');
const model = readFileSync('src/model.ts', 'utf8');
assert(model.includes('patella_registration_optimisation.json'),
  'the phone layer no longer imports the search report');
assert(model.includes('boneOffsets') && model.includes('patellaRegistration.searchedBody'),
  'the phone layer no longer applies the per-bone offset');
assert(model.includes('boneOffsets.get(body)'),
  'the phone layer no longer looks the offset up per body');

const patellaPair = audit.bonePairIntersections['atlas_Femur.r+atlas_Patella.r'];
assert.equal(patellaPair.frames.length, optimised.femurPatellaFrames,
  'the audited patellofemoral overlap disagrees with the search that removed it');
assert.equal(patellaPair.maximumDepthM, optimised.maximumFemurDepthM,
  'the audited patellofemoral depth disagrees with the search');
assert.equal(clearance.pairs['atlas_Femur.r+atlas_Patella.r'].frames.length,
  optimised.femurPatellaFrames,
  'the clearance probe disagrees with the search about the remaining patellofemoral frames');

// The patella-parented OpenSim points moved closer to the bone surface with the offset.
const patellaPoints = attachment.points.filter(record => record.parentFrame === '/bodyset/patella_r');
assert.equal(patellaPoints.length, 5, 'the patella no longer has five screened source points');
for (const record of patellaPoints) {
  assert(record.nearestDistanceM > 0.02 && record.nearestDistanceM < 0.04,
    `${record.point}: the patella surface distance is now ${record.nearestDistanceM} m`);
}
// The card quotes the source-point distances, the offset and what it bought — in this view's description.
assertHeadlineCopy(main, RESEARCH_HEADING, ['2.6–3.7 cm',
  `${(optimised.offsetMagnitudeM * 1000).toFixed(1)} mm`, '87 帧降到 5 帧', '67 帧里相接'],
  'the patella registration search');

console.log(`Patella registration offset verified: a ${(optimised.offsetMagnitudeM * 1000).toFixed(1)} mm ` +
  `constant (${offset.map(value => (value * 1000).toFixed(1)).join(', ')} mm) found in ` +
  `${search.evaluations} evaluations takes the patellofemoral overlap from ${baseline.femurPatellaFrames} ` +
  `to ${optimised.femurPatellaFrames} frames and patella-to-tibia from ${baseline.patellaTibiaFrames} to ` +
  `${optimised.patellaTibiaFrames}, at a median ${(optimised.medianFemurDistanceM * 1000).toFixed(1)} mm ` +
  `patella-to-femur gap, and the animator, the attachment screen and the phone layer all read it.`);
