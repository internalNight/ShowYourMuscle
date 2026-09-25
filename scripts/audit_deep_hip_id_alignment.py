"""Compare released and locally replayed deep-squat hip moments and IK.

The purpose is to locate a remaining inverse-dynamics discrepancy before
interpreting any muscle-capacity deficit as a model-strength issue.
"""

import json

import numpy as np

from analyze_dynamic_squat_id_replay import read_storage
from analyze_dynamic_squats import read_csv
from audit_high_flex_candidate import ROOT, SUBJECTS
from audit_high_flex_hip_capacity import DEEP_INTERVALS
from probe_dynamic_squat_muscle_capacity import subject_masses

OUTPUT = ROOT / "docs/data/deep_squat_hip_id_alignment.json"
MOMENT_NAMES = ("hip_rotation_r_moment", "hip_rotation_l_moment",
                "hip_flexion_r_moment", "hip_flexion_l_moment",
                "hip_adduction_r_moment", "hip_adduction_l_moment")
ANGLE_NAMES = ("hip_rotation_r", "hip_rotation_l", "hip_flexion_r",
               "hip_flexion_l", "hip_adduction_r", "hip_adduction_l")


def round_float(value):
    return round(float(value), 4)


def summarize_pair(source, replay):
    residual = replay - source
    return {
        "sourceMedianNm": round_float(np.median(source)),
        "replayMedianNm": round_float(np.median(replay)),
        "signedBiasNm": round_float(np.mean(residual)),
        "meanAbsoluteErrorNm": round_float(np.mean(np.abs(residual))),
        "maximumAbsoluteErrorNm": round_float(np.max(np.abs(residual))),
        "sameSignFrameCount": int(np.sum(np.sign(source) == np.sign(replay))),
    }


def main():
    masses = subject_masses()
    report = {
        "status": "research_only_released_vs_replayed_inverse_dynamics_diagnostic",
        "momentUnitAssumption": "released CSV N m/kg multiplied by participant mass",
        "replayMethod": "OpenSim 4.6 ID, original scaled model and forceplate loads, independent IK, 6 Hz coordinate lowpass",
        "controlledVariation": "same model, IK, forceplate force and COP; include versus omit free forceplate moment vector",
        "limitations": [
            "released author's forceplate processing and exact ID settings are unknown",
            "replayed IK has small angle discrepancies but is not identical",
            "joint moments are not muscle forces",
        ],
        "subjects": {},
    }
    for subject, config in SUBJECTS.items():
        interval = DEEP_INTERVALS[subject]
        id_path = (ROOT / ".cache/lower-limb/id-reproduction" /
                   ("AB01_id_50_52.sto" if subject == "AB01" else
                    "AB02_id_23_25.sto"))
        no_free_moment_path = id_path.with_name(
            id_path.stem + "_no_free_moment.sto")
        ik_path = config["ik"]
        replay = read_storage(id_path)
        no_free_moment = read_storage(no_free_moment_path)
        ik = read_storage(ik_path)
        if not (np.allclose(replay["time"], ik["time"], atol=1e-6) and
                np.allclose(no_free_moment["time"], ik["time"], atol=1e-6)):
            raise AssertionError("IK and replay ID time grids differ")
        selection = np.where((replay["time"] >= interval[0] - 1e-7) &
                             (replay["time"] <= interval[1] + 1e-7))[0]
        if len(selection) != 21:
            raise AssertionError(f"Unexpected {subject} deep-frame count")
        original_dir = (ROOT / ".cache/lower-limb-raw" / subject /
                        "CSV_Data/squats_1")
        angles = read_csv(original_dir / "Joint_Angle.csv")
        moments = read_csv(original_dir / "Joint_Moments.csv")
        source_indices = np.rint(replay["time"][selection] / 0.005).astype(int)
        if not np.allclose(moments["time"][source_indices],
                           replay["time"][selection], atol=1e-6):
            raise AssertionError("Released and replay time grids differ")
        moment_report = {}
        for name in MOMENT_NAMES:
            original = moments[name][source_indices] * masses[subject]
            baseline = summarize_pair(original, replay[name][selection])
            no_free = summarize_pair(original, no_free_moment[name][selection])
            baseline["withoutForcePlateMoment"] = no_free
            baseline["maeChangeWithoutForcePlateMomentNm"] = round_float(
                no_free["meanAbsoluteErrorNm"] - baseline["meanAbsoluteErrorNm"])
            moment_report[name] = baseline
        interior = np.where((replay["time"] >= replay["time"][0] + 0.4 - 1e-7) &
                            (replay["time"] <= replay["time"][-1] - 0.4 + 1e-7))[0]
        interior_indices = np.rint(replay["time"][interior] / 0.005).astype(int)
        if len(interior) != 241 or not np.allclose(
                moments["time"][interior_indices], replay["time"][interior],
                atol=1e-6):
            raise AssertionError("Unexpected full interior comparison grid")
        interior_errors = {}
        for name in MOMENT_NAMES:
            original = moments[name][interior_indices] * masses[subject]
            interior_errors[name] = {
                "withForcePlateMomentMaENm": round_float(np.mean(np.abs(
                    replay[name][interior] - original))),
                "withoutForcePlateMomentMaENm": round_float(np.mean(np.abs(
                    no_free_moment[name][interior] - original))),
            }
        angle_report = {}
        for name in ANGLE_NAMES:
            deviation = ik[name][selection] - angles[name][source_indices]
            angle_report[name] = {
                "meanAbsoluteErrorDeg": round_float(np.mean(np.abs(deviation))),
                "maximumAbsoluteErrorDeg": round_float(np.max(np.abs(deviation))),
            }
        report["subjects"][subject] = {
            "intervalS": interval,
            "frames": len(selection),
            "sourceMassKg": masses[subject],
            "moments": moment_report,
            "interiorFrames": len(interior),
            "interiorMomentErrors": interior_errors,
            "angles": angle_report,
        }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(report["subjects"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
