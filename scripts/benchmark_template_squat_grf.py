"""Research gate for the viewer's prescribed squat against public force plates.

This uses only the public 0-lb recordings. A fixed-duration template and a
measured-duration diagnostic are reported separately. Neither is a personal
force prediction; duration comparisons here are exploratory, not validation.
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

from analyze_dynamic_squats import load_trial


ROOT = Path(__file__).resolve().parents[1]
G = 9.80665
PROTOCOL = json.loads((ROOT / "src" / "data" / "demo_motion_protocol.json")
                      .read_text(encoding="utf-8"))
DEFAULT_DURATION_S = float(PROTOCOL["cycleDurationS"])
SUBJECTS = ("AB01", "AB02", "AB03", "AB05", "AB06", "AB07", "AB08",
            "AB09", "AB10", "AB11", "AB12", "AB13")
OUTPUT = ROOT / "docs" / "data" / "squat_template_grf_benchmark.json"


def viewer_knee_flexion(data):
    angles = []
    for frame in data["frames"]:
        if frame["exercise"] != "squat":
            continue
        joints = frame["joints"]
        thigh = np.asarray(joints["hip_r"]) - np.asarray(joints["knee_r"])
        shank = np.asarray(joints["ankle_r"]) - np.asarray(joints["knee_r"])
        cosine = np.dot(thigh, shank) / (np.linalg.norm(thigh) * np.linalg.norm(shank))
        angles.append(180 - np.degrees(np.arccos(np.clip(cosine, -1, 1))))
    return float(np.min(angles)), float(np.max(angles))


def measured_repetitions(trial, minimum_depth_deg, minimum_active_fraction):
    time = trial["time"]
    dt = float(np.median(np.diff(time)))
    knee = -trial["angle"][:, 1]
    valleys, _ = find_peaks(-knee, prominence=25, distance=int(0.7 / dt))
    peaks, _ = find_peaks(knee, prominence=30, distance=int(0.7 / dt))
    reps = []
    for start, end in zip(valleys[:-1], valleys[1:]):
        inner = peaks[(peaks > start) & (peaks < end)]
        if len(inner) != 1:
            continue
        peak = inner[0]
        duration = float(time[end] - time[start])
        depth = float(knee[peak])
        if not (0.9 <= duration <= 4.0 and depth >= minimum_depth_deg and
                knee[start] <= 45 and knee[end] <= 45 and
                depth - max(knee[start], knee[end]) >= 40 and
                np.mean(trial["task_active"][start:end + 1]) >= minimum_active_fraction):
            continue
        reps.append((start, peak, end))
    return reps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum-depth-deg", type=float, default=50)
    parser.add_argument("--minimum-active-fraction", type=float, default=0.5)
    parser.add_argument("--probe", type=Path,
                        default=ROOT / "docs/data/squat_dynamic_grf_probe.json")
    parser.add_argument("--poses", type=Path,
                        default=ROOT / "assets/blender/animation_poses.json")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not (0 <= args.minimum_depth_deg <= 180 and 0 <= args.minimum_active_fraction <= 1):
        parser.error("depth must be 0-180 degrees and activity fraction 0-1")
    with (ROOT / ".cache" / "lower-limb-raw" / "Subject_masses.csv").open(
            newline="", encoding="utf-8-sig") as handle:
        masses = {row["Subject"]: float(row["Mass"]) for row in csv.DictReader(handle)}
    probe = json.loads(args.probe.read_text(encoding="utf-8"))
    poses = json.loads(args.poses.read_text(encoding="utf-8"))
    probe_duration_s = float(probe["durationS"])
    if not np.isfinite(probe_duration_s) or not 1.5 <= probe_duration_s <= 6:
        raise ValueError("Probe duration must be from 1.5 to 6 seconds")
    if probe.get("squatDepthDeg") != poses.get("squatDepthDeg"):
        raise ValueError("Force probe and Blender pose export must use the same squat depth")
    source = next(row for row in probe["rows"] if row["profile"]["heightCm"] == 175
                  and row["loadKg"] == 0)
    phases = np.asarray([row["phase"] for row in source["frames"]])
    template_acceleration = np.asarray([row["accelerationMs2"] for row in source["frames"]])
    assert len(phases) == 99 and np.allclose(phases, np.arange(1, 100) / 100)
    rows = []
    for subject in SUBJECTS:
        trial = load_trial(subject, "0lbs")
        time = trial["time"]
        vertical_grf = (trial["grf"]["RForceY_Vertical"]
                        + trial["grf"]["LForceY_Vertical"])
        mass = masses[subject]
        for number, (start, peak, end) in enumerate(measured_repetitions(
                trial, args.minimum_depth_deg, args.minimum_active_fraction), 1):
            duration = float(time[end] - time[start])
            observed = np.interp(time[start] + phases * duration, time,
                                 vertical_grf) / (mass * G)
            prediction_fixed = 1 + template_acceleration / G
            prediction_timed = 1 + template_acceleration / G * (probe_duration_s / duration) ** 2
            static_mae = float(np.mean(np.abs(observed - 1)))
            fixed_mae = float(np.mean(np.abs(observed - prediction_fixed)))
            timed_mae = float(np.mean(np.abs(observed - prediction_timed)))
            rows.append({
                "subject": subject, "rep": number,
                "startS": round(float(time[start]), 3),
                "deepestS": round(float(time[peak]), 3),
                "endS": round(float(time[end]), 3),
                "durationS": round(duration, 3),
                "observedPeakKneeFlexionDeg": round(float(-trial["angle"][peak, 1]), 2),
                "observedMinMaxWeightRatio": [round(float(np.min(observed)), 3),
                                              round(float(np.max(observed)), 3)],
                "observedPeakPhase": round(float(phases[np.argmax(observed)]), 2),
                "staticWeightMaeRatio": round(static_mae, 4),
                "fixedDurationTemplateMaeRatio": round(fixed_mae, 4),
                "measuredDurationTemplateMaeRatio": round(timed_mae, 4),
                "fixedImprovementOverStaticRatio": round(static_mae - fixed_mae, 4),
                "timedImprovementOverStaticRatio": round(static_mae - timed_mae, 4),
            })
    if not rows:
        raise RuntimeError("No complete unloaded squat repetitions passed the segmentation gate")
    subject_rows = []
    for subject in SUBJECTS:
        subset = [row for row in rows if row["subject"] == subject]
        if not subset:
            continue
        subject_rows.append({
            "subject": subject, "reps": len(subset),
            "medianDurationS": round(float(np.median([row["durationS"] for row in subset])), 3),
            "medianPeakKneeFlexionDeg": round(float(np.median([
                row["observedPeakKneeFlexionDeg"] for row in subset])), 2),
            "medianStaticMaeRatio": round(float(np.median([
                row["staticWeightMaeRatio"] for row in subset])), 4),
            "medianFixedTemplateMaeRatio": round(float(np.median([
                row["fixedDurationTemplateMaeRatio"] for row in subset])), 4),
            "medianTimedTemplateMaeRatio": round(float(np.median([
                row["measuredDurationTemplateMaeRatio"] for row in subset])), 4),
        })
    subject_array = lambda key: np.asarray([row[key] for row in subject_rows])
    fixed_improvement = (subject_array("medianStaticMaeRatio")
                         - subject_array("medianFixedTemplateMaeRatio"))
    timed_improvement = (subject_array("medianStaticMaeRatio")
                         - subject_array("medianTimedTemplateMaeRatio"))
    rng = np.random.default_rng(42)
    bootstrap_indices = rng.integers(len(subject_rows), size=(10000, len(subject_rows)))
    fixed_ci = np.quantile(np.median(fixed_improvement[bootstrap_indices], axis=1), [0.025, 0.975])
    timed_ci = np.quantile(np.median(timed_improvement[bootstrap_indices], axis=1), [0.025, 0.975])
    viewer_min, viewer_max = viewer_knee_flexion(poses)
    result = {
        "status": "research_only_not_validated_personal_ground_force_or_muscle_force",
        "source": "Scherpereel et al. 2023 processed public squat angle and force-plate CSVs",
        "protocol": "0-lb only; consecutive standing-like knee-flexion valleys enclosing one deep peak; no template tuning. Linear time-normalization to 99 interior phase points. One participant, not one frame or repetition, is the summary unit.",
        "viewerHeightAssumptionCm": 175,
        "viewerDefaultDurationS": probe_duration_s,
        "viewerDepthTargetDeg": poses.get("squatDepthDeg"),
        "viewerKneeFlexionRangeDeg": [round(viewer_min, 2), round(viewer_max, 2)],
        "grfRatioDefinition": "sum of left and right vertical GRF / (measured subject mass * 9.80665)",
        "maeRatioDefinition": "mean across 99 normalized phase points of |predicted minus observed GRF/body weight|; static baseline is exactly 1",
        "qualityGate": f"one peak between standing-like valleys; 0.9-4 s, peak knee >={args.minimum_depth_deg:g} deg, both valleys <=45 deg, >=40 deg flexion excursion, >={args.minimum_active_fraction:.0%} bilateral task-active flags (not foot contact)",
        "summary": {
            "subjects": len(subject_rows), "reps": len(rows),
            "subjectMedianDurationS": round(float(np.median(subject_array("medianDurationS"))), 3),
            "subjectMedianPeakKneeFlexionDeg": round(float(np.median(subject_array("medianPeakKneeFlexionDeg"))), 2),
            "subjectMedianStaticMaeRatio": round(float(np.median(subject_array("medianStaticMaeRatio"))), 4),
            "subjectMedianFixedTemplateMaeRatio": round(float(np.median(subject_array("medianFixedTemplateMaeRatio"))), 4),
            "subjectMedianTimedTemplateMaeRatio": round(float(np.median(subject_array("medianTimedTemplateMaeRatio"))), 4),
            "pairedSubjectMedianFixedImprovementRatio": round(float(np.median(fixed_improvement)), 4),
            "pairedSubjectMedianFixedImprovementBootstrap95": [round(float(x), 4) for x in fixed_ci],
            "pairedSubjectMedianTimedImprovementRatio": round(float(np.median(timed_improvement)), 4),
            "pairedSubjectMedianTimedImprovementBootstrap95": [round(float(x), 4) for x in timed_ci],
            "subjectsFixedTemplateBeatsStatic": int(np.sum(
                subject_array("medianFixedTemplateMaeRatio") < subject_array("medianStaticMaeRatio"))),
            "subjectsTimedTemplateBeatsStatic": int(np.sum(
                subject_array("medianTimedTemplateMaeRatio") < subject_array("medianStaticMaeRatio"))),
        },
        "limitations": [
            "The viewer prescribes one 175-cm geometry and a symmetric phase curve; trial body heights and actual user motion are unavailable to the app.",
            "Time-normalization uses experimental rep boundaries; measured-duration version is an optimistic diagnostic, not an available phone input.",
            "Unloaded laboratory squats do not validate barbell position, joint net moments, individual muscles, or other exercises.",
            "GRF data are processed by the source; valley segmentation and force-plate baseline may affect errors.",
            "Bootstrap intervals resample 12 participants, not correlated repetitions; they describe this sample and are not validation limits.",
        ],
        "subjects": subject_rows,
        "repetitions": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
