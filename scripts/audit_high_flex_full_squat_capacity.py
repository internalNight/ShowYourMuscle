"""Screen model-only ten-axis muscle capacity across full measured squat cycles.

This uses measured IK and force-plate inverse dynamics as inputs. The output
cannot predict muscle force from the app's self-reported measurements.
"""

import json
import math
import os

import numpy as np
import opensim as osim

from analyze_dynamic_squat_id_replay import read_storage
from audit_high_flex_candidate import CANDIDATE, ROOT, SUBJECTS, read_ik, set_pose
from audit_high_flex_hip_knee_ankle_capacity import COORDINATES, SIDES, mapped_targets
from audit_high_flex_multiaxis_hip_capacity import minimum_uniform_multiplier
from probe_high_flex_scaled_capacity import ratios_from_dimensions, scale_model
from probe_high_flex_segment_scaling import dimensions

OUTPUT = ROOT / "docs/data/high_flex_full_squat_capacity.json"
WINDOWS = {"AB01": (50.0, 52.0), "AB02": (23.0, 25.0)}


def summarize(values):
    if not values:
        return None
    return {"minimum": round(float(min(values)), 4),
            "median": round(float(np.median(values)), 4),
            "maximum": round(float(max(values)), 4)}


def main():
    os.chdir(ROOT)
    osim.Logger.setLevelString("Error")
    report = {
        "status": "research_only_measured_ik_id_feasibility_not_personal_force",
        "source": "AB01 and AB02 original squat IK plus independently replayed no-free-moment ID",
        "candidate": "RajagopalLaiUhlrich2023 80-muscle model scaled to source joint-center dimensions and total mass",
        "sampling": "one frame every 20 ms across each two-second window; skip poses beyond candidate knee range",
        "coordinates": COORDINATES,
        "definitions": {
            "nominal": "minimum common multiplier of all maximum isometric forces to balance ten hip, knee and ankle axes with nonnegative tensions",
            "passiveAdjusted": "same problem after subtracting model passive fiber-along-tendon moment at one-percent activation and zero coordinate speeds",
        },
        "limitations": [
            "IK and inverse-dynamics torques are measured-data inputs, not predicted from phone measurements",
            "nominal and passive-adjusted LPs ignore fiber force-length-velocity effects, co-contraction, other joints, and contact mechanics",
            "candidate strength and muscle paths have no individual calibration; no muscle-force coloring is justified",
            "twenty-millisecond sampling can miss shorter capacity peaks",
        ],
        "subjects": {},
    }
    for subject, config in SUBJECTS.items():
        source = osim.Model(str(config["source"].relative_to(ROOT)))
        source_state = source.initSystem()
        candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
        candidate_state = candidate.initSystem()
        reference = read_ik(config["ik"], config["intervalS"])[0]
        set_pose(source, source_state, reference)
        set_pose(candidate, candidate_state, reference, flip_knee=True)
        factors = ratios_from_dimensions(dimensions(source, source_state, "knee"),
                                         dimensions(candidate, candidate_state,
                                                    "walker_knee"))
        scale_model(candidate, candidate_state, factors,
                    float(source.getTotalMass(source_state)))
        muscles = [candidate.getMuscles().get(i)
                   for i in range(candidate.getMuscles().getSize())]
        maximum_forces = np.array([muscle.getMaxIsometricForce()
                                   for muscle in muscles])
        replay = read_storage(ROOT / ".cache/lower-limb/id-reproduction" /
                              f"{subject}_id_{'50_52' if subject == 'AB01' else '23_25'}_no_free_moment.sto")
        rows = read_ik(config["ik"], WINDOWS[subject])
        if len(rows) != 401:
            raise AssertionError(f"Unexpected two-second IK row count: {subject}")
        sample = rows[::4]
        knee_max = candidate.getCoordinateSet().get("knee_angle_r").getRangeMax()
        records = []
        excluded = []
        for row in sample:
            if any(math.radians(-row[f"knee_angle_{side}"]) > knee_max + 1e-9
                   for side in SIDES):
                excluded.append(round(row["time"], 3))
                continue
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
            nominal = minimum_uniform_multiplier(arms, maximum_forces, targets)
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
            passive = minimum_uniform_multiplier(
                arms, maximum_forces, targets - arms @ passive_forces)
            records.append({
                "timeS": round(row["time"], 3),
                "rightKneeFlexionDeg": round(-row["knee_angle_r"], 2),
                "minimumAbsoluteKneeAnkleAxisCosine": round(min(
                    abs(value) for value in alignment.values()), 6),
                "nominal": nominal,
                "passiveAdjusted": passive,
            })
        if len(sample) != 101:
            raise AssertionError("Unexpected 20 ms sampling count")
        nominal_values = [frame["nominal"].get("minimumUniformFmaxMultiplier")
                          for frame in records]
        passive_values = [frame["passiveAdjusted"].get(
            "minimumUniformFmaxMultiplier") for frame in records]
        report["subjects"][subject] = {
            "totalSampledFrames": len(sample),
            "excludedOutsideKneeRange": len(excluded),
            "excludedTimesS": excluded,
            "feasibleAtAnyUniformStrength": sum(value is not None
                                                for value in nominal_values),
            "nominalStrengthFeasible": sum(
                frame["nominal"].get("atNominalStrengthFeasible", False)
                for frame in records),
            "nominalMultiplier": summarize([x for x in nominal_values
                                             if x is not None]),
            "passiveAdjustedMultiplier": summarize([x for x in passive_values
                                                     if x is not None]),
            "minimumKneeAnkleAxisCosine": min(
                frame["minimumAbsoluteKneeAnkleAxisCosine"]
                for frame in records),
            "frames": records,
        }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({subject: {key: value for key, value in data.items()
                                if key not in ("frames", "excludedTimesS")}
                      for subject, data in report["subjects"].items()},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
