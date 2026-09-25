"""Research-only lower bound on strength needed for six measured hip torques.

The observed inverse-dynamics joint torques and IK are inputs. This is an
optimistic feasibility screen, not a prediction or a muscle-force estimate.
"""

import json
import math
import os

import numpy as np
import opensim as osim
from scipy.optimize import linprog

from analyze_dynamic_squat_id_replay import read_storage
from audit_high_flex_candidate import CANDIDATE, ROOT, SUBJECTS, read_ik, set_pose
from audit_high_flex_hip_capacity import DEEP_INTERVALS, hip_axis_in_ground
from probe_high_flex_scaled_capacity import (ratios_from_dimensions,
                                             scale_model)
from probe_high_flex_segment_scaling import dimensions

OUTPUT = ROOT / "docs/data/high_flex_multiaxis_hip_capacity.json"
SIDES = ("r", "l")
AXES = ("hip_flexion", "hip_adduction", "hip_rotation")
COORDINATES = tuple(f"{axis}_{side}" for side in SIDES for axis in AXES)


def hip_axis_matrix(model, state, side):
    return np.column_stack([hip_axis_in_ground(model, state, f"{axis}_{side}")
                            for axis in AXES])


def equivalent_candidate_targets(source, source_state, candidate,
                                 candidate_state, torque_by_name):
    """Map three generalized torques via the physical 3D hip moment vector."""
    targets = []
    diagnostics = {}
    for side in SIDES:
        source_axes = hip_axis_matrix(source, source_state, side)
        candidate_axes = hip_axis_matrix(candidate, candidate_state, side)
        source_generalized = np.array([
            torque_by_name[f"{axis}_{side}"] for axis in AXES])
        determinant = float(np.linalg.det(source_axes))
        if abs(determinant) < 0.2:
            raise AssertionError(f"{side} source hip axes are poorly conditioned")
        physical_moment = np.linalg.solve(source_axes.T, source_generalized)
        mapped = candidate_axes.T @ physical_moment
        targets.extend(mapped.tolist())
        diagnostics[side] = {
            "sourceAxisDeterminant": round(determinant, 6),
            "sameNamedAxisCosines": [round(float(np.dot(source_axes[:, i],
                                                         candidate_axes[:, i])), 6)
                                     for i in range(3)],
            "sourceGeneralizedNm": np.round(source_generalized, 3).tolist(),
            "candidateGeneralizedNm": np.round(mapped, 3).tolist(),
            "physicalMomentNormNm": round(float(np.linalg.norm(physical_moment)), 3),
        }
    return np.array(targets), diagnostics


def minimum_uniform_multiplier(moment_arms, maximum_forces, targets):
    """Minimize s subject to A(Fmax*x)=tau and 0<=x_i<=s."""
    if not (np.all(np.isfinite(moment_arms)) and
            np.all(np.isfinite(maximum_forces)) and
            np.all(np.isfinite(targets))):
        raise AssertionError("Non-finite hip feasibility input")
    count = len(maximum_forces)
    normalized_arms = moment_arms * maximum_forces[None, :] / 100.0
    equality = np.hstack((normalized_arms, np.zeros((len(targets), 1))))
    upper = np.hstack((np.eye(count), -np.ones((count, 1))))
    objective = np.r_[np.zeros(count), 1.0]
    result = linprog(objective, A_ub=upper, b_ub=np.zeros(count),
                     A_eq=equality, b_eq=targets / 100.0,
                     bounds=[(0, None)] * (count + 1), method="highs")
    if not result.success:
        return {"feasibleAtAnyUniformStrength": False,
                "solverStatus": result.message}
    residual = np.max(np.abs(moment_arms @ (maximum_forces * result.x[:count])
                             - targets))
    if residual > 1e-5:
        raise AssertionError(f"Hip torque reconstruction residual {residual} N.m")
    independent_lower_bounds = []
    for row, target in zip(moment_arms, targets):
        capacity = np.sum(np.maximum(np.sign(target) * row, 0.0)
                          * maximum_forces)
        independent_lower_bounds.append(abs(target) / capacity)
    return {"feasibleAtAnyUniformStrength": True,
            "minimumUniformFmaxMultiplier": round(float(result.x[-1]), 4),
            "largestIndependentAxisLowerBound": round(max(independent_lower_bounds), 4),
            "minimumJointlyFeasibleAboveIndependentBound": round(
                float(result.x[-1]) - max(independent_lower_bounds), 4),
            "largestTorqueResidualNm": round(float(residual), 8),
            "atNominalStrengthFeasible": bool(result.x[-1] <= 1 + 1e-7)}


def main():
    os.chdir(ROOT)
    osim.Logger.setLevelString("Error")
    report = {
        "status": "research_only_multiaxis_strength_feasibility_not_personal_force",
        "candidateModel": "RajagopalLaiUhlrich2023.osim; segment-scaled to source model joint-center distances and total mass",
        "targetDefinition": "same subject 3D hip moment reconstructed from no-free-forceplate-moment OpenSim ID for six hip coordinates, then projected onto candidate axes",
        "optimization": "minimum common multiplier s of all 80 nominal maximum isometric forces so six hip torques can be balanced simultaneously with nonnegative muscle tensions; ignores all other joint torques",
        "limitations": [
            "source IK and inverse-dynamics joint torques are supplied as inputs, not predicted from phone parameters",
            "single common strength multiplier is a mathematical diagnostic, not measured individual strength",
            "muscle force-length-velocity, passive tissue, co-contraction, other joints, and full contact constraints are omitted",
            "candidate remains anatomically unregistered and lacks individual muscle calibration",
            "no solution here can be displayed as personal muscle-force coloring",
        ],
        "subjects": {},
    }
    for subject, config in SUBJECTS.items():
        source = osim.Model(str(config["source"].relative_to(ROOT)))
        source_state = source.initSystem()
        candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
        candidate_state = candidate.initSystem()
        all_rows = read_ik(config["ik"], config["intervalS"])
        initial = all_rows[0]
        set_pose(source, source_state, initial)
        set_pose(candidate, candidate_state, initial, flip_knee=True)
        factors = ratios_from_dimensions(dimensions(source, source_state, "knee"),
                                         dimensions(candidate, candidate_state,
                                                    "walker_knee"))
        scale_model(candidate, candidate_state, factors,
                    float(source.getTotalMass(source_state)))
        maximum_forces = np.array([
            candidate.getMuscles().get(i).getMaxIsometricForce()
            for i in range(candidate.getMuscles().getSize())])
        if len(maximum_forces) != 80 or np.any(maximum_forces <= 0):
            raise AssertionError("Unexpected candidate muscle strengths")
        replay_path = (ROOT / ".cache/lower-limb/id-reproduction" /
                       ("AB01_id_50_52_no_free_moment.sto" if subject == "AB01"
                        else "AB02_id_23_25_no_free_moment.sto"))
        replay = read_storage(replay_path)
        knee_max = candidate.getCoordinateSet().get("knee_angle_r").getRangeMax()
        selected = [row for row in all_rows if
                    DEEP_INTERVALS[subject][0] - 1e-7 <= row["time"] <=
                    DEEP_INTERVALS[subject][1] + 1e-7 and
                    all(math.radians(-row[f"knee_angle_{side}"]) <= knee_max + 1e-9
                        for side in SIDES)]
        frames = []
        muscles = [candidate.getMuscles().get(i)
                   for i in range(candidate.getMuscles().getSize())]
        for row in selected:
            set_pose(source, source_state, row)
            set_pose(candidate, candidate_state, row, flip_knee=True)
            index = int(round((row["time"] - replay["time"][0]) / 0.005))
            if abs(replay["time"][index] - row["time"]) > 1e-6:
                raise AssertionError("IK/ID time grids differ")
            released_torques = {name: float(replay[name + "_moment"][index])
                                for name in COORDINATES}
            mapped_targets, axes = equivalent_candidate_targets(
                source, source_state, candidate, candidate_state,
                released_torques)
            moment_arms = np.array([
                [muscle.computeMomentArm(
                    candidate_state, candidate.getCoordinateSet().get(name))
                 for muscle in muscles] for name in COORDINATES])
            result = minimum_uniform_multiplier(moment_arms, maximum_forces,
                                                 mapped_targets)
            frames.append({"timeS": round(row["time"], 3),
                           "axisMapping": axes, **result})
        if len(frames) != (4 if subject == "AB01" else 21):
            raise AssertionError(f"Unexpected {subject} valid deep frames")
        valid = [item["minimumUniformFmaxMultiplier"] for item in frames
                 if item["feasibleAtAnyUniformStrength"]]
        independent = [item["largestIndependentAxisLowerBound"]
                       for item in frames if item["feasibleAtAnyUniformStrength"]]
        report["subjects"][subject] = {
            "matchedFrames": len(frames),
            "framesFeasibleAtAnyUniformStrength": len(valid),
            "framesFeasibleAtNominalStrength": sum(
                item.get("atNominalStrengthFeasible", False) for item in frames),
            "medianMinimumUniformFmaxMultiplier": round(float(np.median(valid)), 4)
                if valid else None,
            "medianLargestIndependentAxisLowerBound": round(
                float(np.median(independent)), 4) if independent else None,
            "rangeMinimumUniformFmaxMultiplier": [round(min(valid), 4),
                                                    round(max(valid), 4)] if valid else None,
            "frames": frames,
        }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({name: {key: value for key, value in group.items()
                              if key != "frames"}
                      for name, group in report["subjects"].items()},
                     ensure_ascii=False, indent=2))
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
