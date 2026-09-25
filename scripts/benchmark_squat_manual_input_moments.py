"""Held-out-person test of squat net moments using only hand-enterable inputs.

Laboratory repetition boundaries, exact peak knee angle and exact duration are
used to form an optimistic ceiling. No measured per-frame pose enters features.
The output is research evidence, not a personal muscle-force model.
"""

import csv
import json
from pathlib import Path

import numpy as np

from analyze_dynamic_squats import ROOT, load_trial
from benchmark_template_squat_grf import SUBJECTS, measured_repetitions


PHASES = np.arange(1, 100) / 100
TARGETS = ("hip_flexion_r_moment", "knee_angle_r_moment",
           "ankle_angle_r_moment")
LOADS = ("0lbs", "25lbs")
DEPTH_CHOICES = np.array([75.0, 96.0, 117.0])
DURATION_CHOICES = np.array([2.0, 2.8, 4.0])
RIDGE = 11.0  # fixed before testing: one prior-equivalent per training person
OUTPUT = ROOT / "docs/data/squat_manual_input_joint_moment_loso.json"


def rounded(value):
    return round(float(value), 4)


def nearest(value, choices):
    return float(choices[np.argmin(np.abs(choices - value))])


def read_masses():
    path = ROOT / ".cache/lower-limb-raw/Subject_masses.csv"
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {row["Subject"]: float(row["Mass"]) for row in csv.DictReader(handle)}


def repetitions(subject, load, mass):
    trial = load_trial(subject, load)
    time = trial["time"]
    knee = -trial["angle"][:, 1]
    output = []
    for start, peak, end in measured_repetitions(trial, 50, .5):
        duration = float(time[end] - time[start])
        points = time[start] + PHASES * duration
        curves = np.column_stack([np.interp(points, time, trial["moment"][target])
                                  for target in TARGETS])
        output.append({"massKg": mass, "depthDeg": float(knee[peak]),
                       "durationS": duration, "moments": curves})
    return output


def features(row, method):
    mass = (row["massKg"] - 80) / 20
    if method == "mass_only":
        return np.array([mass])
    depth = row["depthDeg"]
    duration = row["durationS"]
    if method == "coarse_manual":
        depth = nearest(depth, DEPTH_CHOICES)
        duration = nearest(duration, DURATION_CHOICES)
    return np.array([mass, (depth - 100) / 20, (duration - 2.8) / 1])


def predict(train, test, method):
    curves = np.asarray([person["curve"] for person in train])
    baseline = np.median(curves, axis=0)
    if method == "phase_median":
        return np.broadcast_to(baseline, (len(test), *baseline.shape))
    x = np.asarray([features(person, method) for person in train])
    z = np.asarray([features(rep, method) for rep in test])
    mean = np.mean(x, axis=0)
    centered = x - mean
    coefficients = np.linalg.solve(
        centered.T @ centered + RIDGE * np.eye(centered.shape[1]),
        centered.T @ (curves - baseline).reshape(len(train), -1))
    return baseline + ((z - mean) @ coefficients).reshape(len(test), *baseline.shape)


def paired_bootstrap(values, seed):
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(5000, len(values)), replace=True)
    return [rounded(x) for x in np.quantile(np.median(samples, axis=1), [.025, .975])]


def main():
    masses = read_masses()
    data = {(subject, load): repetitions(subject, load, masses[subject])
            for subject in SUBJECTS for load in LOADS}
    report = {
        "status": "optimistic_laboratory_manual_input_squat_joint_moment_screen_not_personal_or_muscle_force_validation",
        "source": "Scherpereel et al. 2023, DOI 10.1038/s41597-023-02840-6",
        "protocol": "Separate 0 and 25 lb conditions; hold out one whole person. Every remaining person contributes one median moment curve and one median mass/depth/duration feature vector per condition. Predict each held-out repetition at 99 normalized phases. Ridge 11 on physically scaled input features fixed before evaluation. Source moment N m/kg interpretation is supported by independent IK/ID replay.",
        "models": {
            "phase_median": "training-person median curve; no personal input",
            "mass_only": "mass plus phase, fixed ridge",
            "coarse_manual": "mass plus nearest phone depth (75/96/117 degrees) and duration (2/2.8/4 seconds), fixed ridge",
            "exact_oracle": "mass plus exact laboratory peak depth and repetition duration, fixed ridge; optimistic bound",
        },
        "limitations": [
            "The exact repetition boundaries and phase alignment come from laboratory knee angles; the phone does not observe them.",
            "Depth and duration choices are selected from laboratory truth, while actual user entries may be inaccurate.",
            "The 25-lb object's placement is unspecified and is not validated as a back barbell.",
            "Only 12 people and one protocol; models were designed after earlier inspection of this dataset.",
            "Inverse-dynamics net joint moments do not identify individual muscle forces or activation.",
        ],
        "loads": {},
    }
    methods = tuple(report["models"])
    for load in LOADS:
        participants = {subject: data[subject, load] for subject in SUBJECTS}
        if any(not reps for reps in participants.values()):
            raise ValueError(f"Missing complete {load} repetitions")
        results = []
        for subject in SUBJECTS:
            train = []
            for other in SUBJECTS:
                if other == subject:
                    continue
                reps = participants[other]
                train.append({
                    "curve": np.median([rep["moments"] for rep in reps], axis=0),
                    "massKg": masses[other],
                    "depthDeg": float(np.median([rep["depthDeg"] for rep in reps])),
                    "durationS": float(np.median([rep["durationS"] for rep in reps])),
                })
            held = participants[subject]
            true = np.asarray([rep["moments"] for rep in held])
            errors = {}
            for method in methods:
                estimate = predict(train, held, method)
                errors[method] = [rounded(np.mean(np.abs(estimate[:, :, col] - true[:, :, col])))
                                  for col in range(len(TARGETS))]
            results.append({
                "subject": subject, "repetitions": len(held),
                "medianDepthDeg": rounded(np.median([rep["depthDeg"] for rep in held])),
                "medianDurationS": rounded(np.median([rep["durationS"] for rep in held])),
                "maeNmPerKg": {target: {method: errors[method][col] for method in methods}
                               for col, target in enumerate(TARGETS)},
            })
        summary = {}
        for target in TARGETS:
            baseline = np.array([row["maeNmPerKg"][target]["phase_median"]
                                 for row in results])
            target_summary = {"phaseMedianSubjectMae": rounded(np.median(baseline))}
            for method in methods[1:]:
                errors = np.array([row["maeNmPerKg"][target][method] for row in results])
                improvement = baseline - errors
                target_summary[method] = {
                    "subjectMedianMaeNmPerKg": rounded(np.median(errors)),
                    "subjectsBeatingPhaseMedian": int(np.sum(improvement > 0)),
                    "pairedMedianImprovementNmPerKg": rounded(np.median(improvement)),
                    "pairedMedianImprovementBootstrap95": paired_bootstrap(
                        improvement, 20260925 + len(target) + len(method) + len(load)),
                }
            summary[target] = target_summary
        report["loads"][load] = {"subjects": len(SUBJECTS),
                                 "repetitions": sum(len(reps) for reps in participants.values()),
                                 "summary": summary, "heldOutPeople": results}
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for load, data in report["loads"].items():
        print(load, data["subjects"], "people", data["repetitions"], "reps")
        for target, row in data["summary"].items():
            print(target, "baseline", row["phaseMedianSubjectMae"],
                  *(f"{method}={row[method]['subjectMedianMaeNmPerKg']}"
                    for method in methods[1:]))
    print(OUTPUT)


if __name__ == "__main__":
    main()
