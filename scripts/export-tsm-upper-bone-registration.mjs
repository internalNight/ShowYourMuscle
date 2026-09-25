// Bundle only reviewed geometric transforms; never bundle an inferred force.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';

const expected = ['Humerus.r', 'Radius.r', 'Ulna.r'];
const exercises = {};
for (const exercise of ['bench', 'press']) {
  const source = JSON.parse(readFileSync(`docs/data/tsm_${exercise}_upper_bone_registration.json`, 'utf8'));
  assert.equal(source.status,
    'research_only_geometric_upper_bone_registration_not_anatomical_fit_or_force');
  assert.equal(source.exercise, exercise);
  assert.equal(source.frameCount, 101);
  assert.deepEqual(source.bones.map(bone => bone.atlasSource), expected);
  exercises[exercise] = source.bones.map(bone => {
    assert(bone.uniformScale > 0.7 && bone.uniformScale < 1.2);
    assert(Object.values(bone.maximumJointProxyResidualM).every(value =>
      Number.isFinite(value) && value < 0.03));
    assert(bone.atlasToModelBlenderRows.length === 4 &&
      bone.atlasToModelBlenderRows.every(row => row.length === 4 && row.every(Number.isFinite)));
    assert.deepEqual(bone.atlasToModelBlenderRows[3], [0, 0, 0, 1]);
    return {
      atlasSource: bone.atlasSource,
      modelBody: bone.modelBody,
      atlasToModelBlenderRows: bone.atlasToModelBlenderRows,
      maximumJointProxyResidualM: bone.maximumJointProxyResidualM,
    };
  });
}
const output = {
  schemaVersion: 1,
  status: 'research_only_geometric_upper_bone_overlay_not_anatomical_fit_or_force',
  exercises,
};
writeFileSync('src/data/tsm_upper_bone_registration.json', JSON.stringify(output, null, 2) + '\n');
console.log('Bundled reviewed TSM upper-bone transforms for bench and press.');
