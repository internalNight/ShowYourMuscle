"""Lumbar extension capacity on a research-purpose full-body model with a real trunk.

Earlier rounds could only say that the reduced gait2354-family model has two erector spinae and
therefore cannot carry the deep-squat lumbar extension moment. The locally available
research-purpose candidates are all lower-limb models with no trunk muscles, so that statement
could not be tested. This probe uses a full-body model with a detailed spine (multifidus,
longissimus, iliocostalis, quadratus lumborum, latissimus, rectus abdominis, 520 muscles) and
asks the same question at the anatomically matching L5/S1 level.

The subject's single lumbar_extension angle is distributed evenly over the five lumbar
intervertebral levels, which is an assumption; the even split keeps each level inside a plausible
range and preserves the total trunk flexion that sets the erector spinae fiber lengths.

Research only: moment arms times generic maximum isometric forces with the active force-length
relation and pennation; no passive force, activation dynamics or load sharing.
"""

import json
import math
from pathlib import Path

import numpy as np
import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
FULL_BODY = ROOT / ".cache/model-candidates/cyclistFullBodyMuscle.osim"
OUTPUT = ROOT / "docs/data/full_body_lumbar_capacity.json"
LEVELS = ("L5_S1_FE", "L4_L5_FE", "L3_L4_FE", "L2_L3_FE", "L1_L2_FE")
# The lowest level carries the full external moment of everything above it, so it is the level that
# can be compared with the source model's single lumbar joint.
LOWEST_LEVEL = "L5_S1_FE"
ERECTOR_PREFIXES = ("MF_", "LTp", "IL_", "E0_", "spl", "mul")
OTHER_TRUNK_PREFIXES = ("QL_", "rect_abd", "Ps_")
SHOULDER_SPANNING_PREFIXES = ("LD_", "tra", "Ser", "sup")
SWEEP_DEG = (0.0, -10.0, -20.0, -30.0, -40.0, -50.0)
SUBJECTS = {
    "AB01": {"ik": ROOT / ".cache/lower-limb/AB01_ik_50_52.mot", "startTimeS": 50.0,
             "targetTimeS": 51.32},
    "AB02": {"ik": ROOT / ".cache/lower-limb/AB02_ik_23_25.mot", "startTimeS": 23.0,
             "targetTimeS": 23.685},
}


def read_ik_row(path, start_time_s, target_time_s):
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index("endheader")
    names = lines[start + 1].split()
    index = int(round((target_time_s - start_time_s) / 0.005))
    return dict(zip(names, [float(value) for value in lines[start + 2 + index].split()]))


def apply_source_pose(model, state, row):
    """Apply whichever source coordinates this model also has, so segment lengths are comparable."""
    applied, skipped = {}, []
    for name, value in row.items():
        if name == "time":
            continue
        try:
            coordinate = model.getCoordinateSet().get(name)
        except RuntimeError:
            # CoordinateSet.get raises for a name this model does not have.
            skipped.append(name)
            continue
        angular = not name.endswith(("_tx", "_ty", "_tz"))
        coordinate.setValue(state, math.radians(value) if angular else value, False)
        applied[name] = value
    return applied, skipped


class FullBody:
    """Wraps the full-body model so flexion can be set level by level."""

    def __init__(self):
        self.model = osim.Model(str(FULL_BODY.relative_to(ROOT)))
        self.state = self.model.initSystem()
        muscles = self.model.getMuscles()
        self.names = [muscles.get(index).getName() for index in range(muscles.getSize())]
        self.coordinate = self.model.getCoordinateSet().get(LOWEST_LEVEL)
        self.maximum = np.array([muscles.get(index).getMaxIsometricForce()
                                 for index in range(muscles.getSize())],
                                dtype=float)
        self.masks = {
            "erectorSpinae": self.mask(ERECTOR_PREFIXES),
            "otherTrunk": self.mask(OTHER_TRUNK_PREFIXES),
            "shoulderSpanning": self.mask(SHOULDER_SPANNING_PREFIXES),
        }

    def mask(self, prefixes):
        return np.array([name.startswith(prefixes) for name in self.names])

    def set_flexion(self, total_flexion_deg, row=None):
        """Distribute the subject's lumbar flexion over the five levels and pose the rest."""
        skipped = []
        for name in LEVELS:
            self.model.getCoordinateSet().get(name).setValue(
                self.state, math.radians(total_flexion_deg / len(LEVELS)), False)
        if row is not None:
            _, skipped = apply_source_pose(self.model, self.state, row)
        self.model.assemble(self.state)
        self.model.realizePosition(self.state)
        return skipped

    def report(self, total_flexion_deg):
        muscles = self.model.getMuscles()
        arms = np.array([muscles.get(index).computeMomentArm(self.state, self.coordinate)
                         for index in range(muscles.getSize())], dtype=float)
        self.model.equilibrateMuscles(self.state)
        self.model.realizeDynamics(self.state)
        length_factor = np.array([
            muscles.get(index).getActiveForceLengthMultiplier(self.state) *
            math.cos(muscles.get(index).getPennationAngle(self.state))
            for index in range(muscles.getSize())], dtype=float)
        # Flexion is the negative coordinate direction and stretches the extensors, so their arms
        # point the other way; the probe asserts that pairing rather than assuming it.
        extending = arms > 0
        capacity = np.abs(arms * self.maximum * length_factor)
        groups = {
            "allExtensorsNm": float(capacity[extending].sum()),
            "erectorSpinaeOnlyNm": float(capacity[extending & self.masks["erectorSpinae"]].sum()),
            "withoutShoulderSpanningNm": float(
                capacity[extending & ~self.masks["shoulderSpanning"]].sum()),
            "shoulderSpanningNm": float(capacity[extending & self.masks["shoulderSpanning"]].sum()),
            "flexorsActingAsExtensorsNm": float(capacity[extending & self.masks["otherTrunk"]].sum()),
        }
        fibers = {}
        for label, mask in self.masks.items():
            selected = np.where(mask & extending)[0]
            if len(selected) == 0:
                continue
            fibers[label] = round(float(np.mean([
                muscles.get(int(index)).getFiberLength(self.state) /
                muscles.get(int(index)).getOptimalFiberLength() for index in selected])), 3)
        contributors = []
        # Only muscles pulling in the extension direction belong in a capacity breakdown.
        order = np.argsort(np.where(extending, capacity, 0.0))[::-1][:8]
        for index in order:
            if capacity[index] <= 1.0:
                continue
            contributors.append({
                "muscle": self.names[int(index)],
                "momentArmCm": round(float(arms[index]) * 100, 3),
                "maximumForceN": round(float(self.maximum[index]), 1),
                "activeForceLength": round(float(
                    muscles.get(int(index)).getActiveForceLengthMultiplier(self.state)), 4),
                "capacityNm": round(float(capacity[index]), 1)})
        # Muscles that flex the trunk but pull the other way at this posture, exactly like the
        # hamstrings in the reduced knee model; they are excluded from the erector spinae bound.
        flipped = {self.names[int(index)]: round(float(arms[index]) * 100, 3)
                   for index in np.where(extending & self.masks["otherTrunk"])[0]
                   if capacity[index] > 10.0}
        return {"totalFlexionDeg": total_flexion_deg,
                "levelsDeg": round(total_flexion_deg / len(LEVELS), 3),
                "capacities": {key: round(value, 1) for key, value in groups.items()},
                "normalizedFiberLengths": fibers,
                "flexorsActingAsExtensorsArmsCm": flipped,
                "contributors": contributors}


def calibrate(full):
    """Establish what positive and negative flexion do to the extensors, and which way they pull."""
    evidence = {}
    for sign in (5.0, -5.0):
        for name in LEVELS:
            full.model.getCoordinateSet().get(name).setValue(
                full.state, math.radians(sign), False)
        full.model.assemble(full.state)
        full.model.realizePosition(full.state)
        full.model.equilibrateMuscles(full.state)
        muscles = full.model.getMuscles()
        selected = np.where(full.masks["erectorSpinae"])[0]
        evidence[f"{sign:+.0f}"] = round(float(np.mean([
            muscles.get(int(index)).getFiberLength(full.state) /
            muscles.get(int(index)).getOptimalFiberLength() for index in selected])), 3)
    for name in LEVELS:
        full.model.getCoordinateSet().get(name).setValue(full.state, 0.0, False)
    full.model.assemble(full.state)
    full.model.realizePosition(full.state)
    muscles = full.model.getMuscles()
    arms = np.array([muscles.get(index).computeMomentArm(full.state, full.coordinate)
                     for index in range(muscles.getSize())], dtype=float)
    erector_arms = arms[full.masks["erectorSpinae"]]
    return {
        "extensorFiberLengthAtPlus5Deg": evidence["+5"],
        "extensorFiberLengthAtMinus5Deg": evidence["-5"],
        "flexionIsNegative": evidence["-5"] > evidence["+5"],
        "erectorSpinaePositiveArmMomentNm": round(float(
            (arms[full.masks["erectorSpinae"] & (arms > 0)] *
             full.maximum[full.masks["erectorSpinae"] & (arms > 0)]).sum()), 1),
        "erectorSpinaeNegativeArmMomentNm": round(float(
            (np.abs(arms[full.masks["erectorSpinae"] & (arms < 0)] *
                    full.maximum[full.masks["erectorSpinae"] & (arms < 0)])).sum()), 1),
        "erectorSpinaeMeanArmCm": round(float(np.mean(np.abs(erector_arms))) * 100, 3),
        "erectorSpinaeCount": int(full.masks["erectorSpinae"].sum()),
    }


def main():
    osim.Logger.setLevelString("Error")
    full = FullBody()
    calibration = calibrate(full)
    if not calibration["flexionIsNegative"]:
        raise AssertionError("Lumbar flexion is not the negative coordinate direction")
    reduced = json.loads((ROOT / "docs/data/bilateral_deep_squat_length_capacity.json")
                         .read_text(encoding="utf-8"))
    report = {
        "status": "research_only_cross_model_lumbar_capacity",
        "model": "cyclistFullBodyMuscle.osim",
        "modelProvenance": {
            "muscleCount": full.model.getMuscles().getSize(),
            "bodyCount": full.model.getBodySet().getSize(),
            "totalMassKg": round(float(full.model.getTotalMass(full.state)), 2),
            "levelCoordinates": list(LEVELS),
            "lowestLevelAboveHipM": 0.149,
            "credits": str(full.model.getCredits()).strip()[:400],
        },
        "definition": ("at the lowest lumbar level, the sum over muscles whose moment arm acts in "
                       "the extension direction of maximum isometric force times the active "
                       "force-length multiplier and the cosine of the pennation angle at the "
                       "posed and equilibrated state"),
        "flexionCalibration": calibration,
        "distributionAssumption": ("the source model's single lumbar_extension angle is split "
                                   "evenly over the five lumbar intervertebral levels, so the total "
                                   "flexion and therefore the erector spinae fiber lengths are "
                                   "preserved while no single level takes an implausible angle"),
        "levelCorrespondence": {
            "source": {subject: None for subject in SUBJECTS},
            "fullBodyLowestLevelAboveHipM": 0.149},
        "sweep": {},
        "subjects": {},
        "limitations": [
            "the source model has one lumped lumbar joint while this model has five levels, and the "
            "even split of the total flexion between them is an assumption",
            "the two models have different muscle maximum forces and no individual strength scaling",
            "no passive force, activation dynamics, load sharing or multi-level equilibrium",
            "arm and shoulder posture is left at the model default, which changes the latissimus "
            "and other shoulder-spanning contributions; they are reported separately",
            "the full-body model is a cycling model; its hip and knee range may not accept the "
            "deepest squat angles, and any coordinate it does not share is left at its default",
        ],
    }
    for subject, config in SUBJECTS.items():
        row = read_ik_row(config["ik"], config["startTimeS"], config["targetTimeS"])
        total_flexion = float(row["lumbar_extension"])
        if total_flexion > 0:
            raise AssertionError(f"{subject}: lumbar_extension is not flexed at the target frame")
        full.set_flexion(total_flexion, row)
        posture = {
            "sourceLumbarExtensionDeg": total_flexion,
            "sourceHipFlexionDeg": round(float(row["hip_flexion_r"]), 3),
            "sourceKneeAngleDeg": round(float(row["knee_angle_r"]), 3),
            "appliedCoordinates": len(apply_source_pose(full.model, full.state, row)[0]),
            "distributedLevelsDeg": round(total_flexion / len(LEVELS), 3),
        }
        full.set_flexion(total_flexion, row)
        posture["report"] = full.report(total_flexion)
        # Where the source's single lumbar joint sits relative to this model's lowest level.
        source = osim.Model(str((ROOT / ".cache/lower-limb-raw" / subject / "Models" /
                                 f"{subject}-Scaled1.osim").relative_to(ROOT)))
        source_state = source.initSystem()
        apply_source_pose(source, source_state, row)
        source.assemble(source_state)
        source.realizePosition(source_state)
        lumbar = source.getJointSet().get("back").getChildFrame().getPositionInGround(source_state)
        hip = source.getJointSet().get("hip_r").getChildFrame().getPositionInGround(source_state)
        posture["sourceLumbarJointAboveHipM"] = round(lumbar.get(1) - hip.get(1), 3)
        report["levelCorrespondence"]["source"][subject] = posture["sourceLumbarJointAboveHipM"]
        demand = reduced["subjects"][subject]["targetFrame"]["lumbar_extension"]["demandNm"]
        posture["demandNm"] = demand
        posture["demandToAllExtensors"] = round(
            abs(demand) / posture["report"]["capacities"]["allExtensorsNm"], 3)
        posture["demandToErectorSpinaeOnly"] = round(
            abs(demand) / posture["report"]["capacities"]["erectorSpinaeOnlyNm"], 3)
        posture["demandToWithoutShoulderSpanning"] = round(
            abs(demand) / posture["report"]["capacities"]["withoutShoulderSpanningNm"], 3)
        posture["reducedModelLengthBoundNm"] = reduced["subjects"][subject]["targetFrame"][
            "lumbar_extension"]["lengthBoundNm"]
        report["subjects"][subject] = posture
        print(f"== {subject} total lumbar flexion {total_flexion:.3f} deg "
              f"({total_flexion / len(LEVELS):.3f} per level)")
        print(f"   demand {demand} Nm   allExtensors "
              f"{posture['report']['capacities']['allExtensorsNm']}   erectorSpinaeOnly "
              f"{posture['report']['capacities']['erectorSpinaeOnlyNm']}   withoutShoulder "
              f"{posture['report']['capacities']['withoutShoulderSpanningNm']} Nm")
        print(f"   ratios: all {posture['demandToAllExtensors']}  erector "
              f"{posture['demandToErectorSpinaeOnly']}  noShoulder "
              f"{posture['demandToWithoutShoulderSpanning']}")
    for total in SWEEP_DEG:
        full.set_flexion(total)
        report["sweep"][f"{total:.1f}"] = full.report(total)
        print(f"   sweep {total:6.1f} deg -> allExtensors "
              f"{report['sweep'][f'{total:.1f}']['capacities']['allExtensorsNm']} Nm")
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("SAVED_FULL_BODY_LUMBAR_CAPACITY", OUTPUT)


if __name__ == "__main__":
    main()
