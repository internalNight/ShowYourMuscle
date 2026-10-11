import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';
import { Vector3 } from 'three';

const bundled = await build({ entryPoints: ['src/model.ts'], bundle: true, platform: 'node',
  format: 'esm', write: false });
const source = bundled.outputFiles[0].text;
const { profileOuterDimensions, illustrativeMuscleRadius,
  registeredThighThicknessScale, registeredCalfThicknessScale, registeredArmThicknessScale,
  registeredChestThicknessScale, registeredWaistThicknessScale,
  scaleRegisteredThighPoint, scaleRegisteredLimbPoint } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

function ellipseCm(a, b) {
  return 100 * Math.PI * (3 * (a + b) - Math.sqrt((3 * a + b) * (a + 3 * b)));
}
// A vertex cross-check is only as good as its sample list: five copies of one vertex would satisfy every
// distance assertion below while proving nothing at all, so each list is checked for size and for
// distinct vertex indices before it is trusted.
function assertAuditSamples(label, samples) {
  assert(Array.isArray(samples) && samples.length >= 5,
    `${label}: expected at least five vertex samples, found ${samples?.length}`);
  const indices = new Set(samples.map(item => item.vertexIndex));
  assert.equal(indices.size, samples.length,
    `${label}: the sample list repeats vertex indices (${samples.length} samples, ${indices.size} distinct)`);
}
function polygonEllipseCm(a, b, sides = 64) {
  let perimeter = 0;
  for (let index = 0; index < sides; index++) {
    const start = index * 2 * Math.PI / sides;
    const end = (index + 1) * 2 * Math.PI / sides;
    perimeter += Math.hypot(a * (Math.cos(end) - Math.cos(start)),
      b * (Math.sin(end) - Math.sin(start)));
  }
  return perimeter * 100;
}
for (const profile of [
  { heightCm: 175, weightKg: 72, chestCm: 100, upperArmCm: 32, waistCm: 82, thighCm: 54, calfCm: 36 },
  { heightCm: 190, weightKg: 90, bodyFatPct: 28, chestCm: 112, upperArmCm: 41, waistCm: 104, thighCm: 67, calfCm: 43 },
  { heightCm: 150, weightKg: 46, bodyFatPct: 17, chestCm: 82, upperArmCm: 25, waistCm: 66, thighCm: 42, calfCm: 30 },
]) {
  const outer = profileOuterDimensions(profile);
  const measured = {
    upperArmCm: 100 * 2 * Math.PI * outer.upperArmRadiusM,
    waistCm: ellipseCm(outer.waistHalfWidthM, outer.waistHalfDepthM),
    chestCm: ellipseCm(outer.chestHalfWidthM, outer.chestHalfDepthM),
    thighCm: 100 * 2 * Math.PI * outer.thighRadiusM,
    calfCm: 100 * 2 * Math.PI * outer.calfRadiusM,
  };
  for (const [key, value] of Object.entries(measured)) {
    assert(Math.abs(value - profile[key]) < 1e-9, `${key}: ${value} vs ${profile[key]}`);
  }
  assert(Math.abs(polygonEllipseCm(outer.waistHalfWidthM, outer.waistHalfDepthM) - profile.waistCm) <
    profile.waistCm * 0.0005, 'rendered waist ring differs by more than 0.05%');
  assert(Math.abs(polygonEllipseCm(outer.chestHalfWidthM, outer.chestHalfDepthM) - profile.chestCm) <
    profile.chestCm * 0.0005, 'rendered chest ring differs by more than 0.05%');
}
const referenceProfile = { heightCm: 175, weightKg: 72,
  upperArmCm: 32, waistCm: 82, thighCm: 54, calfCm: 36 };
for (const [field, larger, affected] of [
  ['upperArmCm', 40, ['upperArm']],
  ['waistCm', 100, ['waist', 'back']],
  ['chestCm', 140, ['chest']],
  ['thighCm', 65, ['thigh']],
  ['calfCm', 44, ['calf']],
]) {
  const changedProfile = { ...referenceProfile, [field]: larger };
  for (const category of ['upperArm', 'waist', 'thigh', 'calf', 'chest', 'back']) {
    const before = illustrativeMuscleRadius(referenceProfile, category);
    const after = illustrativeMuscleRadius(changedProfile, category);
    if (affected.includes(category)) assert(after > before, `${field} must thicken ${category} illustrative muscle`);
    else assert(Math.abs(after - before) < 1e-12, `${field} unexpectedly altered ${category} illustrative muscle`);
  }
}
assert(registeredChestThicknessScale(referenceProfile) === 1);
assert(registeredChestThicknessScale({ ...referenceProfile, chestCm: 140 }) > 1);
assert(registeredChestThicknessScale({ ...referenceProfile, chestCm: 55 }) === 0.8);
assert(registeredWaistThicknessScale(referenceProfile) === 1);
assert(registeredWaistThicknessScale({ ...referenceProfile, waistCm: 180 }) === 1.2);
assert(registeredWaistThicknessScale({ ...referenceProfile, waistCm: 45 }) === 0.8);
const staticAtlasSample = JSON.parse(readFileSync(
  'docs/data/z_anatomy_profile_190_40_66_44_chest118_waist110.json', 'utf8'));
assert(Math.abs(registeredChestThicknessScale(staticAtlasSample.profile) -
  staticAtlasSample.girthWidthScales.chest) < 1e-9);
assert(Math.abs(registeredWaistThicknessScale(staticAtlasSample.profile) -
  staticAtlasSample.girthWidthScales.waist) < 1e-9);
const exportedDemo = JSON.parse(readFileSync('assets/blender/demo_profile_poses.json', 'utf8'));
for (const category of ['upperArm', 'waist', 'thigh', 'calf', 'chest', 'back']) {
  assert(Math.abs(exportedDemo.radii[category] - illustrativeMuscleRadius(exportedDemo.profile, category)) < 1e-12,
    `${category} Blender export differs from phone muscle-radius rule`);
}
const fallback = profileOuterDimensions({ heightCm: 185, weightKg: 88, bodyFatPct: 30 });
for (const value of Object.values(fallback)) assert(Number.isFinite(value) && value > 0);
const thighProfiles = [
  [{ heightCm: 175, weightKg: 72, thighCm: 54 }, 1],
  [{ heightCm: 175, weightKg: 72, thighCm: 62 }, 62 / 54],
  [{ heightCm: 190, weightKg: 90, thighCm: 67 }, 67 / (54 * 190 / 175)],
  [{ heightCm: 175, weightKg: 72, thighCm: 25 }, .8],
  [{ heightCm: 175, weightKg: 72, thighCm: 110 }, 1.2],
];
for (const [profile, expected] of thighProfiles) {
  assert(Math.abs(registeredThighThicknessScale(profile) - expected) < 1e-9);
}
for (const [profile, expected] of [
  [{ heightCm: 175, weightKg: 72, calfCm: 36 }, 1],
  [{ heightCm: 175, weightKg: 72, calfCm: 42 }, 42 / 36],
  [{ heightCm: 190, weightKg: 90, calfCm: 43 }, 43 / (36 * 190 / 175)],
  [{ heightCm: 175, weightKg: 72, calfCm: 15 }, .8],
  [{ heightCm: 175, weightKg: 72, calfCm: 75 }, 1.2],
]) {
  assert(Math.abs(registeredCalfThicknessScale(profile) - expected) < 1e-9);
}
for (const [profile, expected] of [
  [{ heightCm: 175, weightKg: 72, upperArmCm: 32 }, 1],
  [{ heightCm: 175, weightKg: 72, upperArmCm: 38 }, 38 / 32],
  [{ heightCm: 190, weightKg: 90, upperArmCm: 40 }, 40 / (32 * 190 / 175)],
  [{ heightCm: 175, weightKg: 72, upperArmCm: 15 }, .8],
  [{ heightCm: 175, weightKg: 72, upperArmCm: 70 }, 1.2],
]) {
  assert(Math.abs(registeredArmThicknessScale(profile) - expected) < 1e-9);
}
assert(registeredArmThicknessScale({ heightCm: 175, weightKg: 95, bodyFatPct: 30 }) >
  registeredArmThicknessScale({ heightCm: 175, weightKg: 72, bodyFatPct: 20 }),
  'missing arm girth should use the declared weight/body-fat visual fallback');
assert(Math.abs(registeredArmThicknessScale({ heightCm: 175, weightKg: 95, bodyFatPct: 30, upperArmCm: 38 }) -
  registeredArmThicknessScale({ heightCm: 175, weightKg: 72, bodyFatPct: 20, upperArmCm: 38 })) < 1e-12,
  'an explicit arm girth should take precedence over the fallback');
const blenderSample = JSON.parse(readFileSync('docs/data/right_thigh_mesh_62cm_audit.json', 'utf8'));
assert.equal(blenderSample.requestedThighCircumferenceCm, 62);
assert(Math.abs(registeredThighThicknessScale({ heightCm: 175, weightKg: 72, thighCm: 62 }) -
  blenderSample.appliedMuscleThicknessScale) < 1e-9);
const standing = JSON.parse(readFileSync('public/data/squat_opensim_reference.json', 'utf8')).frames[0];
const toBlender = ([x, y, z]) => new Vector3(0.09 - x, -z, y);
const hip = toBlender(standing.viewerJointsM.hip);
const femurAxis = toBlender(standing.viewerJointsM.knee).sub(hip).normalize();
for (const muscle of blenderSample.muscles) {
  assertAuditSamples(`${muscle.opensimMuscle} thigh audit`, muscle.radialMappingSamples);
  for (const item of muscle.radialMappingSamples) {
    const vertex = new Vector3(...item.originalBlenderM);
    scaleRegisteredThighPoint(vertex, hip, femurAxis, blenderSample.appliedMuscleThicknessScale,
      new Vector3());
    assert(vertex.distanceTo(new Vector3(...item.personalizedBlenderM)) < 1e-6,
      `${muscle.opensimMuscle} vertex ${item.vertexIndex} differs from Blender`);
    const fraction = (muscle.referenceHighZ - item.originalBlenderM[2]) /
      (muscle.referenceHighZ - muscle.referenceLowZ);
    assert(Math.abs(fraction - item.pathFraction) < 1e-6,
      `${muscle.opensimMuscle} vertex ${item.vertexIndex} path fraction differs`);
  }
}
const vasIntSample = JSON.parse(readFileSync('docs/data/right_vastus_intermedius_mesh_62cm_audit.json', 'utf8'));
assert.equal(vasIntSample.opensimMuscle, 'vas_int_r');
assert.equal(vasIntSample.atlasMesh, 'Vastus intermedius muscle.r');
assert.equal(vasIntSample.body, 'femur_r');
assert.equal(vasIntSample.requestedThighCircumferenceCm, 62);
assertAuditSamples('vas_int_r audit', vasIntSample.radialMappingSamples);
assert(Math.abs(registeredThighThicknessScale({ heightCm: 175, weightKg: 72, thighCm: 62 }) -
  vasIntSample.appliedThicknessScale) < 1e-9);
for (const item of vasIntSample.radialMappingSamples) {
  const vertex = new Vector3(...item.originalBlenderM);
  scaleRegisteredThighPoint(vertex, hip, femurAxis, vasIntSample.appliedThicknessScale, new Vector3());
  assert(vertex.distanceTo(new Vector3(...item.personalizedBlenderM)) < 1e-6,
    `vas_int_r vertex ${item.vertexIndex} differs from Blender`);
  const fraction = (vasIntSample.referenceHighZ - item.originalBlenderM[2]) /
    (vasIntSample.referenceHighZ - vasIntSample.referenceLowZ);
  assert(Math.abs(fraction - item.pathFraction) < 1e-6,
    `vas_int_r vertex ${item.vertexIndex} path fraction differs`);
}
// The atlas mesh reaches the phone under GLTFLoader's sanitized name, so the registered key must
// keep the ".r" suffix collapsed into "r" and stay in the femur/thigh group.
const modelSource = readFileSync('src/model.ts', 'utf8');
const vasIntSpec = modelSource.split('\n').find(line => line.includes("'Vastus intermedius muscler'"));
assert(vasIntSpec, 'model.ts must register the vastus intermedius atlas mesh');
assert(vasIntSpec.includes("id: 'vas_int_r'"), 'the vastus intermedius spec must use the OpenSim vas_int_r id');
assert(vasIntSpec.includes("body: 'femur_r'") && vasIntSpec.includes("girth: 'thigh'"),
  'the vastus intermedius mesh must follow the femur body and the thigh girth group');
// Every registered mesh key must resolve to a node in the atlas GLB under GLTFLoader's sanitized
// name, and to a muscle in the squat lookup. A typo would silently drop the whole research layer.
const glb = readFileSync('public/models/z_anatomy_reference.glb');
const glbNames = new Set(JSON.parse(glb.subarray(20, 20 + glb.readUInt32LE(12)).toString('utf8'))
  .nodes.map(node => String(node.name ?? '').replaceAll('_', ' ').replace(/\.r$/, 'r')));
const muscleSpecs = [...modelSource.matchAll(
  /'([^']+)': \{ id: '([^']+)', color: 0x([0-9a-f]{6}), body: '([^']+)', girth: '([^']+)' \}/g)]
  .map(match => ({ key: match[1], id: match[2], color: match[3], body: match[4], girth: match[5] }));
assert.equal(muscleSpecs.length, 8, 'the research layer must register eight muscle meshes');
assert.equal(new Set(muscleSpecs.map(spec => spec.id)).size, 8, 'registered muscle ids must be unique');
const squatMuscles = new Set(Object.keys(JSON.parse(
  readFileSync('public/data/squat_opensim_reference.json', 'utf8')).frames[0].muscles));
for (const spec of muscleSpecs) {
  assert(glbNames.has(spec.key), `the atlas GLB has no node matching the registered key ${spec.key}`);
  assert(squatMuscles.has(spec.id), `the squat lookup has no muscle ${spec.id}`);
  assert(['pelvis', 'femur_r', 'tibia_r'].includes(spec.body), `${spec.id} has an unknown body ${spec.body}`);
  assert(['none', 'thigh', 'calf'].includes(spec.girth), `${spec.id} has an unknown girth group ${spec.girth}`);
}
const calfSample = JSON.parse(readFileSync('docs/data/right_tibialis_mesh_42cm_audit.json', 'utf8'));
assert.equal(calfSample.requestedCalfCircumferenceCm, 42);
assertAuditSamples('tib_ant_r audit', calfSample.radialMappingSamples);
assert(Math.abs(registeredCalfThicknessScale({ heightCm: 175, weightKg: 72, calfCm: 42 }) -
  calfSample.appliedThicknessScale) < 1e-9);
const medialGastrocnemiusSample = JSON.parse(
  readFileSync('docs/data/right_medial_gastrocnemius_mesh_42cm_audit.json', 'utf8'));
assert.equal(medialGastrocnemiusSample.opensimMuscle, 'med_gas_r');
assert.equal(medialGastrocnemiusSample.atlasMesh, 'Medial head of gastrocnemius.r');
assert.equal(medialGastrocnemiusSample.body, 'tibia_r');
assert.equal(medialGastrocnemiusSample.sceneStored, false);
assertAuditSamples('med_gas_r audit', medialGastrocnemiusSample.radialMappingSamples);
const knee = toBlender(standing.viewerJointsM.knee);
const tibiaAxis = toBlender(standing.viewerJointsM.ankle).sub(knee).normalize();
for (const item of calfSample.radialMappingSamples) {
  const vertex = new Vector3(...item.originalBlenderM);
  scaleRegisteredLimbPoint(vertex, knee, tibiaAxis, calfSample.appliedThicknessScale, new Vector3());
  assert(vertex.distanceTo(new Vector3(...item.personalizedBlenderM)) < 1e-6,
    `tib_ant_r vertex ${item.vertexIndex} differs from Blender`);
  const fraction = (calfSample.referenceHighZ - item.originalBlenderM[2]) /
    (calfSample.referenceHighZ - calfSample.referenceLowZ);
  assert(Math.abs(fraction - item.pathFraction) < 1e-6);
}
// The 42 cm medial gastrocnemius variant stores only its audit, so this is the mesh-specific
// cross-check of the shared calf scaling rule for that mesh.
assert.equal(medialGastrocnemiusSample.requestedCalfCircumferenceCm, 42);
assert.equal(medialGastrocnemiusSample.appliedThicknessScale, calfSample.appliedThicknessScale);
for (const item of medialGastrocnemiusSample.radialMappingSamples) {
  const vertex = new Vector3(...item.originalBlenderM);
  scaleRegisteredLimbPoint(vertex, knee, tibiaAxis, medialGastrocnemiusSample.appliedThicknessScale,
    new Vector3());
  assert(vertex.distanceTo(new Vector3(...item.personalizedBlenderM)) < 1e-6,
    `med_gas_r vertex ${item.vertexIndex} differs from Blender`);
  const fraction = (medialGastrocnemiusSample.referenceHighZ - item.originalBlenderM[2]) /
    (medialGastrocnemiusSample.referenceHighZ - medialGastrocnemiusSample.referenceLowZ);
  assert(Math.abs(fraction - item.pathFraction) < 1e-6,
    `med_gas_r vertex ${item.vertexIndex} path fraction differs`);
}
const soleusSample = JSON.parse(readFileSync('docs/data/right_soleus_mesh_42cm_audit.json', 'utf8'));
assert.equal(soleusSample.opensimMuscle, 'soleus_r');
assert.equal(soleusSample.requestedCalfCircumferenceCm, 42);
assertAuditSamples('soleus_r audit', soleusSample.radialMappingSamples);
assert(Math.abs(registeredCalfThicknessScale({ heightCm: 175, weightKg: 72, calfCm: 42 }) -
  soleusSample.appliedThicknessScale) < 1e-9);
for (const item of soleusSample.radialMappingSamples) {
  const vertex = new Vector3(...item.originalBlenderM);
  scaleRegisteredLimbPoint(vertex, knee, tibiaAxis, soleusSample.appliedThicknessScale, new Vector3());
  assert(vertex.distanceTo(new Vector3(...item.personalizedBlenderM)) < 1e-6,
    `soleus_r vertex ${item.vertexIndex} differs from Blender`);
  const fraction = (soleusSample.referenceHighZ - item.originalBlenderM[2]) /
    (soleusSample.referenceHighZ - soleusSample.referenceLowZ);
  assert(Math.abs(fraction - item.pathFraction) < 1e-6);
}
const armSample = JSON.parse(readFileSync('docs/data/tsm_bench_biceps_long_38cm.json', 'utf8'));
assert.equal(armSample.requestedArmCircumferenceCm, 38);
assertAuditSamples('BIC_long audit', armSample.radialMappingSamples);
assert(Math.abs(registeredArmThicknessScale({ heightCm: 175, weightKg: 72, upperArmCm: 38 }) -
  armSample.appliedThicknessScale) < 1e-9);
const tsmStanding = JSON.parse(readFileSync('public/data/bench_tsm_reference.json', 'utf8')).frames[0];
const toTsmBlender = ([x, y, z]) => new Vector3(x, -z, y);
const shoulder = toTsmBlender(tsmStanding.viewerJointsM.shoulder);
const upperArmAxis = toTsmBlender(tsmStanding.viewerJointsM.elbow).sub(shoulder).normalize();
const bicepsPath = tsmStanding.muscles.BIC_long.viewerPathM.map(toTsmBlender);
const bicepsPathAxis = bicepsPath.at(-1).clone().sub(bicepsPath[0]);
for (const item of armSample.radialMappingSamples) {
  const vertex = new Vector3(...item.originalBlenderM);
  const fraction = Math.min(1, Math.max(0,
    vertex.clone().sub(bicepsPath[0]).dot(bicepsPathAxis) / bicepsPathAxis.lengthSq()));
  assert(Math.abs(fraction - item.pathFraction) < 1e-6);
  scaleRegisteredLimbPoint(vertex, shoulder, upperArmAxis,
    armSample.appliedThicknessScale, new Vector3());
  assert(vertex.distanceTo(new Vector3(...item.personalizedBlenderM)) < 1e-6,
    `BIC_long vertex ${item.vertexIndex} differs from Blender`);
}
console.log('3 profiles match girths; five local inputs alter intended illustrative muscle groups; Blender radii and static chest/waist plus research thigh (four meshes), three calf and arm scaling match phone rules.');
