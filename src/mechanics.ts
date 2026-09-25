import type { BodyProfile, ExerciseId } from './domain';
import { createPose, squatBarSagittalZ, type OpenSimFrame } from './model';
import squatMassTemplate from './data/squat_mass_template.json';

export type ExternalMoment = { joint: string; leverArmCm: number; momentNm: number };
export type SquatBalanceEstimate = {
  bodyComRelativeAnkleCm: number;
  combinedComRelativeAnkleCm: number;
  barRelativeAnkleCm: number;
  bodyComHeightM: number;
  combinedComHeightM: number;
  totalGravityN: number;
};
export type SquatVerticalSupportScenario = {
  status: 'illustrative';
  durationS: number;
  accelerationMs2: number;
  staticWeightN: number;
  verticalSupportN: number;
  ratioToStaticWeight: number;
};
export type BenchLateralScenario = {
  handEffortLateralRatio: number;
  shoulderMomentNm: number;
  elbowMomentNm: number;
};

// The force exerted BY the right hand on the bar has lateral component
// +ratio * vertical support. The equal and opposite force ON the hand is
// (-ratio * F, -F, 0) in the supine viewer frame. These are assumed scenarios,
// not measurements of this user or solved net joint/muscle moments.
export function benchBarbellMomentScenarios(frame: OpenSimFrame, heightCm: number,
  loadKg: number, ratios = [-0.1, 0, 0.4]): BenchLateralScenario[] {
  const hand = frame.viewerJointsM.hand;
  const scale = heightCm / 175;
  const verticalForceN = Math.max(0, loadKg) * 9.80665 / 2;
  const momentMagnitude = (joint: [number, number, number], lateralRatio: number): number => {
    const [rx, ry, rz] = hand.map((value, axis) => (value - joint[axis]) * scale);
    const fx = -lateralRatio * verticalForceN;
    const fy = -verticalForceN;
    return Math.hypot(-rz * fy, rz * fx, rx * fy - ry * fx);
  };
  return ratios.map(handEffortLateralRatio => ({
    handEffortLateralRatio,
    shoulderMomentNm: momentMagnitude(frame.viewerJointsM.shoulder, handEffortLateralRatio),
    elbowMomentNm: momentMagnitude(frame.viewerJointsM.elbow, handEffortLateralRatio),
  }));
}

// Quasi-static barbell-gravity contribution about one side's joints. This is
// an external load component, not a net joint moment or an individual muscle force.
export function barbellGravityMoments(profile: BodyProfile, exercise: ExerciseId,
  phase: number, loadKg: number, squatBarOffsetCm = 0, squatDepthDeg?: number): ExternalMoment[] {
  const pose = createPose(profile, exercise, phase, squatBarOffsetCm, squatDepthDeg);
  const forcePerSideN = Math.max(0, loadKg) * 9.80665 / 2;
  const item = (joint: string, leverArmM: number): ExternalMoment => ({
    joint, leverArmCm: leverArmM * 100, momentNm: forcePerSideN * leverArmM,
  });
  if (exercise === 'squat') {
    const barZ = squatBarSagittalZ(pose.shoulderR.z, squatBarOffsetCm);
    return [
      item('髋', Math.abs(barZ - pose.hipR.z)),
      item('膝', Math.abs(barZ - pose.kneeR.z)),
      item('踝', Math.abs(barZ - pose.ankleR.z)),
    ];
  }
  const wrist = pose.wristR;
  // In the bench scene, a -90° x rotation makes local z vertical. For the
  // standing press, local y stays vertical.
  const horizontalDistance = (joint: typeof wrist): number => exercise === 'bench'
    ? Math.hypot(wrist.x - joint.x, wrist.y - joint.y)
    : Math.hypot(wrist.x - joint.x, wrist.z - joint.z);
  return [
    item('肩', horizontalDistance(pose.shoulderR)),
    item('肘', horizontalDistance(pose.elbowR)),
  ];
}

// A deliberately coarse full-body gravity-center probe. Segment fractions
// come from the preserved gait2354 template, not from 12 separately measured
// people. Segment centers are projected onto the illustrative pose using the
// source model's approximate standing center locations. With no measured CoP,
// acceleration or contact model this cannot produce net joint or muscle force.
export function squatBalanceAtPose(profile: BodyProfile, pose: ReturnType<typeof createPose>,
  loadKg: number, squatBarOffsetCm = 0): SquatBalanceEstimate {
  const stature = profile.heightCm / 175;
  const fraction = squatMassTemplate.fractions;
  const torsoZ = pose.pelvis.z + 0.70 * (pose.chest.z - pose.pelvis.z) - 0.03 * stature;
  const pelvisZ = pose.pelvis.z - 0.08 * stature;
  const thighZ = pose.hipR.z + 0.47 * (pose.kneeR.z - pose.hipR.z);
  const shankZ = pose.kneeR.z + 0.53 * (pose.ankleR.z - pose.kneeR.z);
  const footZ = pose.ankleR.z + 0.12 * stature;
  const bodyComZ = fraction.torso * torsoZ + fraction.pelvis * pelvisZ
    + 2 * (fraction.thighEach * thighZ + fraction.shankEach * shankZ
      + fraction.footEach * footZ);
  const torsoY = pose.pelvis.y + 0.70 * (pose.chest.y - pose.pelvis.y) - 0.03 * stature;
  const pelvisY = pose.pelvis.y - 0.08 * stature;
  const thighY = pose.hipR.y + 0.47 * (pose.kneeR.y - pose.hipR.y);
  const shankY = pose.kneeR.y + 0.53 * (pose.ankleR.y - pose.kneeR.y);
  const footY = pose.ankleR.y - 0.05 * stature;
  const bodyComY = fraction.torso * torsoY + fraction.pelvis * pelvisY
    + 2 * (fraction.thighEach * thighY + fraction.shankEach * shankY
      + fraction.footEach * footY);
  const barZ = squatBarSagittalZ(pose.shoulderR.z, squatBarOffsetCm);
  const barY = pose.shoulderR.y + 0.09;
  const bodyKg = profile.weightKg;
  const barKg = Math.max(0, loadKg);
  const combinedZ = (bodyKg * bodyComZ + barKg * barZ) / (bodyKg + barKg);
  const combinedY = (bodyKg * bodyComY + barKg * barY) / (bodyKg + barKg);
  const ankleZ = pose.ankleR.z;
  return {
    bodyComRelativeAnkleCm: (bodyComZ - ankleZ) * 100,
    combinedComRelativeAnkleCm: (combinedZ - ankleZ) * 100,
    barRelativeAnkleCm: (barZ - ankleZ) * 100,
    bodyComHeightM: bodyComY,
    combinedComHeightM: combinedY,
    totalGravityN: (bodyKg + barKg) * 9.80665,
  };
}

export function squatBalanceEstimate(profile: BodyProfile, phase: number,
  loadKg: number, squatBarOffsetCm = 0, squatDepthDeg?: number): SquatBalanceEstimate {
  return squatBalanceAtPose(profile, createPose(profile, 'squat', phase, squatBarOffsetCm, squatDepthDeg), loadKg, squatBarOffsetCm);
}

// Research-only total vertical support required by the prescribed animation.
// The same 0.01-phase central derivative is used in the force-plate benchmark.
// Without measured motion, contact, and bar placement this is not a person's
// ground reaction force, net joint moment, or any muscle's force.
export function squatVerticalSupportScenario(profile: BodyProfile, phase: number,
  loadKg: number, durationS: number, squatBarOffsetCm = 0,
  squatDepthDeg?: number): SquatVerticalSupportScenario {
  if (!Number.isFinite(durationS) || durationS <= 0) throw new Error('动作时长必须为正数');
  const phaseStep = 0.01;
  const before = squatBalanceEstimate(profile, phase - phaseStep, loadKg, squatBarOffsetCm, squatDepthDeg);
  const current = squatBalanceEstimate(profile, phase, loadKg, squatBarOffsetCm, squatDepthDeg);
  const after = squatBalanceEstimate(profile, phase + phaseStep, loadKg, squatBarOffsetCm, squatDepthDeg);
  const accelerationMs2 = (after.combinedComHeightM - 2 * current.combinedComHeightM
    + before.combinedComHeightM) / (durationS * phaseStep) ** 2;
  const massKg = profile.weightKg + Math.max(0, loadKg);
  const verticalSupportN = current.totalGravityN + massKg * accelerationMs2;
  return { status: 'illustrative', durationS, accelerationMs2,
    staticWeightN: current.totalGravityN, verticalSupportN,
    ratioToStaticWeight: verticalSupportN / current.totalGravityN };
}
