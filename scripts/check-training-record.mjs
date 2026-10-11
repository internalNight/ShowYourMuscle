import assert from 'node:assert/strict';
import { build } from 'esbuild';

const bundled = await build({
  entryPoints: ['src/domain.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
});
const source = bundled.outputFiles[0].text;
const domain = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const {
  defaultProfile, estimatedOneRepMax, entersBarbellCapacityPool, isTrainingEntry, copyTrainingEntry,
  makeLocalBackup, parseLocalBackup, trainingVariations, trainingRanges, trainingEquipments, bodyFields,
} = domain;

const exercises = ['squat', 'bench', 'press'];

// Every option offered for an exercise must be accepted, so the form can never save a rejectable record.
for (const exercise of exercises) {
  assert.ok(trainingVariations[exercise].length > 0, `${exercise} needs at least one variant`);
  assert.ok(trainingRanges[exercise].length > 0, `${exercise} needs at least one range option`);
  for (const variation of trainingVariations[exercise]) {
    assert.ok(isTrainingEntry({ exercise, loadKg: 100, repetitions: 5, date: '2026/9/26', variation }),
      `${exercise} variant ${variation} rejected`);
  }
  for (const range of trainingRanges[exercise]) {
    assert.ok(isTrainingEntry({ exercise, loadKg: 100, repetitions: 5, date: '2026/9/26', range }),
      `${exercise} range ${range} rejected`);
  }
}

// Action-level 1RM stays limited to near-failure sets of at most ten effective repetitions.
assert.equal(estimatedOneRepMax({ exercise: 'bench', loadKg: 100, repetitions: 3, repsInReserve: 0, date: '2026/9/26' }),
  100 * (1 + 3 / 30));
assert.equal(estimatedOneRepMax({ exercise: 'bench', loadKg: 100, repetitions: 5, repsInReserve: 2, date: '2026/9/26' }),
  100 * (1 + 7 / 30));
assert.equal(estimatedOneRepMax({ exercise: 'bench', loadKg: 100, repetitions: 8, repsInReserve: 2, date: '2026/9/26' }),
  100 * (1 + 10 / 30));
assert.equal(estimatedOneRepMax({ exercise: 'bench', loadKg: 100, repetitions: 9, repsInReserve: 2, date: '2026/9/26' }), undefined,
  'eleven effective repetitions must not produce a point estimate');
assert.equal(estimatedOneRepMax({ exercise: 'bench', loadKg: 100, repetitions: 3, repsInReserve: 3, date: '2026/9/26' }), undefined,
  '"three or more" is a lower bound, not RIR 3');
assert.equal(estimatedOneRepMax({ exercise: 'bench', loadKg: 100, repetitions: 3, date: '2026/9/26' }), undefined,
  'unknown proximity to failure must not produce a point estimate');

// A record saved before the equipment field existed came from the barbell form and still counts.
assert.equal(entersBarbellCapacityPool({ exercise: 'bench', loadKg: 100, repetitions: 3, date: '2026/9/26' }), true);
assert.equal(estimatedOneRepMax({ exercise: 'bench', loadKg: 100, repetitions: 3, repsInReserve: 0, date: '2026/9/26' }),
  estimatedOneRepMax({ exercise: 'bench', loadKg: 100, repetitions: 3, repsInReserve: 0, date: '2026/9/26', equipment: 'barbell' }));

// Dumbbell, machine, smith and bodyweight loads are not interchangeable with the barbell pool.
for (const equipment of ['dumbbell', 'machine', 'smith', 'bodyweight', 'other']) {
  const entry = { exercise: 'bench', loadKg: 40, repetitions: 3, repsInReserve: 0, date: '2026/9/26', equipment };
  assert.equal(entersBarbellCapacityPool(entry), false, `${equipment} must stay out of the barbell pool`);
  assert.equal(estimatedOneRepMax(entry), undefined, `${equipment} must not yield a barbell 1RM`);
}

// Field validation.
const base = { exercise: 'squat', loadKg: 100, repetitions: 5, date: '2026/9/26' };
assert.ok(isTrainingEntry(base), 'legacy five-field record must stay valid');
assert.ok(isTrainingEntry({ ...base, equipment: 'barbell', variation: '低杠位', range: '至水平',
  recordedAt: new Date().toISOString() }), 'full record must be valid');
assert.ok(isTrainingEntry({ ...base, variation: '低杠位' }), 'squat variant must be valid for squat');
assert.ok(!isTrainingEntry({ ...base, variation: '上斜' }), 'a bench variant must be rejected for squat');
assert.ok(!isTrainingEntry({ ...base, range: '触胸' }), 'a bench range must be rejected for squat');
assert.ok(!isTrainingEntry({ ...base, equipment: 'kettlebell' }), 'unknown equipment must be rejected');
assert.ok(!isTrainingEntry({ ...base, recordedAt: '2026/9/26' }), 'a bare date is not an ISO timestamp');
assert.ok(!isTrainingEntry({ ...base, recordedAt: '2026-13-45T99:00:00.000Z' }), 'impossible timestamps must be rejected');
assert.ok(isTrainingEntry({ ...base, recordedAt: '2026-09-26T04:05:06.000Z' }));
assert.ok(!isTrainingEntry({ ...base, loadKg: 601 }), 'load above the form range must be rejected');
assert.ok(!isTrainingEntry({ ...base, repetitions: 0 }), 'zero repetitions must be rejected');
assert.ok(!isTrainingEntry({ ...base, date: '2026-09-26' }), 'only the stored display format is accepted');
assert.ok(isTrainingEntry({ ...base, equipment: trainingEquipments[0].id }));

// The import path used to rebuild only five keys, silently dropping everything added since.
const full = { exercise: 'press', loadKg: 60, repetitions: 4, repsInReserve: 1, date: '2026/9/26',
  variation: '站姿实力举', range: '锁定位全程', equipment: 'barbell', recordedAt: '2026-09-26T04:05:06.000Z' };
const copied = copyTrainingEntry(full);
assert.deepEqual(copied, full, 'copyTrainingEntry must keep every field');

const backup = makeLocalBackup(defaultProfile, [full, base]);
const parsed = parseLocalBackup(JSON.parse(JSON.stringify(backup)));
assert.deepEqual(parsed.training[0], full, 'backup round trip must keep the new fields');
assert.deepEqual(parsed.training[1], { ...base, repsInReserve: undefined, variation: undefined,
  range: undefined, equipment: undefined, recordedAt: undefined }, 'legacy records must survive a round trip');

// A legacy backup without the new keys still imports.
const legacy = { format: 'muscle-atlas-local-backup', version: 1, exportedAt: '2026-09-26T04:05:06.000Z',
  profile: defaultProfile, training: [base] };
assert.equal(parseLocalBackup(legacy).training.length, 1);

// Import stays all-or-nothing: one bad record rejects the whole file.
assert.throws(() => parseLocalBackup({ ...legacy, training: [base, { ...base, equipment: 'kettlebell' }] }),
  /第 2 条训练记录/, 'an invalid record must abort the import');
assert.throws(() => parseLocalBackup({ ...legacy, version: 2 }), /不是受支持的肌动图谱备份/);

// The import path is the one place a stranger's file reaches the app, so its refusals are checked from
// both sides: the accepted boundary and the refused one. A rejection-only test would also pass if the
// parser rejected everything, and the boundaries themselves were never exercised before this round.
const validRecord = { exercise: 'squat', loadKg: 100, repetitions: 5, date: '2026/9/26' };
const backupOf = (training) => ({ format: 'muscle-atlas-local-backup', version: 1,
  exportedAt: '2026-09-26T04:05:06.000Z', profile: defaultProfile, training });
assert.equal(parseLocalBackup(backupOf(Array.from({ length: 1000 }, () => ({ ...validRecord })))).training.length,
  1000, 'a thousand records must still import');
assert.throws(() => parseLocalBackup(backupOf(Array.from({ length: 1001 }, () => ({ ...validRecord })))),
  /训练记录数量无效/, 'more than a thousand records must be refused');

for (const field of bodyFields) {
  const at = (value) => parseLocalBackup({ ...backupOf([]), profile: { ...defaultProfile,
    [field.key]: value } });
  assert.equal(at(field.min).profile[field.key], field.min, `${field.label} at its minimum must import`);
  assert.equal(at(field.max).profile[field.key], field.max, `${field.label} at its maximum must import`);
  assert.throws(() => at(field.min - 1), /不在有效范围内/,
    `${field.label} below its minimum must be refused`);
  assert.throws(() => at(field.max + 1), /不在有效范围内/,
    `${field.label} above its maximum must be refused`);
}
const requiredFields = bodyFields.filter(field => field.required);
assert.ok(requiredFields.length > 0, 'the profile must declare at least one required field');
for (const field of requiredFields) {
  const missing = { ...defaultProfile };
  delete missing[field.key];
  assert.throws(() => parseLocalBackup({ ...backupOf([]), profile: missing }),
    /不在有效范围内/, `a missing ${field.label} must be refused, not defaulted`);
}
for (const hostile of [null, undefined, 42, 'x', [], {}, { ...backupOf([]), training: {} },
  { ...backupOf([]), profile: null }, { ...backupOf([]), exportedAt: 'not a date' }]) {
  assert.throws(() => parseLocalBackup(hostile), /备份|不受支持/,
    `hostile backup input was accepted: ${String(JSON.stringify(hostile)).slice(0, 40)}`);
}

// The shape of the estimate itself: a single taken to failure is its own maximum, the reserve shifts it
// by whole repetitions, and the ten-repetition cap bounds it.
const single = { exercise: 'squat', loadKg: 140, repetitions: 1, repsInReserve: 0, date: '2026/9/26',
  equipment: 'barbell' };
assert.equal(estimatedOneRepMax(single), 140, 'a single taken to failure is its own maximum');
assert.equal(estimatedOneRepMax({ ...single, repsInReserve: 1 }), 140 * (1 + 2 / 30),
  'one repetition in reserve on a single counts as two effective repetitions');
const estimateAt = (repetitions) => estimatedOneRepMax({ ...single, repetitions });
assert(estimateAt(2) > estimateAt(1) && estimateAt(5) > estimateAt(2) && estimateAt(10) > estimateAt(5),
  'more effective repetitions must raise the estimate');
assert(estimateAt(10) <= 140 * (1 + 10 / 30) + 1e-9, 'the ten-repetition cap must bound the estimate');
assert.equal(estimatedOneRepMax({ ...single, loadKg: 0 }), undefined,
  'a zero load must not produce an estimate');
assert.equal(estimatedOneRepMax({ ...single, loadKg: 210 }) / 210, estimateAt(1) / 140,
  'the estimate must scale linearly with the load');

// The capacity pool is the intersection of the two rules: barbell equipment and a usable estimate.
const mixed = [
  { exercise: 'squat', loadKg: 100, repetitions: 5, repsInReserve: 2, date: '2026/9/26', equipment: 'barbell' },
  { exercise: 'bench', loadKg: 100, repetitions: 9, repsInReserve: 2, date: '2026/9/26', equipment: 'barbell' },
  { exercise: 'bench', loadKg: 40, repetitions: 3, repsInReserve: 0, date: '2026/9/26', equipment: 'dumbbell' },
  { exercise: 'press', loadKg: 60, repetitions: 4, repsInReserve: 1, date: '2026/9/26' },
  { exercise: 'squat', loadKg: 140, repetitions: 1, repsInReserve: 0, date: '2026/9/26', equipment: 'barbell' },
];
const pool = mixed.map(estimatedOneRepMax).filter(value => value !== undefined);
assert.deepEqual(pool, [100 * (1 + 7 / 30), 60 * (1 + 5 / 30), 140],
  'the pool must hold exactly the eligible barbell estimates, in record order');
for (const [index, entry] of mixed.entries()) {
  if (!entersBarbellCapacityPool(entry)) {
    assert.equal(estimatedOneRepMax(entry), undefined,
      `entry ${index} is outside the barbell pool but still produced an estimate`);
  }
}

console.log(`training records: ${exercises.length} exercises, ${trainingEquipments.length} equipment kinds, `
  + `${Object.values(trainingVariations).flat().length} variants and ${Object.values(trainingRanges).flat().length} range options validated; `
  + 'barbell-only 1RM pool, ISO timestamps and backup round trip checked.');
