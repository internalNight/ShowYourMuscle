"""Audit angle-matched 0/25 lb squat recordings from Scherpereel et al.

The source ZIP is accessed by inspect_second_skin.py --archive lower-limb.
This script reads only extracted local CSVs; it never trains or validates
muscle-force predictions. Source model IK/ID replay now strongly supports
N m/kg despite the conflicting README; see dynamic squat research notes.
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks, savgol_filter
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "lower-limb"
ANGLE_NAMES = (
    "hip_flexion_r", "knee_angle_r", "ankle_angle_r",
    "hip_flexion_l", "knee_angle_l", "ankle_angle_l",
)
ANGLE_LIMITS_DEG = np.array([5, 4, 5, 5, 4, 5])
TRIAL_OVERRIDES = {("AB05", "0lbs"): "squats_2_0lbs"}


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError(f"Empty CSV: {path}")
    return {name: np.array([float(row[name]) for row in rows])
            for name in reader.fieldnames}


def load_trial(subject, load):
    trial = TRIAL_OVERRIDES.get((subject, load), f"squats_1_{load}")
    stem = f"{subject}_{trial}"
    folder = CACHE / subject / trial
    tables = {kind: read_csv(folder / f"{stem}_{kind}.csv")
              for kind in ("angle", "moment_filt", "grf", "activity_flag")}
    angles, moments, grf, flags = (tables[k] for k in
                                   ("angle", "moment_filt", "grf", "activity_flag"))
    time = angles["time"]
    for kind, table in tables.items():
        if len(table["time"]) != len(time) or not np.allclose(
                table["time"], time, atol=1e-6, rtol=0):
            raise ValueError(f"200 Hz time grid mismatch in {subject} {load} {kind}")
    dt = float(np.median(np.diff(time)))
    if not np.isclose(dt, 0.005, atol=1e-5):
        raise ValueError(f"Unexpected sample interval: {dt}")
    knee_flexion = -angles["knee_angle_r"]
    knee_speed = savgol_filter(knee_flexion, 41, 3, deriv=1, delta=dt)
    phase = np.where(knee_speed >= 20, "descent",
                     np.where(knee_speed <= -20, "ascent", "turnaround"))
    angle_matrix = np.column_stack([angles[name] for name in ANGLE_NAMES])
    both_knees = -angle_matrix[:, [1, 4]]
    valid = ((both_knees.min(axis=1) >= 45)
             & (both_knees.max(axis=1) <= 130)
             & (flags["left"] == 1) & (flags["right"] == 1)
             & (phase != "turnaround"))
    peaks, _ = find_peaks(knee_flexion, height=45, prominence=30,
                          distance=int(1 / dt))
    return {
        "time": time, "angle": angle_matrix, "speed": knee_speed,
        "phase": phase, "valid": valid, "moment": moments, "grf": grf,
        "task_active": (flags["left"] == 1) & (flags["right"] == 1),
        "deep_knee_peaks_seconds": [round(float(time[i] - time[0]), 3) for i in peaks],
    }


def describe_difference(values):
    return {"median": round(float(np.median(values)), 4),
            "p25": round(float(np.percentile(values, 25)), 4),
            "p75": round(float(np.percentile(values, 75)), 4)}


def match_phase(unloaded, loaded, phase, angle_limits, speed_limit):
    reference = np.flatnonzero(unloaded["valid"] & (unloaded["phase"] == phase))
    query = np.flatnonzero(loaded["valid"] & (loaded["phase"] == phase))
    if len(reference) == 0 or len(query) == 0:
        return reference[:0], query[:0], len(reference), len(query), None, None

    def features(trial, indices):
        return np.column_stack((trial["angle"][indices] / 10,
                                trial["speed"][indices] / 40))

    _, positions = cKDTree(features(unloaded, reference)).query(features(loaded, query))
    reference = reference[positions]
    angle_errors = np.abs(unloaded["angle"][reference] - loaded["angle"][query])
    speed_errors = np.abs(unloaded["speed"][reference] - loaded["speed"][query])
    accepted = np.all(angle_errors <= angle_limits, axis=1) & (speed_errors <= speed_limit)
    return (reference[accepted], query[accepted],
            int(np.sum(unloaded["valid"] & (unloaded["phase"] == phase))),
            len(accepted), angle_errors[accepted], speed_errors[accepted])


def compare_phase(unloaded, loaded, phase, angle_limits, speed_limit):
    reference, query, reference_count, query_count, angle_errors, speed_errors = (
        match_phase(unloaded, loaded, phase, angle_limits, speed_limit))
    if not len(query):
        return {"reference_frames": reference_count,
                "loaded_frames": query_count, "accepted_matches": 0}

    result = {
        "reference_frames": reference_count,
        "loaded_frames": query_count,
        "accepted_matches": int(len(query)),
        "unique_reference_frames": int(len(np.unique(reference))),
        "median_abs_angle_error_deg": {
            name: round(float(value), 3) for name, value in zip(
                ANGLE_NAMES, np.median(angle_errors, axis=0))},
        "median_abs_knee_speed_error_deg_s": round(float(np.median(speed_errors)), 2),
    }
    for side in ("r", "l"):
        for joint, key in (("knee", f"knee_angle_{side}_moment"),
                           ("hip", f"hip_flexion_{side}_moment")):
            difference = loaded["moment"][key][query] - unloaded["moment"][key][reference]
            result[f"{side}_{joint}_moment_loaded_minus_unloaded"] = describe_difference(difference)
    def total_vertical_grf(trial, indices):
        return (trial["grf"]["RForceY_Vertical"][indices]
                + trial["grf"]["LForceY_Vertical"][indices])
    result["vertical_grf_difference_N"] = describe_difference(
        total_vertical_grf(loaded, query) - total_vertical_grf(unloaded, reference))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", nargs="+", default=[
        "AB01", "AB02", "AB03", "AB05", "AB06", "AB07", "AB08", "AB09",
        "AB10", "AB11", "AB12", "AB13"])
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs" / "data" / "dynamic_squat_angle_match.json")
    parser.add_argument("--angle-scale", type=float, default=1,
                        help="Multiply the six default angle tolerances by this factor")
    parser.add_argument("--speed-limit", type=float, default=50,
                        help="Maximum right knee speed mismatch in deg/s")
    args = parser.parse_args()
    if args.angle_scale <= 0 or args.speed_limit <= 0:
        parser.error("Matching tolerances must be positive")
    angle_limits = ANGLE_LIMITS_DEG * args.angle_scale
    report = {
        "source": "Scherpereel et al., Scientific Data 10:924 (2023); Georgia Tech repository item 1853/70296",
        "doi": "10.1038/s41597-023-02840-6",
        "recordings": "squats_1_0lbs versus squats_1_25lbs, except AB05 uses squats_2_0lbs; within-subject comparison",
        "sampling_hz": 200,
        "moment_unit": "N m/kg strongly supported by paper/official plotting code and independent OpenSim IK/ID replay; accompanying README incorrectly or inconsistently says N m",
        "filters": "Both left/right task activity flags=1 (not foot contact); both knee flexions 45-130 deg; right knee angular speed >=20 deg/s for descent or <=-20 for ascent",
        "matching": "Nearest 0-lb frame within same phase using 6 angles and right knee speed; reference frames may repeat",
        "max_abs_angle_error_deg": angle_limits.tolist(),
        "max_abs_right_knee_speed_error_deg_s": args.speed_limit,
        "interpretation": "Descriptive matched-frame differences only; repeated frames are correlated and do not isolate load or validate individual muscle force",
        "subjects": {},
    }
    for subject in args.subjects:
        unloaded, loaded = load_trial(subject, "0lbs"), load_trial(subject, "25lbs")
        report["subjects"][subject] = {
            "deep_squat_peaks": {"0lbs": unloaded["deep_knee_peaks_seconds"],
                                   "25lbs": loaded["deep_knee_peaks_seconds"]},
            "descent": compare_phase(unloaded, loaded, "descent", angle_limits,
                                     args.speed_limit),
            "ascent": compare_phase(unloaded, loaded, "ascent", angle_limits,
                                    args.speed_limit),
        }
    report["cross_subject_summary"] = {}
    for phase in ("descent", "ascent"):
        accepted = {subject: row[phase] for subject, row in report["subjects"].items()
                    if row[phase]["accepted_matches"] >= 30
                    and row[phase]["accepted_matches"] / max(1, row[phase]["loaded_frames"]) >= 0.2}
        summary = {"quality_gate": ">=30 matched frames and >=20% loaded-frame coverage",
                   "accepted_subjects": list(accepted),
                   "excluded_subjects": [s for s in report["subjects"] if s not in accepted]}
        if accepted:
            summary["median_match_coverage"] = round(float(np.median([
                x["accepted_matches"] / x["loaded_frames"] for x in accepted.values()])), 3)
            for metric in ("r_knee_moment_loaded_minus_unloaded",
                           "l_knee_moment_loaded_minus_unloaded",
                           "r_hip_moment_loaded_minus_unloaded",
                           "l_hip_moment_loaded_minus_unloaded",
                           "vertical_grf_difference_N"):
                values = np.array([row[metric]["median"] for row in accepted.values()])
                summary[metric] = {"median_of_subject_medians": round(float(np.median(values)), 4),
                                   "subjects_positive": int(np.sum(values > 0)),
                                   "subjects_negative": int(np.sum(values < 0)),
                                   "subject_median_range": [round(float(np.min(values)), 4),
                                                            round(float(np.max(values)), 4)]}
        report["cross_subject_summary"][phase] = summary
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
