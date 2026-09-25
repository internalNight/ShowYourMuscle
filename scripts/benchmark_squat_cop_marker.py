"""Evaluate whether a phase-only foot-axis COP template transfers across people.

The target uses experimental force plates and original foot markers. Marker
ankle midpoints are proxies, not OpenSim joint centers. Results stay in research
files and must not be used as personal ankle or muscle-force predictions.
"""

import argparse
import csv
import json
from math import comb
from pathlib import Path

import numpy as np

from analyze_dynamic_squats import ROOT, load_trial
from benchmark_template_squat_grf import G, SUBJECTS, measured_repetitions


RAW = ROOT / ".cache/lower-limb-raw"
PHASES = np.arange(1, 100) / 100


def read_foot_markers(path: Path):
    with path.open(encoding="utf-8") as handle:
        handle.readline()
        handle.readline()
        metadata = handle.readline().split("\t")
        names = handle.readline().split("\t")
    assert metadata[4] == "mm", (path, metadata[:5])
    lookup = {name: 2 + 3 * (i - 2) for i, name in enumerate(names) if name}
    required = ("RANK", "RMANK", "RMT1", "RMT5", "RCAL",
                "LANK", "LMANK", "LMT1", "LMT5", "LCAL")
    assert all(name in lookup for name in required), path
    columns = [1] + [lookup[name] + axis for name in required for axis in (0, 2)]
    table = np.loadtxt(path, delimiter="\t", skiprows=5, usecols=columns)
    time = table[:, 0]
    assert np.all(np.diff(time) > 0), path
    coords = {name: table[:, 1 + 2 * i:3 + 2 * i] / 1000
              for i, name in enumerate(required)}
    return time, coords


def interpolate_valid(query, time, values):
    valid = np.isfinite(values)
    if valid.sum() < 2:
        return np.full(len(query), np.nan)
    return np.interp(query, time[valid], values[valid], left=np.nan, right=np.nan)


def sample_foot(query, time, markers, side):
    sampled = {name: np.column_stack([
        interpolate_valid(query, time, markers[name][:, axis]) for axis in (0, 1)])
        for name in (f"{side}ANK", f"{side}MANK", f"{side}MT1", f"{side}MT5", f"{side}CAL")}
    ankle = (sampled[f"{side}ANK"] + sampled[f"{side}MANK"]) / 2
    toe = (sampled[f"{side}MT1"] + sampled[f"{side}MT5"]) / 2
    heel = sampled[f"{side}CAL"]
    length = np.linalg.norm(toe - heel, axis=1)
    axis = (toe - heel) / length[:, None]
    return ankle, axis, length


def read_masses():
    with (RAW / "Subject_masses.csv").open(newline="", encoding="utf-8-sig") as handle:
        return {row["Subject"]: float(row["Mass"]) for row in csv.DictReader(handle)}


def collect(subjects, masses, load="0lbs"):
    rows = []
    excluded = []
    for subject in subjects:
        trial_name = "squats_2" if subject == "AB05" and load == "0lbs" else "squats_1"
        marker_time, markers = read_foot_markers(
            RAW / subject / "MarkerData" / f"{trial_name}.trc")
        trial = load_trial(subject, load)
        time, grf = trial["time"], trial["grf"]
        for rep, (start, _bottom, end) in enumerate(measured_repetitions(trial, 50, 0.5), 1):
            query = time[start] + PHASES * float(time[end] - time[start])
            for side, prefix in (("R", "R"), ("L", "L")):
                ankle, axis, length = sample_foot(query, marker_time, markers, side)
                cop = np.column_stack((
                    np.interp(query, time, grf[f"{prefix}COPX"]),
                    np.interp(query, time, grf[f"{prefix}COPZ"]),
                ))
                other_side = "L" if side == "R" else "R"
                other_ankle, _, _ = sample_foot(query, marker_time, markers,
                                                 other_side)
                if np.mean(np.linalg.norm(cop - ankle, axis=1) <
                           np.linalg.norm(cop - other_ankle, axis=1)) < 0.9:
                    raise ValueError(f"Force-plate foot order does not match markers: "
                                     f"{subject} {load} rep {rep} {side}")
                force = np.interp(query, time, grf[f"{prefix}ForceY_Vertical"])
                forward_cm = np.sum((cop - ankle) * axis, axis=1) * 100
                valid = ((force >= 0.1 * masses[subject] * G) &
                         np.isfinite(forward_cm) & (length >= 0.12) &
                         (length <= 0.4) & (forward_cm >= -10) &
                         (forward_cm <= length * 100 + 10))
                if valid.sum() < 80:
                    excluded.append({"subject": subject, "rep": rep, "side": side,
                                     "validPhases": int(valid.sum())})
                    continue
                rows.append({"subject": subject, "rep": rep, "side": side,
                             "timeS": [float(time[start]), float(time[end])],
                             "validPhases": int(valid.sum()),
                             "footLengthCm": float(np.nanmedian(length) * 100),
                             "copForwardCm": forward_cm.tolist(),
                             "valid": valid.tolist()})
    return rows, excluded


def subject_curves(rows, subjects):
    curves = {}
    for subject in subjects:
        sample = [np.where(row["valid"], row["copForwardCm"], np.nan)
                  for row in rows if row["subject"] == subject]
        if not sample:
            raise ValueError(f"No valid trajectories for {subject}")
        curves[subject] = np.nanmedian(np.asarray(sample), axis=0)
        if np.any(~np.isfinite(curves[subject])):
            raise ValueError(f"Subject has a phase with no valid COP: {subject}")
    return curves


def mae_for_subject(rows, subject, prediction):
    errors = []
    for row in rows:
        if row["subject"] == subject:
            observed = np.asarray(row["copForwardCm"])
            valid = np.asarray(row["valid"])
            errors.extend(np.abs(observed[valid] - prediction[valid]))
    return float(np.mean(errors))


def evaluate(rows, subjects, masses):
    if len(subjects) < 3:
        return {"note": "At least three people are required for leave-one-person-out evaluation"}
    curves = subject_curves(rows, subjects)
    results = []
    for held_out in subjects:
        train = [subject for subject in subjects if subject != held_out]
        matrix = np.asarray([curves[subject] for subject in train])
        flat_cm = float(np.median(matrix))
        phase_cm = np.median(matrix, axis=0)
        train_mass = np.asarray([masses[subject] for subject in train])
        mass_center = float(np.mean(train_mass))
        centered_mass = train_mass - mass_center
        ridge = len(train) * 20.0 ** 2
        phase_slope = np.sum(centered_mass[:, None] * (matrix - phase_cm), axis=0) / (
            np.sum(centered_mass ** 2) + ridge)
        mass_phase_cm = phase_cm + phase_slope * (masses[held_out] - mass_center)
        scores = {
            "flatTrainMedianCm": mae_for_subject(rows, held_out,
                                                  np.full(len(PHASES), flat_cm)),
            "phaseTrainMedianCm": mae_for_subject(rows, held_out, phase_cm),
            "phaseAndBodyMassCm": mae_for_subject(rows, held_out, mass_phase_cm),
            "fixed6cmExploratory": mae_for_subject(rows, held_out,
                                                    np.full(len(PHASES), 6.0)),
        }
        results.append({"subject": held_out, "massKg": masses[held_out],
                        "trainingFlatCm": round(flat_cm, 3),
                        "maeCm": {key: round(value, 4) for key, value in scores.items()},
                        "phaseMinusFlatImprovementCm": round(
                            scores["flatTrainMedianCm"] - scores["phaseTrainMedianCm"], 4)})
    def cross_summary(key):
        return round(float(np.median([row["maeCm"][key] for row in results])), 4)
    improvements = np.asarray([row["phaseMinusFlatImprovementCm"] for row in results])
    rng = np.random.default_rng(20260925)
    boot = np.median(rng.choice(improvements, size=(5000, len(subjects)), replace=True), axis=1)
    wins = int(np.sum(improvements > 0))
    p_one_sided = sum(comb(len(subjects), k) for k in range(wins, len(subjects) + 1)) / 2 ** len(subjects)
    return {
        "method": "Whole-person leave-one-out. Within each training person, take the per-phase median across both feet and all repetitions; across the other people, compare the overall constant median with per-phase medians. A body-mass slope is fitted per phase with fixed ridge n*(20 kg)^2. Score every held-out repetition/foot/valid phase, then summarize one MAE per held-out person.",
        "subjects": len(subjects), "trajectories": len(rows),
        "medianSubjectMaeCm": {key: cross_summary(key) for key in
                               ("flatTrainMedianCm", "phaseTrainMedianCm",
                                "phaseAndBodyMassCm", "fixed6cmExploratory")},
        "phaseBetterThanFlatSubjects": wins,
        "phaseImprovementMedianCm": round(float(np.median(improvements)), 4),
        "phaseImprovementBootstrap95Cm": [round(float(value), 4) for value in
                                           np.percentile(boot, [2.5, 97.5])],
        "phaseWinsOneSidedSignP": round(p_one_sided, 5),
        "perSubject": results,
        "allPersonPhaseMedianCm": np.median(np.asarray(list(curves.values())), axis=0).round(4).tolist(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", nargs="+", default=SUBJECTS)
    parser.add_argument("--load", choices=("0lbs", "25lbs"), default="0lbs")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs/data/squat_marker_cop_phase_loso.json")
    args = parser.parse_args()
    masses = read_masses()
    rows, excluded = collect(args.subjects, masses, args.load)
    by_subject = {}
    for subject in args.subjects:
        subset = [row for row in rows if row["subject"] == subject]
        if not subset:
            continue
        pooled = np.concatenate([np.asarray(row["copForwardCm"])[row["valid"]]
                                 for row in subset])
        by_subject[subject] = {
            "trajectories": len(subset),
            "copFromMarkerAnkleMedianCm": round(float(np.median(pooled)), 2),
            "copFromMarkerAnkleP05Cm": round(float(np.percentile(pooled, 5)), 2),
            "copFromMarkerAnkleP95Cm": round(float(np.percentile(pooled, 95)), 2),
            "markerFootLengthMedianCm": round(float(np.median(
                [row["footLengthCm"] for row in subset])), 2),
        }
    result = {"status": "marker_based_cop_lopo_not_phone_or_muscle_force_validation",
              "load": args.load, "target": "Sagittal force-plate COP relative to midpoint of medial/lateral ankle markers, projected onto heel-to-metatarsal marker axis, centimetres. Both feet loaded >=10% body weight. Experimental knee-angle event boundaries provide the 99-point phase; the phone does not observe these events.",
              "limitations": ["Ankle marker midpoint is not the OpenSim ankle joint centre.",
                              "Heel and metatarsal marker locations are skin-mounted proxies, not measured anatomical joint axes.",
                              "The source 25-lb load placement is unknown and cannot validate barbell back squats.",
                              "COP alone is not a net joint moment; horizontal forces, body inertia and all joint kinematics remain required.",
                              "Even correct joint moment prediction does not identify individual muscle force."],
              "quality": by_subject, "excluded": excluded,
              "leaveOnePersonOut": evaluate(rows, args.subjects, masses)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({"load": args.load, "excluded": excluded,
                      "summary": {key: value for key, value in
                                  result["leaveOnePersonOut"].items()
                                  if key not in ("perSubject", "allPersonPhaseMedianCm")}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
