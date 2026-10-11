"""Length-dependent muscle capacity at the deep-squat frames.

The repository's capacity audit uses an "optimistic independent upper bound": each muscle's maximum
isometric force times its moment arm, with no force-length relation. That bound is deliberately too
high, and the audit found the experimental right-knee demand exceeds it by 15-22%. Since 142 deg of
knee flexion is far from the quadriceps' optimal length, the honest question is what the same model
can produce *at that length*.

This probe answers it without changing any input:
  * per coordinate, over the same 21-frame interval, the demand against both the maximum-isometric
    bound and a length-dependent isometric bound (active force-length factor and pennation included);
  * the knee decomposition at the target frame, so every newton-metre of the bound is attributable;
  * a knee-angle sweep at the same hip pose, to show how the model's extensor capacity varies with
    depth and to expose the pose range where the model's own hamstring moment arm changes sign.

It reports model capacity only. Nothing here is a measurement of a person, and no muscle force is
solved.
"""

import json
import sys
from pathlib import Path

import numpy as np
import opensim as osim

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_dynamic_squats import read_csv  # noqa: E402
from audit_bilateral_joint_capacity import CONFIGS, read_ik_nearest  # noqa: E402
from audit_full_bilateral_static_optimization import read_sto  # noqa: E402
from export_bilateral_squat_blender_data import apply_row  # noqa: E402
from probe_dynamic_squat_muscle_capacity import subject_masses  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/data/bilateral_deep_squat_length_capacity.json"
COORDINATES = ("knee_angle_r", "knee_angle_l", "hip_flexion_r", "hip_adduction_r",
               "ankle_angle_r", "hip_rotation_r", "lumbar_extension")
SWEEP_ANGLES_DEG = (0.0, -20.0, -40.0, -60.0, -80.0, -100.0, -120.0, -135.0)


def model_path_for(subject):
    return (ROOT / ".cache/lower-limb-raw" / subject / "Models" /
            f"{subject}-Scaled1.osim")


def muscle_forces(model, muscles, state):
    """Maximum isometric force and the force available at the pose's fibre length."""
    maximum = np.array([muscle.getMaxIsometricForce() for muscle in muscles])
    length_dependent = np.array([
        muscle.getMaxIsometricForce() * muscle.getActiveForceLengthMultiplier(state) *
        np.cos(muscle.getPennationAngle(state)) for muscle in muscles])
    return maximum, length_dependent


def capacity(arms, forces, target):
    same_direction = arms if target >= 0 else -arms
    return np.maximum(same_direction, 0) * forces


def analyse_subject(subject):
    config = CONFIGS[subject]
    ik_start, ik_end = config["ikInterval"]
    target_time_s = config["targetTimeS"]
    interval_s = config["capacityIntervalS"]
    ik_path = ROOT / f".cache/lower-limb/{subject}_ik_{ik_start}_{ik_end}.mot"
    id_path = ROOT / f".cache/lower-limb/id-reproduction/{subject}_id_{ik_start}_{ik_end}.sto"
    source_moment_path = (ROOT / ".cache/lower-limb-raw" / subject /
                          "CSV_Data/squats_1/Joint_Moments.csv")
    osim.Logger.setLevelString("Error")
    names, id_values = read_sto(id_path)
    source_moments = read_csv(source_moment_path)
    subject_mass = subject_masses()[subject]
    model = osim.Model(str(model_path_for(subject).relative_to(ROOT)))
    state = model.initSystem()
    muscles = [model.getMuscles().get(i) for i in range(model.getMuscles().getSize())]
    muscle_names = [muscle.getName() for muscle in muscles]
    if not muscles:
        raise ValueError("Model has no muscles")

    report = {"subject": subject, "timeS": target_time_s, "muscleCount": len(muscles),
              "modelPath": str(model_path_for(subject).relative_to(ROOT)),
              "intervalS": list(interval_s), "coordinates": {}, "interval": {},
              "targetFrame": {}, "kneeAngleSweep": {}}

    interval_rows = {name: [] for name in COORDINATES}
    target_row = None
    for moment_row in id_values:
        time_s = float(moment_row[0])
        if not interval_s[0] - 1e-6 <= time_s <= interval_s[1] + 1e-6:
            continue
        apply_row(model, state, read_ik_nearest(time_s, ik_path))
        # Moment arms are read from the posed state before equilibrating the muscles, so the
        # maximum-isometric bound here reproduces the repository's capacity audit exactly; the
        # force-length factor then comes from the equilibrated state at the same pose.
        arms_by_coordinate = {name: np.array([
            muscle.computeMomentArm(state, model.getCoordinateSet().get(name))
            for muscle in muscles]) for name in COORDINATES}
        model.equilibrateMuscles(state)
        targets = dict(zip(names[1:], moment_row[1:]))
        source_index = int(round(time_s / 0.005))
        if abs(source_moments["time"][source_index] - time_s) > 1e-6:
            raise ValueError("Source moment time grid mismatch")
        maximum, length_dependent = muscle_forces(model, muscles, state)
        if abs(time_s - target_time_s) < 1e-6:
            target_row = (targets, source_index, maximum, length_dependent, state,
                          arms_by_coordinate)
        for name in COORDINATES:
            target = float(targets[name + "_moment"])
            arms = arms_by_coordinate[name]
            bound = float(capacity(arms, maximum, target).sum())
            length_bound = float(capacity(arms, length_dependent, target).sum())
            entry = {"demandNm": target,
                     "maximumBoundNm": bound, "lengthBoundNm": length_bound,
                     "demandToMaximumBound": abs(target) / bound if bound > 1e-6 else None,
                     "demandToLengthBound": (abs(target) / length_bound
                                             if length_bound > 1e-6 else None)}
            if name + "_moment" in source_moments:
                source_target = float(source_moments[name + "_moment"][source_index] *
                                      subject_mass)
                source_length_bound = float(capacity(arms, length_dependent, source_target).sum())
                entry["sourceCsvDemandNm"] = source_target
                entry["sourceCsvDemandToLengthBound"] = (
                    abs(source_target) / source_length_bound
                    if source_length_bound > 1e-6 else None)
            interval_rows[name].append(entry)

    for name, rows in interval_rows.items():
        with_source = [row for row in rows if "sourceCsvDemandNm" in row]
        report["interval"][name] = {
            "frameCount": len(rows),
            "medianDemandToMaximumBound": round(float(np.median(
                [row["demandToMaximumBound"] for row in rows])), 3),
            "medianDemandToLengthBound": round(float(np.median(
                [row["demandToLengthBound"] for row in rows])), 3),
            "framesExceedingLengthBound": int(sum(
                1 for row in rows if row["demandToLengthBound"] > 1)),
            # The replay and the published CSV are two independent estimates of the demand; where they
            # disagree, the demand is not known well enough to compare against a capacity at all.
            "medianSourceCsvDemandToLengthBound": (round(float(np.median(
                [row["sourceCsvDemandToLengthBound"] for row in with_source])), 3)
                if with_source else None),
            "framesExceedingSourceCsvLengthBound": (int(sum(
                1 for row in with_source if row["sourceCsvDemandToLengthBound"] > 1))
                if with_source else None),
            "medianReplayVsSourceCsvDifferenceNm": (round(float(np.median(
                [abs(row["demandNm"] - row["sourceCsvDemandNm"]) for row in with_source])), 3)
                if with_source else None),
        }

    targets, source_index, maximum, length_dependent, state, target_arms = target_row
    for name in COORDINATES:
        target = float(targets[name + "_moment"])
        arms = target_arms[name]
        bound = capacity(arms, maximum, target)
        length_bound = capacity(arms, length_dependent, target)
        entry = {
            "demandNm": round(target, 3),
            "maximumBoundNm": round(float(bound.sum()), 3),
            "lengthBoundNm": round(float(length_bound.sum()), 3),
            "demandToMaximumBound": round(abs(target) / float(bound.sum()), 3),
            "demandToLengthBound": round(abs(target) / float(length_bound.sum()), 3),
            "muscles": [{"muscle": muscle_names[index],
                         "momentArmCm": round(float(arms[index]) * 100, 3),
                         "maxIsometricForceN": round(float(maximum[index]), 1),
                         "activeForceLength": round(float(
                             muscles[index].getActiveForceLengthMultiplier(state)), 4),
                         "pennationDeg": round(float(np.degrees(
                             muscles[index].getPennationAngle(state))), 2),
                         "maximumCapacityNm": round(float(bound[index]), 3),
                         "lengthCapacityNm": round(float(length_bound[index]), 3)}
                        for index in np.argsort(bound)[::-1] if bound[index] > 1e-6]}
        # The published CSV is the better demand estimate: the replay used here includes the force
        # plate free moment, which the repository's controlled comparison showed is the wrong
        # convention. Both are recorded so the reader can see the difference.
        if name + "_moment" in source_moments:
            source_target = float(source_moments[name + "_moment"][source_index] * subject_mass)
            source_length_bound = capacity(arms, length_dependent, source_target)
            entry["sourceCsvDemandNm"] = round(source_target, 3)
            entry["sourceCsvDemandToLengthBound"] = round(
                abs(source_target) / float(source_length_bound.sum()), 3)
        report["targetFrame"][name] = entry

    knee = model.getCoordinateSet().get("knee_angle_r")
    base_row = read_ik_nearest(target_time_s, ik_path)
    # Which muscles the model actually offers for each role, and what its own credits say about it.
    report["modelProvenance"] = {
        "credits": str(model.getCredits()).strip(),
        "kneeExtensors": {name: round(float(muscles[muscle_names.index(name)]
                                            .getMaxIsometricForce()), 1)
                          for name in muscle_names if name.startswith(("vas", "rect_fem"))},
        "trunkExtensors": {name: round(float(muscles[muscle_names.index(name)]
                                             .getMaxIsometricForce()), 1)
                           for name in muscle_names if name.startswith(("ercspn", "intobl", "extobl"))},
        "sideKneeExtensorMaxForceN": round(sum(
            float(muscle.getMaxIsometricForce()) for muscle in muscles
            if muscle.getName().startswith(("vas", "rect_fem")) and
            muscle.getName().endswith("_r")), 1),
    }
    # A bilateral squat with symmetric knee angles should not have very different left and right
    # demands, so the target frame's own symmetry is part of the evidence about the demand.
    report["symmetryAtTargetFrame"] = {}
    for joint in ("knee_angle", "hip_flexion", "hip_adduction", "ankle_angle"):
        right = float(targets[f"{joint}_r_moment"]) if f"{joint}_r_moment" in targets else None
        left = float(targets[f"{joint}_l_moment"]) if f"{joint}_l_moment" in targets else None
        report["symmetryAtTargetFrame"][joint] = {
            "rightDemandNm": round(right, 3) if right is not None else None,
            "leftDemandNm": round(left, 3) if left is not None else None,
            "rightToLeftDemandRatio": (round(abs(right) / abs(left), 3)
                                       if right is not None and left and abs(left) > 1e-9 else None),
            "rightAngleDeg": round(float(base_row[f"{joint}_r"]), 2),
            "leftAngleDeg": round(float(base_row[f"{joint}_l"]), 2),
            "leftRightAngleGapDeg": round(abs(float(base_row[f"{joint}_r"]) -
                                              float(base_row[f"{joint}_l"])), 2)}
    for angle in SWEEP_ANGLES_DEG + (base_row["knee_angle_r"],):
        posed = dict(base_row)
        posed["knee_angle_r"] = angle
        apply_row(model, state, posed)
        model.equilibrateMuscles(state)
        maximum, length_dependent = muscle_forces(model, muscles, state)
        arms = np.array([muscle.computeMomentArm(state, knee) for muscle in muscles])
        extending = np.maximum(arms, 0)
        quadriceps = [index for index, name in enumerate(muscle_names)
                      if name.startswith(("vas_int", "rect_fem"))]
        report["kneeAngleSweep"][f"{angle:.3f}"] = {
            "maximumCapacityNm": round(float((extending * maximum).sum()), 1),
            "lengthCapacityNm": round(float((extending * length_dependent).sum()), 1),
            "quadricepsOnlyLengthCapacityNm": round(float(
                (extending[quadriceps] * length_dependent[quadriceps]).sum()), 1),
            "hamstringsMomentArmCm": {name: round(float(arms[muscle_names.index(name)]) * 100, 3)
                                      for name in muscle_names
                                      if name in ("bifemlh_r", "bifemsh_r")},
            "vastiFiberLengthRatio": round(float(
                muscles[muscle_names.index("vas_int_r")].getFiberLength(state) /
                muscles[muscle_names.index("vas_int_r")].getOptimalFiberLength()), 3),
            "vastiActiveForceLength": round(float(
                muscles[muscle_names.index("vas_int_r")].getActiveForceLengthMultiplier(state)), 4)}
    return report


def main():
    subjects = {subject: analyse_subject(subject) for subject in CONFIGS}
    # Cross-subject comparison: a demand that differs by a large factor between two people performing
    # the same movement, while their other joint demands agree, is evidence about the demand rather
    # than about the model's capacity.
    first, second = list(CONFIGS)
    comparison = {}
    for name in COORDINATES:
        left = subjects[first]["targetFrame"][name]
        right = subjects[second]["targetFrame"][name]
        comparison[name] = {
            "demandRatio": round(abs(left["demandNm"]) / abs(right["demandNm"]), 2)
                            if abs(right["demandNm"]) > 1e-9 else None,
            f"{first}DemandNm": left["demandNm"], f"{second}DemandNm": right["demandNm"],
            f"{first}DemandToLengthBound": left["demandToLengthBound"],
            f"{second}DemandToLengthBound": right["demandToLengthBound"]}
    report = {
        "status": "research_only_model_capacity_not_measured_force",
        "crossSubjectComparison": comparison,
        "definition": ("length-dependent isometric bound: per coordinate, the sum over muscles whose "
                       "moment arm points the same way as the demand of max isometric force times "
                       "the active force-length multiplier and the cosine of the pennation angle at "
                       "the posed state; no tendon compliance, passive force, activation dynamics or "
                       "simultaneous multi-joint coupling"),
        "sourceOfDemand": ("replayed inverse dynamics in .cache and the published N m/kg CSV scaled "
                           "by the subject-mass table, as in audit_bilateral_joint_capacity.py"),
        "subjects": subjects,
        "limits": [
            "capacity is a model property, not a measurement of this or any person",
            "the model was scaled geometrically; maximum isometric forces were not individualised",
            "the 54-muscle model reduces the muscle set (see its own credits) so its single vas_int "
            "stands in for the vasti group; the 92-muscle comparison in "
            "docs/data/gait2392_deep_squat_capacity_AB01.json shows that stand-in is not weaker",
            "a demand above the bound means this model cannot produce the moment; it does not prove "
            "the experimental moment is wrong or that a real person could not perform the lift",
            "the experimental knee demand differs by a large factor between the two subjects and "
            "between the two legs of one subject, so that axis cannot be read as a person's capacity "
            "shortfall without first explaining the demand",
            "the hamstring knee moment arm changes sign beyond about 125 deg of flexion in this model, "
            "so part of the knee bound comes from muscles acting there as knee extensors"],
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for subject, data in subjects.items():
        print(f"== {subject}  interval {data['intervalS']}")
        for name, summary in data["interval"].items():
            print(f"   {name:18s} frames={summary['frameCount']:3d} "
                  f"median demand/max-bound={summary['medianDemandToMaximumBound']:6.3f} "
                  f"demand/length-bound={summary['medianDemandToLengthBound']:6.3f} "
                  f"exceed={summary['framesExceedingLengthBound']}")
    print("SAVED_DEEP_SQUAT_LENGTH_CAPACITY", REPORT)


if __name__ == "__main__":
    main()
