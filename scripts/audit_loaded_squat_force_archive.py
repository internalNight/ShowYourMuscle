"""Audit the published loaded back-squat force traces without redistributing them.

Download the CC BY 4.0 Zenodo 12786141 RAR, then extract only its ForcePlatform
directory to .cache/barbell-intensity/extracted. Run this file from any directory.
The archive does not provide individual body masses, 1RMs, or joint kinematics;
therefore this is a trace-quality and load-order audit, not model validation.
"""

import json
import re
from pathlib import Path
from statistics import median

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.cache/barbell-intensity/extracted/Data Motor Variability/ForcePlatform'
OUTPUT = ROOT / 'docs/data/loaded_squat_force_archive_audit.json'
NAME = re.compile(r'PLA_2_S(\d+)_(10|30|50|70|90)_(?:IMU_)?sin\.txt$', re.I)


def summarize(values):
    return {'median': round(float(np.median(values)), 4),
            'min': round(float(np.min(values)), 4),
            'max': round(float(np.max(values)), 4)}


traces = []
for path in sorted(SOURCE.glob('*.txt')):
    match = NAME.fullmatch(path.name)
    if not match:
        raise ValueError(f'Unexpected file name: {path.name}')
    sample = np.loadtxt(path)
    if sample.ndim != 2 or sample.shape[1] != 4 or not np.isfinite(sample).all():
        raise ValueError(f'Unexpected trace shape or nonfinite values: {path}')
    fz = sample[:, 2]
    norm_error = np.abs(np.linalg.norm(sample[:, :3], axis=1) - sample[:, 3])
    traces.append({
        'subject': match.group(1), 'percent1RM': int(match.group(2)),
        'samples': len(sample), 'durationS': len(sample) / 100,
        'meanFzN': float(np.mean(fz)), 'medianFzN': float(np.median(fz)),
        'p05FzN': float(np.percentile(fz, 5)),
        'p95FzN': float(np.percentile(fz, 95)),
        'negativeFzFraction': float(np.mean(fz < 0)),
        'normMaxErrorN': float(np.max(norm_error)),
        'plausibleForceScale': bool(np.median(fz) > 250 and np.percentile(fz, 95) > 400),
    })

subjects = sorted({row['subject'] for row in traces})
expected = [10, 30, 50, 70, 90]
rows = []
for subject in subjects:
    group = sorted((row for row in traces if row['subject'] == subject),
                   key=lambda row: row['percent1RM'])
    if [row['percent1RM'] for row in group] != expected:
        raise ValueError(f'Incomplete five-load series: {subject}')
    x = np.array(expected, dtype=float)
    mean_force = np.array([row['meanFzN'] for row in group])
    median_force = np.array([row['medianFzN'] for row in group])
    slope, intercept = np.polyfit(x, mean_force, 1)
    fitted = slope * x + intercept
    denominator = float(np.sum((mean_force - np.mean(mean_force)) ** 2))
    r2 = 1 - float(np.sum((mean_force - fitted) ** 2)) / denominator if denominator else 0
    rows.append({
        'subject': subject,
        'monotonicMeanFz': bool(np.all(np.diff(mean_force) > 0)),
        'monotonicMedianFz': bool(np.all(np.diff(median_force) > 0)),
        'meanFzNByLoad': [round(float(v), 1) for v in mean_force],
        'durationSByLoad': [round(row['durationS'], 2) for row in group],
        'linearMeanForceR2': round(r2, 4),
        'linearMeanForceSlopeNPerPercent1RM': round(float(slope), 3),
        'linearMeanForceInterceptN': round(float(intercept), 1),
        'allFivePlausibleForceScale': all(row['plausibleForceScale'] for row in group),
        'medianFzNByLoad': [round(float(v), 1) for v in median_force],
    })

valid_rows = [row for row in rows if row['allFivePlausibleForceScale']]
invalid_traces = [row for row in traces if not row['plausibleForceScale']]
intermediate_errors_n = []
intermediate_errors_ratio = []
for row in valid_rows:
    values = row['medianFzNByLoad']
    for index in (1, 2, 3):
        predicted = values[0] + (values[-1] - values[0]) * (expected[index] - 10) / 80
        error = abs(predicted - values[index])
        intermediate_errors_n.append(error)
        intermediate_errors_ratio.append(error / values[index])

by_load = {}
for load in expected:
    group = [row for row in traces if row['percent1RM'] == load]
    by_load[str(load)] = {
        'traces': len(group),
        'durationS': summarize([row['durationS'] for row in group]),
        'meanFzN': summarize([row['meanFzN'] for row in group]),
        'withinTraceP05ToP95FzN': summarize([
            row['p95FzN'] - row['p05FzN'] for row in group]),
    }

result = {
    'source': 'https://zenodo.org/records/12786141',
    'paper': 'https://doi.org/10.1371/journal.pone.0307949',
    'method': 'Each force-platform file is one continuous set at 100 Hz. The third column is tentatively interpreted as vertical force in N when its scale is plausible (>250 median and >400 N p95); the fourth is numerically checked as the resultant of the first three. These thresholds are a transparent screening heuristic, not a validated quality standard. Per-set statistics are descriptive only. Repetitions are not segmented.',
    'summary': {
        'archiveForceFiles': len(traces),
        'uniqueSubjectIds': len(subjects),
        'paperParticipants': 72,
        'allFiveLoadSeries': len(rows),
        'plausibleForceScaleTraces': len(traces) - len(invalid_traces),
        'allFivePlausibleForceScaleSubjects': len(valid_rows),
        'invalidForceScaleFiles': [f"S{row['subject']}_{row['percent1RM']}" for row in invalid_traces],
        'monotonicMeanForceSubjects': sum(row['monotonicMeanFz'] for row in rows),
        'monotonicMedianForceSubjects': sum(row['monotonicMedianFz'] for row in rows),
        'validSubjectsMonotonicMedianForce': sum(row['monotonicMedianFz'] for row in valid_rows),
        'endpointInterpolatedMiddleLoadMedianAbsoluteErrorN': summarize(intermediate_errors_n),
        'endpointInterpolatedMiddleLoadAbsoluteErrorFraction': summarize(intermediate_errors_ratio),
        'linearMeanForceR2': summarize([row['linearMeanForceR2'] for row in rows]),
        'validSubjectsLinearMedianForceR2': summarize([
            1 - float(np.sum((np.array(row['medianFzNByLoad']) - np.polyval(
                np.polyfit(expected, row['medianFzNByLoad'], 1), expected)) ** 2)) /
            float(np.sum((np.array(row['medianFzNByLoad']) - np.mean(row['medianFzNByLoad'])) ** 2))
            for row in valid_rows]),
        'maxResultantColumnErrorN': round(max(row['normMaxErrorN'] for row in traces), 8),
        'negativeVerticalForceSamples': round(sum(row['negativeFzFraction'] * row['samples'] for row in traces)),
        'byLoad': by_load,
    },
    'limitations': [
        'The archive contains 76 complete subject IDs, while the paper reports 72 analyzed participants; no exclusion mapping is supplied.',
        'Several force-platform files have a vertical-channel scale near 9.8 or near zero instead of hundreds of N; their meaning cannot be resolved from the archive. They fail the screening heuristic and cannot be pooled with putative force traces.',
        'Individual body mass and 1RM are absent, so the exact external load and expected absolute support force cannot be reconstructed independently.',
        'The traces contain multiple repetitions and possible setup/rerack periods, but no phase labels or individual joint kinematics. Means do not identify peak effort or muscle force.',
        'Regressing the measured force against percentage load is a within-archive consistency check, not validation of the app model. Fitting individual 1RM or body mass from the same force trace would leak the target.',
        'The 30/50/70% endpoint interpolation uses each person’s measured 10% and 90% forces as calibration. It holds out load conditions, not people, and the phone app cannot collect those force plate calibration values.',
    ],
    'subjects': rows,
}
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
print(f'Saved {OUTPUT}')
