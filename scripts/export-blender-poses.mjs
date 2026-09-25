import { readFileSync, writeFileSync } from 'node:fs';
import { build } from 'esbuild';

const bundled = await build({ entryPoints: ['src/model.ts'], bundle: true, platform: 'node', format: 'esm', write: false });
const { createPose, squatBarSagittalZ, profileOuterDimensions, profileSegmentDimensions, illustrativeMuscleRadius,
  illustrativeMusclePaths, illustrativeBellyRadiusScale } =
  await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const args = process.argv.slice(2);
const option = name => { const index = args.indexOf(name); return index < 0 ? undefined : args[index + 1]; };
if (args.some(arg => arg.startsWith('--') && !['--profile', '--out', '--load-kg', '--squat-bar-offset-cm', '--squat-depth-deg', '--cycle-duration-s'].includes(arg)) ||
    ['--profile', '--out', '--load-kg', '--squat-bar-offset-cm', '--squat-depth-deg', '--cycle-duration-s'].some(name => args.includes(name) && !option(name))) {
  throw new Error('Usage: node scripts/export-blender-poses.mjs [--profile profile.json] [--out output.json] [--load-kg 20] [--squat-bar-offset-cm -6|0|6] [--squat-depth-deg 60..135] [--cycle-duration-s 1.5..6]');
}
const loadKg = Number(option('--load-kg') ?? 20);
const squatBarOffsetCm = Number(option('--squat-bar-offset-cm') ?? 0);
const squatDepthDeg = option('--squat-depth-deg') === undefined ? undefined : Number(option('--squat-depth-deg'));
const cycleDurationS = Number(option('--cycle-duration-s') ?? JSON.parse(readFileSync('src/data/demo_motion_protocol.json', 'utf8')).cycleDurationS);
if (!Number.isFinite(loadKg) || loadKg < 0 || loadKg > 300) throw new Error('load-kg must be from 0 to 300');
if (![-6, 0, 6].includes(squatBarOffsetCm)) throw new Error('squat-bar-offset-cm must be -6, 0 or 6');
if (squatDepthDeg !== undefined && (!Number.isFinite(squatDepthDeg) || squatDepthDeg < 60 || squatDepthDeg > 135)) throw new Error('squat-depth-deg must be from 60 to 135');
if (!Number.isFinite(cycleDurationS) || cycleDurationS < 1.5 || cycleDurationS > 6) throw new Error('cycle-duration-s must be from 1.5 to 6');
const profile = option('--profile')
  ? JSON.parse(readFileSync(option('--profile'), 'utf8'))
  : { heightCm: 175, weightKg: 72, armSpanCm: 175, inseamCm: 80 };
const limits = { heightCm: [120, 220], weightKg: [30, 250], bodyFatPct: [3, 65], chestCm: [55, 180],
  upperArmCm: [15, 70], waistCm: [45, 180], thighCm: [25, 110], calfCm: [15, 75],
  armSpanCm: [100, 250], inseamCm: [45, 120] };
for (const [name, [low, high]] of Object.entries(limits)) {
  const value = profile[name];
  if ((value === undefined && !['heightCm', 'weightKg'].includes(name)) ||
      (typeof value === 'number' && Number.isFinite(value) && value >= low && value <= high)) continue;
  throw new Error(`${name} must be a finite number from ${low} to ${high}`);
}
for (const name of Object.keys(profile)) if (!(name in limits)) throw new Error(`Unknown profile field: ${name}`);
const out = option('--out') ?? 'assets/blender/animation_poses.json';
const exercises = ['squat', 'bench', 'press'];
const frames = [];
for (let action = 0; action < exercises.length; action++) {
  for (let index = 0; index <= 50; index++) {
    const phase = index / 50;
    const pose = createPose(profile, exercises[action], phase, squatBarOffsetCm, squatDepthDeg);
    const joints = Object.fromEntries(Object.entries(pose).map(([name, vector]) =>
      [name.replace(/[LR]$/, suffix => `_${suffix.toLowerCase()}`), [vector.x, vector.z, vector.y]]));
    const muscles = Object.fromEntries(illustrativeMusclePaths(profile, exercises[action], phase, squatBarOffsetCm, squatDepthDeg)
      .map(item => [item.id, { label: item.label, category: item.category, ratio: item.ratio,
        bellyRadiusScale: illustrativeBellyRadiusScale(item.ratio),
        points: item.points.map(vector => [vector.x, vector.z, vector.y]) }]));
    if (Object.keys(muscles).length !== 23) throw new Error('Expected 23 illustrative muscles');
    const barCenter = exercises[action] === 'squat'
      ? [0, squatBarSagittalZ(pose.shoulderR.z, squatBarOffsetCm), pose.shoulderR.y + 0.09]
      : [(pose.wristL.x + pose.wristR.x) / 2, (pose.wristL.z + pose.wristR.z) / 2,
        (pose.wristL.y + pose.wristR.y) / 2];
    frames.push({ frame: action * 60 + index + 1, exercise: exercises[action], phase, joints, muscles,
      barCenter });
  }
}
const radii = Object.fromEntries(['upperArm', 'waist', 'thigh', 'calf', 'chest', 'back']
  .map(category => [category, illustrativeMuscleRadius(profile, category)]));
writeFileSync(out, `${JSON.stringify({ source: 'src/model.ts createPose/squatBarSagittalZ/profileOuterDimensions/illustrativeMuscleRadius',
  status: 'illustrative_geometry_not_validated_force', profile, loadKg, squatBarOffsetCm,
  squatDepthDeg: squatDepthDeg ?? null, cycleDurationS,
  outer: profileOuterDimensions(profile), segments: profileSegmentDimensions(profile), radii, frames }, null, 2)}\n`);
console.log(`Exported ${frames.length} poses across ${exercises.length} actions to ${out}`);
