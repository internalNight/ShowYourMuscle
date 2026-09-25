import squatEvidence from './data/squat_evidence.json';

export type SquatStudyJointMoment = {
  joint: '髋' | '膝';
  momentNmPerKg: number;
};

// The published curves contain the 99 interior phase points (1%...99%).
// Hold the nearest measured point at the two artificial animation endpoints.
export function squatStudyJointMoments(phase: number): SquatStudyJointMoment[] {
  if (!Number.isFinite(phase)) throw new Error('动作相位必须是有限数');
  const sample = (values: number[]): number => {
    const position = Math.max(0, Math.min(values.length - 1, phase * 100 - 1));
    const start = Math.floor(position);
    const end = Math.min(values.length - 1, start + 1);
    return values[start] + (values[end] - values[start]) * (position - start);
  };
  return [
    { joint: '髋', momentNmPerKg: sample(squatEvidence.phaseJointMomentStudyCurves.rightHip.median) },
    { joint: '膝', momentNmPerKg: sample(squatEvidence.phaseJointMomentStudyCurves.rightKnee.median) },
  ];
}
