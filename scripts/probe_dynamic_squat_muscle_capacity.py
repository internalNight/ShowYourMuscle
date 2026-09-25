"""Screen whether the source OpenSim models can span recorded joint moments.

This is a conditional, deliberately optimistic capacity check. It assumes the
CSV moments are Nm/kg and multiplies by the source subject mass. It ignores
force-length/velocity, tendon, passive tissues, co-contraction and coupling,
so it neither predicts nor validates muscle force.
"""

import argparse
import csv
import json
import os
from pathlib import Path

import numpy as np
import opensim as osim

from analyze_dynamic_squats import CACHE, ROOT, load_trial


RAW = ROOT / ".cache" / "lower-limb-raw"
ANGLE_NAMES = (
    "hip_flexion_r", "knee_angle_r", "ankle_angle_r",
    "hip_flexion_l", "knee_angle_l", "ankle_angle_l",
)
JOINTS = tuple((side, joint, f"{coord}_{side}")
               for side in ("r", "l")
               for joint, coord in (("hip", "hip_flexion"),
                                    ("knee", "knee_angle"),
                                    ("ankle", "ankle_angle")))


def subject_masses():
    with (RAW / "Subject_masses.csv").open(newline="") as handle:
        return {row["Subject"]: float(row["Mass"]) for row in csv.DictReader(handle)}


def screen(subject, load, mass, stride):
    trial = load_trial(subject, load)
    # OpenSim's Windows loader fails on the Chinese workspace path; use an ASCII
    # relative path when the command is run from the repository root.
    model_path = RAW / subject / "Models" / f"{subject}-Scaled1.osim"
    model = osim.Model(os.path.relpath(model_path))
    state = model.initSystem()
    coordinates = model.getCoordinateSet()
    muscles = {side: [model.getMuscles().get(i)
                      for i in range(model.getMuscles().getSize())
                      if model.getMuscles().get(i).getName().endswith("_" + side)]
               for side in ("r", "l")}
    strengths = {side: np.array([muscle.getMaxIsometricForce()
                                 for muscle in side_muscles])
                 for side, side_muscles in muscles.items()}
    knees = -trial["angle"][:, [1, 4]]
    candidates = np.flatnonzero(trial["task_active"]
                                & (knees.min(axis=1) >= 10)
                                & (knees.max(axis=1) <= 150))
    indices = set(candidates[::stride])
    for _, _, coordinate in JOINTS:
        if len(candidates):
            targets = np.abs(trial["moment"][coordinate + "_moment"][candidates])
            indices.add(int(candidates[np.argmax(targets)]))
    records = {f"{side}_{joint}": [] for side, joint, _ in JOINTS}
    for index in sorted(indices):
        for name, value in zip(ANGLE_NAMES, trial["angle"][index]):
            coordinates.get(name).setValue(state, float(np.deg2rad(value)), False)
        model.realizePosition(state)
        for side, joint, coordinate in JOINTS:
            arms = np.array([muscle.computeMomentArm(state, coordinates.get(coordinate))
                             for muscle in muscles[side]])
            target = float(trial["moment"][coordinate + "_moment"][index] * mass)
            if target >= 0:
                capacity = float(np.sum(np.maximum(arms, 0) * strengths[side]))
            else:
                capacity = float(np.sum(np.maximum(-arms, 0) * strengths[side]))
            if capacity > 0:
                records[f"{side}_{joint}"].append((abs(target) / capacity,
                                                    target, capacity,
                                                    float(trial["time"][index])))
    result = {"sampled_frames": len(indices), "joints": {}}
    for key, rows in records.items():
        if not rows:
            continue
        ratios = np.array([row[0] for row in rows])
        peak = max(rows, key=lambda row: row[0])
        result["joints"][key] = {
            "capacity_exceeded_frames": int(np.sum(ratios > 1)),
            "median_demand_to_optimistic_capacity": round(float(np.median(ratios)), 3),
            "max_demand_to_optimistic_capacity": round(float(peak[0]), 3),
            "max_ratio_frame": {"time_s": round(peak[3], 3),
                                "target_Nm": round(peak[1], 2),
                                "optimistic_capacity_Nm": round(peak[2], 2)},
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", nargs="+", default=[
        "AB01", "AB02", "AB03", "AB05", "AB06", "AB07", "AB08", "AB09",
        "AB10", "AB11", "AB12", "AB13"])
    parser.add_argument("--stride", type=int, default=5,
                        help="Sample every N valid frames, plus each joint's peak demand")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/data/dynamic_squat_capacity_screen.json")
    args = parser.parse_args()
    if args.stride < 1:
        parser.error("--stride must be at least 1")
    masses = subject_masses()
    report = {
        "assumption": "Published moment CSV interpreted as Nm/kg, multiplied by subject mass; independent IK/ID replay strongly supports this despite conflicting README",
        "capacity_definition": "Sum of all same-side same-direction moment arms times each muscle's max isometric force at recorded hip/knee/ankle angles. Task active and both knees at 10-150 deg flexion. Missing pelvis/lumbar coordinates stay at model defaults. This is an optimistic independent-joint capacity screen, not a muscle-force solution.",
        "stride": args.stride,
        "subjects": {},
    }
    for subject in args.subjects:
        report["subjects"][subject] = {load: screen(subject, load, masses[subject], args.stride)
                                       for load in ("0lbs", "25lbs")}
    report["cross_subject_summary"] = {}
    for load in ("0lbs", "25lbs"):
        report["cross_subject_summary"][load] = {}
        for side, joint, _ in JOINTS:
            key = f"{side}_{joint}"
            rows = [x[load]["joints"][key] for x in report["subjects"].values()]
            report["cross_subject_summary"][load][key] = {
                "subjects_with_any_capacity_exceedance": sum(
                    row["capacity_exceeded_frames"] > 0 for row in rows),
                "median_of_subject_max_demand_to_capacity": round(float(np.median([
                    row["max_demand_to_optimistic_capacity"] for row in rows])), 3),
            }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({subject: {load: result["joints"]["r_knee"]
                                for load, result in loads.items()}
                      for subject, loads in report["subjects"].items()}, indent=2))


if __name__ == "__main__":
    main()
