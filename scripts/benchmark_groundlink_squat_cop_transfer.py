"""Transfer Georgia Tech squat COP templates to independent GroundLink trials.

No GroundLink observations are used to fit the source templates. The measured
pelvis-height event boundaries are used only to score 99 aligned phase points.
"""

import json
import zipfile
from pathlib import Path

import ezc3d
import numpy as np

from benchmark_squat_cop_marker import (PHASES, collect, read_masses,
                                        subject_curves)
from benchmark_template_squat_grf import SUBJECTS
from groundlink_force_format import read_groundlink_npy


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache/groundlink"
OUTPUT = ROOT / "docs/data/groundlink_squat_cop_transfer.json"
SEGMENTS = json.loads((ROOT / "docs/data/groundlink_squat_template_benchmark.json")
                      .read_text(encoding="utf-8"))["repetitions"]
MASSES = {row["subject"]: row["massKg"] for row in json.loads(
    (ROOT / "docs/data/groundlink_squat_force_audit.json").read_text(
        encoding="utf-8"))["subjects"]}
RATE = 250
G = 9.80665


def sample_marker(points, labels, name, query):
    index = labels.index(f"QTMMod_{name}")
    data = points[:, index, :]
    x, y = [], []
    for axis, sink in ((0, x), (1, y)):
        values = data[axis] / 1000
        valid = np.isfinite(values) & (data[3] > 0)
        if valid.sum() < 2:
            raise ValueError(f"Too few marker observations: {name}")
        sink.extend(np.interp(query, np.flatnonzero(valid), values[valid],
                              left=np.nan, right=np.nan))
    return np.column_stack((x, y))


def measure_trial(subject, c3d_path, force, segments):
    c3d = ezc3d.c3d(c3d_path.relative_to(ROOT).as_posix())
    labels = c3d["parameters"]["POINT"]["LABELS"]["value"]
    points = c3d["data"]["points"]
    if c3d["header"]["points"]["frame_rate"] != RATE:
        raise ValueError(c3d_path)
    if len(points[0, 0]) < len(force["CoP"]):
        raise ValueError(f"Force trace longer than markers: {c3d_path}")
    rows = []
    for segment in segments:
        query = (segment["startS"] + PHASES *
                 (segment["endS"] - segment["startS"])) * RATE
        if max(query) >= len(force["CoP"]):
            raise ValueError(f"Segment exceeds force trace: {c3d_path}")
        for side, plate in (("l", 0), ("r", 1)):
            ankle = (sample_marker(points, labels, f"{side}_ank_lat", query) +
                     sample_marker(points, labels, f"{side}_ank_med", query)) / 2
            opposite = "r" if side == "l" else "l"
            other_ankle = (sample_marker(points, labels, f"{opposite}_ank_lat", query) +
                           sample_marker(points, labels, f"{opposite}_ank_med", query)) / 2
            heel = sample_marker(points, labels, f"{side}_foot_heel", query)
            toe = (sample_marker(points, labels, f"{side}_foot_m1", query) +
                   sample_marker(points, labels, f"{side}_foot_m5", query)) / 2
            length = np.linalg.norm(toe - heel, axis=1)
            axis = (toe - heel) / length[:, None]
            cop = np.column_stack([np.interp(query, np.arange(len(force["CoP"])),
                                             force["CoP"][:, plate, direction])
                                   for direction in (0, 1)])
            if np.mean(np.linalg.norm(cop - ankle, axis=1) <
                       np.linalg.norm(cop - other_ankle, axis=1)) < 0.9:
                raise ValueError(f"Force-plate foot order does not match markers: {c3d_path}")
            grf = np.interp(query, np.arange(len(force["GRF"])),
                            force["GRF"][:, plate, 2]) * 1000
            forward_cm = np.sum((cop - ankle) * axis, axis=1) * 100
            valid = ((grf >= 0.1 * MASSES[subject] * G) &
                     np.isfinite(forward_cm) & np.isfinite(length) &
                     (length >= 0.12) & (length <= 0.4) &
                     (forward_cm >= -10) &
                     (forward_cm <= length * 100 + 10))
            if valid.sum() < 80:
                raise ValueError(f"Too few valid phases: {subject} {c3d_path.stem} "
                                 f"rep {segment['rep']} {side}: {valid.sum()}")
            rows.append({"subject": subject, "trial": c3d_path.stem,
                         "rep": segment["rep"], "side": side,
                         "validPhases": int(valid.sum()),
                         "footLengthCm": round(float(np.median(length)), 4) * 100,
                         "copForwardCm": forward_cm, "verticalForceN": grf,
                         "valid": valid})
    return rows


def main():
    source_rows, excluded = collect(SUBJECTS, read_masses())
    if excluded or len(source_rows) != 78:
        raise ValueError(f"Source COP extraction changed: {excluded}, {len(source_rows)}")
    source = np.asarray(list(subject_curves(source_rows, SUBJECTS).values()))
    constant = float(np.median(source))
    phase = np.median(source, axis=0)
    measured = []
    for subject in sorted(MASSES):
        with zipfile.ZipFile(SOURCE / f"{subject}_force.zip") as zipped:
            trials = sorted((SOURCE / "c3d" / subject).glob("*squat*.c3d"))
            if len(trials) != 3:
                raise ValueError(f"Expected three squat files for {subject}")
            for path in trials:
                trial_segments = [row for row in SEGMENTS if
                                  row["subject"] == subject and row["trial"] == path.stem]
                if len(trial_segments) != 3:
                    raise ValueError(f"Expected three segmented reps: {path}")
                force = read_groundlink_npy(zipped.read(f"{subject}/{path.stem}.npy"))
                measured.extend(measure_trial(subject, path, force, trial_segments))
    subject_results = []
    for subject in sorted(MASSES):
        subset = [row for row in measured if row["subject"] == subject]
        observed = np.concatenate([row["copForwardCm"][row["valid"]] for row in subset])
        flat_errors = np.concatenate([np.abs(row["copForwardCm"][row["valid"]] - constant)
                                      for row in subset])
        phase_errors = np.concatenate([np.abs(row["copForwardCm"][row["valid"]] -
                                             phase[row["valid"]]) for row in subset])
        flat_moment_errors = np.concatenate([
            np.abs(row["copForwardCm"][row["valid"]] - constant) / 100 *
            row["verticalForceN"][row["valid"]] for row in subset])
        phase_moment_errors = np.concatenate([
            np.abs(row["copForwardCm"][row["valid"]] - phase[row["valid"]]) / 100 *
            row["verticalForceN"][row["valid"]] for row in subset])
        subject_results.append({"subject": subject, "massKg": MASSES[subject],
                                "trajectories": len(subset),
                                "copForwardMedianCm": round(float(np.median(observed)), 3),
                                "footLengthMedianCm": round(float(np.median(
                                    [row["footLengthCm"] for row in subset])), 3),
                                "sourceFlatMaeCm": round(float(np.mean(flat_errors)), 4),
                                "sourcePhaseMaeCm": round(float(np.mean(phase_errors)), 4),
                                "flatCopOnlyExternalMomentMaeNm": round(float(np.mean(
                                    flat_moment_errors)), 4),
                                "phaseCopOnlyExternalMomentMaeNm": round(float(np.mean(
                                    phase_moment_errors)), 4),
                                "phaseMinusFlatImprovementCm": round(float(
                                    np.mean(flat_errors) - np.mean(phase_errors)), 4)})
    diffs = np.asarray([row["phaseMinusFlatImprovementCm"] for row in subject_results])
    rng = np.random.default_rng(20260925)
    boot = np.median(rng.choice(diffs, size=(5000, len(diffs)), replace=True), axis=1)
    report = {
        "status": "external_lab_cop_transfer_not_personal_joint_or_muscle_force_validation",
        "sourceTemplate": "Georgia Tech 12-person unloaded squat force-plate COP relative to skin-marker ankle midpoint, sagittal heel-to-metatarsal axis; no GroundLink fitting",
        "target": "GroundLink 7-person unloaded squat force-plate COP projected from skin-marker ankle midpoint onto heel-to-M1/M5 axis",
        "alignment": "63 repetitions are segmented by measured pelvis height, then resampled to the same 99 phase points as the source knee-angle event segmentation. This measured alignment is unavailable to the phone.",
        "externalMomentProbe": "Keep measured per-foot vertical force and all other experimental terms identical, replace only the measured sagittal COP arm by the Georgia Tech constant or phase template. Error due to this COP substitution is abs(COP_arm_error * measured_vertical_force); it is not full external or net ankle moment prediction.",
        "limitations": ["The two studies use different marker placements and event definitions.",
                        "The fixed point and phase template are both learned only from the Georgia Tech sample, with no GroundLink calibration.",
                        "GroundLink foot plate order was checked against left/right marker locations; the source foot-marker proxy is not an anatomical ankle joint centre.",
                        "These are unloaded squats and pressure-centre positions, not personal loaded net joint moments or individual muscle forces."],
        "sourceFlatCm": round(constant, 4),
        "summary": {"subjects": len(subject_results), "trials": 21,
                    "trajectories": len(measured),
                    "sourceFlatMedianSubjectMaeCm": round(float(np.median(
                        [row["sourceFlatMaeCm"] for row in subject_results])), 4),
                    "sourcePhaseMedianSubjectMaeCm": round(float(np.median(
                        [row["sourcePhaseMaeCm"] for row in subject_results])), 4),
                    "flatCopOnlyExternalMomentMedianSubjectMaeNm": round(float(np.median(
                        [row["flatCopOnlyExternalMomentMaeNm"] for row in subject_results])), 4),
                    "phaseCopOnlyExternalMomentMedianSubjectMaeNm": round(float(np.median(
                        [row["phaseCopOnlyExternalMomentMaeNm"] for row in subject_results])), 4),
                    "phaseBetterSubjects": int(np.sum(diffs > 0)),
                    "phaseImprovementMedianCm": round(float(np.median(diffs)), 4),
                    "phaseImprovementBootstrap95Cm": [round(float(x), 4)
                                                   for x in np.percentile(boot, [2.5, 97.5])]},
        "subjects": subject_results,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
