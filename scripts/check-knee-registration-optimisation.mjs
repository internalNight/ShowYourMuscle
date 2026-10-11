// Guards the measured knee-registration frontier and the decision not to apply it.
//
// docs/data/knee_registration_optimisation.json is produced by blender/optimise_knee_registration.py
// and docs/data/fibula_registration_optimisation.json by blender/optimise_fibula_registration.py.
// Unlike the patella offset, the tibia offset these searches found is deliberately NOT shipped: it
// halves the bone-to-bone intersections but pushes every tibia-parented OpenSim source point further
// from the bone surface. This check fixes both the frontier (what a constant can and cannot buy) and
// the rejection, so the card cannot claim more than the searches measured and nobody can quietly
// apply the rejected offset.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { assertHeadlineCopy, RESEARCH_HEADING } from './card-text.mjs';

const read = name => JSON.parse(readFileSync(`docs/data/${name}`, 'utf8'));
const knee = read('knee_registration_optimisation.json');
const fibula = read('fibula_registration_optimisation.json');
const attachment = read('attachment_surface_screen.json');
const clearance = read('bone_joint_clearance_probe.json');
const audit = read('registered_mesh_integrity_audit.json');
const main = readFileSync('src/main.ts', 'utf8');

assert.equal(knee.status, 'research_only_knee_registration_search');
assert.equal(knee.framesChecked, 101);
assert.equal(knee.searchedBody, 'tibia_r');
assert.deepEqual(knee.searchedObjects, ['atlas_Tibia.r', 'atlas_Fibula.r'],
  'the knee search no longer moves the whole tibia group');
assert.equal(knee.searchStride >= 1, true, 'the knee search lost its frame stride');
assert(knee.limitations.length >= 5, 'the knee search lost its limitations');
assert(knee.limitations.some(text => text.includes('constant')),
  'the knee search must still say the correction is a single constant');
assert(knee.limitations.some(text => text.includes('cartilage')),
  'the knee search must still name what it cannot model');

// The baseline has to reproduce the shipped audit, or the comparison means nothing.
const baseline = knee.baseline;
assert.equal(baseline.femurTibiaFrames, 97, 'the baseline femur-to-tibia overlap changed');
assert.equal(baseline.femurFibulaFrames, 71, 'the baseline femur-to-fibula overlap changed');
assert.equal(baseline.tibiaCalcaneusFrames, 0, 'the baseline ankle overlap changed');
assert.equal(baseline.femurTibiaFrames,
  audit.summary.addedIntersectingBonePairs['atlas_Femur.r+atlas_Tibia.r'].length,
  'the knee baseline disagrees with the shipped integrity audit');
assert.equal(baseline.femurFibulaFrames,
  audit.summary.addedIntersectingBonePairs['atlas_Femur.r+atlas_Fibula.r'].length,
  'the knee baseline fibula count disagrees with the shipped audit');
assert.equal(baseline.tibiaCalcaneusFrames,
  clearance.summary.bonePairFramesAtZeroClearance['atlas_Tibia.r+atlas_Calcaneus.r'] ?? 0,
  'the knee baseline ankle count disagrees with the clearance probe');

// Every constant configuration, and the honest frontier: nothing clears the knee.
const byLabel = new Map(knee.configurations.map(item => [item.label, item]));
for (const label of ['translation only', 'pivot only', 'pivot plus translation',
  'pivot plus translation plus tilt']) {
  assert(byLabel.has(label), `the knee sweep lost the ${label} configuration`);
}
assert.equal(knee.configurations.length, 4, 'the knee sweep changed shape');
for (const item of knee.configurations) {
  assert.equal(item.parametersAtBound.length, 0,
    `${item.label} ran into a search bound, so the reported optimum is not an interior one`);
  assert(item.optimised.femurTibiaFrames >= baseline.femurTibiaFrames * 0.8,
    `${item.label} now looks like it clears the femur-to-tibia overlap`);
  assert(item.optimised.femurTibiaFrames <= baseline.femurTibiaFrames,
    `${item.label} made the femur-to-tibia overlap worse`);
}
const translation = byLabel.get('translation only');
const pivot = byLabel.get('pivot only');
const tilt = byLabel.get('pivot plus translation plus tilt');
assert.equal(translation.optimised.femurFibulaFrames, 0,
  'the translation-only offset no longer clears the femur-to-fibula overlap');
assert.equal(translation.optimised.femurTibiaFrames, 81,
  'the best femur-to-tibia count changed; re-read the frontier before touching the card');
assert(translation.optimised.maximumFemurTibiaDepthM < baseline.maximumFemurTibiaDepthM * 0.7,
  'the translation-only offset no longer reduces the penetration depth by a third');
assert(translation.optimised.meanKneeSeatDistanceM > baseline.meanKneeSeatDistanceM,
  'the translation-only offset no longer opens the knee seat; the trade-off changed');
assert.equal(pivot.optimised.femurTibiaFrames, baseline.femurTibiaFrames,
  'a pivot shift now clears the femur-to-tibia overlap; the conclusion changed');
assert.equal(pivot.optimised.tibiaCalcaneusFrames, 0,
  'the pivot-only configuration now touches the ankle');
assert(tilt.optimised.tibiaCalcaneusFrames > 10,
  'the tilt configuration no longer shows that a tilt buys the knee by opening the ankle');
assert.equal(knee.optimised.label, knee.bestConfiguration,
  'the marked best configuration is not the recorded optimum');
assert.equal(knee.bestConfiguration, 'translation only',
  'the knee sweep no longer ends on the translation-only offset');

// Why no constant can work: the per-frame motion is a screw motion whose axis is nowhere near the knee.
const centre = knee.effectiveRotationCentre;
assert.equal(centre.framesWithRotationOver10Deg >= 50, true,
  'the diagnostic no longer sees enough knee rotation to be informative');
assert.equal(centre.minimumAxisDistanceToKneeSeatM, centre.maximumAxisDistanceToKneeSeatM,
  'the screw axis now moves between frames; the stated reason for the negative changed');
assert(centre.medianAxisDistanceToKneeSeatM > 0.3 && centre.medianAxisDistanceToKneeSeatM < 0.45,
  `the screw axis is ${centre.medianAxisDistanceToKneeSeatM} m from the knee seat`);
assert.equal(centre.maximumScrewTranslationM, 0,
  'the body motion now slides along its own axis, which changes the explanation');

// The fibula-only route cannot clear its own pair either.
assert.equal(fibula.status, 'research_only_fibula_registration_search');
assert.equal(fibula.searchedObject, 'atlas_Fibula.r');
assert.equal(fibula.baseline.femurFibulaFrames, baseline.femurFibulaFrames,
  'the fibula search and the knee sweep disagree about the baseline');
assert.equal(fibula.optimised.femurFibulaFrames, 52,
  'the best fibula-only count changed; re-read the frontier before touching the card');
assert(fibula.optimised.maximumFemurFibulaDepthM < fibula.baseline.maximumFemurFibulaDepthM,
  'the fibula-only offset no longer reduces the penetration depth');
assert(fibula.optimised.femurFibulaFrames > 20,
  'a fibula-only offset now looks like it clears the pair');
assert(fibula.optimised.offsetMagnitudeM < 0.01,
  'the fibula-only offset is no longer small enough to be a registration');

// The rejection is backed by this data: every tibia-parented source point moves away from the bone.
const rejected = knee.optimised.offsetM;
for (let index = 0; index < 3; index += 1) {
  assert(Math.abs(attachment.rejectedTibiaOffsetM[index] - rejected[index]) < 1e-6,
    'the screened rejected offset is not the one the knee search found');
}
const tibiaPoints = attachment.points.filter(record => record.parentFrame === '/bodyset/tibia_r');
assert.equal(tibiaPoints.length, 8, 'the tibia no longer has eight screened source points');
for (const record of tibiaPoints) {
  assert(record.rejectedOffsetDistanceM > record.nearestDistanceM,
    `${record.muscle} ${record.point}: the rejected offset no longer pushes this point away`);
}
assert.equal(attachment.rejectedOffsetPointsOver20mm, 4,
  'the number of tibia points pushed past 2 cm under the rejected offset changed');
assert.equal(attachment.pointsOver20mm, 18,
  'the shipped attachment screen changed; the rejection comparison is no longer like for like');

// Nobody may apply the rejected offset.
const animator = readFileSync('blender/animate_registered_bones.py', 'utf8');
assert(!animator.includes('knee_registration_optimisation.json'),
  'the bone animator is now reading the rejected knee search');
assert(animator.includes('rejected'),
  'the bone animator no longer records that the tibia offset was rejected');
const model = readFileSync('src/model.ts', 'utf8');
assert(!model.includes('kneeRegistration') && !model.includes("knee_registration_optimisation.json'"),
  'the phone layer is now importing the rejected knee search');
assert(model.includes('deliberately not applied'),
  'the phone layer no longer says why the tibia offset is missing');
const sceneCheck = readFileSync('blender/check_animated_registered_bones.py', 'utf8');
assert(sceneCheck.includes('tibia_registration_offset_m'),
  'the scene check no longer forbids a tibia offset in the saved scenes');
assert.equal(clearance.summary.bonePairFramesAtZeroClearance['atlas_Femur.r+atlas_Tibia.r'], 97,
  'the shipped femur-to-tibia overlap changed, so the knee frontier must be re-measured');
assert.equal(clearance.summary.bonePairFramesAtZeroClearance['atlas_Femur.r+atlas_Fibula.r'], 71,
  'the shipped femur-to-fibula overlap changed, so the knee frontier must be re-measured');

// The card quotes the frontier, the reason and the rejection — inside this view's own description.
assertHeadlineCopy(main, RESEARCH_HEADING,
  ['97／101 → 81／101 帧', '365 mm', '没有采纳', '0.38 cm 到 1.79 cm', '71 帧降到 52 帧', '173 降到 86 帧'],
  'the knee registration search');

console.log(`Knee registration frontier verified: no constant clears the femur-to-tibia overlap ` +
  `(${baseline.femurTibiaFrames} frames at baseline, best ${knee.bestConfiguration} leaves ` +
  `${knee.optimised.optimised.femurTibiaFrames}, pivot-only stays at ${pivot.optimised.femurTibiaFrames}, the tilt ` +
  `variant opens ${tilt.optimised.tibiaCalcaneusFrames} ankle frames), the fibula-only route leaves ` +
  `${fibula.optimised.femurFibulaFrames} of ${fibula.baseline.femurFibulaFrames}, and the ` +
  `${(Math.hypot(...rejected) * 1000).toFixed(0)} mm tibia offset that would clear the fibula is rejected ` +
  `because all eight tibia source points move further from the bone.`);
