"""Audit unmeasured plate-Z pressure-center travel during unloaded squats.

Uses the same laboratory repetitions as the template force benchmark. Plate
COP is force-weighted across feet, and only frames with both plates loaded are
used. This is a model-input sensitivity audit, not a phone COP estimator.
"""

import argparse
import csv
import json
from pathlib import Path
from statistics import median

import numpy as np

from analyze_dynamic_squats import load_trial
from benchmark_template_squat_grf import G, SUBJECTS, measured_repetitions


ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / 'docs/data/squat_template_grf_benchmark.json').read_text(encoding='utf-8'))
parser = argparse.ArgumentParser()
parser.add_argument('--foot-load-fraction', type=float, default=0.1)
parser.add_argument('--out', type=Path, default=ROOT / 'docs/data/squat_cop_excursion_audit.json')
args = parser.parse_args()
if not 0.01 <= args.foot_load_fraction <= 0.3:
    parser.error('--foot-load-fraction must be between 0.01 and 0.3')
with (ROOT / '.cache/lower-limb-raw/Subject_masses.csv').open(
        newline='', encoding='utf-8-sig') as handle:
    masses = {row['Subject']: float(row['Mass']) for row in csv.DictReader(handle)}

baseline_rows = {(row['subject'], row['rep']): row for row in BASELINE['repetitions']}
phases = np.arange(1, 100) / 100
rows = []
rejected = []
for subject in SUBJECTS:
    trial = load_trial(subject, '0lbs')
    time, grf = trial['time'], trial['grf']
    for rep, (start, _peak, end) in enumerate(measured_repetitions(trial, 50, 0.5), 1):
        reference = baseline_rows[(subject, rep)]
        assert abs(float(time[start]) - reference['startS']) < 0.001
        assert abs(float(time[end]) - reference['endS']) < 0.001
        sample_time = time[start] + phases * float(time[end] - time[start])
        right_force = np.interp(sample_time, time, grf['RForceY_Vertical'])
        left_force = np.interp(sample_time, time, grf['LForceY_Vertical'])
        right_z = np.interp(sample_time, time, grf['RCOPZ'])
        left_z = np.interp(sample_time, time, grf['LCOPZ'])
        both_loaded = ((right_force >= args.foot_load_fraction * masses[subject] * G) &
                       (left_force >= args.foot_load_fraction * masses[subject] * G))
        if int(np.sum(both_loaded)) < 80:
            rejected.append({'subject': subject, 'rep': rep, 'reason': 'fewer than 80 bilateral loaded phases'})
            continue
        combined_z = (right_z * right_force + left_z * left_force) / (right_force + left_force)
        valid_z = combined_z[both_loaded]
        excursion_cm = float((np.percentile(valid_z, 95) - np.percentile(valid_z, 5)) * 100)
        bottom = combined_z[(phases >= 0.45) & (phases <= 0.55) & both_loaded]
        beginning = combined_z[(phases <= 0.1) & both_loaded]
        if not len(bottom) or not len(beginning):
            rejected.append({'subject': subject, 'rep': rep, 'reason': 'missing valid start or bottom phases'})
            continue
        start_to_bottom_cm = float((np.median(bottom) - np.median(beginning)) * 100)
        rows.append({
            'subject': subject, 'rep': rep, 'validPhases': int(np.sum(both_loaded)),
            'plateZExcursionP95MinusP5Cm': round(excursion_cm, 2),
            'startToBottomPlateZShiftCm': round(start_to_bottom_cm, 2),
            'staticBodyWeightTimesExcursionNm': round(masses[subject] * G * excursion_cm / 100, 1),
        })

assert len(rows) + len(rejected) == len(baseline_rows) == 39
subject_rows = []
for subject in SUBJECTS:
    subset = [row for row in rows if row['subject'] == subject]
    subject_rows.append({
        'subject': subject, 'reps': len(subset),
        'medianPlateZExcursionCm': round(median(row['plateZExcursionP95MinusP5Cm'] for row in subset), 2),
        'medianAbsStartToBottomShiftCm': round(median(abs(row['startToBottomPlateZShiftCm']) for row in subset), 2),
        'medianStaticBodyWeightTimesExcursionNm': round(median(row['staticBodyWeightTimesExcursionNm'] for row in subset), 1),
    })
summary = {
    'subjects': len(subject_rows), 'reps': len(rows), 'rejectedReps': len(rejected),
    'subjectMedianPlateZExcursionCm': round(median(row['medianPlateZExcursionCm'] for row in subject_rows), 2),
    'subjectMedianAbsStartToBottomShiftCm': round(median(row['medianAbsStartToBottomShiftCm'] for row in subject_rows), 2),
    'subjectMedianStaticBodyWeightTimesExcursionNm': round(median(row['medianStaticBodyWeightTimesExcursionNm'] for row in subject_rows), 1),
    'rangeOfSubjectMedianPlateZExcursionCm': [
        round(min(row['medianPlateZExcursionCm'] for row in subject_rows), 2),
        round(max(row['medianPlateZExcursionCm'] for row in subject_rows), 2),
    ],
}
result = {
    'status': 'laboratory_pressure_center_input_audit_not_phone_prediction',
    'source': BASELINE['source'],
    'method': f'Same 39 unloaded squat repetitions and 99 interior phases as the force benchmark. Combine the two plate COP Z coordinates using each plate vertical force, require each plate to carry at least {args.foot_load_fraction:.0%} of body weight for at least 80 phases, then report the 95th-minus-5th percentile Z excursion. Z is the laboratory plate coordinate; no foot or ankle registration is attempted.',
    'minimumFootLoadFractionOfBodyWeight': args.foot_load_fraction,
    'limitations': [
        'The plate coordinate is global and has not been registered to an individual foot or ankle, so the signed shift is not a validated joint lever arm.',
        'Body weight times total COP excursion is only a scale for possible external-moment sensitivity, not an observed joint moment or an error estimate.',
        'The phone has no pressure plate; this audit does not predict a user pressure-center trajectory.',
        'Only 0-lb trials were analyzed, and both feet must meet a simple force threshold.',
    ],
    'summary': summary, 'subjects': subject_rows, 'repetitions': rows, 'rejected': rejected,
}
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
print(f'Saved {args.out}')
