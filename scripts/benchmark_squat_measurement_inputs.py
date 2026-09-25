"""Exploratory leave-one-person-out test of extra squat measurement inputs.

Segment dimensions come from released scaled models, not tape measurements.
Every variant still uses measured knee angle, unavailable to the phone preset.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import numpy as np
import opensim as osim
from benchmark_squat_moments import SUBJECTS, PHASES, TARGETS, features, fit_predict, load_masses, select_frames
from analyze_dynamic_squats import load_trial
from probe_high_flex_segment_scaling import dimensions

osim.Logger.setLevelString('Error')
masses = load_masses()
anthro = {}
for subject in SUBJECTS:
    path = ROOT / '.cache/lower-limb-raw' / subject / 'Models' / f'{subject}-Scaled1.osim'
    model = osim.Model(str(path.relative_to(ROOT)))
    state = model.initSystem()
    model.realizePosition(state)
    d = dimensions(model, state, 'knee')
    thigh = (d['r']['effectiveHipToKneeM'] + d['l']['effectiveHipToKneeM']) / 2
    shank = (d['r']['tibiaKneeToAnkleM'] + d['l']['tibiaKneeToAnkleM']) / 2
    anthro[subject] = (thigh, shank, d['hipCenterWidthM'])

variants = ('simple', 'normload', 'legonly', 'anthro', 'both')
records = {}
for subject in SUBJECTS:
    rows = []
    thigh, shank, hipwidth = anthro[subject]
    for load in ('0lbs', '25lbs'):
        trial = load_trial(subject, load)
        for phase in PHASES:
            index = select_frames(trial, phase)
            if not len(index):
                continue
            loaded = int(load == '25lbs')
            base = features(trial, index, masses[subject], loaded, phase, False)
            knee = -trial['angle'][index, 1] / 90
            normalized_load = np.full(len(index), loaded * 11.34 / masses[subject])
            lengths = np.column_stack((
                np.full(len(index), thigh), np.full(len(index), shank),
                np.full(len(index), hipwidth),
                knee * (thigh + shank),
            ))
            matrices = {
                'simple': base,
                'normload': np.column_stack((base, normalized_load, knee * normalized_load)),
                'legonly': np.column_stack((base, np.full(len(index), thigh + shank), knee * (thigh + shank))),
                'anthro': np.column_stack((base, lengths)),
                'both': np.column_stack((base, normalized_load, knee * normalized_load, lengths)),
            }
            rows.append((matrices, np.column_stack([trial['moment'][k][index] for k in TARGETS])))
    records[subject] = rows

report = {
    'status': 'research_only_exploratory_measurement_feature_screen',
    'source': 'Scherpereel et al. 2023 dynamic squat files',
    'protocol': 'Leave one whole participant out; same frame eligibility, targets and ridge penalty as benchmark_squat_moments.py; no separate model-selection cohort',
    'momentUnit': 'N m/kg, supported by independent IK/ID replay',
    'featureDefinitions': {
        'simple': 'body mass, nominal 0/25-lb load, measured right knee angle, descent/ascent',
        'normload': 'simple plus load kg / body mass and its knee-angle interaction',
        'legonly': 'simple plus neutral source-model hip-to-knee + knee-to-ankle length and its knee-angle interaction',
        'anthro': 'simple plus neutral source-model hip-to-knee, knee-to-ankle, hip width, and knee-angle/leg-length interaction',
        'both': 'normload and anthro together',
    },
    'limitations': [
        '12 participants and one squat protocol; exploratory feature comparison',
        'scaled-model joint-center distances are not participant tape measurements or phone inputs',
        'all variants use laboratory knee angle, while the app uses a preset animation',
        'trial load location is unspecified and training capacity records are unavailable',
        'joint net moment is not individual muscle force',
    ],
    'subjectModelDimensionsM': {
        subject: dict(zip(('hipToKneeM', 'kneeToAnkleM', 'hipCenterWidthM'),
                          (round(v, 4) for v in values)))
        for subject, values in anthro.items()},
    'summary': {},
}
for target_index, target in enumerate(TARGETS):
    truth = []
    errors = {variant: [] for variant in variants}
    subject_maes = {variant: [] for variant in variants}
    for held in SUBJECTS:
        truth_held = np.concatenate([pair[1][:, target_index] for pair in records[held]])
        truth.extend(truth_held)
        for variant in variants:
            train_x = np.concatenate([matrices[variant] for subject in SUBJECTS if subject != held for matrices, y in records[subject]])
            train_y = np.concatenate([y[:, target_index] for subject in SUBJECTS if subject != held for matrices, y in records[subject]])
            test_x = np.concatenate([matrices[variant] for matrices, y in records[held]])
            residual = fit_predict(train_x, train_y, test_x) - truth_held
            errors[variant].extend(residual)
            subject_maes[variant].append(np.mean(abs(residual)))
    truth = np.asarray(truth)
    print(target)
    report['summary'][target] = {}
    for variant in variants:
        error = np.asarray(errors[variant])
        result = {
            'pooledR2': round(float(1 - np.sum(error ** 2) /
                                    np.sum((truth - truth.mean()) ** 2)), 4),
            'pooledMaeNmPerKg': round(float(np.mean(abs(error))), 4),
            'medianSubjectMaeNmPerKg': round(float(np.median(subject_maes[variant])), 4),
        }
        report['summary'][target][variant] = result
        print(variant, result)
print('anthropometry', {k: tuple(round(v, 3) for v in values) for k, values in anthro.items()})
output = ROOT / 'docs/data/dynamic_squat_measurement_input_benchmark.json'
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                  encoding='utf-8')
