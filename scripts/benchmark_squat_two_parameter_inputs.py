"""Test whether two easy-to-enter squat parameters help the force template.

For an optimistic input-quality scenario, use laboratory measured peak knee flexion and
rep duration to select the nearest phone depth/tempo presets. Real users would
enter rough values, so these results cannot validate personal ground force.
"""

import csv
import json
from collections import Counter
from pathlib import Path
from statistics import median

import numpy as np

from analyze_dynamic_squats import load_trial
from benchmark_template_squat_grf import G, SUBJECTS, measured_repetitions


ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads((ROOT / 'docs/data/squat_template_grf_benchmark.json').read_text(encoding='utf-8'))
PROBE_PATHS = {
    75: ROOT / 'docs/data/squat_dynamic_grf_75_probe.json',
    96: ROOT / 'docs/data/squat_dynamic_grf_probe.json',
    117: ROOT / 'docs/data/squat_dynamic_grf_117_probe.json',
}
TEMPOS = (2.0, 2.8, 4.0)
TEMPLATE_DURATION = 2.8
OUTPUT = ROOT / 'docs/data/squat_two_parameter_input_benchmark.json'

probes = {depth: json.loads(path.read_text(encoding='utf-8'))
          for depth, path in PROBE_PATHS.items()}
acceleration = {}
for depth, probe in probes.items():
    assert probe['durationS'] == TEMPLATE_DURATION
    assert probe['squatDepthDeg'] == (None if depth == 96 else depth)
    source = next(row for row in probe['rows'] if row['profile']['heightCm'] == 175
                  and row['loadKg'] == 0)
    assert len(source['frames']) == 99
    assert np.allclose([item['phase'] for item in source['frames']],
                       np.arange(1, 100) / 100)
    acceleration[depth] = np.asarray([item['accelerationMs2']
                                      for item in source['frames']])

with (ROOT / '.cache/lower-limb-raw/Subject_masses.csv').open(
        newline='', encoding='utf-8-sig') as handle:
    masses = {row['Subject']: float(row['Mass']) for row in csv.DictReader(handle)}

phases = np.arange(1, 100) / 100
reference_rows = {(row['subject'], row['rep']): row for row in BASELINE['repetitions']}
rows = []
for subject in SUBJECTS:
    trial = load_trial(subject, '0lbs')
    time = trial['time']
    vertical_grf = trial['grf']['RForceY_Vertical'] + trial['grf']['LForceY_Vertical']
    for number, (start, peak, end) in enumerate(measured_repetitions(trial, 50, 0.5), 1):
        reference = reference_rows[(subject, number)]
        duration_s = float(time[end] - time[start])
        peak_deg = float(-trial['angle'][peak, 1])
        assert abs(float(time[start]) - reference['startS']) < 0.001
        assert abs(float(time[end]) - reference['endS']) < 0.001
        observed = np.interp(time[start] + phases * duration_s, time,
                             vertical_grf) / (masses[subject] * G)
        chosen_depth = min(PROBE_PATHS, key=lambda depth: (abs(depth - peak_deg), depth))
        chosen_tempo = min(TEMPOS, key=lambda tempo: (abs(tempo - duration_s), tempo))

        def error(depth, tempo):
            predicted = 1 + acceleration[depth] / G * (TEMPLATE_DURATION / tempo) ** 2
            return float(np.mean(np.abs(observed - predicted)))

        errors = {
            'static': float(np.mean(np.abs(observed - 1))),
            'default': error(96, TEMPLATE_DURATION),
            'measuredDepthPreset': error(chosen_depth, TEMPLATE_DURATION),
            'measuredDurationPreset': error(96, chosen_tempo),
            'bothMeasuredPresets': error(chosen_depth, chosen_tempo),
        }
        assert abs(errors['static'] - reference['staticWeightMaeRatio']) < 0.0001
        assert abs(errors['default'] - reference['fixedDurationTemplateMaeRatio']) < 0.0001
        rows.append({
            'subject': subject, 'rep': number,
            'observedPeakKneeFlexionDeg': round(peak_deg, 2),
            'observedDurationS': round(duration_s, 3),
            'chosenDepthPresetDeg': chosen_depth,
            'chosenTempoPresetS': chosen_tempo,
            'maeBodyWeightRatio': {key: round(value, 4) for key, value in errors.items()},
        })

assert len(rows) == len(reference_rows) == 39
subject_rows = []
for subject in SUBJECTS:
    subset = [row for row in rows if row['subject'] == subject]
    subject_rows.append({
        'subject': subject, 'reps': len(subset),
        'medianMaeBodyWeightRatio': {
            key: round(median(row['maeBodyWeightRatio'][key] for row in subset), 4)
            for key in rows[0]['maeBodyWeightRatio']
        },
    })

policies = rows[0]['maeBodyWeightRatio']
summary = {
    'subjects': len(subject_rows), 'reps': len(rows),
    'selectedDepthCounts': {str(depth): Counter(row['chosenDepthPresetDeg'] for row in rows)[depth]
                            for depth in PROBE_PATHS},
    'selectedTempoCounts': {str(tempo): Counter(row['chosenTempoPresetS'] for row in rows)[tempo]
                            for tempo in TEMPOS},
    'subjectMedianMaeBodyWeightRatio': {
        key: round(median(row['medianMaeBodyWeightRatio'][key] for row in subject_rows), 4)
        for key in policies
    },
    'subjectsBeatingDefault': {
        key: sum(row['medianMaeBodyWeightRatio'][key] <
                 row['medianMaeBodyWeightRatio']['default'] for row in subject_rows)
        for key in policies if key != 'default'
    },
}
random = np.random.default_rng(42)
bootstrap_indices = random.integers(len(subject_rows), size=(10000, len(subject_rows)))
summary['pairedSubjectMedianImprovementVsDefault'] = {}
summary['pairedSubjectMedianImprovementBootstrap95'] = {}
for key in policies:
    if key == 'default':
        continue
    improvements = np.asarray([
        row['medianMaeBodyWeightRatio']['default'] - row['medianMaeBodyWeightRatio'][key]
        for row in subject_rows
    ])
    bootstrap_medians = np.median(improvements[bootstrap_indices], axis=1)
    summary['pairedSubjectMedianImprovementVsDefault'][key] = round(float(np.median(improvements)), 4)
    summary['pairedSubjectMedianImprovementBootstrap95'][key] = [
        round(float(value), 4) for value in np.quantile(bootstrap_medians, [0.025, 0.975])
    ]
result = {
    'status': 'optimistic_measured_input_sensitivity_not_phone_personal_validation',
    'source': BASELINE['source'],
    'method': 'Use the measured laboratory peak knee flexion and exact rep duration to choose the nearest of three phone presets each. Compare 99 phase-normalized vertical force samples for the same 39 unloaded repetitions as the default benchmark.',
    'limitations': [
        'Laboratory peak knee flexion and exact repetition duration are oracle inputs; users entering approximate values will generally be less accurate.',
        'The experiment provides the repetition boundaries used for time alignment; the phone does not observe these boundaries.',
        'The 175-cm symmetric template does not use participant-specific segment dimensions, bar path, foot contact, or individual motion shape.',
        'Only 0-lb squats and overall vertical force were tested; no joint moment, muscle activation, or muscle force was validated.',
    ],
    'summary': summary,
    'subjects': subject_rows,
    'repetitions': rows,
}
OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
print(f'Saved {OUTPUT}')
