"""Inspect GroundLink squat GRF/CoP without executing its pickle payloads.

GroundLink's .npy files contain legacy torch-serialized object arrays. The
research archive is kept in .cache; this reader uses pickletools only to locate
two FloatStorage byte strings, and validates their structure before decoding
the float32 values. No pickle.load, numpy allow_pickle, or torch.load is used.
"""

import json
import re
import zipfile
from pathlib import Path
from statistics import median

import numpy as np

from groundlink_force_format import read_groundlink_npy


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / '.cache/groundlink'
OUTPUT = ROOT / 'docs/data/groundlink_squat_force_audit.json'
BODY_MASS_KG = {
    's001': 69.86, 's002': 66.68, 's003': 53.07, 's004': 71.67,
    's005': 90.7, 's006': 48.99, 's007': 63.96,
}
SAMPLE_RATE_HZ = 250
G = 9.80665


def summary(values):
    return {'median': round(float(median(values)), 4),
            'min': round(float(min(values)), 4),
            'max': round(float(max(values)), 4)}


trials = []
for subject, mass in BODY_MASS_KG.items():
    archive = INPUT / f'{subject}_force.zip'
    with zipfile.ZipFile(archive) as zipped:
        members = sorted(name for name in zipped.namelist()
                         if re.fullmatch(rf'{subject}/{subject}_\d+_squat_\d+\.npy', name))
        if not members:
            raise ValueError(f'No squat trials in {archive}')
        for member in members:
            parsed = read_groundlink_npy(zipped.read(member))
            grf_kn = parsed['GRF']
            cop_m = parsed['CoP']
            vertical_kn = grf_kn[:, :, 2]
            total_ratio = vertical_kn.sum(axis=1) * 1000 / (mass * G)
            valid_feet = np.all(vertical_kn > 0.05 * mass * G / 1000, axis=1)
            weighted_cop = np.sum(cop_m[:, :, :2] * vertical_kn[:, :, None], axis=1)
            weighted_cop /= np.maximum(vertical_kn.sum(axis=1)[:, None], 1e-9)
            weighted_cop = weighted_cop[valid_feet]
            if len(weighted_cop) < 0.5 * len(total_ratio):
                raise ValueError(f'Too few two-foot samples: {member}')
            excursions_cm = [float(np.percentile(weighted_cop[:, axis], 95) -
                                   np.percentile(weighted_cop[:, axis], 5)) * 100
                             for axis in range(2)]
            trials.append({
                'subject': subject, 'member': member,
                'samples': len(total_ratio),
                'durationS': round(len(total_ratio) / SAMPLE_RATE_HZ, 3),
                'medianSupportRatioToBodyWeight': round(float(np.median(total_ratio)), 4),
                'staticWeightBaselineMaeRatio': round(float(np.mean(np.abs(total_ratio - 1))), 4),
                'supportP05ToP95RatioRange': round(float(np.percentile(total_ratio, 95) -
                                                           np.percentile(total_ratio, 5)), 4),
                'twoFootValidFraction': round(float(np.mean(valid_feet)), 4),
                'combinedCopXExcursionCm': round(excursions_cm[0], 2),
                'combinedCopYExcursionCm': round(excursions_cm[1], 2),
            })

subjects = []
for subject in BODY_MASS_KG:
    group = [trial for trial in trials if trial['subject'] == subject]
    subjects.append({
        'subject': subject, 'massKg': BODY_MASS_KG[subject], 'trials': len(group),
        'medianSupportRatio': round(median(row['medianSupportRatioToBodyWeight'] for row in group), 4),
        'medianStaticBaselineMaeRatio': round(median(row['staticWeightBaselineMaeRatio'] for row in group), 4),
        'medianCopXExcursionCm': round(median(row['combinedCopXExcursionCm'] for row in group), 2),
        'medianCopYExcursionCm': round(median(row['combinedCopYExcursionCm'] for row in group), 2),
    })

result = {
    'status': 'external_dataset_force_only_audit_not_app_prediction_validation',
    'source': 'https://csr.bu.edu/groundlink/',
    'paper': 'https://arxiv.org/html/2310.03930',
    'method': 'Read the original seven public force ZIPs without unpickling; extract the two-foot xyz GRF and CoP float storages. Multiply recorded GRF by 1000 before dividing summed vertical support by the paper’s subject mass times 9.80665; kN scale is inferred from the standing body-weight check, not documented in a field dictionary. Compute 5th–95th percentile excursion of force-weighted two-foot CoP on global X and Y; both feet must exceed 5% body weight. No rep segmentation, pose matching, or model fitting.',
    'summary': {
        'subjects': len(subjects), 'trials': len(trials),
        'durationS': summary([row['durationS'] for row in trials]),
        'subjectMedianSupportRatio': summary([row['medianSupportRatio'] for row in subjects]),
        'subjectMedianStaticBaselineMaeRatio': summary([row['medianStaticBaselineMaeRatio'] for row in subjects]),
        'subjectMedianCopXExcursionCm': summary([row['medianCopXExcursionCm'] for row in subjects]),
        'subjectMedianCopYExcursionCm': summary([row['medianCopYExcursionCm'] for row in subjects]),
    },
    'limitations': [
        'GroundLink squats are unloaded and include entire trials, not segmented repetitions.',
        'GRF kN scale is inferred from the body-weight support check, not confirmed by a source field dictionary; it is not an individual muscle force.',
        'Global X/Y CoP axes are not registered to each subject’s foot or ankle and the trial range may include setup/ending portions.',
        'The app’s 2.8-second pose/COM template cannot be compared frame-by-frame without motion capture alignment. This force-only audit does not validate the app’s predicted GRF or joint moments.',
    ],
    'subjects': subjects, 'trials': trials,
}
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
print(f'Saved {OUTPUT}')
