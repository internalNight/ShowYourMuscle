"""Research-only ten-axis lower-limb feasibility screen on measured squats."""

import json
import math
import os

import numpy as np
import opensim as osim

from analyze_dynamic_squat_id_replay import read_storage
from audit_high_flex_candidate import CANDIDATE, ROOT, SUBJECTS, read_ik, set_pose
from audit_high_flex_hip_capacity import DEEP_INTERVALS, hip_axis_in_ground
from audit_high_flex_multiaxis_hip_capacity import minimum_uniform_multiplier
from probe_high_flex_scaled_capacity import ratios_from_dimensions, scale_model
from probe_high_flex_segment_scaling import dimensions

OUTPUT = ROOT / "docs/data/high_flex_hip_knee_ankle_capacity.json"
SIDES = ("r", "l")
SINGLE_JOINTS = ("knee_angle", "ankle_angle")
COORDINATES = tuple(f"{name}_{side}" for side in SIDES for name in
                    ("hip_flexion", "hip_adduction", "hip_rotation", *SINGLE_JOINTS))


def joint_axis(model, state, coordinate_name, joint_name):
    """Finite difference the child-frame orientation against one coordinate."""
    coordinate = model.getCoordinateSet().get(coordinate_name)
    joint = model.getJointSet().get(joint_name)
    original = coordinate.getValue(state)
    epsilon = 1e-5

    def orientation(value):
        coordinate.setValue(state, value, False)
        model.realizePosition(state)
        rotation = joint.getChildFrame().getTransformInGround(state).R()
        return np.array([[rotation.get(i, j) for j in range(3)]
                         for i in range(3)])

    try:
        positive = orientation(original + epsilon)
        negative = orientation(original - epsilon)
    finally:
        coordinate.setValue(state, original, False)
        model.realizePosition(state)
    relative = positive @ negative.T
    axis = np.array([relative[2, 1] - relative[1, 2],
                     relative[0, 2] - relative[2, 0],
                     relative[1, 0] - relative[0, 1]])
    norm = float(np.linalg.norm(axis))
    if norm < 1e-8:
        raise AssertionError(f"Unresolved axis for {coordinate_name}")
    return axis / norm


def mapped_targets(source, source_state, candidate, candidate_state, torques):
    """Map matching hip triples and near-parallel knee and ankle moments."""
    values = []
    axis_alignment = {}
    for side in SIDES:
        source_axes = np.column_stack([
            hip_axis_in_ground(source, source_state, f"{axis}_{side}")
            for axis in ("hip_flexion", "hip_adduction", "hip_rotation")])
        candidate_axes = np.column_stack([
            hip_axis_in_ground(candidate, candidate_state, f"{axis}_{side}")
            for axis in ("hip_flexion", "hip_adduction", "hip_rotation")])
        source_torques = np.array([
            torques[f"{axis}_{side}"] for axis in
            ("hip_flexion", "hip_adduction", "hip_rotation")])
        if abs(np.linalg.det(source_axes)) < 0.2:
            raise AssertionError("Source hip axes are poorly conditioned")
        moment_vector = np.linalg.solve(source_axes.T, source_torques)
        values.extend((candidate_axes.T @ moment_vector).tolist())
        for name in SINGLE_JOINTS:
            coordinate_name = f"{name}_{side}"
            joint_base = {"knee_angle": "knee"}.get(name, name.split("_angle")[0])
            source_joint = f"{joint_base}_{side}"
            candidate_joint = (f"walker_knee_{side}" if name == "knee_angle"
                               else source_joint)
            source_axis = joint_axis(source, source_state, coordinate_name,
                                     source_joint)
            candidate_axis = joint_axis(candidate, candidate_state,
                                        coordinate_name, candidate_joint)
            cosine = float(np.dot(source_axis, candidate_axis))
            if abs(cosine) < 0.95:
                raise AssertionError(f"Unmatched {coordinate_name} axis: {cosine}")
            axis_alignment[coordinate_name] = round(cosine, 6)
            values.append(torques[coordinate_name] * cosine)
    return np.array(values), axis_alignment


def main():
    os.chdir(ROOT)
    osim.Logger.setLevelString("Error")
    report = {
        "status": "research_only_full_leg_feasibility_not_muscle_force",
        "coordinateNames": COORDINATES,
        "model": "RajagopalLaiUhlrich2023; segment length and total mass scaled",
        "target": "no-free-forceplate-moment OpenSim ID from source subject model, projected to matching candidate axes",
        "method": "minimum common multiplier of 80 nominal maximum isometric forces balancing ten bilateral hip, knee and ankle generalized moments with nonnegative tensions",
        "limitations": [
            "knee and ankle projection ignores out-of-axis moments; matching axes must differ by under about 18 degrees",
            "candidate subtalar and MTP coordinates are locked and excluded from these ten axes",
            "candidate has no individualized muscle strength or measured-marker registration",
            "the passive-adjusted comparison uses 1 percent activation and zero speed at static fiber equilibrium; it excludes velocity effects, ligaments and individual tissue calibration",
            "fiber dynamics, pelvis and lumbar loads, contact constraints, and co-contraction are omitted",
            "this is a mathematical feasibility diagnostic, not personal muscle-force estimation",
        ],
        "subjects": {},
    }
    for subject, config in SUBJECTS.items():
        source = osim.Model(str(config["source"].relative_to(ROOT)))
        source_state = source.initSystem()
        candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
        candidate_state = candidate.initSystem()
        rows = read_ik(config["ik"], config["intervalS"])
        set_pose(source, source_state, rows[0])
        set_pose(candidate, candidate_state, rows[0], flip_knee=True)
        factors = ratios_from_dimensions(dimensions(source, source_state, "knee"),
                                         dimensions(candidate, candidate_state,
                                                    "walker_knee"))
        scale_model(candidate, candidate_state, factors,
                    float(source.getTotalMass(source_state)))
        muscles = [candidate.getMuscles().get(i)
                   for i in range(candidate.getMuscles().getSize())]
        maximum_forces = np.array([muscle.getMaxIsometricForce()
                                   for muscle in muscles])
        replay_path = (ROOT / ".cache/lower-limb/id-reproduction" /
                       f"{subject}_id_{'50_52' if subject == 'AB01' else '23_25'}_no_free_moment.sto")
        replay = read_storage(replay_path)
        knee_max = candidate.getCoordinateSet().get("knee_angle_r").getRangeMax()
        selected = [row for row in rows if
                    DEEP_INTERVALS[subject][0] - 1e-7 <= row["time"] <=
                    DEEP_INTERVALS[subject][1] + 1e-7 and
                    all(math.radians(-row[f"knee_angle_{side}"]) <= knee_max + 1e-9
                        for side in SIDES)]
        frames = []
        for row in selected:
            set_pose(source, source_state, row)
            set_pose(candidate, candidate_state, row, flip_knee=True)
            index = int(round((row["time"] - replay["time"][0]) / 0.005))
            if abs(replay["time"][index] - row["time"]) > 1e-6:
                raise AssertionError("IK/ID time grids differ")
            torques = {name: float(replay[name + "_moment"][index])
                       for name in COORDINATES}
            targets, alignment = mapped_targets(source, source_state, candidate,
                                                candidate_state, torques)
            arms = np.array([[muscle.computeMomentArm(
                candidate_state, candidate.getCoordinateSet().get(name))
                for muscle in muscles] for name in COORDINATES])
            feasibility = minimum_uniform_multiplier(arms, maximum_forces,
                                                       targets)
            for coordinate_index in range(candidate.getCoordinateSet().getSize()):
                candidate.getCoordinateSet().get(coordinate_index).setSpeedValue(
                    candidate_state, 0.0)
            for muscle in muscles:
                muscle.setActivation(candidate_state, 0.01)
            candidate.equilibrateMuscles(candidate_state)
            candidate.realizeDynamics(candidate_state)
            passive_forces = np.array([
                muscle.getPassiveFiberForceAlongTendon(candidate_state)
                for muscle in muscles])
            passive_torques = arms @ passive_forces
            passive_adjusted = minimum_uniform_multiplier(
                arms, maximum_forces, targets - passive_torques)
            frames.append({"timeS": round(row["time"], 3),
                           "axisAlignment": alignment, **feasibility,
                           "passiveTorqueNm": np.round(passive_torques, 3).tolist(),
                           "passiveAdjusted": passive_adjusted})
        report["subjects"][subject] = {
            "matchedFrames": len(frames),
            "feasibleAtAnyUniformStrength": sum(
                frame["feasibleAtAnyUniformStrength"] for frame in frames),
            "feasibleAtNominalStrength": sum(
                frame.get("atNominalStrengthFeasible", False) for frame in frames),
            "medianMinimumUniformFmaxMultiplier": round(float(np.median([
                frame["minimumUniformFmaxMultiplier"] for frame in frames])), 4)
                if all(frame["feasibleAtAnyUniformStrength"] for frame in frames)
                else None,
            "medianPassiveAdjustedMultiplier": round(float(np.median([
                frame["passiveAdjusted"]["minimumUniformFmaxMultiplier"]
                for frame in frames])), 4)
                if all(frame["passiveAdjusted"]["feasibleAtAnyUniformStrength"]
                       for frame in frames) else None,
            "minimumAbsoluteKneeAnkleAxisCosine": round(min(
                abs(cosine) for frame in frames
                for cosine in frame["axisAlignment"].values()), 6),
            "minimumUniformFmaxMultiplierRange": [
                min(frame["minimumUniformFmaxMultiplier"] for frame in frames),
                max(frame["minimumUniformFmaxMultiplier"] for frame in frames)]
                if all(frame["feasibleAtAnyUniformStrength"] for frame in frames)
                else None,
            "frames": frames,
        }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({name: {key: value for key, value in group.items()
                              if key != "frames"} for name, group in
                      report["subjects"].items()}, indent=2))


if __name__ == "__main__":
    main()
