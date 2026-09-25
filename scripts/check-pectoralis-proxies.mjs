import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { build } from 'esbuild';

const bundled = await build({ entryPoints: ['src/pectoralis-proxy.ts'], bundle: true,
  platform: 'node', format: 'esm', write: false });
const { createPectoralisProxyGeometry, updatePectoralisProxyGeometry } = await import(
  `data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);

let comparisons = 0;
for (const exercise of ['bench', 'press']) {
  const report = JSON.parse(readFileSync(`docs/data/tsm_${exercise}_pectoralis_path_proxies.json`));
  const lookup = JSON.parse(readFileSync(`public/data/${exercise}_tsm_reference.json`));
  assert.equal(report.muscles.length, 3);
  for (const muscle of report.muscles) {
    const geometry = createPectoralisProxyGeometry();
    assert.equal(geometry.getAttribute('position').count, muscle.vertexCount);
    for (const sample of muscle.sampledVertices) {
      const path = lookup.frames[sample.frameIndex].muscles[muscle.modelMuscle].viewerPathM;
      updatePectoralisProxyGeometry(geometry, path, muscle.radiusM);
      const positions = geometry.getAttribute('position');
      for (const [key, blender] of Object.entries(sample.verticesBlenderM)) {
        const index = Number(key);
        const viewer = [positions.getX(index), positions.getY(index), positions.getZ(index)];
        const actualBlender = [viewer[0], -viewer[2], viewer[1]];
        for (let axis = 0; axis < 3; axis++) {
          assert.ok(Math.abs(actualBlender[axis] - blender[axis]) < 2e-6,
            `${exercise} ${muscle.modelMuscle} frame ${sample.frameIndex} vertex ${index} axis ${axis}`);
          comparisons++;
        }
      }
    }
    geometry.dispose();
  }
}
console.log(`Pectoralis path-volume cross-check passed: ${comparisons} Blender/phone vertex coordinates.`);
