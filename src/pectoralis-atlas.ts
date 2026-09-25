import * as THREE from 'three';
import type { ReferenceMuscleShape } from './reference-shape';

export type PectoralisAtlasItem = {
  mesh: THREE.Mesh;
  exercise: 'bench' | 'press';
  muscle: string;
  parent: 'clavicle' | 'thorax';
  shape: ReferenceMuscleShape;
  fractions: Float32Array;
  fractionsReady: boolean;
  endpointCorrectionWeight: number;
};

// Fractions and endpoint transport mirror the Blender shape-key experiment.
// Width adjustment is a visual change derived from the untouched rest mesh.
export function createPectoralisAtlasFractions(shape: ReferenceMuscleShape,
  startingPath: Array<[number, number, number]>): Float32Array {
  const start = new THREE.Vector3(...startingPath[0]);
  const axis = new THREE.Vector3(...startingPath[startingPath.length - 1]).sub(start);
  const squared = axis.lengthSq();
  if (squared < 0.001) throw new Error('胸大肌起始路径过短');
  const result = new Float32Array(shape.rest.length / 3);
  const point = new THREE.Vector3();
  for (let index = 0; index < result.length; index++) {
    point.fromArray(shape.rest, index * 3).sub(start);
    result[index] = THREE.MathUtils.clamp(point.dot(axis) / squared, 0, 1);
  }
  return result;
}

export function updatePectoralisAtlas(item: PectoralisAtlasItem, rigid: THREE.Matrix4,
  startingPath: Array<[number, number, number]>,
  currentPath: Array<[number, number, number]>, widthScale: number): void {
  if (!Number.isFinite(widthScale) || widthScale < 0.8 || widthScale > 1.2) {
    throw new Error('胸肌视觉宽度比例超出范围');
  }
  const { mesh, shape, fractions } = item;
  const position = mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
  const initialOrigin = new THREE.Vector3(...startingPath[0]).applyMatrix4(rigid);
  const initialInsertion = new THREE.Vector3(...startingPath[startingPath.length - 1]).applyMatrix4(rigid);
  const originDelta = new THREE.Vector3(...currentPath[0]).sub(initialOrigin);
  const insertionDelta = new THREE.Vector3(...currentPath[currentPath.length - 1]).sub(initialInsertion);
  const correction = item.endpointCorrectionWeight;
  const { rest, center, axis, first, last } = shape;
  const point = new THREE.Vector3();
  for (let index = 0; index < position.count; index++) {
    const offset = index * 3;
    const x = rest[offset], y = rest[offset + 1], z = rest[offset + 2];
    const dx = x - center.x, dy = y - center.y, dz = z - center.z;
    const axial = dx * axis.x + dy * axis.y + dz * axis.z;
    const along = THREE.MathUtils.clamp((axial - first) / (last - first), 0, 1);
    const gain = (widthScale - 1) * Math.sin(Math.PI * along) ** 2;
    point.set(x + (dx - axial * axis.x) * gain,
      y + (dy - axial * axis.y) * gain, z + (dz - axial * axis.z) * gain)
      .applyMatrix4(rigid);
    point.addScaledVector(originDelta, correction * (1 - fractions[index]));
    point.addScaledVector(insertionDelta, correction * fractions[index]);
    position.setXYZ(index, point.x, point.y, point.z);
  }
  position.needsUpdate = true;
  mesh.geometry.computeVertexNormals();
  mesh.geometry.computeBoundingSphere();
}
