// Bundle the reviewed press geometry registration, never a muscle force estimate.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';

const fit = JSON.parse(readFileSync('docs/data/tsm_pectoralis_landmark_fit_screen.json', 'utf8'));
const audit = JSON.parse(readFileSync('docs/data/tsm_pectoralis_dynamic_registration_audit.json', 'utf8'));
const method = 'medial_clavicle_plus_pectoral_origin_proxy';
for (const exercise of ['bench', 'press']) {
  const motion = JSON.parse(readFileSync(`docs/data/tsm_${exercise}_pectoralis_atlas_probe.json`, 'utf8'));
  const row = fit.records.find(item => item.exercise === exercise && item.method === method);
  const caseAudit = audit.cases.find(item => item.exercise === exercise);
  const weight = exercise === 'bench' ? 0.8 : 1;
  const scenario = exercise === 'bench' ? 'endpoint_blend_80' : 'endpoint_blend';
  const lower = exercise === 'bench' ? 'endpointBlend80MinimumEdgeLengthRatio' : 'endpointBlendMinimumEdgeLengthRatio';
  const upper = exercise === 'bench' ? 'endpointBlend80MaximumEdgeLengthRatio' : 'endpointBlendMaximumEdgeLengthRatio';
  assert.equal(motion.status, 'research_pectoralis_mesh_motion_not_anatomical_or_force_validation');
  assert.equal(motion.exercise ?? 'press', exercise);
  assert.equal(motion.endpointCorrectionWeight ?? 1, weight);
  assert.equal(motion.fit, method);
  assert(row && caseAudit && motion.muscles.length === 3);
  assert(row.atlasToModelBlenderRows.length === 4 &&
    row.atlasToModelBlenderRows.every(line => line.length === 4 && line.every(Number.isFinite)));
  assert.deepEqual(row.atlasToModelBlenderRows[3], [0, 0, 0, 1]);
  const muscles = motion.muscles.map(muscle => {
    const reviewed = caseAudit.muscles.find(item => item.modelMuscle === muscle.modelMuscle);
    assert(reviewed && reviewed.atlasMesh === muscle.atlasMesh);
    assert.equal(reviewed.frameCount, 101);
    assert(reviewed.scenarios[scenario].worst.maximumCm < 4.5);
    assert(reviewed[lower] > 0.5 && reviewed[upper] < 1.5);
    assert.equal(muscle.shapeKeyCount, 102);
    assert(['clavicle', 'thorax'].includes(muscle.rigidParent));
    return {
      atlasMesh: muscle.atlasMesh,
      modelMuscle: muscle.modelMuscle,
      rigidParent: muscle.rigidParent,
      vertexCount: muscle.vertexCount,
    };
  });
  writeFileSync(`src/data/tsm_${exercise}_pectoralis_atlas_registration.json`, JSON.stringify({
    schemaVersion: 1,
    status: `research_geometric_${exercise}_overlay_not_anatomical_or_force_validation`,
    method,
    endpointCorrectionWeight: weight,
    atlasToModelBlenderRows: row.atlasToModelBlenderRows,
    muscles,
  }, null, 2) + '\n');
  console.log(`Bundled reviewed ${exercise} pectoralis atlas registration.`);
}
