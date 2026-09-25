"""Ten-axis capacity against ID recomputed on the candidate itself."""

import json
import math
import os

import numpy as np
import opensim as osim

from analyze_dynamic_squat_id_replay import read_storage
from audit_high_flex_candidate import CANDIDATE, ROOT, SUBJECTS, read_ik, set_pose
from audit_high_flex_hip_knee_ankle_capacity import COORDINATES, SIDES
from audit_high_flex_multiaxis_hip_capacity import minimum_uniform_multiplier
from probe_high_flex_scaled_capacity import ratios_from_dimensions, scale_model
from probe_high_flex_segment_scaling import dimensions

SUBJECT = "AB02"
INTERVAL = (23.6, 23.7)
OUTPUT = ROOT / "docs/data/high_flex_candidate_id_capacity.json"


def summarize(records, key):
    values = [frame[key]["minimumUniformFmaxMultiplier"] for frame in records
              if frame[key]["feasibleAtAnyUniformStrength"]]
    return {
        "feasibleAtAnyMultiplierFrames": len(values),
        "feasibleAtNominalStrengthFrames": sum(
            frame[key].get("atNominalStrengthFeasible", False)
            for frame in records),
        "feasibleAt4p2TimesFrames": sum(value <= 4.2 for value in values),
        "minimum": round(min(values), 4) if values else None,
        "median": round(float(np.median(values)), 4) if values else None,
        "maximum": round(max(values), 4) if values else None,
    }


def main():
    os.chdir(ROOT)
    osim.Logger.setLevelString("Error")
    config = SUBJECTS[SUBJECT]
    source = osim.Model(str(config["source"].relative_to(ROOT)))
    source_state = source.initSystem()
    candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
    state = candidate.initSystem()
    reference = read_ik(config["ik"], config["intervalS"])[0]
    set_pose(source, source_state, reference)
    set_pose(candidate, state, reference, flip_knee=True)
    factors = ratios_from_dimensions(dimensions(source, source_state, "knee"),
                                     dimensions(candidate, state, "walker_knee"))
    scale_model(candidate, state, factors,
                float(source.getTotalMass(source_state)))
    muscles = [candidate.getMuscles().get(i)
               for i in range(candidate.getMuscles().getSize())]
    fmax = np.array([muscle.getMaxIsometricForce() for muscle in muscles])
    id_data = read_storage(ROOT / ".cache/lower-limb/high-flex-candidate-id"
                           / "AB02/candidate_id.sto")
    rows = read_ik(config["ik"], INTERVAL)
    frames = []
    knee_max = candidate.getCoordinateSet().get("knee_angle_r").getRangeMax()
    for row in rows:
        if any(math.radians(-row[f"knee_angle_{side}"]) > knee_max + 1e-9
               for side in SIDES):
            raise AssertionError("Candidate pose outside knee range")
        set_pose(candidate, state, row, flip_knee=True)
        index = int(round((row["time"] - id_data["time"][0]) / 0.005))
        if abs(id_data["time"][index] - row["time"]) > 1e-6:
            raise AssertionError("IK/ID frame mismatch")
        target = np.array([id_data[name + "_moment"][index]
                           for name in COORDINATES])
        arms = np.array([[muscle.computeMomentArm(
            state, candidate.getCoordinateSet().get(name))
            for muscle in muscles] for name in COORDINATES])
        nominal = minimum_uniform_multiplier(arms, fmax, target)
        for coordinate_index in range(candidate.getCoordinateSet().getSize()):
            candidate.getCoordinateSet().get(coordinate_index).setSpeedValue(
                state, 0.0)
        for muscle in muscles:
            muscle.setActivation(state, 0.01)
        candidate.equilibrateMuscles(state)
        candidate.realizeDynamics(state)
        passive_forces = np.array([
            muscle.getPassiveFiberForceAlongTendon(state)
            for muscle in muscles])
        passive = minimum_uniform_multiplier(
            arms, fmax, target - arms @ passive_forces)
        frames.append({"timeS": round(row["time"], 3),
                       "hipRotationTargetNm": {
                           side: round(float(target[COORDINATES.index(
                               f"hip_rotation_{side}")]), 3)
                           for side in SIDES},
                       "nominal": nominal,
                       "passiveAdjusted": passive})
    if len(frames) != 21:
        raise AssertionError("Expected 21 deep-squat frames")
    report = {
        "status": "research_only_candidate_id_capacity_not_personal_muscle_force",
        "subject": SUBJECT,
        "intervalS": INTERVAL,
        "target": "ID recomputed on the scaled candidate using the same measured IK and force plates, without free plate moment",
        "coordinates": COORDINATES,
        "nominal": summarize(frames, "nominal"),
        "passiveAdjusted": summarize(frames, "passiveAdjusted"),
        "limitations": [
            "only ten hip, knee and ankle moments are constrained; pelvis, lumbar and foot constraints are omitted",
            "measured IK and ground forces are inputs, not phone predictions",
            "active capacity is nominal max isometric force times common multiplier; no force-length-velocity or individual calibration",
        ],
        "frames": frames,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"nominal": report["nominal"],
                      "passiveAdjusted": report["passiveAdjusted"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
