"""Exploratory segment-scaled hip-capacity screen for AB01/AB02.

This matches only a few joint-center distances from the source subject models.
It does not calibrate muscle strength, moment axes, anthropometry, or forces.
"""

import json
import math
import subprocess

import numpy as np
import opensim as osim

from analyze_dynamic_squat_id_replay import read_storage
from analyze_dynamic_squats import read_csv
from audit_high_flex_candidate import CANDIDATE, REPO, ROOT, SUBJECTS, read_ik, set_pose
from audit_high_flex_hip_capacity import (COORDINATES, DEEP_INTERVALS,
                                         capacity, hip_axis_in_ground,
                                         summarize, summarize_absolute_nm)
from probe_dynamic_squat_muscle_capacity import subject_masses
from probe_high_flex_segment_scaling import dimensions

OUTPUT = ROOT / "docs/data/high_flex_segment_scaled_capacity.json"


def ratios_from_dimensions(source, generic):
    factors = {"pelvis": source["hipCenterWidthM"] /
               generic["hipCenterWidthM"]}
    for side in ("r", "l"):
        source_side = source[side]
        generic_side = generic[side]
        factors[f"femur_{side}"] = (source_side["effectiveHipToKneeM"] /
                                     generic_side["effectiveHipToKneeM"])
        factors[f"tibia_{side}"] = (source_side["tibiaKneeToAnkleM"] /
                                     generic_side["tibiaKneeToAnkleM"])
        foot_factor = (source_side["footAnkleToMtpM"] /
                       generic_side["footAnkleToMtpM"])
        for body in ("talus", "calcn", "toes"):
            factors[f"{body}_{side}"] = foot_factor
        factors[f"patella_{side}"] = factors[f"femur_{side}"]
    return factors


def scale_model(model, state, factors, target_mass):
    scales = osim.ScaleSet()
    for index in range(model.getBodySet().getSize()):
        body = model.getBodySet().get(index)
        scale = osim.Scale()
        scale.setSegmentName(body.getName())
        factor = factors.get(body.getName(), 1.0)
        scale.setScaleFactors(osim.Vec3(factor, factor, factor))
        scale.setApply(True)
        scales.cloneAndAppend(scale)
    if not model.scale(state, scales, False, target_mass):
        raise RuntimeError("Candidate Model.scale failed")
    if abs(model.getTotalMass(state) - target_mass) > 1e-6:
        raise AssertionError("Scaled model total mass mismatch")


def compare_dimensions(source, candidate):
    names = ("hipCenterWidthM",)
    errors = {name: (candidate[name] - source[name]) / source[name]
              for name in names}
    for side in ("r", "l"):
        for name in ("effectiveHipToKneeM", "tibiaKneeToAnkleM",
                     "footAnkleToMtpM"):
            key = f"{side}.{name}"
            errors[key] = (candidate[side][name] - source[side][name]) / \
                source[side][name]
    return {key: round(value, 6) for key, value in errors.items()}


def resting_passive_moment(model, state, coordinate_name, forces):
    """Signed passive fiber moment at 1% resting activation and zero velocity."""
    coordinate = model.getCoordinateSet().get(coordinate_name)
    return sum(model.getMuscles().get(index).computeMomentArm(
               state, coordinate) * force
               for index, force in enumerate(forces))


def main():
    osim.Logger.setLevelString("Error")
    report = {
        "status": "research_only_segment_scaled_independent_hip_capacity_screen",
        "model": "RajagopalLaiUhlrich2023.osim",
        "candidateRepositoryRevision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "scaleDefinition": "first-frame source/candidate hip-center width, effective hip-knee, knee-ankle, ankle-MTP ratios; uniform factor per affected body; total mass matched to source model",
        "capacityDefinition": "same-direction moment arms times generic maximum isometric force; independent per hip; no force-length or multijoint feasibility",
        "passiveDefinition": "candidate muscle fiber passive force along tendon after static equilibration at 1% activation and zero speed, multiplied by signed moment arm; subtracted from replayed ID demand before comparing with optimistic active capacity",
        "limitations": [
            "joint-center distances from a different model are imperfect anatomy proxies",
            "knee functions and local joint frames differ; match checked only in sampled poses",
            "pelvis scaling is uniform from hip width, not full pelvis measurement",
            "upper body and segment masses are not individually calibrated",
            "candidate maximum muscle forces remain generic after scaling",
            "static passive forces exclude movement-speed damping and ligament or other passive joint structures",
            "source moment units are strongly supported by no-free-moment ID replay, but exact author processing and AB02 residual are not fully known",
            "no optimization, ground-contact, external EMG, or individual strength validation",
        ],
        "subjects": {},
    }
    masses = subject_masses()
    for subject, config in SUBJECTS.items():
        source = osim.Model(str(config["source"].relative_to(ROOT)))
        source_state = source.initSystem()
        candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
        candidate_state = candidate.initSystem()
        all_rows = read_ik(config["ik"], config["intervalS"])
        initial = all_rows[0]
        set_pose(source, source_state, initial)
        set_pose(candidate, candidate_state, initial, flip_knee=True)
        source_dimensions = dimensions(source, source_state, "knee")
        unscaled_dimensions = dimensions(candidate, candidate_state,
                                         "walker_knee")
        unscaled_muscle_forces = {
            candidate.getMuscles().get(index).getName():
            candidate.getMuscles().get(index).getMaxIsometricForce()
            for index in range(candidate.getMuscles().getSize())}
        factors = ratios_from_dimensions(source_dimensions, unscaled_dimensions)
        target_mass = float(source.getTotalMass(source_state))
        scale_model(candidate, candidate_state, factors, target_mass)
        max_force_ratios = [
            candidate.getMuscles().get(index).getMaxIsometricForce() /
            unscaled_muscle_forces[candidate.getMuscles().get(index).getName()]
            for index in range(candidate.getMuscles().getSize())]
        set_pose(candidate, candidate_state, initial, flip_knee=True)
        scaled_dimensions = dimensions(candidate, candidate_state,
                                       "walker_knee")
        initial_errors = compare_dimensions(source_dimensions, scaled_dimensions)
        if max(abs(value) for value in initial_errors.values()) > 1e-4:
            raise AssertionError("First-frame joint distances did not align")
        if max(abs(value - 1.0) for value in max_force_ratios) > 1e-10:
            raise AssertionError("OpenSim changed maximum muscle forces during scaling")
        moments = read_csv(ROOT / ".cache/lower-limb-raw" / subject /
                           "CSV_Data/squats_1/Joint_Moments.csv")
        replay_path = (ROOT / ".cache/lower-limb/id-reproduction" /
                       ("AB01_id_50_52_no_free_moment.sto" if subject == "AB01"
                        else "AB02_id_23_25_no_free_moment.sto"))
        replay_moments = read_storage(replay_path)
        selected = [row for row in all_rows
                    if DEEP_INTERVALS[subject][0] - 1e-7 <= row["time"] <=
                       DEEP_INTERVALS[subject][1] + 1e-7]
        knee_max = candidate.getCoordinateSet().get("knee_angle_r").getRangeMax()
        ratios = {name: [] for name in COORDINATES}
        capacities = {name: [] for name in COORDINATES}
        demands = {name: [] for name in COORDINATES}
        axis_dots = {name: [] for name in COORDINATES}
        replay_ratios = {name: [] for name in COORDINATES}
        replay_demands = {name: [] for name in COORDINATES}
        passive_moments = {name: [] for name in COORDINATES}
        replay_ratios_after_passive = {name: [] for name in COORDINATES}
        deep_errors = []
        for row in selected:
            if any(math.radians(-row[f"knee_angle_{side}"]) > knee_max + 1e-9
                   for side in ("r", "l")):
                continue
            set_pose(source, source_state, row)
            set_pose(candidate, candidate_state, row, flip_knee=True)
            for coordinate_index in range(candidate.getCoordinateSet().getSize()):
                candidate.getCoordinateSet().get(coordinate_index).setSpeedValue(
                    candidate_state, 0.0)
            for muscle_index in range(candidate.getMuscles().getSize()):
                candidate.getMuscles().get(muscle_index).setActivation(
                    candidate_state, 0.01)
            candidate.equilibrateMuscles(candidate_state)
            candidate.realizeDynamics(candidate_state)
            passive_forces = [candidate.getMuscles().get(index).
                              getPassiveFiberForceAlongTendon(candidate_state)
                              for index in range(candidate.getMuscles().getSize())]
            frame_passive_moments = {
                name: resting_passive_moment(candidate, candidate_state,
                                             name, passive_forces)
                for name in COORDINATES}
            deep_errors.append(compare_dimensions(
                dimensions(source, source_state, "knee"),
                dimensions(candidate, candidate_state, "walker_knee")))
            index = int(round(row["time"] / 0.005))
            if abs(moments["time"][index] - row["time"]) > 1e-6:
                raise AssertionError("Moment time grid mismatch")
            replay_index = int(round((row["time"] - replay_moments["time"][0]) /
                                     0.005))
            if abs(replay_moments["time"][replay_index] - row["time"]) > 1e-6:
                raise AssertionError("Replayed ID time grid mismatch")
            for name in COORDINATES:
                moment = float(moments[name + "_moment"][index] *
                               masses[subject])
                replay_demand = float(replay_moments[name + "_moment"][
                    replay_index])
                bound = capacity(candidate, candidate_state, name, moment)
                if bound <= 1e-6:
                    raise AssertionError(f"No {name} capacity")
                ratios[name].append(abs(moment) / bound)
                capacities[name].append(bound)
                demands[name].append(abs(moment))
                replay_bound = capacity(candidate, candidate_state, name,
                                        replay_demand)
                replay_ratios[name].append(abs(replay_demand) / replay_bound)
                replay_demands[name].append(abs(replay_demand))
                passive = frame_passive_moments[name]
                active_target = replay_demand - passive
                if active_target * replay_demand <= 0:
                    raise AssertionError("Passive torque reversed the target direction")
                passive_moments[name].append(passive)
                replay_ratios_after_passive[name].append(
                    abs(active_target) /
                    capacity(candidate, candidate_state, name, active_target))
                axis_dots[name].append(float(np.dot(
                    hip_axis_in_ground(source, source_state, name),
                    hip_axis_in_ground(candidate, candidate_state, name))))
        if len(selected) != 21 or len(deep_errors) == 0:
            raise AssertionError("Unexpected deep-frame selection")
        if len(deep_errors) != (4 if subject == "AB01" else 21):
            raise AssertionError("Valid knee-range frame count changed")
        report["subjects"][subject] = {
            "sourceModel": str(config["source"].relative_to(ROOT)).replace("\\", "/"),
            "sourceIk": str(config["ik"].relative_to(ROOT)).replace("\\", "/"),
            "sourceModelMassKg": round(target_mass, 3),
            "candidateScaledMassKg": round(float(candidate.getTotalMass(
                candidate_state)), 3),
            "bodyUniformScaleFactors": {key: round(value, 5)
                                        for key, value in factors.items()},
            "maxIsometricForceScaleRatioRange": [
                round(min(max_force_ratios), 6),
                round(max(max_force_ratios), 6)],
            "firstFrameDimensionErrorFraction": initial_errors,
            "deepFrameMaximumAbsoluteDimensionErrorFraction": {
                key: round(max(abs(item[key]) for item in deep_errors), 6)
                for key in initial_errors},
            "matchedDeepFrames": len(deep_errors),
            "hipRotation": {
                name: {**summarize(ratios[name]),
                       "absoluteMomentDemandNm": summarize_absolute_nm(
                           demands[name]),
                       "optimisticCapacityNm": summarize_absolute_nm(
                           capacities[name]),
                       "sourceVsScaledAxisCosineMin": round(min(axis_dots[name]),
                                                              6)}
                for name in COORDINATES},
            "replayedIdWithoutForcePlateMomentHipRotation": {
                name: {**summarize(replay_ratios[name]),
                       "absoluteMomentDemandNm": summarize_absolute_nm(
                           replay_demands[name]),
                       "restingPassiveMomentNm": summarize_absolute_nm(
                           passive_moments[name]),
                       "demandAfterPassiveToOptimisticActiveCapacity":
                           summarize(replay_ratios_after_passive[name])}
                for name in COORDINATES},
        }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(report["subjects"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
