import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const data = JSON.parse(readFileSync('public/data/unified_opensim_reference.json', 'utf8'));
const audit = JSON.parse(readFileSync('docs/data/unified_opensim_geometry.json', 'utf8'));
const skin = JSON.parse(readFileSync('public/data/unified_muscle_skin.json', 'utf8'));
const skinWeights = readFileSync('public/data/unified_muscle_weights.bin');
const anatomy = JSON.parse(readFileSync('public/data/unified_anatomy_bones.json', 'utf8'));
assert.equal(data.model, audit.model);
assert.equal(data.bodyNames.length, 80);
assert.equal(data.muscleNames.length, 520);
assert.equal(new Set(data.bodyNames).size, 80);
assert.equal(new Set(data.muscleNames).size, 520);
assert.equal(audit.present.length + audit.missing.length + audit.excluded.length, 132);
assert.equal(skin.meshes.length, 68);
assert.equal(anatomy.bones.length, 91);
assert(anatomy.bones.every(bone => bone.bodyIndex >= 0 && bone.bodyIndex < data.bodyNames.length));
assert(skin.meshes.every(mesh => mesh.modelMuscles.length > 0 &&
  mesh.modelMuscles.every(name => data.muscleNames.includes(name)) &&
  mesh.bodyIndices.length === 3 &&
  mesh.bodyIndices.every(index => index >= 0 && index < data.bodyNames.length) &&
  mesh.axis.length === 3 && mesh.center.length === 3));
assert.equal(skin.meshes.reduce((sum, mesh) => sum + mesh.vertexCount, 0), skinWeights.length);

for (const [action, frames] of Object.entries({ neutral: [data.neutral], ...data.actions })) {
  assert.equal(frames.length, action === 'neutral' ? 1 : 101);
  for (const [index, frame] of frames.entries()) {
    assert.equal(frame.bodies.length, 80, `${action} frame ${index} bodies`);
    assert.equal(frame.paths.length, 520, `${action} frame ${index} paths`);
    assert.equal(frame.lengthsM.length, 520, `${action} frame ${index} lengths`);
    assert(frame.coordinates && typeof frame.coordinates === 'object');
    for (let muscle = 0; muscle < 520; muscle++) {
      assert(frame.paths[muscle].length >= 2, `${action} frame ${index} ${muscle} path`);
      assert(Number.isFinite(frame.lengthsM[muscle]) && frame.lengthsM[muscle] > 0);
    }
  }
  if (action !== 'neutral') {
    const mid = frames[50];
    assert(Object.keys(mid.coordinates).length >= 2, `${action} has no joint coordinates`);
    assert(mid.bodies.some((body, index) => JSON.stringify(body) !== JSON.stringify(data.neutral.bodies[index])),
      `${action} did not change model pose`);
    assert(mid.lengthsM.some((length, index) => Math.abs(length - data.neutral.lengthsM[index]) > 0.001),
      `${action} did not change muscle lengths`);
  }
}
const body = name => data.bodyNames.indexOf(name);
const pos = (frame, name) => frame.bodies[body(name)].p;
const heelHeight = pos(data.neutral, 'calcn_r')[1];
for (const action of ['squat', 'bench']) {
  for (const [index, frame] of data.actions[action].entries()) {
    for (const side of ['r', 'l']) {
      assert(Math.abs(pos(frame, `calcn_${side}`)[1] - heelHeight) < 0.002,
        `${action} ${index}% ${side} heel lost ground contact`);
      assert(pos(frame, `toes_${side}`)[1] > (action === 'bench' ? -0.01 : -0.02),
        `${action} ${index}% ${side} toes passed through ground`);
    }
  }
}
const squat = data.actions.squat[50];
assert(squat.coordinates.knee_angle_r > 1.9 && squat.coordinates.hip_flexion_r > 1.5);
assert(Math.abs(pos(squat, 'calcn_r')[0] - pos(data.neutral, 'calcn_r')[0]) < 0.002);
const benchBottom = data.actions.bench[0], benchTop = data.actions.bench[50];
assert(pos(benchTop, 'hand_r')[1] - pos(benchBottom, 'hand_r')[1] > 0.15,
  'bench hands do not move upward');
assert(Math.abs(pos(benchTop, 'hand_r')[1] - pos(benchTop, 'hand_l')[1]) < 0.04,
  'bench hands are not level');
for (const action of ['bench', 'press']) {
  const widths = data.actions[action].map(frame =>
    Math.abs(pos(frame, 'hand_r')[2] - pos(frame, 'hand_l')[2]));
  assert(Math.max(...widths) - Math.min(...widths) < 0.09,
    `${action} grip width changes more than 9 cm`);
  const rising = data.actions[action].slice(0, 50).every((frame, index) =>
    pos(data.actions[action][index + 1], 'hand_r')[1] >= pos(frame, 'hand_r')[1] - 0.002);
  assert(rising, `${action} bar path reverses vertically during ascent`);
}
const pressBottom = data.actions.press[0], pressTop = data.actions.press[50];
assert(pos(pressTop, 'hand_r')[1] - pos(pressBottom, 'hand_r')[1] > 0.5,
  'press does not reach overhead');
assert(pos(pressTop, 'hand_r')[1] > pos(pressTop, 'head_neck')[1] + 0.35);
console.log('OpenSim: 80 bodies, 520 paths, 304 frames, 68 muscle and 91 bone surfaces; foot clearance and exercise hand paths verified.');
