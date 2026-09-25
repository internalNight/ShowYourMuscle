import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';
import { CylinderGeometry, Mesh, Vector3 } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const bundled = await build({ entryPoints: ['src/reference-shape.ts'], bundle: true,
  platform: 'node', format: 'esm', write: false });
const { prepareReferenceMuscleShape, applyReferenceMuscleThickness, referenceGirthForName } =
  await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);

for (const [name, group] of [
  ['Long_head_of_biceps_brachiir', 'arm'],
  ['(Abdominal_part_of_pectoralis_major_muscle)l', 'chest'],
  ['Sternocostal_head_of_pectoralis_major_muscler', 'chest'],
  ['External_abdominal_oblique_musclel', 'waist'],
  ['Rectus_abdominis_muscle.r', 'waist'],
  ['Vastus lateralis muscle.l', 'thigh'],
  ['Lateral head of gastrocnemius.r', 'calf'],
  ['Femur.r', undefined],
  ['Gluteus maximus muscler', undefined],
]) assert.equal(referenceGirthForName(name), group, name);

const geometry = new CylinderGeometry(.05, .05, .4, 20, 10);
const mesh = new Mesh(geometry);
mesh.name = 'Long head of biceps brachii.r';
const shape = prepareReferenceMuscleShape(mesh, 'arm');
assert.notEqual(mesh.geometry, geometry, 'reference muscle geometry must be independent of source');
const original = shape.rest.slice();
const position = mesh.geometry.getAttribute('position');
applyReferenceMuscleThickness(shape, 1.2);
let widest = 0, endpointMovement = 0;
for (let i = 0; i < position.count; i++) {
  const old = new Vector3(...original.slice(i * 3, i * 3 + 3));
  const now = new Vector3(position.getX(i), position.getY(i), position.getZ(i));
  const offset = old.clone().sub(shape.center);
  const axial = offset.dot(shape.axis);
  const radial = offset.sub(shape.axis.clone().multiplyScalar(axial)).length();
  const newOffset = now.clone().sub(shape.center);
  const newAxial = newOffset.dot(shape.axis);
  const newRadial = newOffset.sub(shape.axis.clone().multiplyScalar(newAxial)).length();
  if (Math.abs((axial - shape.first) / (shape.last - shape.first) - .5) < .01 && radial > .01) {
    widest = Math.max(widest, newRadial / radial);
  }
  if (Math.abs(Math.abs(old.y) - .2) < 1e-5) {
    endpointMovement = Math.max(endpointMovement, old.distanceTo(now));
  }
}
assert(Math.abs(widest - 1.2) < 1e-5, `mid-belly width changed ${widest}x`);
assert(endpointMovement < 1e-7, `endpoints shifted ${endpointMovement} m`);
applyReferenceMuscleThickness(shape, 1);
for (let i = 0; i < position.count; i++) {
  assert.equal(position.getX(i), original[i * 3]);
  assert.equal(position.getY(i), original[i * 3 + 1]);
  assert.equal(position.getZ(i), original[i * 3 + 2]);
}

const asset = readFileSync('public/models/z_anatomy_reference.glb');
const blenderDemo = JSON.parse(readFileSync(
  'docs/data/z_anatomy_profile_190_40_66_44_chest118_waist110.json', 'utf8'));
const gltf = await new GLTFLoader().parseAsync(
  asset.buffer.slice(asset.byteOffset, asset.byteOffset + asset.byteLength), '');
const actualCounts = { arm: 0, chest: 0, waist: 0, thigh: 0, calf: 0 };
const greatestMovement = { arm: 0, chest: 0, waist: 0, thigh: 0, calf: 0 };
let meshCount = 0;
gltf.scene.traverse(object => {
  if (!(object instanceof Mesh)) return;
  meshCount++;
  const group = referenceGirthForName(object.name);
  if (!group) return;
  actualCounts[group]++;
  const originalGeometry = object.geometry;
  const realShape = prepareReferenceMuscleShape(object, group);
  const input = realShape.rest;
  applyReferenceMuscleThickness(realShape, blenderDemo.girthWidthScales[group]);
  assert.notEqual(originalGeometry, object.geometry);
  const positions = object.geometry.getAttribute('position');
  let changed = 0;
  for (let i = 0; i < positions.count; i++) {
    const displacement = Math.hypot(positions.getX(i) - input[i * 3],
      positions.getY(i) - input[i * 3 + 1], positions.getZ(i) - input[i * 3 + 2]);
    if (displacement > 1e-6) changed++;
    greatestMovement[group] = Math.max(greatestMovement[group], displacement);
  }
  assert(changed > positions.count * .2, `${object.name} barely changed`);
  applyReferenceMuscleThickness(realShape, 1);
  for (let i = 0; i < positions.count; i++) {
    assert.equal(positions.getX(i), input[i * 3]);
    assert.equal(positions.getY(i), input[i * 3 + 1]);
    assert.equal(positions.getZ(i), input[i * 3 + 2]);
  }
});
assert.equal(meshCount, 165);
assert.deepEqual(actualCounts, { arm: 12, chest: 6, waist: 4, thigh: 16, calf: 8 });
for (const distance of Object.values(greatestMovement)) assert(distance > .002);
for (const [group, distance] of Object.entries(greatestMovement)) {
  const blenderDistance = blenderDemo.maximumLocalVertexDisplacementM[group];
  assert(Math.abs(distance - blenderDistance) < .0001,
    `${group} phone/Blender maximum vertex movement differs by ${Math.abs(distance - blenderDistance)} m`);
}
console.log(`Actual atlas: ${meshCount} meshes, 46 local girth shapes, reversible; phone/Blender maximum vertex movement agrees within 0.1 mm.`);
