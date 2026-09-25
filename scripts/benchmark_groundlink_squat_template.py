"""Independent-laboratory audit of the phone's unloaded squat support template.

The app predictions come from export_groundlink_squat_template.mjs. Experimental
pelvis marker height is used only to segment and time-align three reps per trial;
the app has no access to that marker or measured duration. This is an optimistic
research benchmark, not a user-level force or muscle validation.
"""

import argparse
import json
import zipfile
from pathlib import Path
from statistics import median

import ezc3d
import numpy as np
from scipy.signal import find_peaks, savgol_filter

from groundlink_force_format import read_groundlink_npy


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.cache/groundlink'
TEMPLATE = json.loads((SOURCE / 'template_predictions.json').read_text(encoding='utf-8'))
OUTPUT = ROOT / 'docs/data/groundlink_squat_template_benchmark.json'
RATE = 250
G = 9.80665


parser = argparse.ArgumentParser()
parser.add_argument('--top-fraction', type=float, default=0.9)
parser.add_argument('--out', type=Path, default=OUTPUT)
args = parser.parse_args()
if not 0.75 <= args.top_fraction <= 0.97:
    parser.error('--top-fraction must be from 0.75 to 0.97')


def segment_reps(height_m):
    smoothed = savgol_filter(height_m, 101, 3)
    bottoms, _ = find_peaks(-smoothed, prominence=0.12, distance=int(0.8 * RATE))
    if len(bottoms) != 3:
        raise ValueError(f'Expected three pelvis-height squat troughs; found {len(bottoms)}')
    reps = []
    for index, bottom in enumerate(bottoms):
        left = 0 if index == 0 else int(bottoms[index - 1]) + 1
        right = len(smoothed) - 1 if index == 2 else int(bottoms[index + 1]) - 1
        left_top = float(np.max(smoothed[left:bottom]))
        right_top = float(np.max(smoothed[bottom + 1:right + 1]))
        bottom_height = float(smoothed[bottom])
        depth = min(left_top, right_top) - bottom_height
        if depth < 0.2:
            raise ValueError(f'Insufficient pelvis excursion: {depth:.3f} m')
        left_gate = bottom_height + args.top_fraction * (left_top - bottom_height)
        right_gate = bottom_height + args.top_fraction * (right_top - bottom_height)
        before = np.where(smoothed[left:bottom] >= left_gate)[0]
        after = np.where(smoothed[bottom + 1:right + 1] >= right_gate)[0]
        if not len(before) or not len(after):
            raise ValueError('Squat start or end top crossing missing')
        start = left + int(before[-1])
        end = bottom + 1 + int(after[0])
        duration = (end - start) / RATE
        if not 0.8 <= duration <= 5.5:
            raise ValueError(f'Unreasonable rep duration: {duration:.2f} s')
        reps.append((start, int(bottom), end, round(depth, 3)))
    if any(reps[i][2] >= reps[i + 1][0] for i in range(2)):
        raise ValueError('Overlapping squat repetitions')
    return reps


phases = np.asarray(TEMPLATE['phases'], dtype=float)
assert len(phases) == 99 and np.allclose(phases, np.arange(1, 100) / 100)
template_by_subject = {row['subject']: row for row in TEMPLATE['rows']}
assert len(template_by_subject) == 7 and TEMPLATE['loadKg'] == 0
rows = []
for subject, template in sorted(template_by_subject.items()):
    c3d_paths = sorted((SOURCE / 'c3d' / subject).glob('*squat*.c3d'))
    if len(c3d_paths) != 3:
        raise ValueError(f'Expected three C3Ds for {subject}; found {len(c3d_paths)}')
    with zipfile.ZipFile(SOURCE / f'{subject}_force.zip') as zipped:
        for c3d_path in c3d_paths:
            # EZC3D's Windows binary cannot open this workspace's non-ASCII
            # absolute path; the ASCII relative path works from project root.
            c3d = ezc3d.c3d(c3d_path.relative_to(ROOT).as_posix())
            labels = c3d['parameters']['POINT']['LABELS']['value']
            marker = c3d['data']['points'][:, labels.index('QTMMod_pelvis_sac'), :]
            if c3d['header']['points']['frame_rate'] != RATE or np.any(marker[3] <= 0):
                raise ValueError(f'Invalid pelvis marker or rate: {c3d_path}')
            height_m = marker[2] / 1000
            member = f'{subject}/{c3d_path.stem}.npy'
            force = read_groundlink_npy(zipped.read(member))['GRF']
            missing_tail_frames = len(height_m) - len(force)
            if missing_tail_frames < 0 or missing_tail_frames > 600:
                raise ValueError(f'Unexpected force/marker frame mismatch: {c3d_path}')
            # s007's published processed-force traces omit the C3D tail. The
            # strongest anticorrelation with its raw analog force is at shift
            # zero in all three trials; therefore only the common prefix is
            # retained, with no guessed start-time shift.
            if missing_tail_frames and subject != 's007':
                raise ValueError(f'Only s007 may have a shorter force tail: {c3d_path}')
            height_m = height_m[:len(force)]
            observed_ratio = force[:, :, 2].sum(axis=1) * 1000 / (template['weightKg'] * G)
            prediction_fixed = np.asarray(template['supportRatio'], dtype=float)
            for rep, (start, bottom, end, depth_m) in enumerate(segment_reps(height_m), 1):
                duration = (end - start) / RATE
                observed = np.interp(start + phases * (end - start),
                                     np.arange(len(observed_ratio)), observed_ratio)
                prediction_timed = 1 + (prediction_fixed - 1) * (
                    TEMPLATE['durationS'] / duration) ** 2
                rows.append({
                    'subject': subject, 'trial': c3d_path.stem, 'rep': rep,
                    'forceTailTrimmedFrames': missing_tail_frames,
                    'startS': round(start / RATE, 3), 'bottomS': round(bottom / RATE, 3),
                    'endS': round(end / RATE, 3), 'durationS': round(duration, 3),
                    'pelvisVerticalExcursionM': depth_m,
                    'bottomPhase': round((bottom - start) / (end - start), 3),
                    'medianObservedSupportRatio': round(float(np.median(observed)), 4),
                    'staticMaeRatio': round(float(np.mean(np.abs(observed - 1))), 4),
                    'fixedTemplateMaeRatio': round(float(np.mean(np.abs(observed - prediction_fixed))), 4),
                    'measuredDurationTemplateMaeRatio': round(float(np.mean(np.abs(observed - prediction_timed))), 4),
                })

subjects = []
for subject in sorted(template_by_subject):
    group = [row for row in rows if row['subject'] == subject]
    subjects.append({
        'subject': subject, 'reps': len(group),
        'medianDurationS': round(median(row['durationS'] for row in group), 3),
        'medianBottomPhase': round(median(row['bottomPhase'] for row in group), 3),
        'medianStaticMaeRatio': round(median(row['staticMaeRatio'] for row in group), 4),
        'medianFixedTemplateMaeRatio': round(median(row['fixedTemplateMaeRatio'] for row in group), 4),
        'medianMeasuredDurationTemplateMaeRatio': round(median(row['measuredDurationTemplateMaeRatio'] for row in group), 4),
    })

static = np.asarray([row['medianStaticMaeRatio'] for row in subjects])
fixed = np.asarray([row['medianFixedTemplateMaeRatio'] for row in subjects])
timed = np.asarray([row['medianMeasuredDurationTemplateMaeRatio'] for row in subjects])
rng = np.random.default_rng(42)
samples = rng.integers(0, len(subjects), size=(10000, len(subjects)))
improvement = static - fixed
timed_improvement = static - timed
result = {
    'status': 'independent_lab_optimistic_alignment_not_personal_force_or_muscle_validation',
    'source': 'https://csr.bu.edu/groundlink/',
    'appTemplate': 'src/mechanics.ts squatVerticalSupportScenario, exported without refitting by scripts/export_groundlink_squat_template.mjs',
    'method': f'Three pelvis-sacrum vertical minima per C3D. Start/end at nearest {args.top_fraction:.0%}-of-upright-height crossing around each trough; 101-frame Savitzky-Golay smoothing, >=0.2 m excursion, 0.8-5.5 s. Normalize GRF by paper subject mass times 9.80665; time-warp measured rep to 99 interior phase points. For s007 only, processed force omits a 456–597-frame suffix; raw C3D analog force has strongest anticorrelation at zero shift in all three trials, so the marker suffix is trimmed. One subject is the summary unit.',
    'topFraction': args.top_fraction,
    'summary': {
        'subjects': len(subjects), 'trials': 21, 'reps': len(rows),
        'subjectMedianDurationS': round(median(row['medianDurationS'] for row in subjects), 3),
        'subjectMedianBottomPhase': round(median(row['medianBottomPhase'] for row in subjects), 3),
        'subjectMedianStaticMaeRatio': round(float(np.median(static)), 4),
        'subjectMedianFixedTemplateMaeRatio': round(float(np.median(fixed)), 4),
        'subjectMedianMeasuredDurationTemplateMaeRatio': round(float(np.median(timed)), 4),
        'pairedSubjectMedianFixedImprovementRatio': round(float(np.median(improvement)), 4),
        'pairedSubjectMedianFixedImprovementBootstrap95': [round(float(x), 4) for x in np.quantile(
            np.median(improvement[samples], axis=1), [0.025, 0.975])],
        'subjectsFixedBeatsStatic': int(np.sum(fixed < static)),
        'pairedSubjectMedianMeasuredDurationImprovementRatio': round(float(np.median(timed_improvement)), 4),
        'pairedSubjectMedianMeasuredDurationImprovementBootstrap95': [round(float(x), 4) for x in np.quantile(
            np.median(timed_improvement[samples], axis=1), [0.025, 0.975])],
        'subjectsMeasuredDurationBeatsStatic': int(np.sum(timed < static)),
    },
    'limitations': [
        'Unloaded squats only, seven people from a different laboratory; no loaded barbell, joint moment, muscle activation or muscle-force validation.',
        'Experimental pelvis marker sets start/end boundaries, and the measured-duration diagnostic additionally supplies actual rep duration. Neither is observed by the phone app.',
        'Force and marker data are source-processed; the raw numeric GRF scale is inferred from body-weight support rather than a source field dictionary. A single pelvis marker is a segmentation proxy, not the body center of mass.',
        'The s007 suffix crop is diagnosed by timing correlation; the raw analog force has different scale and sign and is not used as the quantitative target.',
        'The template was developed and inspected on another unloaded dataset before this external comparison, so these data test transfer but not a pre-registered model.',
        'Bootstrap resamples people rather than correlated reps; seven subjects give a wide and uncertain interval.',
    ],
    'subjects': subjects, 'repetitions': rows,
}
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
print(f'Saved {args.out}')
