"""Length-dependent knee capacity on a research-purpose model, swept against the reduced one.

The previous round found that 34% of the reduced gait2354-family knee bound at the deepest
squat frame comes from hamstrings whose knee moment arm changes sign beyond about 125 deg of
flexion, and that the same model's own credits state its muscle set is not intended for
research. This probe sweeps the knee angle on both the reduced source model and the
RajagopalLaiUhlrich2023 candidate (segment-scaled to the same subject, 80 lower-body muscles,
separate vasti, patellofemoral joint) under one pose convention, so the two capacity curves can
be compared without the demand question interfering.

Research only: moment arms times generic maximum isometric forces with the active force-length
relation; no tendon compliance, passive force, activation dynamics or multi-joint feasibility.
"""

import json
import math
import subprocess
from pathlib import Path

import numpy as np
import opensim as osim

from audit_high_flex_candidate import CANDIDATE, REPO, ROOT, SUBJECTS, read_ik, set_pose
from analyze_dynamic_squats import read_csv
from probe_dynamic_squat_muscle_capacity import subject_masses
from probe_high_flex_scaled_capacity import ratios_from_dimensions, scale_model
from probe_high_flex_segment_scaling import dimensions

OUTPUT = ROOT / "docs/data/high_flex_length_capacity.json"

SWEEP_DEG = (0.0, -20.0, -40.0, -60.0, -80.0, -100.0, -120.0, -130.0, -135.0, -140.0)
COORDINATES = ("knee_angle_r", "knee_angle_l", "hip_flexion_r", "hip_adduction_r",
               "ankle_angle_r", "hip_rotation_r")
EXTENSOR_PREFIXES = ("vas", "recfem", "rect_fem")
FLEXOR_PREFIXES = ("bifem", "bflh", "bfsh", "semimem", "semiten", "grac", "sar")


def apply_pose(model, state, row, override=None, flip_knee=False):
    """Apply an IK row; override names the coordinate and its source-convention value.

    flip_knee converts the source knee sign convention to the candidate's, and must only be
    used for models that store knee flexion with the opposite sign.
    """
    coordinates = model.getCoordinateSet()
    for name, value in row.items():
        if name == "time":
            continue
        coordinate = coordinates.get(name)
        if coordinate is None:
            continue
        if override is not None and name == override[0]:
            value = override[1]
        if flip_knee and name in ("knee_angle_r", "knee_angle_l"):
            value = -value
        angular = not name.endswith(("_tx", "_ty", "_tz"))
        coordinate.setValue(state, math.radians(value) if angular else value, False)
    state.setTime(row["time"])
    model.assemble(state)
    model.realizePosition(state)


def knee_report(model, state, flexion_deg, flip_knee):
    """Signed knee capacity at one flexion angle, in the source model's sign convention."""
    coordinate = model.getCoordinateSet().get("knee_angle_r")
    # Moment arms are read from the posed state before the muscles are equilibrated, matching
    # the repository's capacity audit; the force-length factor then comes from equilibrium.
    muscles = model.getMuscles()
    names = [muscles.get(index).getName() for index in range(muscles.getSize())]
    arms = np.array([muscles.get(index).computeMomentArm(state, coordinate)
                     for index in range(muscles.getSize())])
    maximum_forces = np.array([muscles.get(index).getMaxIsometricForce()
                               for index in range(muscles.getSize())])
    # Which sign of moment arm extends the knee is read from the model's own vasti and rectus
    # femoris rather than assumed, because the two models store the knee angle with opposite signs.
    extensor_muscles = np.array([name.startswith(EXTENSOR_PREFIXES) for name in names])
    extensor_sign = int(np.sign(
        float((arms[extensor_muscles] * maximum_forces[extensor_muscles]).sum())))
    if extensor_sign == 0:
        raise AssertionError(f"No knee extensor moment arm at {flexion_deg} deg")
    model.equilibrateMuscles(state)
    model.realizeDynamics(state)
    length_forces = np.array([
        muscles.get(index).getMaxIsometricForce() *
        muscles.get(index).getActiveForceLengthMultiplier(state) *
        math.cos(muscles.get(index).getPennationAngle(state))
        for index in range(muscles.getSize())])
    flexors = np.array([name.startswith(FLEXOR_PREFIXES) for name in names])
    extending = np.sign(arms) == extensor_sign
    report = {
        "flexionDeg": flexion_deg,
        # The value the model actually holds, reported in the source convention, so that a
        # coordinate-range clamp cannot hide inside the comparison.
        "appliedFlexionDeg": round((-1.0 if flip_knee else 1.0) *
                                   math.degrees(float(coordinate.getValue(state))), 3),
        "poseClamped": abs((-1.0 if flip_knee else 1.0) *
                           math.degrees(float(coordinate.getValue(state))) - flexion_deg) > 0.01,
        "extensionMomentArmSign": extensor_sign,
        "maximumCapacityNm": round(float(np.abs(arms[extending] * maximum_forces[extending]).sum()), 1),
        "lengthCapacityNm": round(float(np.abs(arms[extending] * length_forces[extending]).sum()), 1),
        "extensorsOnlyMaximumNm": round(float(
            np.abs(arms[extending & extensor_muscles] *
                   maximum_forces[extending & extensor_muscles]).sum()), 1),
        "extensorsOnlyLengthNm": round(float(
            np.abs(arms[extending & extensor_muscles] *
                   length_forces[extending & extensor_muscles]).sum()), 1),
        "flexorsActingAsExtensorsMaximumNm": round(float(
            np.abs(arms[extending & flexors] * maximum_forces[extending & flexors]).sum()), 1),
        "extensorFiberLengths": {names[int(index)]: round(float(
            muscles.get(int(index)).getFiberLength(state) /
            muscles.get(int(index)).getOptimalFiberLength()), 3)
            for index in np.where(extensor_muscles)[0]},
        "muscles": {names[int(index)]: {
            "momentArmCm": round(float(arms[index]) * 100, 3),
            "maximumForceN": round(float(maximum_forces[index]), 1),
            "activeForceLength": round(float(
                muscles.get(int(index)).getActiveForceLengthMultiplier(state)), 4),
            "pennationDeg": round(float(math.degrees(
                muscles.get(int(index)).getPennationAngle(state))), 2)}
            for index in np.argsort(np.abs(arms))[::-1] if abs(arms[index]) > 1e-5},
    }
    return report


def coordinate_capacity(model, state, name, demand_nm):
    """Same-direction bound for one coordinate given a demand expressed in this model's sign."""
    coordinate = model.getCoordinateSet().get(name)
    muscles = model.getMuscles()
    arms = np.array([muscles.get(index).computeMomentArm(state, coordinate)
                     for index in range(muscles.getSize())])
    maximum = np.array([muscles.get(index).getMaxIsometricForce()
                        for index in range(muscles.getSize())])
    model.equilibrateMuscles(state)
    model.realizeDynamics(state)
    length_dependent = np.array([
        muscles.get(index).getMaxIsometricForce() *
        muscles.get(index).getActiveForceLengthMultiplier(state) *
        math.cos(muscles.get(index).getPennationAngle(state))
        for index in range(muscles.getSize())])
    same_way = np.sign(arms) == np.sign(demand_nm)
    return (float(np.abs(arms[same_way] * maximum[same_way]).sum()),
            float(np.abs(arms[same_way] * length_dependent[same_way]).sum()))


def repository_revision(path):
    """Revision of the candidate model repository, without requiring a git executable."""
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        pass
    head = Path(path) / ".git" / "HEAD"
    if head.is_file():
        reference = head.read_text(encoding="utf-8").strip()
        if reference.startswith("ref:"):
            target = Path(path) / ".git" / reference.split(" ", 1)[1].strip()
            if target.is_file():
                return target.read_text(encoding="utf-8").strip()
        return reference
    return None


def main():
    osim.Logger.setLevelString("Error")
    masses = subject_masses()
    report = {
        "status": "research_only_cross_model_length_capacity",
        "sourceModel": "gait2354-family subject-scaled models in .cache/lower-limb-raw",
        "candidateModel": "RajagopalLaiUhlrich2023.osim scaled to the same segment ratios and mass",
        "candidateRepositoryRevision": repository_revision(REPO),
        "capacityDefinition": ("per coordinate, the sum over muscles whose moment arm points the same "
                               "way as the demand of maximum isometric force, and separately of that "
                               "force times the active force-length multiplier and the cosine of the "
                               "pennation angle at the equilibrated posed state"),
        "sweepDeg": list(SWEEP_DEG),
        "subjects": {},
        "limitations": [
            "maximum isometric forces stay generic after geometric scaling in both models",
            "no tendon compliance, passive force, activation dynamics or multi-joint feasibility",
            "the candidate is posed with the source IK row, not with its own inverse kinematics",
            "the candidate knee range ends at 140 deg of flexion, so deeper source frames cannot "
            "be compared and are reported separately",
            "moment arms are read before equilibrating the muscles, matching the capacity audit",
            "the two models may use different default activations, which changes the force-length "
            "factor; only the curves, not the absolute numbers, should be compared across models",
        ],
    }
    for subject, config in SUBJECTS.items():
        source = osim.Model(str(config["source"].relative_to(ROOT)))
        source_state = source.initSystem()
        candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
        candidate_state = candidate.initSystem()
        rows = read_ik(config["ik"], config["intervalS"])
        initial = rows[0]
        set_pose(source, source_state, initial)
        set_pose(candidate, candidate_state, initial, flip_knee=True)
        factors = ratios_from_dimensions(dimensions(source, source_state, "knee"),
                                         dimensions(candidate, candidate_state, "walker_knee"))
        target_mass = float(source.getTotalMass(source_state))
        scale_model(candidate, candidate_state, factors, target_mass)
        candidate_max_flexion = math.degrees(
            candidate.getCoordinateSet().get("knee_angle_r").getRangeMax())
        deepest = min(rows, key=lambda row: row["knee_angle_r"])
        if abs(deepest["time"] - config["deepestS"]) > 1e-6:
            raise AssertionError("Unexpected deepest frame")
        sweep = {}
        for angle in SWEEP_DEG:
            if -angle > candidate_max_flexion + 1e-9:
                continue
            entry = {}
            for label, model, state, flip in (("source", source, source_state, False),
                                              ("candidate", candidate, candidate_state, True)):
                apply_pose(model, state, deepest, override=("knee_angle_r", angle),
                           flip_knee=flip)
                entry[label] = knee_report(model, state, angle, flip)
            sweep[f"{angle:.1f}"] = entry
        masses_for_subject = masses[subject]
        moments = read_csv(ROOT / ".cache/lower-limb-raw" / subject /
                           "CSV_Data/squats_1/Joint_Moments.csv")
        moment_index = int(round(deepest["time"] / 0.005))
        if abs(moments["time"][moment_index] - deepest["time"]) > 1e-6:
            raise AssertionError("Moment time grid mismatch")
        # The demand direction comes from the experimental joint moment, not from the pose angle.
        # The candidate stores knee flexion with the opposite sign, so the same physical demand
        # flips there; the hip and ankle axes were already checked to share the source direction.
        target_frame = {}
        for name in COORDINATES:
            demand = float(moments[name + "_moment"][moment_index] * masses_for_subject)
            entry = {"demandNm": round(demand, 3)}
            for label, model, state, flip in (("source", source, source_state, False),
                                              ("candidate", candidate, candidate_state, True)):
                apply_pose(model, state, deepest, flip_knee=flip)
                sign = -1.0 if name.startswith("knee_angle") and flip else 1.0
                bound, length_bound = coordinate_capacity(model, state, name, demand * sign)
                applied = math.degrees(float(
                    model.getCoordinateSet().get(name).getValue(state))) * (
                        -1.0 if name.startswith("knee_angle") and flip else 1.0)
                entry[label] = {"demandSign": sign,
                                "appliedPoseDeg": round(applied, 3),
                                "poseClamped": abs(applied - float(deepest[name])) > 0.01,
                                "maximumBoundNm": round(bound, 1),
                                "lengthBoundNm": round(length_bound, 1),
                                "demandToMaximumBound": round(abs(demand) / bound, 3),
                                "demandToLengthBound": round(abs(demand) / length_bound, 3)}
            target_frame[name] = entry
        report["subjects"][subject] = {
            "subjectMassKg": masses_for_subject,
            "deepestFrameTimeS": deepest["time"],
            "deepestKneeFlexionDeg": round(-deepest["knee_angle_r"], 3),
            "candidateMaximumFlexionDeg": round(candidate_max_flexion, 3),
            "candidatePoseClampedCoordinates": sorted(
                name for name, entry in target_frame.items()
                if entry["candidate"]["poseClamped"]),
            "muscleCount": {"source": source.getMuscles().getSize(),
                            "candidate": candidate.getMuscles().getSize()},
            "sweep": sweep,
            "targetFrame": target_frame,
        }
        print(f"== {subject} deepest {deepest['time']}s knee "
              f"{-deepest['knee_angle_r']:.1f} deg, candidate max "
              f"{candidate_max_flexion:.1f} deg")
        for key, entry in sweep.items():
            print(f"   knee {key:>7} deg  source length {entry['source']['lengthCapacityNm']:6.1f} "
                  f"(extensors {entry['source']['extensorsOnlyLengthNm']:6.1f})  candidate length "
                  f"{entry['candidate']['lengthCapacityNm']:6.1f} "
                  f"(extensors {entry['candidate']['extensorsOnlyLengthNm']:6.1f})")
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("SAVED_HIGH_FLEX_LENGTH_CAPACITY", OUTPUT)


if __name__ == "__main__":
    main()
