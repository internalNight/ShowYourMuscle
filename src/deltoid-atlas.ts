import * as THREE from 'three';

export type DeltoidAtlasItem = {
  mesh: THREE.Mesh;
  exercise: 'bench' | 'press';
  muscle: string;
  rest: Float32Array;
  fractions: Float32Array;
  restingPath: Float32Array;
};

type MeasuredPath = { points: THREE.Vector3[]; lengths: number[]; total: number };

function measurePath(path: Array<[number, number, number]>): MeasuredPath {
  const points = path.map(point => new THREE.Vector3(...point));
  const lengths = points.slice(1).map((point, index) => point.distanceTo(points[index]));
  return { points, lengths, total: lengths.reduce((sum, value) => sum + value, 0) };
}

function atFraction(path: MeasuredPath, fraction: number, target: THREE.Vector3): THREE.Vector3 {
  let remaining = fraction * path.total;
  for (let index = 0; index < path.lengths.length; index++) {
    const length = path.lengths[index];
    if (remaining <= length && length > 0) {
      return target.copy(path.points[index]).lerp(path.points[index + 1], remaining / length);
    }
    remaining -= length;
  }
  return target.copy(path.points[path.points.length - 1]);
}

// This candidate transport mirrors the saved Blender shape keys; length color
// remains based on the separate OpenSim muscle-tendon path.
export function prepareDeltoidAtlas(mesh: THREE.Mesh, exercise: 'bench' | 'press',
  muscle: string, startingPath: Array<[number, number, number]>): DeltoidAtlasItem {
  const position = mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
  const rest = new Float32Array(position.array as ArrayLike<number>);
  const fractions = new Float32Array(position.count);
  const restingPath = new Float32Array(rest.length);
  const start = new THREE.Vector3(...startingPath[0]);
  const axis = new THREE.Vector3(...startingPath[startingPath.length - 1]).sub(start);
  const squared = axis.lengthSq();
  if (squared < 0.001) throw new Error(`三角肌研究路径过短：${muscle}`);
  const measured = measurePath(startingPath);
  const point = new THREE.Vector3();
  const onPath = new THREE.Vector3();
  for (let index = 0; index < position.count; index++) {
    point.fromArray(rest, index * 3).sub(start);
    const fraction = THREE.MathUtils.clamp(point.dot(axis) / squared, 0, 1);
    fractions[index] = fraction;
    atFraction(measured, fraction, onPath).toArray(restingPath, index * 3);
  }
  return { mesh, exercise, muscle, rest, fractions, restingPath };
}

export function updateDeltoidAtlas(item: DeltoidAtlasItem, rigid: THREE.Matrix4,
  currentPath: Array<[number, number, number]>): void {
  const measured = measurePath(currentPath);
  const position = item.mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
  const point = new THREE.Vector3();
  const rigidPathPoint = new THREE.Vector3();
  const currentPathPoint = new THREE.Vector3();
  for (let index = 0; index < position.count; index++) {
    const offset = index * 3;
    const fraction = item.fractions[index];
    point.fromArray(item.rest, offset).applyMatrix4(rigid);
    rigidPathPoint.fromArray(item.restingPath, offset).applyMatrix4(rigid);
    atFraction(measured, fraction, currentPathPoint);
    point.addScaledVector(currentPathPoint.sub(rigidPathPoint), .25 * (1 - fraction) ** 2);
    position.setXYZ(index, point.x, point.y, point.z);
  }
  position.needsUpdate = true;
  item.mesh.geometry.computeVertexNormals();
  item.mesh.geometry.computeBoundingSphere();
}
