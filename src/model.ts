import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { createPectoralisAtlasFractions, updatePectoralisAtlas,
  type PectoralisAtlasItem } from './pectoralis-atlas';
import { prepareDeltoidAtlas, updateDeltoidAtlas, type DeltoidAtlasItem } from './deltoid-atlas';
import { applyReferenceMuscleThickness, prepareReferenceMuscleShape, referenceGirthForName,
  type ReferenceMuscleShape } from './reference-shape';
import { clamp, type BodyProfile, type ExerciseId, type ViewMode } from './domain';
import standingRegistration from '../docs/data/standing_registration_probe.json';
import tsmUpperBoneRegistration from './data/tsm_upper_bone_registration.json';
import tsmPectoralisAtlasRegistration from './data/tsm_press_pectoralis_atlas_registration.json';
import tsmBenchPectoralisAtlasRegistration from './data/tsm_bench_pectoralis_atlas_registration.json';

type JointName = 'pelvis' | 'chest' | 'neck' | 'head' | 'shoulderL' | 'shoulderR' |
  'elbowL' | 'elbowR' | 'wristL' | 'wristR' | 'hipL' | 'hipR' |
  'kneeL' | 'kneeR' | 'ankleL' | 'ankleR';
type Pose = Record<JointName, THREE.Vector3>;
type Muscle = {
  label: string;
  mesh: THREE.Mesh;
  secondMesh: THREE.Mesh;
  points: (pose: Pose) => THREE.Vector3[];
  baseline: number;
  category: 'upperArm' | 'waist' | 'thigh' | 'calf' | 'chest' | 'back';
};
export type MuscleCategory = Muscle['category'];
type RegisteredAnatomyMuscle = {
  mesh: THREE.Mesh;
  identityColor: number;
  body: 'pelvis' | 'femur_r' | 'tibia_r';
  girth: 'none' | 'thigh' | 'calf';
  restingBlender: Float32Array;
  fractions: Float32Array;
  restingPath: Float32Array;
  lastPhase: number;
  lastThicknessScale: number;
};
type TsmUpperMuscle = {
  mesh: THREE.Mesh;
  exercise: 'bench' | 'press';
  standing: Float32Array;
  fractions?: Float32Array;
  restingPath?: Float32Array;
};
type TsmDeltoidCandidate = {
  mesh: THREE.Mesh;
  exercise: 'bench' | 'press';
  muscle: string;
  prepared?: DeltoidAtlasItem;
};
const registeredMuscleSpecs: Record<string, { id: string; color: number; body: 'pelvis' | 'femur_r' | 'tibia_r'; girth: 'none' | 'thigh' | 'calf' }> = {
  'Gluteus maximus muscler': { id: 'glut_max2_r', color: 0xd9927d, body: 'pelvis', girth: 'none' },
  'Rectus femoris muscler': { id: 'rect_fem_r', color: 0x9875c7, body: 'femur_r', girth: 'thigh' },
  'Short head of biceps femorisr': { id: 'bifemsh_r', color: 0x66b3c7, body: 'femur_r', girth: 'thigh' },
  'Semimembranosus muscler': { id: 'semimem_r', color: 0xc18fb3, body: 'femur_r', girth: 'thigh' },
  'Tibialis anterior muscler': { id: 'tib_ant_r', color: 0x80bb94, body: 'tibia_r', girth: 'calf' },
  'Soleus muscler': { id: 'soleus_r', color: 0xd1a36b, body: 'tibia_r', girth: 'calf' },
};
const tsmDeltoidSpecs = [
  { muscle: 'DeltoideusClavicle_A', atlas: 'Clavicular part of deltoid muscler' },
  { muscle: 'DeltoideusScapula_M', atlas: 'Acromial part of deltoid muscler' },
  { muscle: 'DeltoideusScapula_P', atlas: 'Scapular spinal part of deltoid muscler' },
] as const;
export type RegisteredMuscleColorMode = 'identity' | 'path-length';
export type JointMomentOverlay = ReadonlyArray<
  { joint: string; source: 'barbell'; magnitudeNm: number } |
  { joint: string; source: 'study'; magnitudeNmPerKg: number }
>;

function momentBadge(label: string, ringColor = '#f4a667'): THREE.Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('无法绘制关节外力标记');
  context.fillStyle = 'rgba(16, 33, 50, 0.91)';
  context.beginPath();
  context.arc(64, 64, 39, 0, Math.PI * 2);
  context.fill();
  context.strokeStyle = ringColor;
  context.lineWidth = 9;
  context.beginPath();
  context.arc(64, 64, 43, 0, Math.PI * 2);
  context.stroke();
  context.fillStyle = '#fff2df';
  context.font = 'bold 40px sans-serif';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(label, 64, 66);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(canvas), transparent: true, depthTest: false, depthWrite: false,
  }));
  sprite.renderOrder = 10;
  sprite.visible = false;
  return sprite;
}

export function momentBadgeDiameter(momentNm: number): number {
  const magnitude = Math.max(0, momentNm);
  return 0.13 + 0.2 * magnitude / (magnitude + 90);
}

export function studyMomentBadgeDiameter(momentNmPerKg: number): number {
  const magnitude = Math.max(0, momentNmPerKg);
  return 0.13 + 0.2 * magnitude / (magnitude + 0.6);
}

function pathLengthColor(ratio: number): string {
  if (ratio > 1.025) return '#42b9db';
  if (ratio < 0.975) return '#c78ad8';
  return '#af818b';
}
export type OpenSimFrame = {
  phase: number;
  viewerJointsM: Record<string, [number, number, number]>;
  blenderBodyFrames?: Record<string, { translationM: [number, number, number]; rotationRows: number[][] }>;
  muscles: Record<string, {
    lengthM: number;
    ratioToStanding?: number;
    ratioToStartingPose?: number;
    momentArmsM: Record<string, number>;
    viewerPathM: Array<[number, number, number]>;
  }>;
};

const boneConnections: Array<[JointName, JointName]> = [
  ['pelvis', 'chest'], ['chest', 'neck'], ['neck', 'head'],
  ['chest', 'shoulderL'], ['chest', 'shoulderR'],
  ['shoulderL', 'elbowL'], ['shoulderR', 'elbowR'],
  ['elbowL', 'wristL'], ['elbowR', 'wristR'],
  ['pelvis', 'hipL'], ['pelvis', 'hipR'],
  ['hipL', 'kneeL'], ['hipR', 'kneeR'],
  ['kneeL', 'ankleL'], ['kneeR', 'ankleR'],
];

function mix(a: THREE.Vector3, b: THREE.Vector3, t: number): THREE.Vector3 {
  return a.clone().lerp(b, t);
}

function positionBetween(mesh: THREE.Object3D, a: THREE.Vector3, b: THREE.Vector3, radius: number): void {
  const direction = b.clone().sub(a);
  mesh.position.copy(a).addScaledVector(direction, 0.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.clone().normalize());
  mesh.scale.set(radius, direction.length() / 2, radius);
}

const torsoRingPositions = [0, 0.18, 0.45, 0.72, 0.94, 1.04];
const torsoSides = 64;

function makeTorsoGeometry(): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(torsoRingPositions.length * torsoSides * 3);
  const indices: number[] = [];
  for (let ring = 0; ring < torsoRingPositions.length - 1; ring++) {
    for (let side = 0; side < torsoSides; side++) {
      const next = (side + 1) % torsoSides;
      const a = ring * torsoSides + side;
      const b = ring * torsoSides + next;
      const c = (ring + 1) * torsoSides + side;
      const d = (ring + 1) * torsoSides + next;
      indices.push(a, b, c, b, d, c);
    }
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  return geometry;
}

function shapeTorso(mesh: THREE.Mesh, pelvis: THREE.Vector3, chest: THREE.Vector3,
  waistHalfWidthM: number, waistHalfDepthM: number,
  chestHalfWidthM: number, chestHalfDepthM: number, statureScale: number): void {
  const height = chest.distanceTo(pelvis);
  const baseChestWidth = Math.max(0.225 * statureScale, waistHalfWidthM * 1.16);
  const baseChestDepth = Math.max(0.165 * statureScale, waistHalfDepthM * 1.14);
  const width = [Math.max(0.18 * statureScale, waistHalfWidthM * 1.12),
    Math.max(0.155 * statureScale, waistHalfWidthM * 1.03), waistHalfWidthM,
    Math.max(0.18 * statureScale, waistHalfWidthM * 1.12),
    chestHalfWidthM,
    Math.max(0.195 * statureScale, waistHalfWidthM * 1.08) * chestHalfWidthM / baseChestWidth];
  const depth = [Math.max(0.13 * statureScale, waistHalfDepthM * 1.08),
    Math.max(0.12 * statureScale, waistHalfDepthM * 1.03), waistHalfDepthM,
    Math.max(0.145 * statureScale, waistHalfDepthM * 1.09),
    chestHalfDepthM,
    Math.max(0.135 * statureScale, waistHalfDepthM * 1.04) * chestHalfDepthM / baseChestDepth];
  const attribute = mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
  for (let ring = 0; ring < torsoRingPositions.length; ring++) {
    for (let side = 0; side < torsoSides; side++) {
      const angle = side * 2 * Math.PI / torsoSides;
      attribute.setXYZ(ring * torsoSides + side,
        width[ring] * Math.cos(angle), height * torsoRingPositions[ring], depth[ring] * Math.sin(angle));
    }
  }
  attribute.needsUpdate = true;
  mesh.geometry.computeVertexNormals();
  mesh.geometry.computeBoundingSphere();
  mesh.position.copy(pelvis);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), chest.clone().sub(pelvis).normalize());
}

function solveJoint(start: THREE.Vector3, end: THREE.Vector3, first: number, second: number, bendHint: THREE.Vector3): THREE.Vector3 {
  const line = end.clone().sub(start);
  const distance = line.length();
  const direction = line.clone().normalize();
  const along = (first * first - second * second + distance * distance) / (2 * distance);
  const outward = Math.sqrt(Math.max(0, first * first - along * along));
  const bend = bendHint.clone().addScaledVector(direction, -bendHint.dot(direction)).normalize();
  return start.clone().addScaledVector(direction, along).addScaledVector(bend, outward);
}

// Dimensions of the teaching skeleton. Inseam and arm span set segment ratios,
// while standing stature stays anchored to height. This is a geometry mapping,
// not a reconstruction of a person's bones from surface measurements.
export function profileSegmentDimensions(profile: BodyProfile): {
  femurM: number; tibiaM: number; upperArmM: number; forearmM: number;
  torsoM: number; appliedInseamCm: number; appliedArmSpanCm: number;
  inseamClamped: boolean; armSpanClamped: boolean;
} {
  const stature = profile.heightCm / 175;
  const requestedInseam = profile.inseamCm ?? 80 * stature;
  const legFactor = clamp(requestedInseam / (80 * stature), 0.85, 1.16);
  const appliedInseamCm = 80 * stature * legFactor;
  const requestedArmSpan = profile.armSpanCm ?? profile.heightCm;
  const appliedArmSpanCm = clamp(requestedArmSpan, profile.heightCm * 0.88, profile.heightCm * 1.12);
  const shoulderSpanM = 0.54 * stature;
  const eachArmM = (appliedArmSpanCm / 100 - shoulderSpanM) / 2;
  const femurM = 0.46 * stature * legFactor;
  const tibiaM = 0.42 * stature * legFactor;
  return {
    femurM, tibiaM,
    upperArmM: eachArmM * 0.34 / 0.61,
    forearmM: eachArmM * 0.27 / 0.61,
    torsoM: 0.44 * stature - (femurM + tibiaM - 0.88 * stature),
    appliedInseamCm, appliedArmSpanCm,
    inseamClamped: Math.abs(requestedInseam - appliedInseamCm) > 0.01,
    armSpanClamped: Math.abs(requestedArmSpan - appliedArmSpanCm) > 0.01,
  };
}

export function squatBarSagittalZ(shoulderZ: number, offsetCm = 0): number {
  return shoulderZ - 0.045 + offsetCm / 100;
}

export function createPose(profile: BodyProfile, exercise: ExerciseId, phase: number,
  squatBarOffsetCm = 0, squatDepthDeg?: number): Pose {
  const s = profile.heightCm / 175;
  const segments = profileSegmentDimensions(profile);
  const side = (x: number, sign: number) => x * sign * s;
  const smoothCycle = Math.sin(Math.PI * phase) ** 2;
  const down = exercise === 'squat' ? smoothCycle : 0;
  const press = exercise === 'press' ? smoothCycle : 0;
  const benchDown = exercise === 'bench' ? smoothCycle : 0;
  const femurLength = segments.femurM;
  const tibiaLength = segments.tibiaM;
  const upperArmLength = segments.upperArmM;
  const forearmLength = segments.forearmM;
  // Keep the neutral knee slightly flexed. A fully extended two-link IK leg
  // is singular and creates spurious acceleration in inverse dynamics.
  const standingHipY = 0.10 * s + femurLength + tibiaLength - 0.015 * s;
  // When a depth target is supplied, solve the bottom hip height from the
  // two fixed leg lengths and the selected knee angle. Keep the existing
  // prototype trajectory unchanged when no depth target is supplied.
  const targetSpanSq = squatDepthDeg === undefined ? undefined
    : femurLength ** 2 + tibiaLength ** 2
      + 2 * femurLength * tibiaLength * Math.cos(squatDepthDeg * Math.PI / 180);
  const bottomHipVerticalM = targetSpanSq === undefined ? undefined
    : Math.sqrt(Math.max(0, targetSpanSq - (0.02 * s) ** 2 - (0.225 * s) ** 2));
  const hipDropM = bottomHipVerticalM === undefined ? 0.32 * s
    : standingHipY - (0.10 * s + bottomHipVerticalM);
  const hipY = standingHipY - hipDropM * down;
  const hipZ = -0.225 * down * s;
  // A torso lean keeps the default illustrative body+bar gravity line near
  // the ankle through the squat. This is a geometric teaching trajectory,
  // not a measured athlete's bar path or inverse-dynamics solution.
  const torsoForwardM = Math.min(0.345 * s, 0.80 * segments.torsoM) * down;
  const chestY = hipY + Math.sqrt(segments.torsoM ** 2 - torsoForwardM ** 2);
  const chestZ = hipZ + torsoForwardM;
  const result = {} as Pose;
  result.pelvis = new THREE.Vector3(0, hipY, hipZ);
  result.chest = new THREE.Vector3(0, chestY, chestZ);
  result.neck = new THREE.Vector3(0, chestY + 0.14 * s, chestZ);
  result.head = new THREE.Vector3(0, chestY + 0.25 * s, chestZ);
  for (const sign of [-1, 1]) {
    const suffix = sign < 0 ? 'L' : 'R';
    const assign = (joint: string, value: THREE.Vector3) => {
      result[`${joint}${suffix}` as JointName] = value;
    };
    const shoulder = new THREE.Vector3(side(0.27, sign), chestY + 0.025 * s, chestZ);
    assign('shoulder', shoulder);
    const hip = new THREE.Vector3(side(0.16, sign), hipY, hipZ);
    const ankle = new THREE.Vector3(side(0.18, sign), 0.10 * s, 0);
    assign('hip', hip);
    assign('knee', solveJoint(hip, ankle, femurLength, tibiaLength, new THREE.Vector3(0, 0, 1)));
    assign('ankle', ankle);
    if (exercise === 'bench') {
      const wrist = new THREE.Vector3(side(0.32, sign), chestY - 0.05 * s, (0.41 - 0.24 * benchDown) * s);
      assign('wrist', wrist);
      assign('elbow', solveJoint(shoulder, wrist, upperArmLength, forearmLength, new THREE.Vector3(sign, 0, 0)));
    } else if (exercise === 'press') {
      // Illustrative standing bar path screened against An et al. (2025)
      // group ranges: ~44 cm vertical and ~9 cm AP in 173 cm participants.
      // The paper describes a small initial forward motion followed by a
      // posterior return toward the shoulder. The bend location is a teaching
      // choice, since participant-level trajectories were not published.
      // Group means do not validate this subject's joint trajectory.
      // Both hands stay fixed on a rigid bar throughout the repetition.
      const smoothStep = (value: number) => {
        const t = clamp(value, 0, 1);
        return t * t * (3 - 2 * t);
      };
      const barSagittalM = press <= 0.2
        ? 0.12 + 0.02 * smoothStep(press / 0.2)
        : 0.14 - 0.093 * smoothStep((press - 0.2) / 0.8);
      const wrist = new THREE.Vector3(side(0.34, sign),
        chestY + (0.133 + 0.443 * press) * s,
        chestZ + barSagittalM * s);
      // Short arm spans can make the group-average overhead height unreachable.
      const maxReach = upperArmLength + forearmLength - 0.005 * s;
      const dx = wrist.x - shoulder.x;
      const dz = wrist.z - shoulder.z;
      wrist.y = Math.min(wrist.y,
        shoulder.y + Math.sqrt(Math.max(0, maxReach ** 2 - dx ** 2 - dz ** 2)));
      assign('wrist', wrist);
      assign('elbow', solveJoint(shoulder, wrist, upperArmLength, forearmLength, new THREE.Vector3(sign, 0, 0)));
    } else {
      const wrist = new THREE.Vector3(side(0.42, sign), shoulder.y + 0.09,
        squatBarSagittalZ(shoulder.z, squatBarOffsetCm));
      assign('wrist', wrist);
      assign('elbow', solveJoint(shoulder, wrist, upperArmLength, forearmLength,
        new THREE.Vector3(sign * 0.4, -1, 0.3)));
    }
  }
  return result;
}

export function squatKneeFlexionDeg(pose: Pose): number {
  const thigh = pose.hipR.clone().sub(pose.kneeR);
  const shank = pose.ankleR.clone().sub(pose.kneeR);
  const cosine = clamp(thigh.dot(shank) / (thigh.length() * shank.length()), -1, 1);
  return 180 - Math.acos(cosine) * 180 / Math.PI;
}

// Cross-section dimensions for the illustrative shell. A measured girth
// constrains the outer contour; it does not determine individual muscle size.
export function profileOuterDimensions(profile: BodyProfile): {
  upperArmRadiusM: number; thighRadiusM: number; calfRadiusM: number;
  waistHalfWidthM: number; waistHalfDepthM: number; waistCircumferenceCm: number;
  chestHalfWidthM: number; chestHalfDepthM: number; chestCircumferenceCm: number;
} {
  const stature = profile.heightCm / 175;
  const fat = clamp(profile.bodyFatPct ?? 20, 3, 65);
  const massPrior = clamp(Math.cbrt(profile.weightKg / (72 * stature ** 3)), 0.76, 1.35);
  const softTissuePrior = clamp(1 + (fat - 20) * 0.004, 0.82, 1.18);
  const fallback = stature * massPrior * softTissuePrior;
  const armCm = profile.upperArmCm ?? 32 * fallback;
  const waistCm = profile.waistCm ?? 82 * fallback;
  const thighCm = profile.thighCm ?? 54 * fallback;
  const calfCm = profile.calfCm ?? 36 * fallback;
  const waistAspect = 1.25;
  // Ramanujan's ellipse-perimeter approximation is linear in the scale.
  const unitWaistPerimeter = Math.PI * (3 * (waistAspect + 1) -
    Math.sqrt((3 * waistAspect + 1) * (waistAspect + 3)));
  const waistHalfDepthM = (waistCm / 100) / unitWaistPerimeter;
  const waistHalfWidthM = waistHalfDepthM * waistAspect;
  const baseChestHalfWidthM = Math.max(0.225 * stature, waistHalfWidthM * 1.16);
  const baseChestHalfDepthM = Math.max(0.165 * stature, waistHalfDepthM * 1.14);
  const chestAspect = baseChestHalfWidthM / baseChestHalfDepthM;
  const unitChestPerimeter = Math.PI * (3 * (chestAspect + 1) -
    Math.sqrt((3 * chestAspect + 1) * (chestAspect + 3)));
  const defaultChestCm = baseChestHalfDepthM * unitChestPerimeter * 100;
  const chestCm = profile.chestCm ?? defaultChestCm;
  const chestHalfDepthM = (chestCm / 100) / unitChestPerimeter;
  return {
    upperArmRadiusM: (armCm / 100) / (2 * Math.PI),
    thighRadiusM: (thighCm / 100) / (2 * Math.PI),
    calfRadiusM: (calfCm / 100) / (2 * Math.PI),
    waistHalfWidthM,
    waistHalfDepthM,
    waistCircumferenceCm: waistCm,
    chestHalfWidthM: chestHalfDepthM * chestAspect,
    chestHalfDepthM,
    chestCircumferenceCm: chestCm,
  };
}

// Shared by the phone preview and Blender authoring export. This is a visual
// thickness heuristic, not a measurement of muscle volume or force.
export function illustrativeMuscleRadius(profile: BodyProfile, category: MuscleCategory): number {
  const outer = profileOuterDimensions(profile);
  const localScale = category === 'upperArm' ? outer.upperArmRadiusM / (0.32 / (2 * Math.PI))
    : category === 'waist' || category === 'back' ? outer.waistCircumferenceCm / 82
    : category === 'thigh' ? outer.thighRadiusM / (0.54 / (2 * Math.PI))
    : category === 'calf' ? outer.calfRadiusM / (0.36 / (2 * Math.PI))
    : category === 'chest' ? outer.chestCircumferenceCm / profileOuterDimensions({ heightCm: profile.heightCm,
      weightKg: profile.weightKg, bodyFatPct: profile.bodyFatPct, waistCm: profile.waistCm }).chestCircumferenceCm : 1;
  const base: Record<MuscleCategory, number> = {
    upperArm: 0.035, waist: 0.044, thigh: 0.057, calf: 0.039, chest: 0.048, back: 0.031,
  };
  const fat = clamp(profile.bodyFatPct ?? 20, 3, 65);
  const statureScale = profile.heightCm / 175;
  const leanMassPrior = profile.weightKg * (1 - fat / 100);
  const leanScale = clamp(Math.cbrt(leanMassPrior / (57.6 * statureScale ** 3)), 0.76, 1.3);
  return base[category] * Math.sqrt(localScale) * leanScale * statureScale;
}

// Bounded visual scenarios: circumference does not identify individual muscle
// volumes, attachments, or strength.
export function registeredThighThicknessScale(profile: BodyProfile): number {
  const referenceCircumferenceCm = 54 * profile.heightCm / 175;
  const measuredOrFallbackCm = profileOuterDimensions(profile).thighRadiusM * 200 * Math.PI;
  return clamp(measuredOrFallbackCm / referenceCircumferenceCm, 0.8, 1.2);
}

export function registeredCalfThicknessScale(profile: BodyProfile): number {
  const referenceCircumferenceCm = 36 * profile.heightCm / 175;
  const measuredOrFallbackCm = profileOuterDimensions(profile).calfRadiusM * 200 * Math.PI;
  return clamp(measuredOrFallbackCm / referenceCircumferenceCm, 0.8, 1.2);
}

export function registeredArmThicknessScale(profile: BodyProfile): number {
  const referenceCircumferenceCm = 32 * profile.heightCm / 175;
  const measuredOrFallbackCm = profileOuterDimensions(profile).upperArmRadiusM * 200 * Math.PI;
  return clamp(measuredOrFallbackCm / referenceCircumferenceCm, 0.8, 1.2);
}

export function registeredChestThicknessScale(profile: BodyProfile): number {
  const baseline = profileOuterDimensions({ ...profile, chestCm: undefined }).chestCircumferenceCm;
  return clamp(profileOuterDimensions(profile).chestCircumferenceCm / baseline, 0.8, 1.2);
}

export function registeredWaistThicknessScale(profile: BodyProfile): number {
  const baseline = profileOuterDimensions({ ...profile, waistCm: undefined }).waistCircumferenceCm;
  return clamp(profileOuterDimensions(profile).waistCircumferenceCm / baseline, 0.8, 1.2);
}

export function scaleRegisteredLimbPoint(point: THREE.Vector3, origin: THREE.Vector3,
  axis: THREE.Vector3, thicknessScale: number, axisPoint: THREE.Vector3): void {
  const axial = axisPoint.copy(point).sub(origin).dot(axis);
  axisPoint.copy(axis).multiplyScalar(axial).add(origin);
  point.sub(axisPoint).multiplyScalar(thicknessScale).add(axisPoint);
}

export const scaleRegisteredThighPoint = scaleRegisteredLimbPoint;

// Keeps the size of the teaching glyph roughly stable while its centerline
// changes length. This is visual geometry, not measured fibre volume or force.
export function illustrativeBellyRadiusScale(lengthRatio: number): number {
  return clamp(1 / Math.sqrt(Math.max(lengthRatio, 0.2)), 0.75, 1.25);
}


function buildIllustrativeMuscles(addMuscle: (label: string, category: MuscleCategory,
  points: (pose: Pose) => THREE.Vector3[]) => void): void {
    const alongTrunk = (pose: Pose, distance: number) =>
      pose.chest.clone().sub(pose.pelvis).normalize().multiplyScalar(distance);
    // A posterior offset tied to the illustrative torso direction keeps
    // teaching paths outside its back surface during squat trunk flexion.
    const back = (pose: Pose, distance: number) => {
      const trunk = alongTrunk(pose, 1);
      return new THREE.Vector3(0, trunk.z, -trunk.y).multiplyScalar(distance);
    };
    for (const sign of [-1, 1]) {
      const side = sign < 0 ? 'L' : 'R';
      const cn = sign < 0 ? '左' : '右';
      const p = (pose: Pose, name: string) => pose[`${name}${side}` as JointName];
      addMuscle(`${cn}胸大肌`, 'chest', pose => [
        pose.chest.clone().add(new THREE.Vector3(sign * 0.05, 0.035, 0.10)),
        mix(p(pose, 'shoulder'), p(pose, 'elbow'), 0.23).add(new THREE.Vector3(0, 0, 0.08)),
      ]);
      addMuscle(`${cn}三角肌`, 'upperArm', pose => [
        p(pose, 'shoulder').clone().add(new THREE.Vector3(sign * 0.04, 0.025, 0.02)),
        mix(p(pose, 'shoulder'), p(pose, 'elbow'), 0.48).add(new THREE.Vector3(sign * 0.025, 0, 0.04)),
      ]);
      addMuscle(`${cn}肱二头肌`, 'upperArm', pose => [
        mix(p(pose, 'shoulder'), p(pose, 'elbow'), 0.18).add(new THREE.Vector3(0, 0, 0.06)),
        mix(p(pose, 'elbow'), p(pose, 'wrist'), 0.13).add(new THREE.Vector3(0, 0, 0.06)),
      ]);
      addMuscle(`${cn}肱三头肌`, 'upperArm', pose => [
        p(pose, 'shoulder').clone().add(new THREE.Vector3(0, 0, -0.055)),
        p(pose, 'elbow').clone().add(new THREE.Vector3(0, 0, -0.05)),
      ]);
      addMuscle(`${cn}斜方肌上束`, 'back', pose => [
        pose.neck.clone().add(new THREE.Vector3(sign * 0.04, -0.04, 0)).add(back(pose, 0.06)),
        p(pose, 'shoulder').clone().add(back(pose, 0.075)),
      ]);
      addMuscle(`${cn}背阔肌`, 'back', pose => [
        mix(pose.pelvis, pose.chest, 0.18).add(new THREE.Vector3(sign * 0.13, 0, 0)).add(back(pose, 0.13)),
        mix(pose.pelvis, pose.chest, 0.63).add(new THREE.Vector3(sign * 0.18, 0, 0)).add(back(pose, 0.14)),
        mix(p(pose, 'shoulder'), p(pose, 'elbow'), 0.24).add(back(pose, 0.055)),
      ]);
      addMuscle(`${cn}竖脊肌`, 'back', pose => [
        pose.pelvis.clone().add(new THREE.Vector3(sign * 0.075, 0, 0)).add(alongTrunk(pose, 0.035)).add(back(pose, 0.115)),
        pose.chest.clone().add(new THREE.Vector3(sign * 0.08, 0, 0)).add(alongTrunk(pose, -0.045)).add(back(pose, 0.13)),
      ]);
      addMuscle(`${cn}臀大肌`, 'waist', pose => [
        p(pose, 'hip').clone().add(new THREE.Vector3(0, 0.01, -0.08)),
        mix(p(pose, 'hip'), p(pose, 'knee'), 0.31).add(new THREE.Vector3(0, 0, -0.07)),
      ]);
      addMuscle(`${cn}股四头肌`, 'thigh', pose => [
        mix(p(pose, 'hip'), p(pose, 'knee'), 0.12).add(new THREE.Vector3(0, 0, 0.055)),
        p(pose, 'knee').clone().add(new THREE.Vector3(0, 0, 0.10)),
        mix(p(pose, 'knee'), p(pose, 'ankle'), 0.08).add(new THREE.Vector3(0, 0, 0.045)),
      ]);
      addMuscle(`${cn}腘绳肌`, 'thigh', pose => [
        p(pose, 'hip').clone().add(new THREE.Vector3(0, 0, -0.06)),
        p(pose, 'knee').clone().add(new THREE.Vector3(0, 0, -0.09)),
        mix(p(pose, 'knee'), p(pose, 'ankle'), 0.08).add(new THREE.Vector3(0, 0, -0.05)),
      ]);
      addMuscle(`${cn}小腿肌群`, 'calf', pose => [
        mix(p(pose, 'knee'), p(pose, 'ankle'), 0.08).add(new THREE.Vector3(0, 0, -0.04)),
        mix(p(pose, 'knee'), p(pose, 'ankle'), 0.78).add(new THREE.Vector3(0, 0, -0.04)),
      ]);
    }
    addMuscle('腹直肌', 'waist', pose => [
      mix(pose.chest, pose.pelvis, 0.20).add(new THREE.Vector3(0, 0, 0.09)),
      mix(pose.chest, pose.pelvis, 0.84).add(new THREE.Vector3(0, 0, 0.08)),
    ]);
}

const illustrativeMuscleIds: Record<string, string> = {
  '胸大肌': 'pectoralis_major', '三角肌': 'deltoid',
  '肱二头肌': 'biceps_brachii', '肱三头肌': 'triceps_brachii',
  '臀大肌': 'gluteus_maximus', '股四头肌': 'quadriceps',
  '腘绳肌': 'hamstrings', '小腿肌群': 'calf', '腹直肌': 'rectus_abdominis',
  '斜方肌上束': 'trapezius_upper', '背阔肌': 'latissimus_dorsi', '竖脊肌': 'erector_spinae',
};

// The authoring export and phone renderer use the same path definitions.
export function illustrativeMusclePaths(profile: BodyProfile, exercise: ExerciseId, phase: number,
  squatBarOffsetCm = 0, squatDepthDeg?: number):
  Array<{ id: string; label: string; category: MuscleCategory; points: THREE.Vector3[]; ratio: number }> {
  const pose = createPose(profile, exercise, phase, squatBarOffsetCm, squatDepthDeg);
  const reference = createPose(profile, exercise, 0, squatBarOffsetCm, squatDepthDeg);
  const length = (points: THREE.Vector3[]) => points.slice(1)
    .reduce((sum, point, index) => sum + point.distanceTo(points[index]), 0);
  const result: Array<{ id: string; label: string; category: MuscleCategory;
    points: THREE.Vector3[]; ratio: number }> = [];
  buildIllustrativeMuscles((label, category, path) => {
    const side = label.startsWith('左') ? '_l' : label.startsWith('右') ? '_r' : '';
    const body = side ? label.slice(1) : label;
    const id = illustrativeMuscleIds[body] + side;
    const points = path(pose);
    result.push({ id, label, category, points, ratio: length(points) / length(path(reference)) });
  });
  return result;
}

export class AnatomyPrototype {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(38, 1, 0.01, 100);
  readonly renderer: THREE.WebGLRenderer;
  readonly muscleNames: string[] = [];
  assetLoaded = false;
  assetError = false;
  referenceLoaded = false;
  referenceError = false;
  selectedReferenceName = '';
  selectedReferenceIsBone = false;
  private readonly root = new THREE.Group();
  private readonly reference = new THREE.Group();
  private readonly opensimReference = new THREE.Group();
  private readonly registeredBones = new THREE.Group();
  private readonly registeredBoneMeshes = new Map<string, { mesh: THREE.Mesh; standingWorld: THREE.Matrix4 }>();
  private readonly registeredMuscles = new Map<string, RegisteredAnatomyMuscle>();
  private readonly tsmUpperBoneGroup = new THREE.Group();
  private readonly tsmUpperBoneMeshes = new Map<string, { mesh: THREE.Mesh; standingWorld: THREE.Matrix4; body: string; exercise: 'bench' | 'press' }>();
  private readonly tsmUpperMuscleMeshes = new Map<string, TsmUpperMuscle>();
  private readonly tsmPectoralisAtlasMeshes = new Map<string, PectoralisAtlasItem>();
  private readonly tsmDeltoidAtlasMeshes = new Map<string, TsmDeltoidCandidate>();
  tsmUpperBonesLoaded = false;
  tsmUpperBonesError = false;
  private tsmUpperBonesRequested = false;
  private tsmUpperBonesEnabled = false;
  registeredBonesLoaded = false;
  registeredBonesError = false;
  private registeredBonesRequested = false;
  private registeredBonesEnabled = false;
  private readonly opensimBones: THREE.Mesh[] = [];
  private readonly opensimJoints: THREE.Mesh[] = [];
  private readonly opensimPaths = new Map<string, { segments: THREE.Mesh[]; material: THREE.MeshStandardMaterial }>();
  private readonly rootMomentMarkers = new Map<string, THREE.Sprite>();
  private readonly studyMomentMarkers = new Map<string, THREE.Sprite>();
  private readonly opensimMomentMarkers = new Map<string, THREE.Sprite>();
  private readonly referenceBones: THREE.Mesh[] = [];
  private readonly referenceMuscles: THREE.Mesh[] = [];
  private readonly referenceMuscleShapes: ReferenceMuscleShape[] = [];
  private referenceScene?: THREE.Group;
  private referenceSourceCenter = new THREE.Vector3();
  private referenceSourceHeight = 1;
  private currentProfile: BodyProfile = { heightCm: 175, weightKg: 72 };
  private anatomyReferencePromise?: Promise<THREE.Group>;
  private selectedReferenceMesh?: THREE.Mesh;
  private referenceMode = false;
  private referenceRequested = false;
  private readonly anatomy = new THREE.Group();
  private readonly bones: THREE.Mesh[] = [];
  private readonly joints: THREE.Mesh[] = [];
  private readonly muscles: Muscle[] = [];
  private readonly skinSegments: Array<{ mesh: THREE.Mesh; start: JointName; end: JointName; type: 'upperArm' | 'thigh' | 'calf' }> = [];
  private readonly bar: THREE.Mesh;
  private readonly barPlates: THREE.Mesh[] = [];
  private readonly bench: THREE.Mesh;
  private readonly skin: THREE.Mesh;
  private readonly target = new THREE.Vector3(0, 0.92, 0);
  private azimuth = 0.16;
  private elevation = 0.22;
  private distance = 3.6;
  private opensimCameraFactor = 0.45;
  private opensimCameraOffset = 0;
  private readonly container: HTMLElement;
  private readonly onAssetChange?: () => void;

  constructor(container: HTMLElement, onAssetChange?: () => void) {
    this.container = container;
    this.onAssetChange = onAssetChange;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    container.append(this.renderer.domElement);
    this.scene.background = new THREE.Color('#101c2b');
    this.scene.add(new THREE.HemisphereLight(0xd9efff, 0x1d3041, 2.5));
    const key = new THREE.DirectionalLight(0xffffff, 3);
    key.position.set(-2, 5, 5);
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0x55c7e3, 2);
    rim.position.set(2, 2, -3);
    this.scene.add(rim);
    const floor = new THREE.GridHelper(4, 12, 0x2d5064, 0x234052);
    floor.position.y = 0.015;
    this.scene.add(floor);
    this.scene.add(this.root);
    this.reference.visible = false;
    this.scene.add(this.reference);
    this.opensimReference.visible = false;
    this.scene.add(this.opensimReference);
    // Blender -> GLTF rotates Z-up to Y-up. Reflecting GLTF X and adding
    // 0.09 m reproduces the research overlay's Blender -> viewer mapping.
    this.registeredBones.scale.x = -1;
    this.registeredBones.position.x = 0.09;
    this.opensimReference.add(this.registeredBones);
    this.tsmUpperBoneGroup.visible = false;
    this.opensimReference.add(this.tsmUpperBoneGroup);
    this.createOpenSimReference();
    this.root.add(this.anatomy);
    for (const joint of ['髋', '膝', '踝', '肩', '肘']) {
      const marker = momentBadge(joint);
      this.anatomy.add(marker);
      this.rootMomentMarkers.set(joint, marker);
      if (joint === '髋' || joint === '膝') {
        const studyMarker = momentBadge(joint, '#d8acff');
        this.anatomy.add(studyMarker);
        this.studyMomentMarkers.set(joint, studyMarker);
      }
      if (joint === '肩' || joint === '肘') {
        const researchMarker = momentBadge(joint);
        this.opensimReference.add(researchMarker);
        this.opensimMomentMarkers.set(joint, researchMarker);
      }
    }
    const boneGeometry = new THREE.CylinderGeometry(1, 1, 2, 10);
    const boneMaterial = new THREE.MeshStandardMaterial({ color: 0xdce9ed, roughness: 0.55 });
    for (const _connection of boneConnections) {
      const bone = new THREE.Mesh(boneGeometry, boneMaterial);
      this.anatomy.add(bone);
      this.bones.push(bone);
    }
    const jointGeometry = new THREE.SphereGeometry(1, 12, 8);
    for (const _joint of Array.from({ length: 16 })) {
      const joint = new THREE.Mesh(jointGeometry, boneMaterial);
      joint.scale.setScalar(0.032);
      this.anatomy.add(joint);
      this.joints.push(joint);
    }
    this.makeMuscles();
    this.skin = new THREE.Mesh(
      makeTorsoGeometry(),
      new THREE.MeshStandardMaterial({ color: 0x9fc2c7, transparent: true, opacity: 0.21,
        depthWrite: false, side: THREE.DoubleSide }),
    );
    this.anatomy.add(this.skin);
    const skinMaterial = new THREE.MeshStandardMaterial({
      color: 0x9fc2c7, transparent: true, opacity: 0.085, depthWrite: false, side: THREE.DoubleSide,
    });
    for (const side of ['L', 'R']) {
      for (const [start, end, type] of [
        [`shoulder${side}`, `elbow${side}`, 'upperArm'],
        [`hip${side}`, `knee${side}`, 'thigh'],
        [`knee${side}`, `ankle${side}`, 'calf'],
      ] as Array<[JointName, JointName, 'upperArm' | 'thigh' | 'calf']>) {
        const mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 14, 10), skinMaterial);
        this.anatomy.add(mesh);
        this.skinSegments.push({ mesh, start, end, type });
      }
    }
    this.bar = new THREE.Mesh(
      new THREE.CylinderGeometry(0.018, 0.018, 1.35, 12),
      new THREE.MeshStandardMaterial({ color: 0xe9b371, metalness: 0.55, roughness: 0.3 }),
    );
    this.bar.rotation.z = Math.PI / 2;
    this.anatomy.add(this.bar);
    for (const sign of [-1, 1]) {
      const plate = new THREE.Mesh(
        new THREE.CylinderGeometry(0.12, 0.12, 1, 18),
        new THREE.MeshStandardMaterial({ color: 0x3c5460, metalness: 0.48, roughness: 0.4 }),
      );
      plate.rotation.z = Math.PI / 2;
      plate.userData.side = sign;
      this.anatomy.add(plate);
      this.barPlates.push(plate);
    }
    this.bench = new THREE.Mesh(
      new THREE.BoxGeometry(0.52, 0.1, 1.35),
      new THREE.MeshStandardMaterial({ color: 0x496474, roughness: 0.8 }),
    );
    this.scene.add(this.bench);
    this.installControls();
    new ResizeObserver(() => this.resize()).observe(container);
    this.updateCamera();
    this.loadBlenderMeshes(onAssetChange);
  }

  private createOpenSimReference(): void {
    const boneMaterial = new THREE.MeshStandardMaterial({ color: 0xd7e5ec, roughness: 0.6 });
    const boneGeometry = new THREE.CylinderGeometry(1, 1, 2, 10);
    for (let index = 0; index < 5; index++) {
      const bone = new THREE.Mesh(boneGeometry, boneMaterial);
      this.opensimReference.add(bone);
      this.opensimBones.push(bone);
    }
    const jointGeometry = new THREE.SphereGeometry(1, 12, 8);
    for (let index = 0; index < 6; index++) {
      const joint = new THREE.Mesh(jointGeometry, boneMaterial);
      joint.scale.setScalar(0.023);
      this.opensimReference.add(joint);
      this.opensimJoints.push(joint);
    }
  }

  private loadAnatomyReference(): Promise<THREE.Group> {
    this.anatomyReferencePromise ??= new Promise((resolve, reject) => {
      new GLTFLoader().load('/models/z_anatomy_reference.glb', gltf => resolve(gltf.scene),
        undefined, reject);
    });
    return this.anatomyReferencePromise;
  }

  setTsmUpperBonesEnabled(enabled: boolean, onAssetChange?: () => void): void {
    this.tsmUpperBonesEnabled = enabled;
    this.tsmUpperBoneGroup.visible = enabled && this.tsmUpperBonesLoaded;
    if (!enabled || this.tsmUpperBonesRequested) return;
    this.tsmUpperBonesRequested = true;
    void this.loadAnatomyReference().then(gltfScene => {
      gltfScene.updateMatrixWorld(true);
      const toGlTf = new THREE.Matrix4().set(
        1, 0, 0, 0,  0, 0, 1, 0,  0, -1, 0, 0,  0, 0, 0, 1,
      );
      const fromGlTf = toGlTf.clone().invert();
      const matrixFromRows = (rows: number[][]) => new THREE.Matrix4().set(
        rows[0][0], rows[0][1], rows[0][2], rows[0][3],
        rows[1][0], rows[1][1], rows[1][2], rows[1][3],
        rows[2][0], rows[2][1], rows[2][2], rows[2][3],
        rows[3][0], rows[3][1], rows[3][2], rows[3][3],
      );
      const atlas = new Map<string, THREE.Mesh>();
      gltfScene.traverse(object => {
        if (object instanceof THREE.Mesh) {
          atlas.set(object.name.replaceAll('_', ' ').replace(/\.r$/, 'r'), object);
        }
      });
      for (const exercise of ['bench', 'press'] as const) {
        const humerusRegistration = tsmUpperBoneRegistration.exercises[exercise]
          .find(row => row.modelBody === 'humerus');
        if (!humerusRegistration) throw new Error(`缺少 ${exercise} 肱骨配准`);
        for (const row of tsmUpperBoneRegistration.exercises[exercise]) {
          const source = atlas.get(row.atlasSource.replace('.r', 'r'));
          if (!source) throw new Error(`缺少上肢解剖网格：${row.atlasSource}`);
          const mesh = source.clone();
          mesh.material = new THREE.MeshStandardMaterial({ color: 0xefb863, roughness: 0.68,
            side: THREE.DoubleSide });
          mesh.name = `tsm_${exercise}_${row.modelBody}`;
          mesh.matrixAutoUpdate = false;
          const registration = toGlTf.clone().multiply(matrixFromRows(row.atlasToModelBlenderRows))
            .multiply(fromGlTf);
          mesh.matrix.copy(registration).multiply(source.matrixWorld);
          this.tsmUpperBoneGroup.add(mesh);
          this.tsmUpperBoneMeshes.set(`${exercise}:${row.modelBody}`, {
            mesh, standingWorld: mesh.matrix.clone(), body: row.modelBody, exercise,
          });
        }
        const source = atlas.get('Long head of biceps brachiir');
        if (!source) throw new Error('缺少右肱二头肌长头解剖网格');
        const registration = toGlTf.clone()
          .multiply(matrixFromRows(humerusRegistration.atlasToModelBlenderRows))
          .multiply(fromGlTf).multiply(source.matrixWorld);
        const geometry = source.geometry.clone();
        geometry.applyMatrix4(registration);
        const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
          color: 0xaf818b, roughness: 0.62, side: THREE.DoubleSide,
        }));
        mesh.name = `tsm_${exercise}_BIC_long_research_mesh`;
        this.tsmUpperBoneGroup.add(mesh);
        const position = geometry.getAttribute('position') as THREE.BufferAttribute;
        const standing = new Float32Array(position.array as ArrayLike<number>);
        this.tsmUpperMuscleMeshes.set(exercise, { mesh, exercise, standing });
        for (const spec of tsmDeltoidSpecs) {
          const deltoid = atlas.get(spec.atlas);
          if (!deltoid) throw new Error(`缺少三角肌候选网格：${spec.atlas}`);
          const deltoidGeometry = deltoid.geometry.clone();
          deltoidGeometry.applyMatrix4(toGlTf.clone()
            .multiply(matrixFromRows(humerusRegistration.atlasToModelBlenderRows))
            .multiply(fromGlTf).multiply(deltoid.matrixWorld));
          const deltoidMesh = new THREE.Mesh(deltoidGeometry, new THREE.MeshStandardMaterial({
            color: 0xaf818b, roughness: 0.67, side: THREE.DoubleSide,
          }));
          deltoidMesh.name = `tsm_${exercise}_${spec.muscle}_atlas_candidate`;
          this.tsmUpperBoneGroup.add(deltoidMesh);
          this.tsmDeltoidAtlasMeshes.set(`${exercise}:${spec.muscle}`,
            { mesh: deltoidMesh, exercise, muscle: spec.muscle });
        }
      }
      for (const exercise of ['bench', 'press'] as const) {
        const registration = exercise === 'bench' ? tsmBenchPectoralisAtlasRegistration
          : tsmPectoralisAtlasRegistration;
        const atlasFit = toGlTf.clone()
          .multiply(matrixFromRows(registration.atlasToModelBlenderRows)).multiply(fromGlTf);
        for (const row of registration.muscles) {
          const source = atlas.get(row.atlasMesh.replace('.r', 'r'));
          if (!source) throw new Error(`缺少胸肌研究网格：${row.atlasMesh}`);
          const geometry = source.geometry.clone();
          geometry.applyMatrix4(atlasFit.clone().multiply(source.matrixWorld));
          const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
            color: 0xaf818b, roughness: 0.66, side: THREE.DoubleSide,
          }));
          mesh.name = `tsm_${exercise}_${row.modelMuscle}_atlas_research_mesh`;
          this.tsmUpperBoneGroup.add(mesh);
          const shape = prepareReferenceMuscleShape(mesh, 'chest');
          if (shape.rest.length / 3 !== row.vertexCount) {
            throw new Error(`胸肌研究网格顶点数不符：${row.atlasMesh}`);
          }
          this.tsmPectoralisAtlasMeshes.set(`${exercise}:${row.modelMuscle}`, {
            mesh, exercise, muscle: row.modelMuscle,
            parent: row.rigidParent as 'clavicle' | 'thorax',
            shape, fractions: new Float32Array(row.vertexCount), fractionsReady: false,
            endpointCorrectionWeight: registration.endpointCorrectionWeight,
          });
        }
      }
      if (this.tsmUpperBoneMeshes.size !== 6) throw new Error('上肢三骨配准数据不完整');
      if (this.tsmUpperMuscleMeshes.size !== 2) throw new Error('肱二头肌长头研究网格不完整');
      if (this.tsmDeltoidAtlasMeshes.size !== 6) throw new Error('三角肌三束候选网格不完整');
      if (this.tsmPectoralisAtlasMeshes.size !== 6) {
        throw new Error('卧推或实力举胸大肌三束研究网格不完整');
      }
      this.tsmUpperBonesLoaded = true;
      this.tsmUpperBoneGroup.visible = this.tsmUpperBonesEnabled;
      onAssetChange?.();
    }).catch(error => {
      this.tsmUpperBonesError = true;
      this.tsmUpperBoneGroup.visible = false;
      console.error('上肢解剖骨骼加载失败', error);
      onAssetChange?.();
    });
  }

  private updateTsmUpperBones(frame: OpenSimFrame, starting: OpenSimFrame,
    exercise: ExerciseId, showBones: boolean, showMuscles: boolean,
    profile: BodyProfile): void {
    this.tsmUpperBoneGroup.visible = this.tsmUpperBonesEnabled && this.tsmUpperBonesLoaded &&
      (showBones || showMuscles) && exercise !== 'squat';
    if (!this.tsmUpperBoneGroup.visible || !frame.blenderBodyFrames || !starting.blenderBodyFrames) return;
    const toGlTf = new THREE.Matrix4().set(
      1, 0, 0, 0,  0, 0, 1, 0,  0, -1, 0, 0,  0, 0, 0, 1,
    );
    const fromGlTf = toGlTf.clone().invert();
    const bodyMatrix = (data: { translationM: [number, number, number]; rotationRows: number[][] }) => {
      const r = data.rotationRows;
      const p = data.translationM;
      return new THREE.Matrix4().set(
        r[0][0], r[0][1], r[0][2], p[0],
        r[1][0], r[1][1], r[1][2], p[1],
        r[2][0], r[2][1], r[2][2], p[2],
        0, 0, 0, 1,
      );
    };
    for (const item of this.tsmUpperBoneMeshes.values()) {
      item.mesh.visible = showBones && item.exercise === exercise;
      if (!item.mesh.visible) continue;
      const current = frame.blenderBodyFrames[item.body];
      const original = starting.blenderBodyFrames[item.body];
      if (!current || !original) throw new Error(`缺少 ${item.body} 刚体坐标`);
      const relative = bodyMatrix(current).multiply(bodyMatrix(original).invert());
      item.mesh.matrix.copy(toGlTf).multiply(relative).multiply(fromGlTf)
        .multiply(item.standingWorld);
      item.mesh.matrixWorldNeedsUpdate = true;
    }
    const pathPoint = (points: THREE.Vector3[], distances: number[], total: number,
      fraction: number, result: THREE.Vector3) => {
      let remaining = fraction * total;
      for (let index = 0; index < distances.length; index++) {
        if (remaining <= distances[index] && distances[index] > 0) {
          return result.copy(points[index]).lerp(points[index + 1], remaining / distances[index]);
        }
        remaining -= distances[index];
      }
      return result.copy(points[points.length - 1]);
    };
    for (const item of this.tsmUpperMuscleMeshes.values()) {
      item.mesh.visible = showMuscles && item.exercise === exercise;
      if (!item.mesh.visible) continue;
      const rest = starting.muscles.BIC_long.viewerPathM.map(point => new THREE.Vector3(...point));
      const current = frame.muscles.BIC_long.viewerPathM.map(point => new THREE.Vector3(...point));
      const measurePath = (points: THREE.Vector3[]) => {
        const lengths = points.slice(1).map((point, index) => point.distanceTo(points[index]));
        return { lengths, total: lengths.reduce((sum, length) => sum + length, 0) };
      };
      const restMeasure = measurePath(rest);
      const currentMeasure = measurePath(current);
      const position = item.mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
      if (!item.fractions || !item.restingPath) {
        item.fractions = new Float32Array(position.count);
        item.restingPath = new Float32Array(position.count * 3);
        const axis = rest[rest.length - 1].clone().sub(rest[0]);
        const axisSquared = axis.lengthSq();
        if (axisSquared < 0.01) throw new Error('肱二头肌长头模型路径过短');
        const point = new THREE.Vector3();
        const onPath = new THREE.Vector3();
        for (let index = 0; index < position.count; index++) {
          point.fromArray(item.standing, index * 3);
          const fraction = THREE.MathUtils.clamp(point.sub(rest[0]).dot(axis) / axisSquared, 0, 1);
          item.fractions[index] = fraction;
          pathPoint(rest, restMeasure.lengths, restMeasure.total, fraction, onPath)
            .toArray(item.restingPath, index * 3);
        }
      }
      const currentBody = frame.blenderBodyFrames.humerus;
      const originalBody = starting.blenderBodyFrames.humerus;
      const rigid = toGlTf.clone().multiply(bodyMatrix(currentBody)
        .multiply(bodyMatrix(originalBody).invert())).multiply(fromGlTf);
      const shoulder = new THREE.Vector3(...starting.viewerJointsM.shoulder);
      const upperArmAxis = new THREE.Vector3(...starting.viewerJointsM.elbow)
        .sub(shoulder).normalize();
      const thicknessScale = registeredArmThicknessScale(profile);
      const point = new THREE.Vector3();
      const axisPoint = new THREE.Vector3();
      const originalPathPoint = new THREE.Vector3();
      const currentPathPoint = new THREE.Vector3();
      for (let index = 0; index < position.count; index++) {
        const fraction = item.fractions[index];
        point.fromArray(item.standing, index * 3);
        scaleRegisteredLimbPoint(point, shoulder, upperArmAxis, thicknessScale, axisPoint);
        point.applyMatrix4(rigid);
        originalPathPoint.fromArray(item.restingPath, index * 3).applyMatrix4(rigid);
        pathPoint(current, currentMeasure.lengths, currentMeasure.total, fraction, currentPathPoint);
        const weight = 0.25 * Math.abs(2 * fraction - 1) ** 2;
        point.addScaledVector(currentPathPoint.sub(originalPathPoint), weight);
        position.setXYZ(index, point.x, point.y, point.z);
      }
      position.needsUpdate = true;
      item.mesh.geometry.computeVertexNormals();
      item.mesh.geometry.computeBoundingSphere();
      const material = item.mesh.material as THREE.MeshStandardMaterial;
      material.color.set(pathLengthColor(frame.muscles.BIC_long.ratioToStartingPose ?? 1));
    }
    for (const candidate of this.tsmDeltoidAtlasMeshes.values()) {
      candidate.mesh.visible = showMuscles && candidate.exercise === exercise;
      if (!candidate.mesh.visible) continue;
      const muscle = frame.muscles[candidate.muscle];
      const initial = starting.muscles[candidate.muscle];
      if (!muscle || !initial) throw new Error(`缺少三角肌路径：${candidate.muscle}`);
      candidate.prepared ??= prepareDeltoidAtlas(candidate.mesh, candidate.exercise,
        candidate.muscle, initial.viewerPathM);
      const rigid = toGlTf.clone().multiply(bodyMatrix(frame.blenderBodyFrames.humerus)
        .multiply(bodyMatrix(starting.blenderBodyFrames.humerus).invert())).multiply(fromGlTf);
      updateDeltoidAtlas(candidate.prepared, rigid, muscle.viewerPathM);
      (candidate.mesh.material as THREE.MeshStandardMaterial).color
        .set(pathLengthColor(muscle.ratioToStartingPose ?? 1));
    }
    for (const item of this.tsmPectoralisAtlasMeshes.values()) {
      item.mesh.visible = showMuscles && item.exercise === exercise;
      if (!item.mesh.visible) continue;
      const restPath = starting.muscles[item.muscle]?.viewerPathM;
      const muscle = frame.muscles[item.muscle];
      const currentBody = frame.blenderBodyFrames[item.parent];
      const originalBody = starting.blenderBodyFrames[item.parent];
      if (!restPath || !muscle || !currentBody || !originalBody) {
        throw new Error(`缺少胸肌动态路径或刚体：${item.muscle}`);
      }
      if (!item.fractionsReady) {
        item.fractions = createPectoralisAtlasFractions(item.shape, restPath);
        item.fractionsReady = true;
      }
      const relative = bodyMatrix(currentBody).multiply(bodyMatrix(originalBody).invert());
      const rigid = toGlTf.clone().multiply(relative).multiply(fromGlTf);
      updatePectoralisAtlas(item, rigid, restPath, muscle.viewerPathM,
        registeredChestThicknessScale(profile));
      (item.mesh.material as THREE.MeshStandardMaterial).color
        .set(pathLengthColor(muscle.ratioToStartingPose ?? 1));
    }
  }

  setRegisteredBonesEnabled(enabled: boolean, onAssetChange?: () => void): void {
    this.registeredBonesEnabled = enabled;
    this.registeredBones.visible = enabled && this.registeredBonesLoaded;
    if (!enabled || this.registeredBonesRequested) return;
    this.registeredBonesRequested = true;
    void this.loadAnatomyReference().then(gltfScene => {
      const bodyByName: Record<string, string> = {
        'Hip boner': 'pelvis', Femurr: 'femur_r',
        Tibiar: 'tibia_r', Fibular: 'tibia_r',
        Patellar: 'patella_r', Calcaneusr: 'calcn_r',
      };
      gltfScene.updateMatrixWorld(true);
      const shift = standingRegistration.translationM;
      // The Blender standing translation expressed in GLTF's Y-up frame.
      const translation = new THREE.Matrix4().makeTranslation(shift[0], shift[2], -shift[1]);
      gltfScene.traverse(object => {
        // GLTFLoader sanitizes the source's ".r" suffix into a bare "r".
        const normalizedName = object.name.replaceAll('_', ' ').replace(/\.r$/, 'r');
        const body = bodyByName[normalizedName];
        const muscleSpec = registeredMuscleSpecs[normalizedName];
        if (object instanceof THREE.Mesh && muscleSpec) {
          const geometry = object.geometry.clone();
          geometry.applyMatrix4(translation.clone().multiply(object.matrixWorld));
          const position = geometry.getAttribute('position') as THREE.BufferAttribute;
          const restingBlender = new Float32Array(position.count * 3);
          const fractions = new Float32Array(position.count);
          let low = Infinity;
          let high = -Infinity;
          for (let i = 0; i < position.count; i++) {
            const offset = i * 3;
            restingBlender[offset] = position.getX(i);
            restingBlender[offset + 1] = -position.getZ(i);
            restingBlender[offset + 2] = position.getY(i);
            low = Math.min(low, restingBlender[offset + 2]);
            high = Math.max(high, restingBlender[offset + 2]);
          }
          if (high - low < 0.2 || position.count < 1000) throw new Error(`${muscleSpec.id} 网格尺寸异常`);
          for (let i = 0; i < position.count; i++) fractions[i] = (high - restingBlender[i * 3 + 2]) / (high - low);
          const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({
            color: muscleSpec.color, roughness: 0.68, side: THREE.DoubleSide,
          }));
          mesh.matrixAutoUpdate = false;
          this.registeredBones.add(mesh);
          this.registeredMuscles.set(muscleSpec.id, { mesh, identityColor: muscleSpec.color,
            body: muscleSpec.body, girth: muscleSpec.girth, restingBlender, fractions,
            restingPath: new Float32Array(position.count * 3), lastPhase: -1,
            lastThicknessScale: NaN });
          return;
        }
        if (!(object instanceof THREE.Mesh) || !body) return;
        const mesh = object.clone();
        mesh.material = new THREE.MeshStandardMaterial({ color: 0xefb863, roughness: 0.68, side: THREE.DoubleSide });
        mesh.matrixAutoUpdate = false;
        mesh.matrix.copy(translation).multiply(object.matrixWorld);
        this.registeredBones.add(mesh);
        this.registeredBoneMeshes.set(body + ':' + object.name,
          { mesh, standingWorld: mesh.matrix.clone() });
      });
      if (this.registeredBoneMeshes.size !== 6 || this.registeredMuscles.size !== Object.keys(registeredMuscleSpecs).length) {
        this.registeredBonesError = true;
        console.error('解剖骨骼或肌肉名称匹配失败', this.registeredBoneMeshes.size, this.registeredMuscles.size,
          JSON.stringify(gltfScene.children.map(child => child.name).filter(name => /Femur|Tibia|Fibula|Hip|Patella|Calcaneus/.test(name))));
        this.registeredBones.clear();
        this.registeredBoneMeshes.clear();
        this.registeredMuscles.clear();
      } else {
        this.registeredBonesLoaded = true;
        this.registeredBones.visible = this.registeredBonesEnabled;
      }
      onAssetChange?.();
    }).catch(error => {
      this.registeredBonesError = true;
      console.error('动态解剖骨骼加载失败', error);
      onAssetChange?.();
    });
  }

  private updateRegisteredBones(frame: OpenSimFrame, standing: OpenSimFrame,
    showBones: boolean, showMuscles: boolean, selectedMuscle: string,
    profile: BodyProfile, colorMode: RegisteredMuscleColorMode): void {
    this.registeredBones.visible = this.registeredBonesEnabled && this.registeredBonesLoaded && (showBones || showMuscles);
    if (!this.registeredBones.visible || !frame.blenderBodyFrames || !standing.blenderBodyFrames) return;
    const toGlTf = new THREE.Matrix4().set(
      1, 0, 0, 0,  0, 0, 1, 0,  0, -1, 0, 0,  0, 0, 0, 1,
    );
    const fromGlTf = toGlTf.clone().invert();
    const matrix = (body: { translationM: [number, number, number]; rotationRows: number[][] }) => {
      const r = body.rotationRows;
      const p = body.translationM;
      return new THREE.Matrix4().set(
        r[0][0], r[0][1], r[0][2], p[0],
        r[1][0], r[1][1], r[1][2], p[1],
        r[2][0], r[2][1], r[2][2], p[2],
        0, 0, 0, 1,
      );
    };
    for (const [key, item] of this.registeredBoneMeshes) {
      item.mesh.visible = showBones;
      if (!showBones) continue;
      const body = key.split(':')[0];
      const current = frame.blenderBodyFrames[body];
      const original = standing.blenderBodyFrames[body];
      if (!current || !original) continue;
      const relative = matrix(current).multiply(matrix(original).invert());
      item.mesh.matrix.copy(toGlTf).multiply(relative).multiply(fromGlTf).multiply(item.standingWorld);
      item.mesh.matrixWorldNeedsUpdate = true;
    }
    for (const [id, study] of this.registeredMuscles) {
      study.mesh.visible = showMuscles;
      const thicknessScale = study.girth === 'thigh'
        ? registeredThighThicknessScale(profile)
        : study.girth === 'calf' ? registeredCalfThicknessScale(profile) : 1;
      const material = study.mesh.material as THREE.MeshStandardMaterial;
      const currentPath = frame.muscles[id];
      const standingPath = standing.muscles[id];
      const ratio = currentPath && standingPath && standingPath.lengthM > 0
        ? currentPath.lengthM / standingPath.lengthM : 1;
      if (colorMode === 'path-length') material.color.set(pathLengthColor(ratio));
      else material.color.setHex(study.identityColor);
      material.emissive.set(id === selectedMuscle ? 0x654321 : 0x000000);
      if (showMuscles && (study.lastPhase !== frame.phase || study.lastThicknessScale !== thicknessScale)) {
        this.updateRegisteredMuscleMesh(id, study, frame, standing, matrix, thicknessScale);
        study.lastPhase = frame.phase;
        study.lastThicknessScale = thicknessScale;
      }
    }
  }

  private updateRegisteredMuscleMesh(id: string, study: RegisteredAnatomyMuscle,
    frame: OpenSimFrame, standing: OpenSimFrame,
    bodyMatrix: (body: { translationM: [number, number, number]; rotationRows: number[][] }) => THREE.Matrix4,
    thicknessScale: number): void {
    const currentBody = frame.blenderBodyFrames?.[study.body];
    const standingBody = standing.blenderBodyFrames?.[study.body];
    const currentMuscle = frame.muscles[id];
    const standingMuscle = standing.muscles[id];
    if (!currentBody || !standingBody || !currentMuscle || !standingMuscle) return;
    const toBlender = (point: [number, number, number]) =>
      new THREE.Vector3(0.09 - point[0], -point[2], point[1]);
    const origin = toBlender(standing.viewerJointsM[study.body === 'femur_r' ? 'hip' : 'knee']);
    const axis = toBlender(standing.viewerJointsM[study.body === 'femur_r' ? 'knee' : 'ankle']).sub(origin).normalize();
    const path = (points: Array<[number, number, number]>) => {
      const vectors = points.map(toBlender);
      const lengths = vectors.slice(1).map((point, index) => point.distanceTo(vectors[index]));
      return { vectors, lengths, total: lengths.reduce((sum, value) => sum + value, 0) };
    };
    const pathPoint = (data: ReturnType<typeof path>, fraction: number, result: THREE.Vector3) => {
      let remaining = fraction * data.total;
      for (let index = 0; index < data.lengths.length; index++) {
        const length = data.lengths[index];
        if (remaining <= length) return result.copy(data.vectors[index]).lerp(data.vectors[index + 1], remaining / length);
        remaining -= length;
      }
      return result.copy(data.vectors[data.vectors.length - 1]);
    };
    const currentPath = path(currentMuscle.viewerPathM);
    if (study.lastPhase < 0) {
      const rest = path(standingMuscle.viewerPathM);
      const result = new THREE.Vector3();
      for (let i = 0; i < study.fractions.length; i++) {
        pathPoint(rest, study.fractions[i], result).toArray(study.restingPath, i * 3);
      }
    }
    const delta = bodyMatrix(currentBody).multiply(bodyMatrix(standingBody).invert());
    const position = study.mesh.geometry.getAttribute('position') as THREE.BufferAttribute;
    const point = new THREE.Vector3();
    const restPathPoint = new THREE.Vector3();
    const currentPathPoint = new THREE.Vector3();
    const axisPoint = new THREE.Vector3();
    for (let i = 0; i < position.count; i++) {
      const offset = i * 3;
      point.fromArray(study.restingBlender, offset);
      if (study.girth !== 'none') scaleRegisteredLimbPoint(point, origin, axis, thicknessScale, axisPoint);
      point.applyMatrix4(delta);
      restPathPoint.fromArray(study.restingPath, offset).applyMatrix4(delta);
      pathPoint(currentPath, study.fractions[i], currentPathPoint);
      const u = Math.abs(2 * study.fractions[i] - 1);
      const weight = (id === 'glut_max2_r' ? 0.1 : 0.5) * u * u;
      point.addScaledVector(currentPathPoint.sub(restPathPoint), weight);
      position.setXYZ(i, point.x, point.z, -point.y);
    }
    position.needsUpdate = true;
    study.mesh.geometry.computeVertexNormals();
    study.mesh.geometry.computeBoundingSphere();
  }

  private updateOpenSimReference(frame: OpenSimFrame, exercise: ExerciseId, selectedMuscle: string,
    showBones: boolean, showMuscles: boolean, overlayUpperBones: boolean): void {
    const vector = (name: string) => new THREE.Vector3(...frame.viewerJointsM[name]);
    const jointNames = exercise === 'squat' ? ['foot', 'ankle', 'knee', 'hip', 'back']
      : ['thorax', 'clavicle', 'scapula', 'shoulder', 'elbow', 'hand'];
    for (let index = 0; index < this.opensimBones.length; index++) {
      const upperBoneMeshReplacesCylinder = overlayUpperBones && exercise !== 'squat' &&
        this.tsmUpperBonesEnabled && this.tsmUpperBonesLoaded && index >= 3;
      const visible = showBones && index < jointNames.length - 1 && !upperBoneMeshReplacesCylinder;
      this.opensimBones[index].visible = visible;
      if (visible) positionBetween(this.opensimBones[index], vector(jointNames[index]), vector(jointNames[index + 1]), 0.017);
    }
    for (let index = 0; index < this.opensimJoints.length; index++) {
      const visible = showBones && index < jointNames.length;
      this.opensimJoints[index].visible = visible;
      if (visible) this.opensimJoints[index].position.copy(vector(jointNames[index]));
    }
    for (const item of this.opensimPaths.values()) {
      for (const segment of item.segments) segment.visible = false;
    }
    for (const [name, data] of Object.entries(frame.muscles)) {
      let item = this.opensimPaths.get(name);
      if (!item) {
        const material = new THREE.MeshStandardMaterial({ color: 0x7890a2, roughness: 0.65, transparent: true, opacity: 0.5 });
        item = { segments: [], material };
        this.opensimPaths.set(name, item);
      }
      const selected = name === selectedMuscle;
      item.material.color.set(selected ? '#f6c86b' : '#7890a2');
      item.material.opacity = selected ? 1 : 0.42;
      while (item.segments.length < data.viewerPathM.length - 1) {
        const segment = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 2, 8), item.material);
        this.opensimReference.add(segment);
        item.segments.push(segment);
      }
      for (let index = 0; index < item.segments.length; index++) {
        const segment = item.segments[index];
        segment.visible = showMuscles && index < data.viewerPathM.length - 1;
        if (segment.visible) {
          positionBetween(segment, new THREE.Vector3(...data.viewerPathM[index]),
            new THREE.Vector3(...data.viewerPathM[index + 1]), selected ? 0.010 : 0.0045);
        }
      }
    }
  }

  private loadBlenderMeshes(onAssetChange?: () => void): void {
    new GLTFLoader().load('/models/prototype_parts.glb', gltf => {
      const geometry = (name: string): THREE.BufferGeometry => {
        const mesh = gltf.scene.getObjectByName(name);
        if (!(mesh instanceof THREE.Mesh)) throw new Error(`GLB 缺少模型部件：${name}`);
        return mesh.geometry;
      };
      try {
        const bone = geometry('bone_shaft');
        const joint = geometry('joint_sphere');
        const muscle = geometry('muscle_spindle');
        const skin = geometry('skin_segment');
        const old = new Set<THREE.BufferGeometry>();
        for (const mesh of this.bones) { old.add(mesh.geometry); mesh.geometry = bone; }
        for (const mesh of this.joints) { old.add(mesh.geometry); mesh.geometry = joint; }
        for (const item of this.muscles) {
          old.add(item.mesh.geometry);
          item.mesh.geometry = muscle;
          item.secondMesh.geometry = muscle;
        }
        for (const item of this.skinSegments) { old.add(item.mesh.geometry); item.mesh.geometry = skin; }
        for (const item of old) item.dispose();
        this.assetLoaded = true;
        this.renderer.render(this.scene, this.camera);
      } catch (error) {
        this.assetError = true;
        console.error('Blender GLB 加载失败', error);
      }
      onAssetChange?.();
    }, undefined, error => {
      this.assetError = true;
      console.error('Blender GLB 下载失败', error);
      onAssetChange?.();
    });
  }

  setReferenceMode(enabled: boolean, onAssetChange?: () => void): void {
    this.referenceMode = enabled;
    this.reference.visible = enabled && this.referenceLoaded;
    this.root.visible = !enabled;
    if (enabled && !this.referenceRequested) {
      this.referenceRequested = true;
      void this.loadAnatomyReference().then(source => {
        const referenceScene = source.clone(true);
        const bones = new Set(['Clavicle', 'Scapula', 'Humerus', 'Radius', 'Ulna', 'Femur', 'Tibia', 'Fibula',
          'Patella', 'Calcaneus', 'Hip bone', 'Sacrum', 'Body of sternum', 'Manubrium of sternum']);
        referenceScene.traverse(object => {
          if (!(object instanceof THREE.Mesh)) return;
          const fullName = object.name.replaceAll('_', ' ');
          const sideStripped = object.name.replace(/[._]?[lr]$/i, '').replaceAll('_', ' ');
          const isBone = [fullName, sideStripped].some(name =>
            bones.has(name) || name.startsWith('Vertebra ') || name.endsWith(' rib'));
          object.material = new THREE.MeshStandardMaterial({
            color: isBone ? 0xdce8e8 : 0xc88491,
            roughness: 0.72,
            side: THREE.DoubleSide,
          });
          (isBone ? this.referenceBones : this.referenceMuscles).push(object);
          const girth = isBone ? undefined : referenceGirthForName(object.name);
          if (girth) this.referenceMuscleShapes.push(prepareReferenceMuscleShape(object, girth));
        });
        if (this.referenceMuscleShapes.length !== 46) {
          throw new Error(`解剖参考围度网格不完整：${this.referenceMuscleShapes.length}/46`);
        }
        const bounds = new THREE.Box3().setFromObject(referenceScene);
        const height = bounds.max.y - bounds.min.y;
        if (!Number.isFinite(height) || height < 0.5) {
          this.referenceError = true;
          onAssetChange?.();
          return;
        }
        this.referenceSourceCenter = bounds.getCenter(new THREE.Vector3());
        this.referenceSourceHeight = height;
        this.referenceScene = referenceScene;
        this.reference.add(referenceScene);
        this.updateReferenceProfile(this.currentProfile);
        this.referenceLoaded = true;
        this.reference.visible = this.referenceMode;
        onAssetChange?.();
      }).catch(error => {
        this.referenceError = true;
        console.error('解剖参考 GLB 加载失败', error);
        onAssetChange?.();
      });
    }
  }

  private updateReferenceProfile(profile: BodyProfile): void {
    if (!this.referenceScene) return;
    const stature = profile.heightCm / 175;
    const factor = 1.55 * stature / this.referenceSourceHeight;
    this.referenceScene.scale.setScalar(factor);
    this.referenceScene.position.set(-this.referenceSourceCenter.x * factor,
      0.92 * stature - this.referenceSourceCenter.y * factor,
      -this.referenceSourceCenter.z * factor);
    const girths = {
      arm: registeredArmThicknessScale(profile),
      chest: registeredChestThicknessScale(profile),
      waist: registeredWaistThicknessScale(profile),
      thigh: registeredThighThicknessScale(profile),
      calf: registeredCalfThicknessScale(profile),
    };
    for (const shape of this.referenceMuscleShapes) {
      applyReferenceMuscleThickness(shape, girths[shape.girth]);
    }
  }

  private updateMomentMarkers(pose: Pose, frame: OpenSimFrame | undefined,
    exercise: ExerciseId, view: ViewMode, moments: JointMomentOverlay): void {
    const researchBench = view === 'demand' && exercise === 'bench' && !!frame;
    const rootPoints: Record<string, JointName> = {
      髋: 'hipR', 膝: 'kneeR', 踝: 'ankleR', 肩: 'shoulderR', 肘: 'elbowR',
    };
    for (const [joint, marker] of this.rootMomentMarkers) {
      const item = moments.find(value => value.joint === joint && value.source === 'barbell');
      const value = item?.source === 'barbell' ? item.magnitudeNm : 0;
      marker.visible = !this.referenceMode && view === 'demand' && !researchBench && value > 0.1;
      if (!marker.visible) continue;
      marker.position.copy(pose[rootPoints[joint]]);
      marker.scale.setScalar(momentBadgeDiameter(value));
    }
    for (const [joint, marker] of this.studyMomentMarkers) {
      const item = moments.find(value => value.joint === joint && value.source === 'study');
      const value = item?.source === 'study' ? item.magnitudeNmPerKg : 0;
      marker.visible = !this.referenceMode && view === 'demand' && exercise === 'squat' && value > 0.001;
      if (!marker.visible) continue;
      marker.position.copy(pose[rootPoints[joint]]);
      marker.scale.setScalar(studyMomentBadgeDiameter(value));
    }
    for (const [joint, marker] of this.opensimMomentMarkers) {
      const item = moments.find(value => value.joint === joint && value.source === 'barbell');
      const value = item?.source === 'barbell' ? item.magnitudeNm : 0;
      const position = frame?.viewerJointsM[joint === '肩' ? 'shoulder' : 'elbow'];
      marker.visible = !this.referenceMode && researchBench && !!position && value > 0.1;
      if (!marker.visible || !position) continue;
      marker.position.set(...position);
      marker.scale.setScalar(momentBadgeDiameter(value));
    }
  }

  private addMuscle(label: string, category: Muscle['category'], points: Muscle['points']): void {
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(1, 16, 10),
      new THREE.MeshStandardMaterial({ color: 0x9e8290, roughness: 0.66, emissive: 0x0f1118 }),
    );
    this.anatomy.add(mesh);
    const secondMesh = new THREE.Mesh(mesh.geometry, mesh.material);
    secondMesh.visible = false;
    this.anatomy.add(secondMesh);
    this.muscles.push({ label, category, points, mesh, secondMesh, baseline: 1 });
    this.muscleNames.push(label);
  }

  private makeMuscles(): void {
    buildIllustrativeMuscles((label, category, points) => this.addMuscle(label, category, points));
  }

  update(profile: BodyProfile, exercise: ExerciseId, phase: number, view: ViewMode, showBones: boolean, showMuscles: boolean, loadKg = 20, opensimFrame?: OpenSimFrame, selectedOpenSimMuscle = 'vas_int_r', opensimStandingFrame?: OpenSimFrame, squatBarOffsetCm = 0, selectedIllustrativeMuscle = '', squatDepthDeg?: number, registeredColorMode: RegisteredMuscleColorMode = 'identity', momentOverlay: JointMomentOverlay = []): Array<{ label: string; ratio: number; lengthM: number; baselineM: number }> {
    this.currentProfile = profile;
    if (this.referenceMode && this.referenceLoaded) this.updateReferenceProfile(profile);
    const pose = createPose(profile, exercise, phase, squatBarOffsetCm, squatDepthDeg);
    const reference = createPose(profile, exercise, 0, squatBarOffsetCm, squatDepthDeg);
    for (let i = 0; i < boneConnections.length; i++) {
      const [a, b] = boneConnections[i];
      positionBetween(this.bones[i], pose[a], pose[b], 0.022 * profile.heightCm / 175);
      this.bones[i].visible = showBones;
    }
    const jointNames = Object.keys(pose) as JointName[];
    for (let i = 0; i < this.joints.length; i++) {
      this.joints[i].position.copy(pose[jointNames[i]]);
      this.joints[i].visible = showBones;
    }
    const outer = profileOuterDimensions(profile);
    const statureScale = profile.heightCm / 175;
    const values: Array<{ label: string; ratio: number; lengthM: number; baselineM: number }> = [];
    for (const muscle of this.muscles) {
      const points = muscle.points(pose);
      const referencePoints = muscle.points(reference);
      const pathLength = (path: THREE.Vector3[]) => path.slice(1).reduce((sum, point, index) => sum + point.distanceTo(path[index]), 0);
      muscle.baseline = pathLength(referencePoints);
      const lengthM = pathLength(points);
      const ratio = lengthM / muscle.baseline;
      const radius = illustrativeMuscleRadius(profile, muscle.category)
        * illustrativeBellyRadiusScale(ratio)
        * (view === 'length' && muscle.label === selectedIllustrativeMuscle ? 1.35 : 1);
      positionBetween(muscle.mesh, points[0], points[1], radius);
      muscle.mesh.visible = showMuscles;
      if (points.length === 3) {
        positionBetween(muscle.secondMesh, points[1], points[2], radius * 0.52);
        muscle.secondMesh.visible = showMuscles;
      } else {
        muscle.secondMesh.visible = false;
      }
      const material = muscle.mesh.material as THREE.MeshStandardMaterial;
      if (view !== 'length') material.color.set('#888a91');
      else material.color.set(pathLengthColor(ratio));
      values.push({ label: muscle.label, ratio, lengthM, baselineM: muscle.baseline });
    }
    shapeTorso(this.skin, pose.pelvis, pose.chest,
      outer.waistHalfWidthM, outer.waistHalfDepthM,
      outer.chestHalfWidthM, outer.chestHalfDepthM, statureScale);
    this.skin.visible = showMuscles;
    const outlineRadius = {
      upperArm: outer.upperArmRadiusM, thigh: outer.thighRadiusM, calf: outer.calfRadiusM,
    };
    for (const segment of this.skinSegments) {
      positionBetween(segment.mesh, pose[segment.start], pose[segment.end], outlineRadius[segment.type]);
      segment.mesh.visible = showMuscles;
    }
    if (exercise === 'bench') {
      this.root.rotation.x = -Math.PI / 2;
      this.root.position.set(0, 0.71, 0);
      this.anatomy.position.set(0, -1.04 * profile.heightCm / 175, 0);
      this.bench.visible = true;
      this.bench.position.set(0, 0.57, -0.31);
      this.target.set(0, 0.78, -0.15);
      this.bar.position.copy(pose.wristL).add(pose.wristR).multiplyScalar(0.5);
    } else {
      this.root.rotation.x = 0;
      this.root.position.set(0, 0, 0);
      this.anatomy.position.set(0, 0, 0);
      this.bench.visible = false;
      this.target.set(0, 0.92 * profile.heightCm / 175, 0);
      this.bar.position.copy(exercise === 'press'
        ? pose.wristL.clone().add(pose.wristR).multiplyScalar(0.5)
        : pose.shoulderL.clone().add(pose.shoulderR).multiplyScalar(0.5).add(new THREE.Vector3(0, 0.09, 0)));
      if (exercise === 'squat') this.bar.position.z = squatBarSagittalZ(this.bar.position.z, squatBarOffsetCm);
    }
    this.bar.visible = loadKg > 0 && !this.referenceMode && !opensimFrame;
    const eachSide = Math.max(0, (loadKg - 20) / 2);
    for (const plate of this.barPlates) {
      plate.visible = eachSide > 0 && this.bar.visible;
      plate.position.copy(this.bar.position).add(new THREE.Vector3(plate.userData.side * 0.52, 0, 0));
      const radius = 0.7 + 0.3 * Math.min(eachSide / 20, 1);
      plate.scale.set(radius, Math.min(0.018 + eachSide * 0.0012, 0.11), radius);
    }
    if (this.referenceMode) {
      this.root.visible = false;
      this.opensimReference.visible = false;
      this.bench.visible = false;
      this.reference.visible = this.referenceLoaded;
      for (const bone of this.referenceBones) bone.visible = showBones;
      for (const muscle of this.referenceMuscles) muscle.visible = showMuscles;
      this.target.set(0, 0.92 * statureScale, 0);
    } else if ((view === 'opensim' || (view === 'demand' && exercise === 'bench')) && opensimFrame) {
      this.root.visible = false;
      this.opensimReference.visible = true;
      const factor = profile.heightCm / 175;
      const anchor = exercise === 'squat' ? new THREE.Vector3(0.18, 0.10, 0)
        : exercise === 'bench' ? new THREE.Vector3(0.27, 0.75, 0) : new THREE.Vector3(0.30, 1.45, 0);
      const center = exercise === 'squat' ? new THREE.Vector3(0.12, 0.57, 0)
        : exercise === 'bench' ? new THREE.Vector3(0.35, 0.96, 0.02) : new THREE.Vector3(0.30, 1.56, 0.20);
      this.opensimCameraFactor = exercise === 'squat' ? 0.45 : 0.42;
      this.opensimCameraOffset = exercise === 'squat' ? 1.20 : 0.50;
      this.opensimReference.scale.setScalar(factor);
      this.opensimReference.position.copy(anchor).addScaledVector(anchor, -factor);
      this.updateOpenSimReference(opensimFrame, exercise, selectedOpenSimMuscle,
        showBones, showMuscles && view === 'opensim', view === 'opensim');
      this.updateRegisteredBones(opensimFrame, opensimStandingFrame ?? opensimFrame,
        showBones && exercise === 'squat', showMuscles && exercise === 'squat',
        selectedOpenSimMuscle, profile, registeredColorMode);
      this.updateTsmUpperBones(opensimFrame, opensimStandingFrame ?? opensimFrame,
        exercise, showBones && view === 'opensim', showMuscles && view === 'opensim', profile);
      this.target.copy(anchor).addScaledVector(center.sub(anchor), factor);
    } else {
      this.root.visible = true;
      this.opensimReference.visible = false;
    }
    this.updateMomentMarkers(pose, opensimFrame, exercise, view, momentOverlay);
    this.updateCamera();
    this.renderer.render(this.scene, this.camera);
    return values;
  }

  private updateCamera(): void {
    const ce = Math.cos(this.elevation);
    const distance = this.distance * (this.opensimReference.visible ? this.opensimCameraFactor : 1);
    const azimuth = this.azimuth + (this.opensimReference.visible ? this.opensimCameraOffset : 0);
    this.camera.position.set(
      this.target.x + Math.sin(azimuth) * ce * distance,
      this.target.y + Math.sin(this.elevation) * distance,
      this.target.z + Math.cos(azimuth) * ce * distance,
    );
    this.camera.lookAt(this.target);
  }

  private resize(): void {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    if (width <= 0 || height <= 0) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
    this.renderer.render(this.scene, this.camera);
  }

  private installControls(): void {
    const canvas = this.renderer.domElement;
    canvas.style.touchAction = 'none';
    let lastX = 0;
    let lastY = 0;
    let pointerStartX = 0;
    let pointerStartY = 0;
    let moved = false;
    let active = false;
    canvas.addEventListener('pointerdown', event => {
      active = true;
      lastX = event.clientX;
      lastY = event.clientY;
      pointerStartX = event.clientX;
      pointerStartY = event.clientY;
      moved = false;
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', event => {
      if (!active) return;
      if (Math.hypot(event.clientX - pointerStartX, event.clientY - pointerStartY) > 5) moved = true;
      this.azimuth += (event.clientX - lastX) * 0.008;
      this.elevation = clamp(this.elevation + (event.clientY - lastY) * 0.006, -1.1, 1.1);
      lastX = event.clientX;
      lastY = event.clientY;
      this.updateCamera();
      this.renderer.render(this.scene, this.camera);
    });
    canvas.addEventListener('pointerup', event => {
      if (active && !moved && this.referenceMode && this.referenceLoaded) {
        const rect = canvas.getBoundingClientRect();
        const pointer = new THREE.Vector2(
          (event.clientX - rect.left) / rect.width * 2 - 1,
          -(event.clientY - rect.top) / rect.height * 2 + 1,
        );
        const raycaster = new THREE.Raycaster();
        this.reference.updateMatrixWorld(true);
        raycaster.setFromCamera(pointer, this.camera);
        const candidates = [...this.referenceBones, ...this.referenceMuscles].filter(mesh => mesh.visible);
        const hit = raycaster.intersectObjects(candidates, false)[0];
        if (this.selectedReferenceMesh) {
          (this.selectedReferenceMesh.material as THREE.MeshStandardMaterial).emissive.set('#000000');
        }
        this.selectedReferenceMesh = hit?.object as THREE.Mesh | undefined;
        this.selectedReferenceName = this.selectedReferenceMesh?.name ?? '';
        this.selectedReferenceIsBone = this.selectedReferenceMesh
          ? this.referenceBones.includes(this.selectedReferenceMesh) : false;
        if (this.selectedReferenceMesh) {
          (this.selectedReferenceMesh.material as THREE.MeshStandardMaterial).emissive.set('#9a561e');
        }
        this.onAssetChange?.();
      }
      active = false;
    });
    canvas.addEventListener('pointercancel', () => { active = false; });
    canvas.addEventListener('wheel', event => {
      event.preventDefault();
      this.distance = clamp(this.distance + event.deltaY * 0.003, 1.7, 6);
      this.updateCamera();
      this.renderer.render(this.scene, this.camera);
    }, { passive: false });
  }
}
