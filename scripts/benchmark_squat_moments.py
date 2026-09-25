"""Leave-one-person-out benchmark for squat joint-moment prediction.

Uses only body mass, nominal carried load, phase and joint kinematics as
features. The richer variant uses measured lab angles and speed, so its
performance is an optimistic bound for a phone preset with no video input.
CSV moment units are supported as N m/kg by an independent IK/ID replay.
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from analyze_dynamic_squats import ROOT, load_trial, match_phase, ANGLE_LIMITS_DEG


SUBJECTS = ("AB01", "AB02", "AB03", "AB05", "AB06", "AB07", "AB08",
            "AB09", "AB10", "AB11", "AB12", "AB13")
PHASES = ("descent", "ascent")
TARGETS = ("hip_flexion_r_moment", "knee_angle_r_moment")


def load_masses():
    path = ROOT / ".cache/lower-limb-raw/Subject_masses.csv"
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {row["Subject"]: float(row["Mass"]) for row in csv.DictReader(handle)}


def select_frames(trial, phase, maximum=100):
    eligible = np.flatnonzero(trial["valid"] & (trial["phase"] == phase))
    if len(eligible) <= maximum:
        return eligible
    return eligible[np.linspace(0, len(eligible) - 1, maximum).astype(int)]


def features(trial, indices, mass, load, phase, rich):
    angle = trial["angle"][indices]
    knee = -angle[:, 1] / 90
    x = [np.ones(len(indices)), knee, knee * knee,
         np.full(len(indices), mass / 80),
         np.full(len(indices), load),
         knee * load, np.full(len(indices), phase == "ascent")]
    if rich:
        hip = angle[:, 0] / 90
        ankle = angle[:, 2] / 45
        speed = np.abs(trial["speed"][indices]) / 100
        left_knee = -angle[:, 4] / 90
        x += [hip, hip * hip, ankle, speed, left_knee,
              angle[:, 3] / 90, angle[:, 5] / 45,
              hip * load, speed * load, knee * hip]
    return np.column_stack(x)


def fit_predict(train_x, train_y, test_x, penalty=10):
    # Fixed physical scaling above; center only non-intercept columns using
    # training people, never the held-out subject.
    mean = train_x[:, 1:].mean(axis=0)
    scale = train_x[:, 1:].std(axis=0)
    scale[scale < 0.05] = 1
    x = np.column_stack((np.ones(len(train_x)), (train_x[:, 1:] - mean) / scale))
    z = np.column_stack((np.ones(len(test_x)), (test_x[:, 1:] - mean) / scale))
    identity = np.eye(x.shape[1]) * penalty
    identity[0, 0] = 0
    coef = np.linalg.solve(x.T @ x + identity, x.T @ train_y)
    return z @ coef


def rounded(x):
    return round(float(x), 4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/data/dynamic_squat_loso_benchmark.json")
    args = parser.parse_args()
    masses = load_masses()
    trials = {(s, load): load_trial(s, load) for s in SUBJECTS
              for load in ("0lbs", "25lbs")}
    records = {}
    for subject in SUBJECTS:
        pieces = []
        for load in ("0lbs", "25lbs"):
            for phase in PHASES:
                trial = trials[subject, load]
                indices = select_frames(trial, phase)
                if not len(indices):
                    continue
                pieces.append({
                    "trial": trial, "indices": indices, "load": int(load == "25lbs"),
                    "phase": phase,
                    "simple": features(trial, indices, masses[subject],
                                       int(load == "25lbs"), phase, False),
                    "rich": features(trial, indices, masses[subject],
                                     int(load == "25lbs"), phase, True),
                    "target": np.column_stack([trial["moment"][k][indices]
                                               for k in TARGETS]),
                })
        records[subject] = pieces

    report = {
        "source": "Scherpereel et al. 2023, DOI 10.1038/s41597-023-02840-6",
        "moment_unit": "N m/kg strongly supported by independent OpenSim IK/ID replay; raw CSV values used without mass conversion",
        "protocol": "Leave one entire subject out; both 0/25-lb trials of that subject excluded from training. Maximum 100 evenly spaced eligible frames per subject/trial/phase. Both knees 45-130 deg, activity flags 1, speed >=20 deg/s. Ridge penalty 10 in training-standardized feature space.",
        "simple_inputs": "mass, carried load, measured right knee flexion, descent/ascent",
        "rich_inputs": "simple plus measured bilateral hip/knee/ankle angles and right knee angular speed; optimistic bound because phone app has preset rather than measured motion",
        "targets": list(TARGETS),
        "subjects": {},
    }
    all_errors = {model: {target: [] for target in TARGETS}
                  for model in ("phase_load_baseline", "simple", "rich")}
    all_truth = {target: [] for target in TARGETS}
    for subject in SUBJECTS:
        train = [part for other in SUBJECTS if other != subject
                 for part in records[other]]
        held = records[subject]
        train_y = np.concatenate([p["target"] for p in train])
        test_y = np.concatenate([p["target"] for p in held])
        predictions = {}
        for model in ("simple", "rich"):
            predictions[model] = fit_predict(
                np.concatenate([p[model] for p in train]), train_y,
                np.concatenate([p[model] for p in held]))
        # A properly trained, very simple reference: mean for each condition.
        baseline = []
        for part in held:
            condition_y = np.concatenate([p["target"] for p in train
                                          if p["load"] == part["load"]
                                          and p["phase"] == part["phase"]])
            baseline.append(np.tile(condition_y.mean(axis=0),
                                    (len(part["indices"]), 1)))
        predictions["phase_load_baseline"] = np.concatenate(baseline)
        subject_report = {"frames": len(test_y), "by_target": {},
                          "matched_load_changes": {}}
        for col, target in enumerate(TARGETS):
            truth = test_y[:, col]
            all_truth[target].extend(truth.tolist())
            target_result = {}
            for model, pred in predictions.items():
                residual = pred[:, col] - truth
                all_errors[model][target].extend(residual.tolist())
                target_result[model] = {
                    "mae": rounded(np.mean(np.abs(residual))),
                    "bias": rounded(np.mean(residual)),
                    "p90_abs_error": rounded(np.percentile(np.abs(residual), 90)),
                }
            subject_report["by_target"][target] = target_result
        for phase in PHASES:
            unloaded, loaded = trials[subject, "0lbs"], trials[subject, "25lbs"]
            reference, query, _, query_count, _, _ = match_phase(
                unloaded, loaded, phase, ANGLE_LIMITS_DEG, 50)
            if len(query) < 30 or len(query) / max(1, query_count) < 0.2:
                continue
            change = {"matched_frames": len(query), "targets": {}}
            for col, target in enumerate(TARGETS):
                actual = loaded["moment"][target][query] - unloaded["moment"][target][reference]
                row = {"observed_median": rounded(np.median(actual))}
                for model in ("simple", "rich"):
                    train_x = np.concatenate([p[model] for p in train])
                    x_loaded = features(loaded, query, masses[subject], 1, phase,
                                        model == "rich")
                    x_unloaded = features(loaded, query, masses[subject], 0, phase,
                                          model == "rich")
                    prediction = fit_predict(train_x, train_y,
                                             np.concatenate((x_loaded, x_unloaded)))
                    estimated = prediction[:len(query), col] - prediction[len(query):, col]
                    row[f"{model}_median"] = rounded(np.median(estimated))
                change["targets"][target] = row
            subject_report["matched_load_changes"][phase] = change
        report["subjects"][subject] = subject_report

    report["summary"] = {}
    for target in TARGETS:
        truth = np.array(all_truth[target])
        target_result = {"frames": len(truth), "subject_count": len(SUBJECTS),
                         "target_iqr": rounded(np.subtract(*np.percentile(truth, [75, 25])))}
        for model in all_errors:
            error = np.array(all_errors[model][target])
            per_subject_mae = [report["subjects"][s]["by_target"][target][model]["mae"]
                               for s in SUBJECTS]
            target_result[model] = {
                "median_subject_mae": rounded(np.median(per_subject_mae)),
                "mean_subject_mae": rounded(np.mean(per_subject_mae)),
                "pooled_mae": rounded(np.mean(np.abs(error))),
                "pooled_p90_abs_error": rounded(np.percentile(np.abs(error), 90)),
                "pooled_r2": rounded(1 - np.sum(error ** 2) /
                                     np.sum((truth - truth.mean()) ** 2)),
                "subjects_beating_baseline": sum(
                    report["subjects"][s]["by_target"][target][model]["mae"] <
                    report["subjects"][s]["by_target"][target]["phase_load_baseline"]["mae"]
                    for s in SUBJECTS) if model != "phase_load_baseline" else None,
            }
        report["summary"][target] = target_result
    report["matched_load_change_summary"] = {}
    for phase in PHASES:
        report["matched_load_change_summary"][phase] = {}
        for target in TARGETS:
            subjects = [s for s in SUBJECTS if phase in report["subjects"][s]["matched_load_changes"]]
            actual = np.array([report["subjects"][s]["matched_load_changes"][phase]
                               ["targets"][target]["observed_median"] for s in subjects])
            row = {"subjects": subjects, "observed_subjects_positive": int(np.sum(actual > 0)),
                   "observed_subjects_negative": int(np.sum(actual < 0))}
            for model in ("simple", "rich"):
                prediction = np.array([report["subjects"][s]["matched_load_changes"][phase]
                                       ["targets"][target][f"{model}_median"] for s in subjects])
                row[model] = {
                    "direction_correct": int(np.sum(np.sign(prediction) == np.sign(actual))),
                    "median_subject_abs_change_error": rounded(np.median(np.abs(prediction - actual))),
                    "predicted_subjects_positive": int(np.sum(prediction > 0)),
                    "predicted_subjects_negative": int(np.sum(prediction < 0)),
                }
            report["matched_load_change_summary"][phase][target] = row
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({"moment_prediction": report["summary"],
                      "load_change": report["matched_load_change_summary"]}, indent=2))


if __name__ == "__main__":
    main()
