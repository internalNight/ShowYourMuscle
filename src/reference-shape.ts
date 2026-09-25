import * as THREE from 'three';

export type ReferenceGirth = 'arm' | 'chest' | 'waist' | 'thigh' | 'calf';
export type ReferenceMuscleShape = {
  mesh: THREE.Mesh;
  girth: ReferenceGirth;
  rest: Float32Array;
  center: THREE.Vector3;
  axis: THREE.Vector3;
  first: number;
  last: number;
  appliedScale: number;
};

const arm = new Set([
  'Long head of biceps brachii', 'Short head of biceps brachii',
  'Lateral head of triceps brachii', 'Long head of triceps brachii',
  'Medial head of triceps brachii', 'Brachialis muscle',
]);
const chest = new Set([
  '(Abdominal part of pectoralis major muscle)',
  'Clavicular head of pectoralis major muscle',
  'Sternocostal head of pectoralis major muscle',
]);
const waist = new Set([
  'External abdominal oblique muscle', 'Rectus abdominis muscle',
]);
const thigh = new Set([
  'Rectus femoris muscle', 'Vastus intermedius muscle',
  'Vastus lateralis muscle', 'Vastus medialis muscle',
  'Long head of biceps femoris', 'Short head of biceps femoris',
  'Semimembranosus muscle', 'Semitendinosus muscle',
]);
const calf = new Set([
  'Lateral head of gastrocnemius', 'Medial head of gastrocnemius',
  'Soleus muscle', 'Tibialis anterior muscle',
]);

export function referenceGirthForName(name: string): ReferenceGirth | undefined {
  const base = name.replaceAll('_', ' ').replace(/[._]?[lr]$/i, '');
  if (arm.has(base)) return 'arm';
  if (chest.has(base)) return 'chest';
  if (waist.has(base)) return 'waist';
  if (thigh.has(base)) return 'thigh';
  if (calf.has(base)) return 'calf';
  return undefined;
}

// Width changes are confined to the middle of a source mesh: both extreme
// ends remain in place. This is a generic visual shape adjustment, not an
// anatomical muscle-volume reconstruction or an attachment registration.
export function prepareReferenceMuscleShape(mesh: THREE.Mesh,
  girth: ReferenceGirth): ReferenceMuscleShape {
  mesh.geometry = mesh.geometry.clone();
  const position = mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
  if (!position || position.count < 20) throw new Error(`Invalid atlas muscle: ${mesh.name}`);
  const rest = new Float32Array(position.count * 3);
  const center = new THREE.Vector3();
  const low = new THREE.Vector3(Infinity, Infinity, Infinity);
  const high = new THREE.Vector3(-Infinity, -Infinity, -Infinity);
  for (let i = 0; i < position.count; i++) {
    const x = position.getX(i), y = position.getY(i), z = position.getZ(i);
    rest.set([x, y, z], i * 3);
    center.x += x; center.y += y; center.z += z;
    low.min(new THREE.Vector3(x, y, z));
    high.max(new THREE.Vector3(x, y, z));
  }
  center.divideScalar(position.count);
  const extent = high.sub(low);
  const axis = new THREE.Vector3(extent.x >= extent.y && extent.x >= extent.z ? 1 : 0,
    extent.y > extent.x && extent.y >= extent.z ? 1 : 0,
    extent.z > extent.x && extent.z > extent.y ? 1 : 0);
  const covariance = new Float64Array(9);
  for (let i = 0; i < position.count; i++) {
    const x = rest[i * 3] - center.x;
    const y = rest[i * 3 + 1] - center.y;
    const z = rest[i * 3 + 2] - center.z;
    covariance[0] += x * x; covariance[1] += x * y; covariance[2] += x * z;
    covariance[4] += y * y; covariance[5] += y * z; covariance[8] += z * z;
  }
  covariance[3] = covariance[1]; covariance[6] = covariance[2]; covariance[7] = covariance[5];
  for (let step = 0; step < 16; step++) {
    const x = covariance[0] * axis.x + covariance[1] * axis.y + covariance[2] * axis.z;
    const y = covariance[3] * axis.x + covariance[4] * axis.y + covariance[5] * axis.z;
    const z = covariance[6] * axis.x + covariance[7] * axis.y + covariance[8] * axis.z;
    axis.set(x, y, z).normalize();
  }
  let first = Infinity, last = -Infinity;
  for (let i = 0; i < position.count; i++) {
    const projection = (rest[i * 3] - center.x) * axis.x +
      (rest[i * 3 + 1] - center.y) * axis.y + (rest[i * 3 + 2] - center.z) * axis.z;
    first = Math.min(first, projection);
    last = Math.max(last, projection);
  }
  if (!Number.isFinite(last - first) || last - first < 0.01) {
    throw new Error(`Atlas muscle has no valid long axis: ${mesh.name}`);
  }
  return { mesh, girth, rest, center, axis, first, last, appliedScale: 1 };
}

export function applyReferenceMuscleThickness(shape: ReferenceMuscleShape, scale: number): void {
  if (!Number.isFinite(scale) || scale < 0.8 || scale > 1.2) {
    throw new Error('Atlas muscle thickness scale must stay within 0.8–1.2');
  }
  if (shape.appliedScale === scale) return;
  const position = shape.mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
  const { rest, center, axis, first, last } = shape;
  for (let i = 0; i < position.count; i++) {
    const x = rest[i * 3], y = rest[i * 3 + 1], z = rest[i * 3 + 2];
    const dx = x - center.x, dy = y - center.y, dz = z - center.z;
    const axial = dx * axis.x + dy * axis.y + dz * axis.z;
    const fraction = THREE.MathUtils.clamp((axial - first) / (last - first), 0, 1);
    const gain = (scale - 1) * Math.sin(Math.PI * fraction) ** 2;
    position.setXYZ(i, x + (dx - axial * axis.x) * gain,
      y + (dy - axial * axis.y) * gain, z + (dz - axial * axis.z) * gain);
  }
  position.needsUpdate = true;
  shape.mesh.geometry.computeVertexNormals();
  shape.mesh.geometry.computeBoundingSphere();
  shape.mesh.geometry.computeBoundingBox();
  shape.appliedScale = scale;
}
