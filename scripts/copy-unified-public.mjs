import { copyFile, mkdir, stat } from 'node:fs/promises';
import { join, resolve, sep } from 'node:path';

const root = resolve();
const files = [
  'sw.js',
  'manifest.webmanifest',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'models/unified_opensim_skeleton.glb',
  'models/unified_muscle_surfaces.glb',
  'models/unified_anatomy_bones.glb',
  'models/NOTICE-unified-opensim.txt',
  'models/NOTICE-z-anatomy.txt',
  'data/unified_opensim_reference.json',
  'data/unified_pose_basis.json',
  'data/unified_muscle_skin.json',
  'data/unified_muscle_weights.bin',
  'data/unified_anatomy_bones.json',
];
for (const relative of files) {
  const source = resolve(root, 'public', relative);
  const target = resolve(root, 'dist', relative);
  if (!source.startsWith(`${resolve(root, 'public')}${sep}`) ||
      !target.startsWith(`${resolve(root, 'dist')}${sep}`)) {
    throw new Error(`asset escaped package roots: ${relative}`);
  }
  await stat(source);
  await mkdir(join(target, '..'), { recursive: true });
  await copyFile(source, target);
}
console.log(`Copied ${files.length} unified OpenSim app assets.`);
