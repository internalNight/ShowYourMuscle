import * as THREE from 'three';

// A path-shaped teaching volume. It is not a registered muscle surface.
export const PECTORALIS_PROXY_RINGS = 21;
export const PECTORALIS_PROXY_SIDES = 8;

export function createPectoralisProxyGeometry(): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(PECTORALIS_PROXY_RINGS * PECTORALIS_PROXY_SIDES * 3);
  const indices: number[] = [];
  for (let ring = 0; ring < PECTORALIS_PROXY_RINGS - 1; ring++) {
    for (let side = 0; side < PECTORALIS_PROXY_SIDES; side++) {
      const next = (side + 1) % PECTORALIS_PROXY_SIDES;
      const a = ring * PECTORALIS_PROXY_SIDES + side;
      const b = ring * PECTORALIS_PROXY_SIDES + next;
      const c = (ring + 1) * PECTORALIS_PROXY_SIDES + side;
      const d = (ring + 1) * PECTORALIS_PROXY_SIDES + next;
      indices.push(a, c, b, b, c, d);
    }
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  return geometry;
}

function pointOnPath(path: THREE.Vector3[], fraction: number, target: THREE.Vector3): THREE.Vector3 {
  const lengths = path.slice(1).map((point, index) => point.distanceTo(path[index]));
  let remaining = THREE.MathUtils.clamp(fraction, 0, 1) * lengths.reduce((a, b) => a + b, 0);
  for (let index = 0; index < lengths.length; index++) {
    if (remaining <= lengths[index] && lengths[index] > 0) {
      return target.copy(path[index]).lerp(path[index + 1], remaining / lengths[index]);
    }
    remaining -= lengths[index];
  }
  return target.copy(path[path.length - 1]);
}

export function updatePectoralisProxyGeometry(geometry: THREE.BufferGeometry,
  points: Array<[number, number, number]>, baseRadiusM: number): void {
  const path = points.map(point => new THREE.Vector3(...point));
  const position = geometry.getAttribute('position') as THREE.BufferAttribute;
  const center = new THREE.Vector3();
  const tangent = path[path.length - 1].clone().sub(path[0]).normalize();
  const normal = new THREE.Vector3();
  const binormal = new THREE.Vector3();
  const reference = Math.abs(tangent.z) < 0.9
    ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(0, 1, 0);
  normal.crossVectors(tangent, reference).normalize();
  binormal.crossVectors(tangent, normal).normalize();
  for (let ring = 0; ring < PECTORALIS_PROXY_RINGS; ring++) {
    const fraction = ring / (PECTORALIS_PROXY_RINGS - 1);
    pointOnPath(path, fraction, center);
    const radius = baseRadiusM * (0.15 + 0.85 * Math.sin(Math.PI * fraction) ** 0.8);
    for (let side = 0; side < PECTORALIS_PROXY_SIDES; side++) {
      const angle = side * 2 * Math.PI / PECTORALIS_PROXY_SIDES;
      const offset = ring * PECTORALIS_PROXY_SIDES + side;
      position.setXYZ(offset,
        center.x + radius * (Math.cos(angle) * normal.x + Math.sin(angle) * binormal.x),
        center.y + radius * (Math.cos(angle) * normal.y + Math.sin(angle) * binormal.y),
        center.z + radius * (Math.cos(angle) * normal.z + Math.sin(angle) * binormal.z));
    }
  }
  position.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
}
