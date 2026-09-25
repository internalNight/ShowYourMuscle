"""Screen full-pose muscle torque capacity at an experimental deep squat frame.

Independent-coordinate upper bounds deliberately ignore force-length limits,
simultaneous torque coupling, passive tissue and activation dynamics.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import opensim as osim

from analyze_dynamic_squats import read_csv
from audit_full_bilateral_static_optimization import read_sto
from export_bilateral_squat_blender_data import apply_row
from probe_dynamic_squat_muscle_capacity import subject_masses

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = {
    "AB01": {"ikInterval": (50, 52), "targetTimeS": 51.32,
             "capacityIntervalS": (51.25, 51.35)},
    "AB02": {"ikInterval": (23, 25), "targetTimeS": 23.685,
             "capacityIntervalS": (23.65, 23.75)},
}
INTERVAL_COORDINATES = ("hip_rotation_r", "hip_rotation_l", "knee_angle_r",
                        "lumbar_extension")


def read_ik_nearest(target, ik_path):
    lines = ik_path.read_text(encoding="utf-8").splitlines()
    start = lines.index("endheader")
    names = lines[start + 1].split()
    rows = [[float(value) for value in line.split()]
            for line in lines[start + 2:] if line.strip()]
    row = min(rows, key=lambda item: abs(item[0] - target))
    if abs(row[0] - target) > 1e-6:
        raise ValueError("Experimental IK frame not found")
    return dict(zip(names, row))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", choices=CONFIGS, default="AB01")
    parser.add_argument("--model", type=Path,
                        help="Alternative OpenSim model with the same coordinate names")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    subject = args.subject
    config = CONFIGS[subject]
    target_time_s = config["targetTimeS"]
    interval_s = config["capacityIntervalS"]
    ik_start, ik_end = config["ikInterval"]
    ik_path = (ROOT / ".cache/lower-limb" /
               f"{subject}_ik_{ik_start}_{ik_end}.mot")
    model_path = (args.model or ROOT / ".cache/lower-limb-raw" / subject /
                  "Models" / f"{subject}-Scaled1.osim").resolve()
    id_path = (ROOT / ".cache/lower-limb/id-reproduction" /
               f"{subject}_id_{ik_start}_{ik_end}.sto")
    source_moment_path = (ROOT / ".cache/lower-limb-raw" / subject /
                          "CSV_Data/squats_1/Joint_Moments.csv")
    osim.Logger.setLevelString("Error")
    names, id_values = read_sto(id_path)
    source_moments = read_csv(source_moment_path)
    subject_mass = subject_masses()[subject]
    target_index = int(np.argmin(abs(id_values[:, 0] - target_time_s)))
    if abs(id_values[target_index, 0] - target_time_s) > 1e-6:
        raise ValueError("Replayed ID frame not found")
    moments = dict(zip(names[1:], id_values[target_index, 1:]))
    source_index = int(round(target_time_s / 0.005))
    if abs(source_moments["time"][source_index] - target_time_s) > 1e-6:
        raise ValueError("Source moment frame not found")
    model = osim.Model(str(model_path.relative_to(ROOT)))
    state = model.initSystem()
    apply_row(model, state, read_ik_nearest(target_time_s, ik_path))
    muscles = [model.getMuscles().get(i)
               for i in range(model.getMuscles().getSize())]
    if not muscles:
        raise ValueError("Model has no muscles")
    rows = []
    strengths = np.array([muscle.getMaxIsometricForce() for muscle in muscles])
    for index in range(model.getCoordinateSet().getSize()):
        coordinate = model.getCoordinateSet().get(index)
        name = coordinate.getName()
        if name.endswith(("_tx", "_ty", "_tz")):
            continue
        column = name + "_moment"
        target = float(moments[column])
        arms = np.array([muscle.computeMomentArm(state, coordinate)
                         for muscle in muscles])
        same_direction = arms if target >= 0 else -arms
        contributions = np.maximum(same_direction, 0) * strengths
        capacity = float(np.sum(contributions))
        unsupported = capacity < 1e-6
        ratio = None if unsupported else abs(target) / capacity
        source_target = (float(source_moments[column][source_index] * subject_mass)
                         if column in source_moments else None)
        source_capacity = (float(np.sum(np.maximum(arms if source_target >= 0 else -arms,
                                                   0) * strengths))
                           if source_target is not None else None)
        source_ratio = (abs(source_target) / source_capacity
                        if source_capacity is not None and source_capacity > 1e-6
                        else None)
        rows.append({"coordinate": name, "targetMomentNm": round(target, 3),
                     "optimisticIndependentCapacityNm": round(capacity, 3),
                     "demandToCapacity": round(ratio, 3) if ratio is not None else None,
                     "sourceRawCsvMomentNmAssumingNmPerKg": (
                         round(source_target, 3) if source_target is not None else None),
                     "sourceCsvDemandToCapacity": (
                         round(source_ratio, 3) if source_ratio is not None else None),
                     "topMuscleCapacityContributors": [
                         {"muscle": muscles[i].getName(),
                          "optimisticMomentNm": round(float(contributions[i]), 3)}
                         for i in np.argsort(contributions)[::-1][:5]
                         if contributions[i] > 1e-6],
                     "unsupportedByMuscles": unsupported,
                     "capacityExceeded": ratio > 1 if ratio is not None else False})
    interval_rows = {name: [] for name in INTERVAL_COORDINATES}
    source_interval_rows = {name: [] for name in INTERVAL_COORDINATES}
    replay_source_differences = {name: [] for name in INTERVAL_COORDINATES}
    for moment_row in id_values:
        time_s = float(moment_row[0])
        if not interval_s[0] - 1e-6 <= time_s <= interval_s[1] + 1e-6:
            continue
        apply_row(model, state, read_ik_nearest(time_s, ik_path))
        targets = dict(zip(names[1:], moment_row[1:]))
        source_index = int(round(time_s / 0.005))
        if abs(source_moments["time"][source_index] - time_s) > 1e-6:
            raise ValueError("Source moment time grid mismatch")
        for name in INTERVAL_COORDINATES:
            coordinate = model.getCoordinateSet().get(name)
            target = float(targets[name + "_moment"])
            arms = np.array([muscle.computeMomentArm(state, coordinate)
                             for muscle in muscles])
            same_direction = arms if target >= 0 else -arms
            capacity = float(np.sum(np.maximum(same_direction, 0) * strengths))
            interval_rows[name].append(abs(target) / capacity if capacity > 1e-6
                                       else None)
            source_column = name + "_moment"
            if source_column in source_moments:
                source_target = float(source_moments[source_column][source_index] *
                                      subject_mass)
                source_direction = arms if source_target >= 0 else -arms
                source_capacity = float(np.sum(np.maximum(source_direction, 0) *
                                               strengths))
                source_interval_rows[name].append(
                    abs(source_target) / source_capacity if source_capacity > 1e-6
                    else None)
                replay_source_differences[name].append(abs(target - source_target))
    interval_summary = {}
    for name, ratios in interval_rows.items():
        valid = np.array([value for value in ratios if value is not None])
        interval_summary[name] = {
            "frameCount": len(ratios),
            "exceededFrameCount": int(np.sum(valid > 1)),
            "minDemandToCapacity": round(float(np.min(valid)), 3),
            "medianDemandToCapacity": round(float(np.median(valid)), 3),
            "maxDemandToCapacity": round(float(np.max(valid)), 3),
        }
        source_valid = np.array([value for value in source_interval_rows[name]
                                 if value is not None])
        if len(source_valid):
            interval_summary[name]["sourceRawCsvAssumingNmPerKg"] = {
                "frameCount": len(source_valid),
                "exceededFrameCount": int(np.sum(source_valid > 1)),
                "minDemandToCapacity": round(float(np.min(source_valid)), 3),
                "medianDemandToCapacity": round(float(np.median(source_valid)), 3),
                "maxDemandToCapacity": round(float(np.max(source_valid)), 3),
                "replayedIdVsSourceRawMaeNm": round(float(np.mean(
                    replay_source_differences[name])), 3),
            }
    result = {
        "status": "research_only_optimistic_independent_joint_upper_bound",
        "subject": subject,
        "timeS": target_time_s,
        "modelPath": str(model_path.relative_to(ROOT)),
        "modelMassKg": float(model.getTotalMass(state)),
        "input": "replayed experimental inverse-dynamics moments, original released raw CSV joint moments, and full experimental IK",
        "sourceRawMomentUnitAssumption": "N m/kg multiplied by the subject-mass table; supported but not conclusively proven for every coordinate",
        "subjectMassKgForSourceCsv": subject_mass,
        "muscleCount": len(muscles),
        "definition": "For each rotational coordinate independently, sum all same-direction moment arms times max isometric muscle force; ignores force-length, passive tissue and simultaneous multi-joint allocation.",
        "pelvisIdResidual": {name: round(float(moments[name]), 3)
                             for name in ("pelvis_tx_force", "pelvis_ty_force",
                                          "pelvis_tz_force", "pelvis_tilt_moment",
                                          "pelvis_list_moment", "pelvis_rotation_moment")},
        "exceededCoordinates": [row["coordinate"] for row in rows
                                if row["capacityExceeded"]],
        "unactuatedCoordinates": [row["coordinate"] for row in rows
                                   if row["unsupportedByMuscles"]],
        "intervalS": list(interval_s),
        "intervalSummary": interval_summary,
        "coordinates": rows,
    }
    output = args.output or (ROOT / "docs/data" /
                             ("bilateral_deep_squat_joint_capacity.json" if
                              subject == "AB01" else
                              f"bilateral_deep_squat_joint_capacity_{subject}.json"))
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n",
                      encoding="utf-8")
    print(json.dumps({"exceeded": result["exceededCoordinates"],
                      "unactuated": result["unactuatedCoordinates"],
                      "intervalSummary": interval_summary,
                      "worstRatios": sorted(
                          [{"coordinate": row["coordinate"],
                            "ratio": row["demandToCapacity"]} for row in rows
                           if row["demandToCapacity"] is not None],
                          key=lambda row: row["ratio"], reverse=True)[:8]}, indent=2))


if __name__ == "__main__":
    main()
