"""Research-only static muscle allocation on matched squat frames.

Uses source-subject OpenSim moment arms and max isometric forces, but omits
muscle-tendon dynamics and missing pelvis/lumbar kinematics. Outputs must stay
outside the phone app until force and EMG validation are established.
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
import opensim as osim
from scipy.optimize import lsq_linear

from analyze_dynamic_squats import ANGLE_LIMITS_DEG, ROOT, load_trial, match_phase
from probe_dynamic_squat_muscle_capacity import ANGLE_NAMES, RAW, subject_masses


GROUPS = {
    "glut_max": ("glut_max1", "glut_max2", "glut_max3"),
    "biceps_femoris": ("bifemlh", "bifemsh"),
    "vastus_intermedius": ("vas_int",),
    "rectus_femoris": ("rect_fem",),
}


def solve_frame(model, state, coordinates, muscles, strengths, trial, frame, mass,
                regularization_nm):
    for name, value in zip(ANGLE_NAMES, trial["angle"][frame]):
        coordinates.get(name).setValue(state, float(np.deg2rad(value)), False)
    model.realizePosition(state)
    muscles = muscles["r"]
    strengths = strengths["r"]
    names = ("hip_flexion_r", "knee_angle_r", "ankle_angle_r")
    arms = np.array([[muscle.computeMomentArm(state, coordinates.get(name))
                      for muscle in muscles] for name in names])
    torque = np.array([trial["moment"][name + "_moment"][frame] * mass
                       for name in names])
    matrix = arms * strengths
    # A small activation penalty selects one of many possible force allocations;
    # this is an arbitrary modeling choice and part of sensitivity analysis.
    reg = regularization_nm * np.eye(len(muscles))
    solution = lsq_linear(np.vstack((matrix, reg)),
                          np.r_[torque, np.zeros(len(muscles))],
                          bounds=(0, 1), tol=1e-8, max_iter=100)
    predicted = matrix @ solution.x
    force = solution.x * strengths
    grouped = {}
    for group, stems in GROUPS.items():
        selected = [j for j, muscle in enumerate(muscles)
                    if any(muscle.getName() == stem + "_r" for stem in stems)]
        grouped[group] = float(np.sum(force[selected]))
    return {"residual_nm": torque - predicted,
            "group_force_n": grouped,
            "max_activation": float(np.max(solution.x)),
            "optimizer_success": bool(solution.success)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="AB01")
    parser.add_argument("--stride", type=int, default=5,
                        help="Use every Nth matched loaded frame in each phase")
    parser.add_argument("--regularization-nm", type=float, default=5)
    parser.add_argument("--glut-max-strength-scale", type=float, default=1)
    parser.add_argument("--biceps-femoris-strength-scale", type=float, default=1)
    parser.add_argument("--output", type=Path,
                        default=ROOT / ".cache/lower-limb/static_optimization_pilot.json")
    args = parser.parse_args()
    if (args.stride < 1 or args.regularization_nm <= 0
            or args.glut_max_strength_scale <= 0
            or args.biceps_femoris_strength_scale <= 0):
        parser.error("Stride, regularization and strength scales must be positive")
    trials = {load: load_trial(args.subject, load) for load in ("0lbs", "25lbs")}
    model_path = RAW / args.subject / "Models" / f"{args.subject}-Scaled1.osim"
    model = osim.Model(os.path.relpath(model_path))
    state = model.initSystem()
    coordinates = model.getCoordinateSet()
    muscles = {side: [model.getMuscles().get(i)
                      for i in range(model.getMuscles().getSize())
                      if model.getMuscles().get(i).getName().endswith("_" + side)]
               for side in ("r", "l")}
    strengths = {side: np.array([x.getMaxIsometricForce() for x in values])
                 for side, values in muscles.items()}
    for index, muscle in enumerate(muscles["r"]):
        if any(muscle.getName() == stem + "_r" for stem in GROUPS["glut_max"]):
            strengths["r"][index] *= args.glut_max_strength_scale
        if any(muscle.getName() == stem + "_r" for stem in GROUPS["biceps_femoris"]):
            strengths["r"][index] *= args.biceps_femoris_strength_scale
    mass = subject_masses()[args.subject]
    report = {
        "subject": args.subject,
        "status": "research_only_unvalidated_static_allocation",
        "assumptions": "CSV moments treated as Nm/kg; only right hip/knee/ankle; max isometric force limits; no force-length/velocity or passive tissue; missing pelvis/lumbar coordinates left at model defaults",
        "regularization_nm": args.regularization_nm,
        "glut_max_strength_scale": args.glut_max_strength_scale,
        "biceps_femoris_strength_scale": args.biceps_femoris_strength_scale,
        "stride": args.stride,
        "phases": {},
    }
    for phase in ("descent", "ascent"):
        i, j, _, _, _, _ = match_phase(trials["0lbs"], trials["25lbs"],
                                       phase, ANGLE_LIMITS_DEG, 50)
        i, j = i[::args.stride], j[::args.stride]
        if not len(i):
            continue
        samples = {load: [solve_frame(model, state, coordinates, muscles, strengths,
                                      trials[load], int(index), mass,
                                      args.regularization_nm)
                          for index in indices]
                   for load, indices in (("0lbs", i), ("25lbs", j))}
        result = {"matched_pairs": len(i)}
        for load, values in samples.items():
            residual = np.array([item["residual_nm"] for item in values])
            result[load] = {
                "median_abs_residual_nm": {
                    joint: round(float(value), 3)
                    for joint, value in zip(("hip", "knee", "ankle"),
                                            np.median(np.abs(residual), axis=0))},
                "max_abs_residual_nm": {
                    joint: round(float(value), 3)
                    for joint, value in zip(("hip", "knee", "ankle"),
                                            np.max(np.abs(residual), axis=0))},
                "optimizer_success_rate": round(float(np.mean([
                    item["optimizer_success"] for item in values])), 3),
                "median_group_force_n": {group: round(float(np.median([
                    item["group_force_n"][group] for item in values])), 2)
                    for group in GROUPS},
            }
        result["loaded_to_unloaded_group_force_ratio"] = {
            group: round(result["25lbs"]["median_group_force_n"][group]
                         / result["0lbs"]["median_group_force_n"][group], 3)
            for group in GROUPS
            if result["0lbs"]["median_group_force_n"][group] > 0}
        report["phases"][phase] = result
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(report["phases"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
