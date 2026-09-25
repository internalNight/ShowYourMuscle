import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { build } from 'esbuild';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const bundled = await build({ entryPoints: ['src/deltoid-atlas.ts'], bundle: true,
  platform: 'node', format: 'esm', write: false });
const { prepareDeltoidAtlas, updateDeltoidAtlas } = await import(
  `data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const bytes = readFileSync('public/models/z_anatomy_reference.glb');
const gltf = await new GLTFLoader().parseAsync(
  bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '');
gltf.scene.updateMatrixWorld(true);
const atlas = new Map();
gltf.scene.traverse(object => {
  if (object instanceof THREE.Mesh) atlas.set(object.name.replaceAll('_', ' ').replace(/\.r$/, 'r'), object);
});
const fromRows = rows => new THREE.Matrix4().set(...rows.flat());
const toGlTf = new THREE.Matrix4().set(1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1);
const fromGlTf = toGlTf.clone().invert();
const body = data => new THREE.Matrix4().set(
  data.rotationRows[0][0], data.rotationRows[0][1], data.rotationRows[0][2], data.translationM[0],
  data.rotationRows[1][0], data.rotationRows[1][1], data.rotationRows[1][2], data.translationM[1],
  data.rotationRows[2][0], data.rotationRows[2][1], data.rotationRows[2][2], data.translationM[2],
  0, 0, 0, 1,
);
let checks = 0;
let maxErrorM = 0;
for (const exercise of ['bench', 'press']) {
  const registration = JSON.parse(readFileSync(`docs/data/tsm_${exercise}_upper_bone_registration.json`));
  const humerus = registration.bones.find(row => row.modelBody === 'humerus');
  assert(humerus);
  const fit = toGlTf.clone().multiply(fromRows(humerus.atlasToModelBlenderRows)).multiply(fromGlTf);
  const frames = JSON.parse(readFileSync(`public/data/${exercise}_tsm_reference.json`)).frames;
  const report = JSON.parse(readFileSync(`docs/data/tsm_${exercise}_deltoid_atlas_probe.json`));
  assert.equal(report.muscles.length, 3);
  for (const row of report.muscles) {
    const source = atlas.get(row.atlasMesh.replace('.r', 'r'));
    assert(source, row.atlasMesh);
    const geometry = source.geometry.clone();
    geometry.applyMatrix4(fit.clone().multiply(source.matrixWorld));
    const mesh = new THREE.Mesh(geometry);
    assert.equal(geometry.getAttribute('position').count, row.vertexCount);
    const item = prepareDeltoidAtlas(mesh, exercise, row.muscle,
      frames[0].muscles[row.muscle].viewerPathM);
    for (const [frameIndex, samples] of Object.entries(row.sampledVerticesBlenderM)) {
      const frame = frames[Number(frameIndex)];
      const rigid = toGlTf.clone().multiply(body(frame.blenderBodyFrames.humerus)
        .multiply(body(frames[0].blenderBodyFrames.humerus).invert())).multiply(fromGlTf);
      updateDeltoidAtlas(item, rigid, frame.muscles[row.muscle].viewerPathM);
      const positions = geometry.getAttribute('position');
      for (const [index, expected] of Object.entries(samples)) {
        const actual = [positions.getX(Number(index)), -positions.getZ(Number(index)),
          positions.getY(Number(index))];
        for (let axis = 0; axis < 3; axis++) {
          const error = Math.abs(actual[axis] - expected[axis]);
          maxErrorM = Math.max(maxErrorM, error);
          assert(error < 2e-6, `${exercise} ${row.muscle} frame ${frameIndex} vertex ${index}: ${error}`);
          checks++;
        }
      }
    }
  }
}
console.log(`${checks} Blender/phone deltoid coordinates agree; maximum error ${maxErrorM.toExponential(3)} m.`);
