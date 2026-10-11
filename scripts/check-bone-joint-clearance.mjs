// Guards the joint-clearance probe that follows up the mesh-integrity audit.
//
// docs/data/bone_joint_clearance_probe.json is produced by blender/probe_bone_joint_clearance.py.
// The integrity audit left one question open — how large a cartilage-like joint gap would clear the
// registered meshes' interpenetration — and the probe answers it with a measured negative: even a
// 10 mm rigid clearance along the tibial axis leaves most of the femur-to-tibia and femur-to-patella
// overlaps in place. This check keeps that answer, and the per-pair numbers behind it, from drifting.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { assertHeadlineCopy, RESEARCH_HEADING } from './card-text.mjs';

const read = name => JSON.parse(readFileSync(`docs/data/${name}`, 'utf8'));
const probe = read('bone_joint_clearance_probe.json');
const audit = read('registered_mesh_integrity_audit.json');
const main = readFileSync('src/main.ts', 'utf8');

assert.equal(probe.status, 'research_only_bone_joint_clearance_probe');
assert.equal(probe.framesChecked, 101);
assert.equal(probe.referenceFrame, 1);
assert.deepEqual(probe.clearanceStepsMm, [0, 2, 4, 6, 8, 10], 'the clearance steps changed');
assert.deepEqual(probe.tibiaSideObjects.sort(),
  ['atlas_Fibula.r', 'atlas_Tibia.r', 'med_gas_r', 'soleus_r', 'tib_ant_r'].sort(),
  'the tibia-side set changed');
assert.equal(probe.referenceIntersectingPairs.length, 20,
  'the standing reference intersection count changed');
assert(probe.limitations.length >= 6, 'the probe lost its limitations');
assert(probe.limitations.some(text => text.includes('no published cartilage')),
  'the probe must still say that no published cartilage thickness was checked');
assert(probe.limitations.some(text => text.includes('no scene is modified')),
  'the probe must still say that the clearance is hypothetical');

// The probe must be measuring the same overlaps the integrity audit recorded.
const auditMusclePairs = {};
for (const [muscle, entry] of Object.entries(audit.musclesChecked)) {
  for (const [partner, record] of Object.entries(entry.addedIntersections)) {
    auditMusclePairs[`${muscle}+${partner}`] = record;
  }
}
const auditBonePairs = audit.bonePairIntersections;
assert.equal(audit.summary.addedIntersectionFrameCount, 97, 'the audit frame count changed');
assert.equal(Object.keys(auditMusclePairs).length, 8, 'the audit no longer records eight muscle pairs');
assert.equal(Object.keys(auditBonePairs).length, 3, 'the audit no longer records three bone pairs');
assert.equal(audit.summary.addedIntersectingBonePairs['atlas_Femur.r+atlas_Tibia.r'].length, 97,
  'the audit box control no longer shows the femur-to-tibia intersection');
assert(!('atlas_Patella.r+atlas_Tibia.r' in audit.summary.addedIntersectingBonePairs),
  'the patella-to-tibia overlap came back after the measured patella offset');

const expectedFrames = {
  'atlas_Femur.r+atlas_Tibia.r': 97,
  'atlas_Femur.r+atlas_Fibula.r': 71,
  'rect_fem_r+atlas_Patella.r': 67,
  'bifemsh_r+atlas_Tibia.r': 61,
  'rect_fem_r+atlas_Femur.r': 59,
  'tib_ant_r+atlas_Femur.r': 55,
  'bifemsh_r+tib_ant_r': 53,
  'bifemsh_r+soleus_r': 41,
  'glut_max2_r+rect_fem_r': 39,
  'vas_int_r+atlas_Hip bone.r': 33,
  // What remains of the patellofemoral pair after the measured patella offset: grazing frames only.
  'atlas_Femur.r+atlas_Patella.r': 5,
};
assert.deepEqual(Object.keys(probe.pairs).sort(), Object.keys(expectedFrames).sort(),
  'the set of pairs gaining intersections changed');

const bonePairs = new Set(Object.keys(auditBonePairs));
for (const [key, frames] of Object.entries(expectedFrames)) {
  const record = probe.pairs[key];
  assert.equal(record.frames.length, frames, `${key}: frame count changed`);
  assert.equal(record.frames[0], Math.min(...record.frames), `${key}: frames are out of order`);
  assert(record.maximumDepthM >= 0 && record.maximumDepthM < 0.01,
    `${key}: depth ${record.maximumDepthM} m left its band`);
  if (key !== 'atlas_Femur.r+atlas_Patella.r') {
    assert(record.maximumDepthM > 0.0005, `${key}: depth ${record.maximumDepthM} m left its band`);
  }
  // The audit and the probe measure the same scene, so their depths must agree.
  const audited = bonePairs.has(key) ? auditBonePairs[key] : auditMusclePairs[key];
  assert(audited, `${key}: the integrity audit no longer records this pair`);
  assert.equal(record.maximumDepthM, audited.maximumDepthM,
    `${key}: the probe and the integrity audit disagree on the deepest overlap`);
  for (const step of probe.clearanceStepsMm) {
    const value = record.clearanceSweepFramesIntersecting[String(step)];
    assert(value <= frames, `${key}: more frames intersect after a clearance than before`);
  }
  assert.equal(record.clearanceSweepFramesIntersecting['0'], frames,
    `${key}: the zero-clearance column must match the measured frame count`);
}

// Where the overlap sits decides how to read it: joint line versus hip-region contact.
const kneeDistance = key => probe.pairs[key].deepestPoint.distanceToKneeCentreM;
const patellaPair = probe.pairs['atlas_Femur.r+atlas_Patella.r'];
assert.equal(patellaPair.maximumDepthM, 0, 'the patellofemoral pair is no longer grazing contact');
assert.equal(patellaPair.deepestPoint, null,
  'the patellofemoral pair now has a measurable depth, so the offset no longer holds');
assert(kneeDistance('atlas_Femur.r+atlas_Tibia.r') > 0.04 &&
  kneeDistance('atlas_Femur.r+atlas_Tibia.r') < 0.07,
  'the deepest femur-to-tibia overlap moved away from the proximal shin');
// The contact the patella offset traded for sits on the patella itself, at the knee.
assert(kneeDistance('rect_fem_r+atlas_Patella.r') < 0.02,
  'the rectus femoris contact with the patella moved away from the patella');
for (const key of ['glut_max2_r+rect_fem_r', 'rect_fem_r+atlas_Femur.r',
  'vas_int_r+atlas_Hip bone.r']) {
  assert(kneeDistance(key) > 0.3, `${key}: the deepest overlap no longer sits in the hip region`);
}

// The measured negative: a cartilage-scale clearance is not enough, and 10 mm is not either.
assert.equal(probe.summary.tibiaClearanceClearingAllBonePairOverlapMm, null,
  'a tibial clearance now clears every bone-pair overlap, so the conclusion must be revisited');
assert.equal(probe.summary.tibiaClearanceClearingAllMusclePairOverlapMm, null,
  'a tibial clearance now clears every muscle-pair overlap, so the conclusion must be revisited');
assert.equal(probe.pairs['atlas_Femur.r+atlas_Tibia.r'].clearanceSweepFramesIntersecting['10'], 81,
  'the femur-to-tibia overlap no longer resists a 10 mm clearance');
assert.equal(probe.pairs['atlas_Femur.r+atlas_Fibula.r'].clearanceSweepFramesIntersecting['10'], 20,
  'the femur-to-fibula overlap no longer resists a 10 mm clearance');
// What is left of the patellofemoral pair does yield to a small patellar clearance, and the
// rectus femoris contact with the patella yields to a larger one.
assert.equal(probe.summary.patellaClearancePerPatellaPairMm['atlas_Femur.r+atlas_Patella.r'], 2,
  'the residual patellofemoral grazing no longer clears at 2 mm');
assert.equal(probe.pairs['rect_fem_r+atlas_Patella.r'].patellaSweepFramesIntersecting['10'], 0,
  'the rectus femoris no longer separates from the patella at 10 mm');

// What a clearance does fix: contacts inside the folded knee clear at 6-8 mm.
assert.equal(probe.pairs['bifemsh_r+tib_ant_r'].clearanceSweepFramesIntersecting['6'], 0,
  'the short head of biceps femoris no longer separates from tibialis anterior at 6 mm');
assert.equal(probe.pairs['bifemsh_r+soleus_r'].clearanceSweepFramesIntersecting['8'], 0,
  'the short head of biceps femoris no longer separates from soleus at 8 mm');
assert.deepEqual(probe.summary.tibiaClearancePerPairMm['bifemsh_r+tib_ant_r'], 6,
  'the tibialis anterior clearance threshold changed');
assert.deepEqual(probe.summary.tibiaClearancePerPairMm['bifemsh_r+soleus_r'], 8,
  'the soleus clearance threshold changed');
assert.deepEqual(probe.summary.pairsUnaffectedByTibiaClearance,
  ['atlas_Femur.r+atlas_Patella.r', 'glut_max2_r+rect_fem_r', 'rect_fem_r+atlas_Femur.r',
    'rect_fem_r+atlas_Patella.r', 'vas_int_r+atlas_Hip bone.r'],
  'the set of pairs a tibial clearance cannot touch changed');

// The card quotes the headline numbers, so it must not drift from the probe — and the numbers have to be
// in this view's own description, not merely somewhere in main.ts.
assertHeadlineCopy(main, RESEARCH_HEADING, ['81／97 帧', '靠关节间隙修不了', '87 帧降到 5 帧', '73 帧降到 0 帧'],
  'the joint-clearance probe');

console.log(`Joint-clearance probe verified: ${Object.keys(probe.pairs).length} pairs gain ` +
  `intersections during the squat, and a rigid clearance does not remove them — 10 mm distally ` +
  `still leaves ${probe.pairs['atlas_Femur.r+atlas_Tibia.r'].clearanceSweepFramesIntersecting['10']}/97 ` +
  `frames of femur-to-tibia overlap, while the residual patellofemoral grazing yields at ` +
  `${probe.summary.patellaClearancePerPatellaPairMm['atlas_Femur.r+atlas_Patella.r']} mm, so the ` +
  `femur-to-tibia fix has to be registration rather than a wider joint gap.`);
