import benchVelocityBenchmark from './data/bench_velocity_benchmark.json';

export type BenchTempoMode = 'teaching' | 'study50' | 'study75';
export type BenchPlaybackTiming = {
  descentS: number;
  ascentS: number;
  totalS: number;
  meanAscentMPerS: number;
  source: 'illustrative' | 'group_median';
};

// The study reports mean concentric velocity only. Reference playback therefore
// uses its rep-level median for ascent and explicitly ASSUMES a 1 s descent.
// This is a group kinematics illustration, not a personal load/force prediction.
export function benchPlaybackTiming(mode: BenchTempoMode, heightCm: number,
  teachingCycleS: number): BenchPlaybackTiming {
  const strokeM = benchVelocityBenchmark.demo.referenceHandVerticalStrokeM
    * heightCm / benchVelocityBenchmark.demo.referenceStatureCm;
  const studySpeed = mode === 'study50'
    ? benchVelocityBenchmark.measured.fiftyPercentOneRmLpt.medianMPerS
    : mode === 'study75'
      ? benchVelocityBenchmark.measured.seventyFivePercentOneRmLpt.medianMPerS : undefined;
  const descentS = studySpeed === undefined ? teachingCycleS / 2 : 1;
  const ascentS = studySpeed === undefined ? teachingCycleS / 2 : strokeM / studySpeed;
  return { descentS, ascentS, totalS: descentS + ascentS,
    meanAscentMPerS: strokeM / ascentS,
    source: studySpeed === undefined ? 'illustrative' : 'group_median' };
}

// Phase 0→0.5 lowers the bar; 0.5→1 raises it. Convert through time so a
// dropped animation frame also crosses the halfway boundary correctly.
export function advanceBenchPhase(phase: number, elapsedS: number,
  timing: BenchPlaybackTiming): number {
  const currentTime = phase <= 0.5
    ? phase * 2 * timing.descentS
    : timing.descentS + (phase - 0.5) * 2 * timing.ascentS;
  const nextTime = ((currentTime + elapsedS) % timing.totalS + timing.totalS) % timing.totalS;
  return nextTime <= timing.descentS
    ? nextTime / (2 * timing.descentS)
    : 0.5 + (nextTime - timing.descentS) / (2 * timing.ascentS);
}
