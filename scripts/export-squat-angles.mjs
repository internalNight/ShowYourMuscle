import { writeFileSync } from 'node:fs';
import { build } from 'esbuild';

const bundled = await build({ entryPoints: ['src/model.ts'], bundle: true, platform: 'node', format: 'esm', write: false });
const { createPose, squatBarSagittalZ } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const profile = { heightCm: 175, weightKg: 72, armSpanCm: 175, inseamCm: 80 };
const frames = [];
for (let index = 0; index <= 100; index++) {
  const phase = index / 100;
  const pose = createPose(profile, 'squat', phase);
  const torso = pose.chest.clone().sub(pose.pelvis);
  const thigh = pose.kneeR.clone().sub(pose.hipR);
  const hipToKnee = pose.hipR.clone().sub(pose.kneeR);
  const ankleToKnee = pose.ankleR.clone().sub(pose.kneeR);
  const shin = pose.kneeR.clone().sub(pose.ankleR);
  frames.push({
    phase,
    barSagittalRelativeAnkleM: squatBarSagittalZ(pose.shoulderR.z) - pose.ankleR.z,
    hip_flexion_r: -(Math.PI - torso.angleTo(thigh)),
    knee_angle_r: -(Math.PI - hipToKnee.angleTo(ankleToKnee)),
    ankle_angle_r: -Math.atan2(shin.z, shin.y),
  });
}
writeFileSync('assets/opensim/squat_angles.json', `${JSON.stringify({ source: 'src/model.ts createPose', profile, frames }, null, 2)}\n`);
console.log('Exported 101 visual squat poses to assets/opensim/squat_angles.json');
console.log(frames[50]);
