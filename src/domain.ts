export type ExerciseId = 'squat' | 'bench' | 'press';
export type ViewMode = 'length' | 'opensim' | 'demand';

export type BodyProfile = {
  heightCm: number;
  weightKg: number;
  bodyFatPct?: number;
  chestCm?: number;
  upperArmCm?: number;
  waistCm?: number;
  thighCm?: number;
  calfCm?: number;
  armSpanCm?: number;
  inseamCm?: number;
};

export type TrainingEntry = {
  exercise: ExerciseId;
  loadKg: number;
  repetitions: number;
  repsInReserve?: number;
  date: string;
};

// A set-level capacity proxy, never an estimate of an individual muscle's mass or force.
// Deliberately limited to near-failure sets of at most ten effective repetitions.
// The form's RIR=3 option means "three or more", so it cannot yield a point estimate.
export function estimatedOneRepMax(entry: TrainingEntry): number | undefined {
  if (!Number.isFinite(entry.loadKg) || entry.loadKg <= 0 ||
      !Number.isInteger(entry.repetitions) || entry.repetitions < 1 ||
      entry.repsInReserve === undefined || !Number.isInteger(entry.repsInReserve) ||
      entry.repsInReserve < 0 || entry.repsInReserve >= 3) return undefined;
  const effectiveReps = entry.repetitions + entry.repsInReserve;
  if (effectiveReps > 10) return undefined;
  if (effectiveReps === 1) return entry.loadKg;
  return entry.loadKg * (1 + effectiveReps / 30);
}

export const defaultProfile: BodyProfile = {
  heightCm: 175,
  weightKg: 72,
  upperArmCm: 32,
  waistCm: 82,
  thighCm: 54,
  calfCm: 36,
};

export const exercises: Record<ExerciseId, { label: string; cue: string }> = {
  squat: { label: '深蹲', cue: '下蹲 → 起身' },
  bench: { label: '卧推', cue: '下放 → 推起' },
  press: { label: '实力举', cue: '上推 → 回落' },
};

export const bodyFields: Array<{
  key: keyof BodyProfile;
  label: string;
  min: number;
  max: number;
  step?: number;
  required?: boolean;
}> = [
  { key: 'heightCm', label: '身高 cm', min: 120, max: 220, required: true },
  { key: 'weightKg', label: '体重 kg', min: 30, max: 250, required: true, step: 0.1 },
  { key: 'bodyFatPct', label: '体脂率 %', min: 3, max: 65, step: 0.1 },
  { key: 'chestCm', label: '胸围 cm', min: 55, max: 180, step: 0.1 },
  { key: 'upperArmCm', label: '放松臂围 cm', min: 15, max: 70, step: 0.1 },
  { key: 'waistCm', label: '腰围 cm', min: 45, max: 180, step: 0.1 },
  { key: 'thighCm', label: '大腿围 cm', min: 25, max: 110, step: 0.1 },
  { key: 'calfCm', label: '小腿围 cm', min: 15, max: 75, step: 0.1 },
  { key: 'armSpanCm', label: '臂展 cm', min: 100, max: 250, step: 0.1 },
  { key: 'inseamCm', label: '内侧腿长 cm', min: 45, max: 120, step: 0.1 },
];

export function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

export function parseProfile(form: HTMLFormElement): BodyProfile {
  const data = new FormData(form);
  const profile: Partial<BodyProfile> = {};
  for (const field of bodyFields) {
    const raw = String(data.get(field.key) ?? '').trim();
    if (!raw) {
      if (field.required) throw new Error(`${field.label}不能为空`);
      continue;
    }
    const value = Number(raw);
    if (!Number.isFinite(value) || value < field.min || value > field.max) {
      throw new Error(`${field.label}须在 ${field.min}–${field.max} 之间`);
    }
    profile[field.key] = value;
  }
  return profile as BodyProfile;
}

export function loadProfile(): BodyProfile {
  try {
    const stored = localStorage.getItem('muscle-atlas-profile-v1');
    if (!stored) return { ...defaultProfile };
    const parsed = JSON.parse(stored) as BodyProfile;
    if (!Number.isFinite(parsed.heightCm) || !Number.isFinite(parsed.weightKg)) {
      return { ...defaultProfile };
    }
    return parsed;
  } catch {
    return { ...defaultProfile };
  }
}

export function saveProfile(profile: BodyProfile): void {
  localStorage.setItem('muscle-atlas-profile-v1', JSON.stringify(profile));
}

export function loadTraining(): TrainingEntry[] {
  try {
    const stored = localStorage.getItem('muscle-atlas-training-v1');
    if (!stored) return [];
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is TrainingEntry => {
      if (!item || typeof item !== 'object') return false;
      const entry = item as Partial<TrainingEntry>;
      return (entry.exercise === 'squat' || entry.exercise === 'bench' || entry.exercise === 'press') &&
        typeof entry.loadKg === 'number' && Number.isFinite(entry.loadKg) && entry.loadKg >= 0 && entry.loadKg <= 600 &&
        Number.isInteger(entry.repetitions) && entry.repetitions! >= 1 && entry.repetitions! <= 50 &&
        (entry.repsInReserve === undefined ||
          (Number.isInteger(entry.repsInReserve) && entry.repsInReserve >= 0 && entry.repsInReserve <= 3)) &&
        typeof entry.date === 'string' && /^\d{4}\/\d{1,2}\/\d{1,2}$/.test(entry.date);
    });
  } catch {
    return [];
  }
}

export function saveTraining(entries: TrainingEntry[]): void {
  localStorage.setItem('muscle-atlas-training-v1', JSON.stringify(entries));
}

export type LocalBackup = {
  format: 'muscle-atlas-local-backup';
  version: 1;
  exportedAt: string;
  profile: BodyProfile;
  training: TrainingEntry[];
};

export function makeLocalBackup(profile: BodyProfile, training: TrainingEntry[]): LocalBackup {
  return {
    format: 'muscle-atlas-local-backup', version: 1,
    exportedAt: new Date().toISOString(), profile, training,
  };
}

export function parseLocalBackup(value: unknown): LocalBackup {
  if (!value || typeof value !== 'object') throw new Error('备份文件格式不正确');
  const data = value as Partial<LocalBackup>;
  if (data.format !== 'muscle-atlas-local-backup' || data.version !== 1 ||
      typeof data.exportedAt !== 'string' || !Number.isFinite(Date.parse(data.exportedAt))) {
    throw new Error('不是受支持的肌动图谱备份');
  }
  if (!data.profile || typeof data.profile !== 'object') throw new Error('备份缺少身体参数');
  const source = data.profile as Record<string, unknown>;
  const profile: Partial<BodyProfile> = {};
  for (const field of bodyFields) {
    const value = source[field.key];
    if (value === undefined && !field.required) continue;
    if (typeof value !== 'number' || !Number.isFinite(value) || value < field.min || value > field.max) {
      throw new Error(`备份中的${field.label}不在有效范围内`);
    }
    (profile as Record<string, number>)[field.key] = value;
  }
  if (!Array.isArray(data.training) || data.training.length > 1000) {
    throw new Error('备份中的训练记录数量无效');
  }
  const training: TrainingEntry[] = data.training.map((item, index) => {
    if (!item || typeof item !== 'object') throw new Error(`第 ${index + 1} 条训练记录格式错误`);
    const entry = item as Partial<TrainingEntry>;
    if ((entry.exercise !== 'squat' && entry.exercise !== 'bench' && entry.exercise !== 'press') ||
        typeof entry.loadKg !== 'number' || !Number.isFinite(entry.loadKg) || entry.loadKg < 0 || entry.loadKg > 600 ||
        !Number.isInteger(entry.repetitions) || entry.repetitions! < 1 || entry.repetitions! > 50 ||
        (entry.repsInReserve !== undefined && (!Number.isInteger(entry.repsInReserve) ||
          entry.repsInReserve < 0 || entry.repsInReserve > 3)) ||
        typeof entry.date !== 'string' || !/^\d{4}\/\d{1,2}\/\d{1,2}$/.test(entry.date)) {
      throw new Error(`第 ${index + 1} 条训练记录不在有效范围内`);
    }
    return {
      exercise: entry.exercise, loadKg: entry.loadKg,
      repetitions: entry.repetitions!, repsInReserve: entry.repsInReserve,
      date: entry.date,
    };
  });
  return { format: 'muscle-atlas-local-backup', version: 1,
    exportedAt: data.exportedAt, profile: profile as BodyProfile, training };
}
