// Guards the deformation-integrity audit of the squat research layer.
//
// docs/data/registered_mesh_integrity_audit.json is produced by blender/audit_registered_mesh_integrity.py
// and answers the roadmap's stage-1 acceptance items "no wrong flips" and "no interpenetration"
// across every frame instead of five sampled ones. The audit passes the flip and edge-distortion
// parts and fails the interpenetration part, so this check keeps both halves honest: the clean
// results must stay clean, and the measured penetration must stay visible rather than being
// quietly dropped from the documentation.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { assertHeadlineCopy, RESEARCH_HEADING } from './card-text.mjs';

const read = name => JSON.parse(readFileSync(`docs/data/${name}`, 'utf8'));
const audit = read('registered_mesh_integrity_audit.json');
const alignment = read('right_leg_mesh_alignment_probe.json');
const source = JSON.parse(readFileSync('public/data/squat_opensim_reference.json', 'utf8'));
const model = readFileSync('src/model.ts', 'utf8');

assert.equal(audit.status, 'research_only_mesh_integrity_audit');
assert.equal(audit.framesChecked, 101, 'the audit no longer covers every frame');
assert.equal(audit.referenceFrame, 1, 'the reference frame changed');
assert.deepEqual(audit.edgeRatioGate, [0.5, 1.5], 'the edge-ratio gate changed');
assert.equal(Object.keys(audit.musclesChecked).length, 8, 'the audit no longer covers eight meshes');
assert.equal(Object.keys(audit.boneMeshes).length, 6, 'the audit no longer covers six bone meshes');
assert(audit.limitations.length >= 6, 'the audit lost its limitations');
assert(audit.limitations.some(text => text.includes('reference state')),
  'the audit no longer explains that already-intersecting pairs are the reference state');

// The scene and the app must register the same meshes on the same bones.
const registry = new Map();
for (const match of model.matchAll(/'([^']+)':\s*\{\s*id:\s*'([^']+)',\s*color:\s*0x[0-9a-f]+,\s*body:\s*'([^']+)'/g)) {
  registry.set(match[2], { atlas: match[1], body: match[3] });
}
assert.equal(registry.size, 8, `expected eight registered muscles in src/model.ts, found ${registry.size}`);

// The probe stores raw atlas node names; GLTFLoader folds ".r" to "r" and underscores to spaces.
const normalise = name => name.replace(/_/g, ' ').replace(/\.r\b/g, 'r');
const alignedByAtlas = new Map(Object.values(alignment.muscles)
  .map(item => [normalise(item.atlasMesh), item]));

// The reference model must still be the source of the audited frames.
assert.equal(source.frames.length, 101, 'the OpenSim reference no longer has 101 frames');
const musclesInReference = new Set(Object.keys(source.frames[0].muscles));

for (const [muscle, entry] of Object.entries(audit.musclesChecked)) {
  const registered = registry.get(muscle);
  assert(registered, `${muscle}: the audit covers a muscle the app does not register`);
  assert.equal(entry.body, registered.body,
    `${muscle}: the audit drives it from ${entry.body} but the app registers ${registered.body}`);
  assert(musclesInReference.has(muscle),
    `${muscle}: the muscle is missing from the OpenSim reference frames`);
  const aligned = alignedByAtlas.get(registered.atlas);
  assert(aligned, `${muscle}: no standing alignment record for ${registered.atlas}`);
  assert.equal(entry.vertexCount, aligned.vertexCount,
    `${muscle}: the audited vertex count differs from the standing alignment probe`);

  // The clean half of the audit: no flips, no degenerate faces, no edge outside the gate.
  assert.deepEqual(entry.flippedFaces.frames, [], `${muscle}: faces now flip during the squat`);
  assert.deepEqual(entry.degenerateFaces.frames, [], `${muscle}: faces now collapse during the squat`);
  assert.equal(entry.edgeRatio.edgesBelowGate, 0, `${muscle}: an edge fell below the gate`);
  assert.equal(entry.edgeRatio.edgesAboveGate, 0, `${muscle}: an edge rose above the gate`);
  assert(entry.edgeRatio.minimum >= 0.5 && entry.edgeRatio.maximum <= 1.5,
    `${muscle}: edge ratios ${entry.edgeRatio.minimum}-${entry.edgeRatio.maximum} leave the gate`);

  // Self-intersection must not grow beyond the standing reference state.
  assert(entry.selfIntersections.maximumFacePairs <= entry.selfIntersections.referenceFacePairs,
    `${muscle}: self-intersection grew from ${entry.selfIntersections.referenceFacePairs} to ` +
    `${entry.selfIntersections.maximumFacePairs}`);
  assert.deepEqual(entry.selfIntersections.framesAboveReference, [],
    `${muscle}: frames now exceed the reference self-intersection count`);
}

// The failing half: the deformation adds interpenetration, and it must stay documented.
const addedPairs = audit.summary.addedIntersectingMeshPairs;
const expectedAdded = ['bifemsh_r+atlas_Tibia.r', 'bifemsh_r+soleus_r', 'bifemsh_r+tib_ant_r',
  'glut_max2_r+rect_fem_r', 'rect_fem_r+atlas_Femur.r', 'rect_fem_r+atlas_Patella.r',
  'tib_ant_r+atlas_Femur.r', 'vas_int_r+atlas_Hip bone.r'];
assert.deepEqual(Object.keys(addedPairs).sort(), expectedAdded.slice().sort(),
  'the set of newly intersecting muscle pairs changed');
for (const pair of expectedAdded) {
  assert(addedPairs[pair].length > 20,
    `${pair}: only ${addedPairs[pair].length} frames still show the added intersection`);
  for (const frame of addedPairs[pair]) {
    assert(frame >= 1 && frame <= 101, `${pair}: frame ${frame} is outside the audited range`);
  }
}
assert(audit.summary.maximumAddedDepthM > 0.005 && audit.summary.maximumAddedDepthM < 0.01,
  `the deepest added penetration is now ${audit.summary.maximumAddedDepthM} m`);

// The bone-to-bone control: the registered bone meshes themselves interpenetrate, which is what
// makes part of the muscle-to-bone overlap inherited rather than created by the deformation.
const bonePairs = audit.summary.addedIntersectingBonePairs;
assert(Object.keys(bonePairs).includes('atlas_Femur.r+atlas_Tibia.r'),
  'the femur-to-tibia control measurement disappeared');
assert(bonePairs['atlas_Femur.r+atlas_Tibia.r'].length > 90,
  'the femur and tibia no longer interpenetrate through the squat');
assert(bonePairs['atlas_Femur.r+atlas_Tibia.r'][0] <= 5,
  'the femur-to-tibia intersection no longer starts near the beginning of the squat');
// The measured patella offset brought the patellofemoral overlap down from 87 frames to a handful of
// grazing frames, and removed the patella-to-tibia pair entirely; those must not come back.
assert.equal(bonePairs['atlas_Femur.r+atlas_Patella.r'].length, 5,
  'the patellofemoral overlap no longer matches the offset that removed it');
assert(!('atlas_Patella.r+atlas_Tibia.r' in bonePairs),
  'the patella-to-tibia overlap came back after the measured offset');
assert.deepEqual(audit.summary.framesWithFlippedFaces, [],
  'the whole-layer flip summary is no longer empty');
assert.equal(audit.summary.referenceIntersectingMeshPairs.length, 20,
  'the standing reference intersection count changed');

// The research layer's own description quotes these numbers, so it must not drift — and they have to be
// inside that description rather than merely somewhere in the file.
const main = readFileSync('src/main.ts', 'utf8');
const deepestMm = Math.round(audit.summary.maximumAddedDepthM * 1000 * 10) / 10;
assertHeadlineCopy(main, RESEARCH_HEADING, [`${deepestMm} mm`,
  `${bonePairs['atlas_Femur.r+atlas_Tibia.r'].length}／101 帧`,
  `${audit.summary.referenceIntersectingMeshPairs.length} 对网格相交`, '不穿模', '面翻转',
  `${bonePairs['atlas_Femur.r+atlas_Patella.r'].length} 帧`, '股直肌'],
  'the registered mesh integrity audit');

console.log(`Registered mesh integrity verified: ${audit.framesChecked} frames x 8 meshes keep ` +
  `edge ratios in ${audit.summary.worstEdgeRatioMinimum}-${audit.summary.worstEdgeRatioMaximum} ` +
  `with no flipped or degenerate face and no self-intersection beyond the standing state. The ` +
  `audit also measures what the coarse registration cannot deliver: ${expectedAdded.length} muscle ` +
  `pairs gain intersections during the squat (up to ${(audit.summary.maximumAddedDepthM * 1000).toFixed(2)} mm), ` +
  `and the bone meshes themselves intersect from frame ` +
  `${bonePairs['atlas_Femur.r+atlas_Tibia.r'][0]} (${bonePairs['atlas_Femur.r+atlas_Tibia.r'].length} frames), ` +
  `with the patellofemoral pair held down to ${bonePairs['atlas_Femur.r+atlas_Patella.r'].length} frames by ` +
  `the measured offset.`);
