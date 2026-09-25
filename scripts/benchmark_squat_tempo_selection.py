"""Leave-one-person-out audit of selecting among three preset squat tempos.

Input files are the same 0-lb laboratory repetitions evaluated independently
at 2, 2.8, and 4 seconds. Selection uses only the other subjects' errors.
This is an internal sensitivity check, not a validation for a phone user.
"""

import json
from collections import Counter
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    2.0: ROOT / '.cache/lower-limb/template_grf_2s_benchmark.json',
    2.8: ROOT / 'docs/data/squat_template_grf_benchmark.json',
    4.0: ROOT / '.cache/lower-limb/template_grf_4s_benchmark.json',
}
OUTPUT = ROOT / 'docs/data/squat_tempo_loso_benchmark.json'
data = {tempo: json.loads(path.read_text(encoding='utf-8')) for tempo, path in SOURCES.items()}
subjects = [row['subject'] for row in data[2.8]['subjects']]
assert len(subjects) == 12 and len(set(subjects)) == 12
for tempo, result in data.items():
    assert result['viewerDefaultDurationS'] == tempo
    assert [row['subject'] for row in result['subjects']] == subjects
    assert [(row['subject'], row['rep'], row['startS'], row['endS'])
            for row in result['repetitions']] == [
                (row['subject'], row['rep'], row['startS'], row['endS'])
                for row in data[2.8]['repetitions']]

by_tempo = {tempo: {row['subject']: row for row in result['subjects']}
            for tempo, result in data.items()}
rows = []
for held_out in subjects:
    training = [subject for subject in subjects if subject != held_out]
    training_median_error = {
        tempo: median(by_tempo[tempo][subject]['medianFixedTemplateMaeRatio']
                      for subject in training)
        for tempo in SOURCES
    }
    selected = min(SOURCES, key=lambda tempo: (training_median_error[tempo], tempo))
    observed = by_tempo[2.8][held_out]
    rows.append({
        'subject': held_out,
        'selectedTempoS': selected,
        'selectedMaeRatio': by_tempo[selected][held_out]['medianFixedTemplateMaeRatio'],
        'default28sMaeRatio': observed['medianFixedTemplateMaeRatio'],
        'staticMaeRatio': observed['medianStaticMaeRatio'],
        'trainingMedianErrorByTempo': {str(tempo): round(value, 4)
                                       for tempo, value in training_median_error.items()},
    })

summary = {
    'subjects': len(rows),
    'reps': len(data[2.8]['repetitions']),
    'selectedTempoCounts': {str(tempo): Counter(row['selectedTempoS'] for row in rows)[tempo]
                            for tempo in SOURCES},
    'heldOutMedianStaticMaeRatio': round(median(row['staticMaeRatio'] for row in rows), 4),
    'heldOutMedianDefault28sMaeRatio': round(median(row['default28sMaeRatio'] for row in rows), 4),
    'heldOutMedianSelectedMaeRatio': round(median(row['selectedMaeRatio'] for row in rows), 4),
    'selectedBeatsStaticSubjects': sum(row['selectedMaeRatio'] < row['staticMaeRatio'] for row in rows),
    'selectedBeatsDefaultSubjects': sum(row['selectedMaeRatio'] < row['default28sMaeRatio'] for row in rows),
}
result = {
    'status': 'internal_leave_one_subject_out_tempo_sensitivity_not_personal_validation',
    'method': 'For each held-out subject, choose the template duration with the lowest median subject-level force-plate MAE among the remaining 11; evaluate the chosen duration on the held-out subject. Repetitions and lab time alignment are identical across durations.',
    'limitations': [
        'All three duration candidates were inspected on this dataset before the leave-one-subject-out analysis; this is not an external validation cohort.',
        'The app does not observe the user\'s true rep duration, motion, bar position, or foot forces.',
        'Only unloaded squats were tested; no joint moments, single-muscle forces, or other exercises were validated.',
    ],
    'summary': summary,
    'subjects': rows,
}
OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
print(f'Saved {OUTPUT}')
