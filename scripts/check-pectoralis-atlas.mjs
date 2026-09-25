import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { build } from 'esbuild';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const bundled = await build({ entryPoints: ['src/pectoralis-atlas.ts', 'src/reference-shape.ts'],
  bundle: true, platform: 'node', format: 'esm', write: false, outdir: 'out' });
const moduleFor = async name => {
  const output = bundled.outputFiles.find(file => file.path.endsWith(`/${name}.js`) ||
    file.path.endsWith(`\\${name}.js`));
  assert(output, `missing bundled ${name}`);
  return import(`data:text/javascript;base64,${Buffer.from(output.text).toString('base64')}`);
};
const { createPectoralisAtlasFractions, updatePectoralisAtlas } = await moduleFor('pectoralis-atlas');
const { prepareReferenceMuscleShape } = await moduleFor('reference-shape');
const asset = readFileSync('public/models/z_anatomy_reference.glb');
const gltf = await new GLTFLoader().parseAsync(
  asset.buffer.slice(asset.byteOffset, asset.byteOffset + asset.byteLength), '');
gltf.scene.updateMatrixWorld(true);
const atlas = new Map();
gltf.scene.traverse(object => {
  if (object instanceof THREE.Mesh) atlas.set(object.name.replaceAll('_', ' ').replace(/\.r$/, 'r'), object);
});
const matrix = rows => new THREE.Matrix4().set(...rows.flat());
const toGlTf = new THREE.Matrix4().set(1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1);
const fromGlTf = toGlTf.clone().invert();
const body = row => new THREE.Matrix4().set(
  row.rotationRows[0][0], row.rotationRows[0][1], row.rotationRows[0][2], row.translationM[0],
  row.rotationRows[1][0], row.rotationRows[1][1], row.rotationRows[1][2], row.translationM[1],
  row.rotationRows[2][0], row.rotationRows[2][1], row.rotationRows[2][2], row.translationM[2],
  0, 0, 0, 1,
);
let checks = 0;
let maxErrorM = 0;
for (const exercise of ['bench', 'press']) {
  const registration = JSON.parse(readFileSync(`src/data/tsm_${exercise}_pectoralis_atlas_registration.json`));
  const report = JSON.parse(readFileSync(`docs/data/tsm_${exercise}_pectoralis_atlas_probe.json`));
  const frames = JSON.parse(readFileSync(`public/data/${exercise}_tsm_reference.json`)).frames;
  for (const row of registration.muscles) {
    const source = atlas.get(row.atlasMesh.replace('.r', 'r'));
    assert(source, row.atlasMesh);
    const geometry = source.geometry.clone();
    geometry.applyMatrix4(toGlTf.clone().multiply(matrix(registration.atlasToModelBlenderRows))
      .multiply(fromGlTf).multiply(source.matrixWorld));
    const mesh = new THREE.Mesh(geometry);
    const shape = prepareReferenceMuscleShape(mesh, 'chest');
    const startPath = frames[0].muscles[row.modelMuscle].viewerPathM;
    const item = { mesh, shape, exercise, muscle: row.modelMuscle, parent: row.rigidParent,
      fractions: createPectoralisAtlasFractions(shape, startPath), fractionsReady: true,
      endpointCorrectionWeight: registration.endpointCorrectionWeight };
    const expected = report.muscles.find(muscle => muscle.modelMuscle === row.modelMuscle);
    assert.equal(mesh.geometry.getAttribute('position').count, expected.vertexCount);
    for (const [frameIndex, vertices] of Object.entries(expected.sampledVerticesBlenderM)) {
      const current = frames[Number(frameIndex)];
      const rigid = toGlTf.clone().multiply(body(current.blenderBodyFrames[row.rigidParent])
        .multiply(body(frames[0].blenderBodyFrames[row.rigidParent]).invert())).multiply(fromGlTf);
      updatePectoralisAtlas(item, rigid, startPath, current.muscles[row.modelMuscle].viewerPathM, 1);
      const position = mesh.geometry.getAttribute('position');
      for (const [key, blender] of Object.entries(vertices)) {
        const index = Number(key);
        const actual = [position.getX(index), -position.getZ(index), position.getY(index)];
        for (let axis = 0; axis < 3; axis++) {
          const error = Math.abs(actual[axis] - blender[axis]);
          maxErrorM = Math.max(maxErrorM, error);
          assert(error < 2e-6, `${row.modelMuscle} frame ${frameIndex} vertex ${key}: ${error}`);
          checks++;
        }
      }
    }
    // Local girth adjustment must move the belly and preserve the starting endpoints.
    updatePectoralisAtlas(item, new THREE.Matrix4(), startPath, startPath, 1.2);
    const position = mesh.geometry.getAttribute('position');
    let changed = 0;
    for (let index = 0; index < position.count; index++) {
      const before = new THREE.Vector3().fromArray(shape.rest, index * 3);
      const after = new THREE.Vector3(position.getX(index), position.getY(index), position.getZ(index));
      if (before.distanceTo(after) > 1e-5) changed++;
    }
    assert(changed > position.count * 0.2, `${row.modelMuscle} chest width did not update`);
  }
}

console.log(`Bench and press pectoralis atlas cross-check passed: ${checks} coordinates, max error ${maxErrorM.toExponential(2)} m.`);
