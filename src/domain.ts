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

export type TrainingEquipment = 'barbell' | 'dumbbell' | 'machine' | 'smith' | 'bodyweight' | 'other';

export type TrainingEntry = {
  exercise: ExerciseId;
  loadKg: number;
  repetitions: number;
  repsInReserve?: number;
  date: string;
  /** Self-reported technique variant. Recorded for the user's own log; the app has one preset motion per exercise and does not model variants. */
  variation?: string;
  /** Self-reported range of motion, chosen from a coarse list. Not a measured joint angle or bar travel. */
  range?: string;
  /** Self-reported equipment. Only barbell entries enter the action-level 1RM comparison pool. */
  equipment?: TrainingEquipment;
  /** Local date-time of entry in ISO 8601. Absent on records saved before this field existed. */
  recordedAt?: string;
};

export const trainingVariations: Record<ExerciseId, readonly string[]> = {
  squat: ['高杠位', '低杠位', '前蹲', '箱式深蹲', '其他'],
  bench: ['平板', '上斜', '下斜', '窄握', '其他'],
  press: ['站姿实力举', '坐姿推举', '借力推举', '其他'],
};

export const trainingRanges: Record<ExerciseId, readonly string[]> = {
  squat: ['全程（大腿低于水平）', '至水平', '半蹲'],
  bench: ['触胸', '距胸数厘米', '半程'],
  press: ['锁定位全程', '部分幅度'],
};

export const trainingEquipments: ReadonlyArray<{ id: TrainingEquipment; label: string }> = [
  { id: 'barbell', label: '杠铃' },
  { id: 'dumbbell', label: '哑铃' },
  { id: 'smith', label: '史密斯机' },
  { id: 'machine', label: '固定器械' },
  { id: 'bodyweight', label: '自重／辅助' },
  { id: 'other', label: '其他' },
];

export function trainingEquipmentLabel(entry: TrainingEntry): string {
  // Records saved before the field existed all came from the barbell form.
  const id = entry.equipment ?? 'barbell';
  return trainingEquipments.find(item => item.id === id)?.label ?? '其他';
}

// The action-level 1RM comparison pool assumes a barbell load in kilograms. Dumbbell,
// machine and bodyweight loads are not interchangeable with it, so they are excluded.
export function entersBarbellCapacityPool(entry: TrainingEntry): boolean {
  return (entry.equipment ?? 'barbell') === 'barbell';
}

export function isTrainingVariation(exercise: ExerciseId, value: unknown): value is string {
  return typeof value === 'string' && trainingVariations[exercise].includes(value);
}

export function isTrainingRange(exercise: ExerciseId, value: unknown): value is string {
  return typeof value === 'string' && trainingRanges[exercise].includes(value);
}

export function isTrainingEquipment(value: unknown): value is TrainingEquipment {
  return typeof value === 'string' && trainingEquipments.some(item => item.id === value);
}

export function isIsoTimestamp(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value));
}

// A set-level capacity proxy, never an estimate of an individual muscle's mass or force.
// Deliberately limited to near-failure sets of at most ten effective repetitions.
// The form's RIR=3 option means "three or more", so it cannot yield a point estimate.
export function estimatedOneRepMax(entry: TrainingEntry): number | undefined {
  if (!entersBarbellCapacityPool(entry)) return undefined;
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

// Where each input is meant to be measured. The diagram and the form share this list so the
// stated landmarks cannot drift apart. Every value is a self-reported measurement; the app
// derives outline geometry from it and never claims to have measured the user.
export type MeasurementAnchor =
  | 'stature' | 'mass' | 'fat' | 'chest' | 'arm' | 'waist' | 'thigh' | 'calf' | 'span' | 'inseam';

export const measurementSites: ReadonlyArray<{
  key: keyof BodyProfile;
  anchor: MeasurementAnchor;
  note: string;
}> = [
  { key: 'heightCm', anchor: 'stature', note: '不穿鞋靠墙站立，头顶到地面' },
  { key: 'weightKg', anchor: 'mass', note: '自报体重，不用于推算单块肌肉' },
  { key: 'bodyFatPct', anchor: 'fat', note: '自报估计值；不同设备或公式结果不同' },
  { key: 'chestCm', anchor: 'chest', note: '平静呼气末，经乳头水平的水平围' },
  { key: 'upperArmCm', anchor: 'arm', note: '手臂放松下垂，上臂中点水平围' },
  { key: 'waistCm', anchor: 'waist', note: '自然呼气末，经脐上方的水平围' },
  { key: 'thighCm', anchor: 'thigh', note: '站立放松，大腿最粗处水平围' },
  { key: 'calfCm', anchor: 'calf', note: '站立放松，小腿最粗处水平围' },
  { key: 'armSpanCm', anchor: 'span', note: '双臂侧平举，两手中指指尖的距离' },
  { key: 'inseamCm', anchor: 'inseam', note: '裆部到地面，内侧腿长' },
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

// Shared by localStorage reads and backup imports so both accept exactly the same records.
export function isTrainingEntry(value: unknown): value is TrainingEntry {
  if (!value || typeof value !== 'object') return false;
  const entry = value as Partial<TrainingEntry>;
  if (entry.exercise !== 'squat' && entry.exercise !== 'bench' && entry.exercise !== 'press') return false;
  if (typeof entry.loadKg !== 'number' || !Number.isFinite(entry.loadKg) ||
      entry.loadKg < 0 || entry.loadKg > 600) return false;
  if (!Number.isInteger(entry.repetitions) || entry.repetitions! < 1 || entry.repetitions! > 50) return false;
  if (entry.repsInReserve !== undefined &&
      (!Number.isInteger(entry.repsInReserve) || entry.repsInReserve < 0 || entry.repsInReserve > 3)) return false;
  if (typeof entry.date !== 'string' || !/^\d{4}\/\d{1,2}\/\d{1,2}$/.test(entry.date)) return false;
  if (entry.variation !== undefined && !isTrainingVariation(entry.exercise, entry.variation)) return false;
  if (entry.range !== undefined && !isTrainingRange(entry.exercise, entry.range)) return false;
  if (entry.equipment !== undefined && !isTrainingEquipment(entry.equipment)) return false;
  if (entry.recordedAt !== undefined && !isIsoTimestamp(entry.recordedAt)) return false;
  return true;
}

export function copyTrainingEntry(entry: TrainingEntry): TrainingEntry {
  return {
    exercise: entry.exercise, loadKg: entry.loadKg,
    repetitions: entry.repetitions, repsInReserve: entry.repsInReserve,
    date: entry.date, variation: entry.variation, range: entry.range,
    equipment: entry.equipment, recordedAt: entry.recordedAt,
  };
}

export function loadTraining(): TrainingEntry[] {
  try {
    const stored = localStorage.getItem('muscle-atlas-training-v1');
    if (!stored) return [];
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isTrainingEntry).map(copyTrainingEntry);
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
    if (!isTrainingEntry(item)) throw new Error(`第 ${index + 1} 条训练记录不在有效范围内`);
    return copyTrainingEntry(item);
  });
  return { format: 'muscle-atlas-local-backup', version: 1,
    exportedAt: data.exportedAt, profile: profile as BodyProfile, training };
}
