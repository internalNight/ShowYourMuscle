import assert from 'node:assert/strict';

const names = ['thorax', 'clavicle', 'scapula', 'humerus', 'ulna', 'radius', 'hand'];
const blender = ([x, y, z]) => [x, -z, y];
const dot = (a, b) => a.reduce((sum, value, axis) => sum + value * b[axis], 0);
const determinant = m => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
  m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
  m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);

export function checkTsmBodyFrames(data) {
  for (const frame of data.frames) {
    assert.deepEqual(Object.keys(frame.blenderBodyFrames), names);
    for (const name of names) {
      const { translationM, rotationRows: rotation } = frame.blenderBodyFrames[name];
      assert.equal(translationM.length, 3);
      assert(translationM.every(Number.isFinite));
      assert.equal(rotation.length, 3);
      assert(rotation.every(row => row.length === 3 && row.every(Number.isFinite)));
      for (let axis = 0; axis < 3; axis++) {
        for (let other = 0; other < 3; other++) {
          assert(Math.abs(dot(rotation[axis], rotation[other]) -
            Number(axis === other)) < 1e-8);
        }
      }
      assert(Math.abs(determinant(rotation) - 1) < 1e-8);
      if (frame.viewerJointsM[name]) {
        const expected = blender(frame.viewerJointsM[name]);
        assert(Math.hypot(...expected.map((value, axis) => value - translationM[axis])) < 1e-10);
      }
    }
  }
  for (const name of names) {
    const first = data.frames[0].blenderBodyFrames[name];
    const last = data.frames.at(-1).blenderBodyFrames[name];
    assert(Math.hypot(...first.translationM.map((value, axis) => value - last.translationM[axis])) < 1e-8);
    for (let row = 0; row < 3; row++) {
      for (let col = 0; col < 3; col++) {
        assert(Math.abs(first.rotationRows[row][col] - last.rotationRows[row][col]) < 1e-8);
      }
    }
  }
}
