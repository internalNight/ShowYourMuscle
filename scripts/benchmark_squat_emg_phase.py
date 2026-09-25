"""Leave-one-person-out test of a squat-phase surface-EMG colour prior.

This tests the *shape* of electrical activity across a repetition, not its
absolute amplitude or muscle force. The held-out person's own median envelope
is used solely to put the observed curve on a comparable scale; the phone
cannot observe that scale from body measurements or lifting records.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from analyze_dynamic_squat_emg import CHANNELS, emg_envelopes
from analyze_dynamic_squats import ROOT, load_trial
from benchmark_template_squat_grf import SUBJECTS, measured_repetitions


PHASES = np.arange(1, 100) / 100
OUTPUT = ROOT / "docs/data/squat_emg_phase_loso.json"


def subject_curve(subject, load):
    trial = load_trial(subject, load)
    reps = measured_repetitions(trial, 50, 0.5)
    if not reps:
        return None
    envelopes = emg_envelopes(subject, load, trial["time"], 100)
    result = {}
    for side in ("R", "L"):
        for muscle in CHANNELS:
            name = side + muscle
            curves = []
            for start, _, end in reps:
                t = trial["time"]
                curves.append(np.interp(t[start] + PHASES * (t[end] - t[start]),
                                        t, envelopes[name]))
            curve = np.median(curves, axis=0)
            scale = np.median(curve)
            if not np.isfinite(scale) or scale <= 0:
                raise ValueError(f"Invalid EMG envelope scale: {subject} {load} {name}")
            result[name] = curve / scale
    return {"reps": len(reps), "channels": result}


def evaluate(subjects):
    channels = next(iter(subjects.values()))["channels"]
    rows = []
    for person, target in subjects.items():
        training = [item["channels"] for other, item in subjects.items()
                    if other != person]
        for channel in channels:
            prediction = np.median([item[channel] for item in training], axis=0)
            prediction /= np.median(prediction)
            observed = target["channels"][channel]
            static_mae = np.mean(np.abs(observed - 1))
            template_mae = np.mean(np.abs(observed - prediction))
            correlation = spearmanr(observed, prediction).statistic
            rows.append({"subject": person, "channel": channel,
                         "reps": target["reps"],
                         "staticMae": round(float(static_mae), 4),
                         "templateMae": round(float(template_mae), 4),
                         "improvement": round(float(static_mae - template_mae), 4),
                         "phaseSpearman": round(float(correlation), 4),
                         "observedPhaseRange": [round(float(np.min(observed)), 3),
                                                round(float(np.max(observed)), 3)]})
    summary = {}
    for channel in channels:
        subset = [row for row in rows if row["channel"] == channel]
        improvement = np.asarray([row["improvement"] for row in subset])
        summary[channel] = {
            "subjects": len(subset),
            "medianStaticMae": round(float(np.median([r["staticMae"] for r in subset])), 4),
            "medianTemplateMae": round(float(np.median([r["templateMae"] for r in subset])), 4),
            "medianPairedImprovement": round(float(np.median(improvement)), 4),
            "subjectsTemplateBeatsStatic": int(np.sum(improvement > 0)),
            "medianPhaseSpearman": round(float(np.median([r["phaseSpearman"] for r in subset])), 4),
        }
    return rows, summary


def group_shape(subjects):
    """Descriptive curves only; the LOSO scores above do not use these curves."""
    shape = {}
    for channel in ("RRF", "RVL", "RBF"):
        curves = np.asarray([item["channels"][channel] for item in subjects.values()])
        shape[channel] = {
            "p25": [round(float(x), 3) for x in np.quantile(curves, 0.25, axis=0)],
            "median": [round(float(x), 3) for x in np.median(curves, axis=0)],
            "p75": [round(float(x), 3) for x in np.quantile(curves, 0.75, axis=0)],
        }
    return shape


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    reports = {}
    for load in ("0lbs", "25lbs"):
        subjects = {subject: curve for subject in SUBJECTS
                    if (curve := subject_curve(subject, load)) is not None}
        if len(subjects) < 3:
            raise ValueError(f"Too few complete repetitions for LOSO: {load}")
        rows, summary = evaluate(subjects)
        reports[load] = {
            "participants": list(subjects),
            "repetitions": {name: item["reps"] for name, item in subjects.items()},
            "summary": summary,
            "descriptiveGroupShape": group_shape(subjects),
            "heldOutResults": rows,
        }
    report = {
        "source": "Scherpereel et al. (2023), synchronized squat surface EMG and knee kinematics",
        "status": "research_only_no_personal_muscle_force_or_activation_prediction",
        "protocol": "12 candidate participants, 0 and 25 lb squat trials evaluated separately; one participant is held out at a time. Complete repetitions use the existing knee-flexion segmentation gate. Each repetition is resampled to 99 interior phase points. A participant's median repetition curve is divided by its own temporal median. The training participants' normalized curves are pooled by phasewise median; the held-out person's data never enter the template. Static baseline is a flat normalized value of 1. MAE and Spearman are across 99 phase points, summarized across participants.",
        "signalProcessing": "4th-order zero-phase Butterworth 20-450 Hz bandpass, centered 100 ms RMS envelope; 2000-Hz to 200-Hz interpolation",
        "caveats": [
            "Normalization uses the held-out participant's measured EMG. It makes waveform shapes comparable only; the phone has no way to know absolute EMG amplitude from anthropometrics or gym records.",
            "Surface EMG is electrical activity, not muscle activation, recruitment, mechanical tension, or force. Electrode placement, tissue thickness, crosstalk, and fatigue are not controlled here.",
            "0 and 25 lb are source protocol labels; placement of the extra 25 lb is not documented, so this does not validate a barbell back squat.",
            "Repetition boundaries and duration come from experimental knee kinematics; the phone's prescribed animation does not know an individual user's actual motion.",
            "The flat baseline uses the held-out person's own median amplitude, making it an intentionally strong baseline for shape prediction.",
        ],
        "loads": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    for load, section in reports.items():
        print(load, len(section["participants"]),
              sum(section["repetitions"].values()), "repetitions")
        for channel in ("RRF", "RVL", "RGMAX", "RBF", "RGMED"):
            print(channel, section["summary"][channel])
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
