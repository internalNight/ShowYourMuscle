"""Compare optimistic hip-rotation capacity on valid deep-squat frames.

The published inverse-dynamics CSV is treated as N m/kg, as established in
the preceding unit audit. This is a model-parameter screen, not proof of
muscle force or physiological strength.
"""

import json
import math

import numpy as np
import opensim as osim

from analyze_dynamic_squats import read_csv
from audit_high_flex_candidate import (CANDIDATE, OUTPUT as RANGE_AUDIT,
                                       ROOT, SUBJECTS, read_ik, set_pose)
from probe_dynamic_squat_muscle_capacity import subject_masses

OUTPUT = ROOT / "docs/data/high_flex_hip_capacity_audit.json"
DEEP_INTERVALS = {"AB01": (51.25, 51.35), "AB02": (23.65, 23.75)}
COORDINATES = ("hip_rotation_r", "hip_rotation_l")


def capacity(model, state, coordinate_name, target_nm):
    coordinate = model.getCoordinateSet().get(coordinate_name)
    sign = 1 if target_nm >= 0 else -1
    return sum(max(sign * muscle.computeMomentArm(state, coordinate), 0.0) *
               muscle.getMaxIsometricForce()
               for muscle in (model.getMuscles().get(index)
                              for index in range(model.getMuscles().getSize())))


def summarize(values):
    array = np.array(values)
    return {"frameCount": len(array), "exceededFrameCount": int(np.sum(array > 1)),
            "medianDemandToCapacity": round(float(np.median(array)), 3),
            "minDemandToCapacity": round(float(np.min(array)), 3),
            "maxDemandToCapacity": round(float(np.max(array)), 3)}


def summarize_absolute_nm(values):
    return {"median": round(float(np.median(values)), 3),
            "min": round(float(np.min(values)), 3),
            "max": round(float(np.max(values)), 3)}


def hip_axis_in_ground(model, state, coordinate_name):
    """Numerically differentiate femur orientation w.r.t. a hip coordinate."""
    coordinate = model.getCoordinateSet().get(coordinate_name)
    joint = model.getJointSet().get("hip_" + coordinate_name[-1])
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
    return axis / np.linalg.norm(axis)


def main():
    osim.Logger.setLevelString("Error")
    range_audit = json.loads(RANGE_AUDIT.read_text(encoding="utf-8"))
    candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
    candidate_state = candidate.initSystem()
    knee_max = candidate.getCoordinateSet().get("knee_angle_r").getRangeMax()
    result = {"status": "research_only_optimistic_independent_hip_upper_bound",
              "sourceModel": "RajagopalLaiUhlrich2023 generic 80 lower-limb muscles",
              "candidateMassKg": round(float(candidate.getTotalMass(candidate_state)), 3),
              "target": "published AB01/AB02 raw inverse-dynamics CSV hip rotation moments, assumed N m/kg and multiplied by participant mass",
              "definition": "same-direction moment arms times maximum isometric force, independently per hip; ignores force-length, coupling, passive tissues and personal strength",
              "frameSelection": "only deepest-interval frames within both knees' 0–140 degree candidate range",
              "subjects": {},
              "limitations": [
                  "candidate mass and segment geometry are not scaled to participants",
                  "hip axes and body geometry are not exactly registered to the gait2354 subject models",
                  "AB01 has only four deepest-interval frames inside range",
                  "released moment convention is strongly supported by no-free-moment ID replay, but exact author processing and AB02 residual remain",
              ]}
    masses = subject_masses()
    for subject, config in SUBJECTS.items():
        source = osim.Model(str(config["source"].relative_to(ROOT)))
        source_state = source.initSystem()
        moments = read_csv(ROOT / ".cache/lower-limb-raw" / subject /
                           "CSV_Data/squats_1/Joint_Moments.csv")
        rows = [row for row in read_ik(config["ik"], config["intervalS"])
                if DEEP_INTERVALS[subject][0] - 1e-7 <= row["time"] <=
                   DEEP_INTERVALS[subject][1] + 1e-7]
        ratios = {name: {"subject54": [], "highFlex80": []}
                  for name in COORDINATES}
        demands = {name: [] for name in COORDINATES}
        capacities = {name: {"subject54": [], "highFlex80": []}
                      for name in COORDINATES}
        axis_dots = {name: [] for name in COORDINATES}
        excluded = 0
        for row in rows:
            if any(math.radians(-row[f"knee_angle_{side}"]) > knee_max + 1e-9
                   for side in ("r", "l")):
                excluded += 1
                continue
            set_pose(source, source_state, row)
            set_pose(candidate, candidate_state, row, flip_knee=True)
            source_index = int(round(row["time"] / 0.005))
            if abs(moments["time"][source_index] - row["time"]) > 1e-6:
                raise ValueError("Joint moment grid mismatch")
            for name in COORDINATES:
                axis_dots[name].append(float(np.dot(
                    hip_axis_in_ground(source, source_state, name),
                    hip_axis_in_ground(candidate, candidate_state, name))))
                demand = float(moments[name + "_moment"][source_index] *
                               masses[subject])
                demands[name].append(abs(demand))
                for key, model, state in (("subject54", source, source_state),
                                          ("highFlex80", candidate,
                                           candidate_state)):
                    upper_bound = capacity(model, state, name, demand)
                    if upper_bound <= 1e-6:
                        raise AssertionError(f"No {name} muscle capacity")
                    ratios[name][key].append(abs(demand) / upper_bound)
                    capacities[name][key].append(upper_bound)
        if len(rows) != 21 or len(rows) - excluded == 0:
            raise AssertionError("Unexpected deep interval selection")
        result["subjects"][subject] = {
            "inputFrameCount": len(rows),
            "excludedOutsideKneeRange": excluded,
            "matchedFrameCount": len(rows) - excluded,
            "participantMassKg": masses[subject],
            "hipRotation": {
                name: {"absoluteMomentDemandNm": summarize_absolute_nm(demands[name]),
                       **{key: {**summarize(values),
                                "optimisticCapacityNm": summarize_absolute_nm(
                                    capacities[name][key])}
                          for key, values in groups.items()}}
                for name, groups in ratios.items()},
            "hipAxisCosineSourceVsCandidate": {
                name: {"min": round(min(values), 5),
                       "median": round(float(np.median(values)), 5),
                       "max": round(max(values), 5)}
                for name, values in axis_dots.items()},
        }
    if result["subjects"]["AB01"]["matchedFrameCount"] != 4 or \
            result["subjects"]["AB02"]["matchedFrameCount"] != 21:
        raise AssertionError("Deep frame range changed")
    if range_audit["model"] != "RajagopalLaiUhlrich2023.osim":
        raise AssertionError("Range audit model mismatch")
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(result["subjects"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
