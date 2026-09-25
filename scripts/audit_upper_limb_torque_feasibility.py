"""Screen joint torques against a deliberately simple OpenSim muscle envelope.

Forces are bounded by each model muscle's nominal maximum isometric force.
The linear program tests two joint torques, not actual fibre force, dynamics,
contact, passive tissues, or a validated exercise muscle-force prediction.
"""

import json
import os
from pathlib import Path

import numpy as np
import opensim as osim
from scipy.optimize import linprog


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".cache/upper-limb-torque"
OUTPUT = ROOT / "docs/data/upper_limb_torque_capacity_screen.json"
SUBJECTS = tuple(f"S{number:02d}" for number in range(1, 18))
INPUT_COORDS = ("elv_angle", "shoulder_elv", "shoulder_rot", "elbow_flexion",
                "pro_sup", "deviation", "flexion")
TARGET_COORDS = ("shoulder_elv", "elbow_flexion")
STRIDE = 50  # Every half-second, with the final frame included.


def capacity_screen(moment_arms, fmax, demand):
    bounds = [(0, float(value)) for value in fmax]
    exact = linprog(np.zeros(len(fmax)), A_eq=moment_arms, b_eq=demand,
                    bounds=bounds, method="highs")
    positive = (np.maximum(moment_arms, 0) * fmax).sum(axis=1)
    negative = (np.minimum(moment_arms, 0) * fmax).sum(axis=1)
    outside = (demand < negative - 1e-5) | (demand > positive + 1e-5)
    if exact.success and np.max(np.abs(moment_arms @ exact.x - demand)) <= 1e-4:
        return True, 0.0, outside, bounds
    count = len(fmax)
    objective = np.r_[np.zeros(count), np.ones(4)]
    equalities = np.hstack((moment_arms, np.eye(2), -np.eye(2)))
    residual = linprog(objective, A_eq=equalities, b_eq=demand,
                       bounds=[*bounds, *((0, None),) * 4], method="highs")
    if not residual.success:
        raise RuntimeError(f"torque residual LP failed: {residual.message}")
    return False, float(residual.fun), outside, bounds


def force_interval(moment_arms, demand, bounds, index):
    objective = np.zeros(len(bounds))
    objective[index] = 1
    minimum = linprog(objective, A_eq=moment_arms, b_eq=demand,
                      bounds=bounds, method="highs")
    maximum = linprog(-objective, A_eq=moment_arms, b_eq=demand,
                      bounds=bounds, method="highs")
    if not minimum.success or not maximum.success:
        raise RuntimeError("muscle force interval LP failed on feasible frame")
    if max(np.max(np.abs(moment_arms @ result.x - demand))
           for result in (minimum, maximum)) > 1e-4:
        raise RuntimeError("muscle force interval does not reproduce joint torque")
    return [round(float(minimum.x[index]), 2), round(float(maximum.x[index]), 2)]


def inspect_subject(subject):
    base = DATA / subject
    positions = np.genfromtxt(base / "MJ/T0/humanPositions.csv", delimiter=",", names=True)
    torques = np.genfromtxt(base / "MJ/T0/muscleTorque.csv", delimiter=",", names=True)
    if len(positions) != len(torques) or np.max(np.abs(positions["TIME"] - torques["time"])) > 1e-6:
        raise ValueError(f"{subject}: positions and torque time axes differ")
    # OpenSim's Windows C++ file loader needs an ASCII relative path here.
    model = osim.Model(f".cache/upper-limb-torque/{subject}/scaledModel.osim")
    state = model.initSystem()
    coordinate_set = model.getCoordinateSet()
    muscle_set = model.getMuscles()
    muscles = [muscle_set.get(index) for index in range(muscle_set.getSize())]
    names = [muscle.getName() for muscle in muscles]
    fmax = np.array([muscle.getMaxIsometricForce() for muscle in muscles])
    detail_indices = {0, len(positions) // 4, len(positions) // 2,
                      3 * len(positions) // 4, len(positions) - 1}
    indices = set(range(0, len(positions), STRIDE)) | detail_indices
    rows = []
    details = []
    for index in sorted(indices):
        pose = positions[index]
        for name in INPUT_COORDS:
            coordinate_set.get(name).setValue(state, float(pose[name]), False)
        model.assemble(state)
        coordinate_error = max(abs(coordinate_set.get(name).getValue(state) - float(pose[name]))
                               for name in INPUT_COORDS)
        # Constrained dependent coordinates may shift slightly during assemble.
        # Keep the exact error per frame; stop if it exceeds roughly 0.6 degrees.
        if coordinate_error > 0.01:
            raise ValueError(f"{subject} frame {index}: coordinate error {coordinate_error}")
        model.realizePosition(state)
        arms = np.array([[muscle.computeMomentArm(state, coordinate_set.get(name))
                          for muscle in muscles] for name in TARGET_COORDS])
        demand = np.array([float(torques[name][index]) for name in TARGET_COORDS])
        if not np.isfinite(arms).all() or not np.isfinite(demand).all():
            raise ValueError(f"{subject} frame {index}: nonfinite torque data")
        if np.linalg.matrix_rank(arms) != 2:
            raise ValueError(f"{subject} frame {index}: shoulder/elbow moment arms lack rank")
        feasible, residual, outside, bounds = capacity_screen(arms, fmax, demand)
        rows.append({"frame": index, "timeS": round(float(pose["TIME"]), 3),
                     "demandNm": [round(float(value), 3) for value in demand],
                     "feasibleUnderNominalFmax": feasible,
                     "minimumL1TorqueResidualNm": round(residual, 4),
                     "independentCapacityExceeded": [bool(value) for value in outside],
                     "maximumCoordinateErrorRad": coordinate_error})
        if index in detail_indices:
            detail = dict(rows[-1])
            if feasible:
                detail["forceIntervalsN"] = {name: force_interval(
                    arms, demand, bounds, names.index(name))
                    for name in ("PECT", "DELTAnt", "TRILong")}
                detail["intervalWidthFractionOfNominalFmax"] = {
                    name: round((interval[1] - interval[0]) / fmax[names.index(name)], 4)
                    for name, interval in detail["forceIntervalsN"].items()}
            details.append(detail)
    return {"subject": subject, "modelMuscles": len(muscles),
            "frames": len(rows), "feasibleFrames": sum(row["feasibleUnderNominalFmax"] for row in rows),
            "independentShoulderCapacityExceededFrames": sum(
                row["independentCapacityExceeded"][0] for row in rows),
            "independentElbowCapacityExceededFrames": sum(
                row["independentCapacityExceeded"][1] for row in rows),
            "largestMinimumL1TorqueResidualNm": max(
                row["minimumL1TorqueResidualNm"] for row in rows),
            "largestCoordinateErrorRad": max(row["maximumCoordinateErrorRad"] for row in rows),
            "detailFrames": details}


def main():
    os.chdir(ROOT)
    rows = [inspect_subject(subject) for subject in SUBJECTS]
    interval_summary = {}
    for name in ("PECT", "DELTAnt", "TRILong"):
        widths = [detail["intervalWidthFractionOfNominalFmax"][name]
                  for subject in rows for detail in subject["detailFrames"]
                  if "intervalWidthFractionOfNominalFmax" in detail]
        interval_summary[name] = {
            "feasibleDetailFrames": len(widths),
            "medianWidthFractionOfNominalFmax": float(np.median(widths)),
            "framesSpanningAtLeast95PercentOfNominalFmax": int(sum(width >= .95 for width in widths)),
        }
    report = {
        "status": "research_only_nominal_capacity_screen_not_personal_force",
        "source": "https://zenodo.org/records/11209324",
        "license": "CC BY-SA 4.0",
        "task": "MJ/T0 upper-limb tracking, not bench or overhead press",
        "assumption": "0 <= each muscle tension <= its serialized max_isometric_force; instantaneous linear moment-arm torque; no force-length-velocity, passive tissue, reserve actuator, joint coupling or contact",
        "sampleStrideFrames": STRIDE,
        "participants": len(rows), "testedFrames": sum(row["frames"] for row in rows),
        "feasibleFrames": sum(row["feasibleFrames"] for row in rows),
        "independentShoulderCapacityExceededFrames": sum(
            row["independentShoulderCapacityExceededFrames"] for row in rows),
        "independentElbowCapacityExceededFrames": sum(
            row["independentElbowCapacityExceededFrames"] for row in rows),
        "maximumAppliedCoordinateErrorRad": max(
            row["largestCoordinateErrorRad"] for row in rows),
        "largestMinimumL1TorqueResidualNm": max(
            row["largestMinimumL1TorqueResidualNm"] for row in rows),
        "muscleForceIntervalSummary": interval_summary,
        "subjects": rows,
        "limitations": [
            "Even a feasible two-coordinate torque does not identify a unique muscle-force allocation.",
            "The nominal isometric force cap is neither a dynamic eccentric capacity nor a personal strength measurement.",
            "The processed torque target may depend on the source inverse-dynamics conventions and has not been independently replayed from external forces here.",
            "Only shoulder elevation and elbow flexion torques are screened; other coordinates and the exoskeleton interaction are omitted.",
            "No bench, overhead press, or single-muscle ground truth is included.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "participants", "testedFrames", "feasibleFrames",
        "independentShoulderCapacityExceededFrames",
        "independentElbowCapacityExceededFrames")}, indent=2))
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
