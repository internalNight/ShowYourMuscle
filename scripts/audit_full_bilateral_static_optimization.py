"""Audit solver diagnostics for the measured-input bilateral squat probe."""

import argparse
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
def read_sto(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines.index("endheader")
    names = lines[header + 1].split()
    values = np.array([[float(cell) for cell in line.split()]
                       for line in lines[header + 2:] if line.strip()])
    if values.shape[1] != len(names):
        raise ValueError(f"Column mismatch in {path}")
    return names, values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="AB01")
    parser.add_argument("--variant", choices=("physiology", "no-physiology"),
                        default="physiology")
    parser.add_argument("--run-tag", default="")
    parser.add_argument("--log", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    prefix = (f"{args.subject}_static_optimization_probe_"
              "full_bilateral_static_optimization")
    variant_dir = args.variant + (f"-{args.run_tag}" if args.run_tag else "")
    directory = (ROOT / ".cache/lower-limb/full-bilateral-static-optimization"
                 / args.subject / variant_dir)
    if args.variant == "physiology" and not args.run_tag and not directory.exists():
        directory = directory.parent
    log_name = ("full_bilateral_static_optimization_run.log" if
                args.variant == "physiology" else
                "full_bilateral_static_optimization_no_physiology.log")
    log_path = args.log or ROOT / ".cache/lower-limb" / log_name
    names, activations = read_sto(directory / f"{prefix}_activation.sto")
    force_names, forces = read_sto(directory / f"{prefix}_force.sto")
    if not np.allclose(activations[:, 0], forces[:, 0]):
        raise ValueError("Activation and force timestamps differ")
    log = log_path.read_text(encoding="utf-8", errors="replace")
    failed = [float(value) for value in re.findall(
        r"optimizer could not find a solution at time\s*=\s*([0-9]+(?:\.[0-9]+)?)", log,
        flags=re.IGNORECASE)]
    failed_indices = sorted(set(int(np.argmin(abs(activations[:, 0] - time)))
                                for time in failed))
    success_mask = np.ones(len(activations), dtype=bool)
    success_mask[failed_indices] = False
    muscle_indices = [i for i, name in enumerate(names) if i and not name.startswith("reserve_")]
    muscle_activations = activations[:, muscle_indices]
    saturated = np.sum(muscle_activations >= 0.99, axis=1)
    force_index = {name: i for i, name in enumerate(force_names)}
    pelvis = [f"reserve_pelvis_{axis}" for axis in ("tx", "ty", "tz")]
    pelvis_rot = [f"reserve_pelvis_{axis}" for axis in ("tilt", "list", "rotation")]
    joint_reserves = [name for name in force_names if name.startswith("reserve_")
                      and name not in pelvis + pelvis_rot]
    def maxima(columns, mask):
        return {name: round(float(np.max(np.abs(forces[mask, force_index[name]]))), 3)
                for name in columns}
    report = {
        "status": "diagnostic_rejected_for_personal_muscle_force",
        "subject": args.subject,
        "useMusclePhysiology": args.variant == "physiology",
        "runTag": args.run_tag,
        "input": "measured bilateral ground reaction forces plus replayed OpenSim IK",
        "timeIntervalS": [float(activations[0, 0]), float(activations[-1, 0])],
        "frameCount": len(activations),
        "optimizerFailedFrameCount": len(failed_indices),
        "optimizerFailedFrameTimesS": [round(float(activations[i, 0]), 3)
                                      for i in failed_indices],
        "successfulFrameCount": int(np.sum(success_mask)),
        "muscleCount": len(muscle_indices),
        "medianSaturatedMusclesPerFrameAll": float(np.median(saturated)),
        "maxSaturatedMusclesPerFrameAll": int(np.max(saturated)),
        "medianSaturatedMusclesPerSuccessfulFrame": (
            float(np.median(saturated[success_mask])) if np.any(success_mask) else None),
        "maxAbsPelvisTranslationReserveNOnSuccessfulFrames": (
            maxima(pelvis, success_mask) if np.any(success_mask) else None),
        "maxAbsPelvisRotationReserveNmOnSuccessfulFrames": (
            maxima(pelvis_rot, success_mask) if np.any(success_mask) else None),
        "maxAbsJointReserveNmOnSuccessfulFrames": (
            maxima(joint_reserves, success_mask) if np.any(success_mask) else None),
        "limitations": [
            "Tool run success only means files were written; individual frames can fail.",
            "The solver consumes measured force plates and measured IK, so this is not a phone-input prediction.",
            "A failed frame's reported activations or forces must not be interpreted.",
            "Muscle force needs independent validation and personalized strength parameters.",
        ],
    }
    output_name = ("full_bilateral_static_optimization_audit.json" if
                   args.variant == "physiology" else
                   "full_bilateral_static_optimization_no_physiology_audit.json")
    output = args.output or ROOT / "docs/data" / output_name
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "frameCount", "optimizerFailedFrameCount", "successfulFrameCount",
        "medianSaturatedMusclesPerSuccessfulFrame",
        "maxAbsPelvisTranslationReserveNOnSuccessfulFrames",
        "maxAbsPelvisRotationReserveNmOnSuccessfulFrames")}, indent=2))


if __name__ == "__main__":
    main()
