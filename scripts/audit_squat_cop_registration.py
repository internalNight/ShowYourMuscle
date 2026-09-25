"""Register measured squat force-plate COP to replayed OpenSim feet.

Research diagnostic only: two subjects and short original-marker IK clips.
COP is a ground point, and ankle-to-MTP is only an approximate sagittal axis.
"""

import json
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
import opensim as osim

from analyze_dynamic_squats import ROOT, load_trial
from audit_dynamic_squat_gravity_balance import read_motion


CASES = (
    ("AB01", "0lbs", 50, 52),
    ("AB01", "25lbs", 1, 3),
    ("AB02", "0lbs", 23, 25),
    ("AB02", "25lbs", 1, 3),
)


def describe(values):
    return {
        "medianCm": round(float(np.median(values) * 100), 2),
        "p05Cm": round(float(np.percentile(values, 5) * 100), 2),
        "p95Cm": round(float(np.percentile(values, 95) * 100), 2),
        "p05ToP95ExcursionCm": round(float((np.percentile(values, 95) -
                                            np.percentile(values, 5)) * 100), 2),
    }


def inspect(subject, load, start, end):
    motion_path = ROOT / ".cache/lower-limb" / f"{subject}_ik_{start:g}_{end:g}.mot"
    model_path = (ROOT / ".cache/lower-limb-raw" / subject / "Models" /
                  f"{subject}-Scaled1.osim")
    names, motion = read_motion(motion_path)
    times = motion[:, 0]
    trial = load_trial(subject, load)
    grf = trial["grf"]

    # The copied ASCII path avoids an OpenSim Windows non-ASCII path failure.
    with tempfile.NamedTemporaryFile(prefix=f"cop_{subject}_", suffix=".osim",
                                     delete=False) as handle:
        temporary = Path(handle.name)
    shutil.copyfile(model_path, temporary)
    try:
        model = osim.Model(str(temporary))
        state = model.initSystem()
        coordinates = model.getCoordinateSet()
        setters = [(i, coordinates.get(name),
                    not name.endswith(("_tx", "_ty", "_tz")))
                   for i, name in enumerate(names[1:], 1)]
        joint_set = model.getJointSet()
        joint_frames = {
            side: (joint_set.get(f"ankle_{side}").getChildFrame(),
                   joint_set.get(f"mtp_{side}").getChildFrame())
            for side in ("r", "l")
        }
        total_mass = model.getTotalMass(state)
        added_load_kg = 25 * 0.45359237 if load == "25lbs" else 0.0
        fixed_cop_forward_m = 0.06
        output = {side: {"ap": [], "ml": [], "length": [], "axisX": [],
                         "axisZ": [], "worldX": [], "worldZ": [],
                         "verticalForce": [], "externalSagittalMoment": [],
                         "fixedCopMeasuredForceMoment": [],
                         "fixedCopStaticHalfWeightMoment": [],
                         "horizontalForceCorrection": [],
                         "sourceNetAnkleMomentNm": []}
                  for side in ("r", "l")}
        for row in motion:
            time = row[0]
            for column, coordinate, angular in setters:
                value = math.radians(row[column]) if angular else row[column]
                coordinate.setValue(state, value, False)
            model.realizePosition(state)
            for side, prefix in (("r", "R"), ("l", "L")):
                force = float(np.interp(time, trial["time"],
                                        grf[f"{prefix}ForceY_Vertical"]))
                if force < 100:
                    continue
                ankle_frame, mtp_frame = joint_frames[side]
                ankle_v = ankle_frame.getPositionInGround(state)
                mtp_v = mtp_frame.getPositionInGround(state)
                ankle = np.array([ankle_v.get(i) for i in range(3)])
                mtp = np.array([mtp_v.get(i) for i in range(3)])
                foot = (mtp - ankle)[[0, 2]]
                length = float(np.linalg.norm(foot))
                if length < 0.05:
                    raise ValueError(f"Implausible ankle-to-MTP distance: {length}")
                axis = foot / length
                cop = np.array([np.interp(time, trial["time"], grf[f"{prefix}COPX"]),
                                np.interp(time, trial["time"], grf[f"{prefix}COPZ"])])
                delta = cop - ankle[[0, 2]]
                force_horizontal = np.array([
                    np.interp(time, trial["time"], grf[f"{prefix}ForceX"]),
                    np.interp(time, trial["time"], grf[f"{prefix}ForceZ"]),
                ])
                force_forward = float(np.dot(force_horizontal, axis))
                cop_y = float(np.interp(time, trial["time"],
                                        grf[f"{prefix}COPY_Vertical"]))
                # Moment about the ankle's horizontal axis perpendicular to the
                # foot: r_AP * F_vertical - r_vertical * F_AP. This is only
                # the plate's external moment, not the net ankle joint moment.
                horizontal_correction = -(cop_y - ankle[1]) * force_forward
                external_moment = float(np.dot(delta, axis) * force +
                                        horizontal_correction)
                fixed_cop_measured_force = fixed_cop_forward_m * force + horizontal_correction
                fixed_cop_static_weight = (fixed_cop_forward_m *
                                           (total_mass + added_load_kg) *
                                           9.80665 / 2)
                row_out = output[side]
                source_moment = float(np.interp(time, trial["time"],
                    trial["moment"][f"ankle_angle_{side}_moment"]))
                for key, value in (("ap", float(np.dot(delta, axis))),
                                   ("ml", float(np.dot(delta, [-axis[1], axis[0]]))),
                                   ("length", length), ("axisX", axis[0]),
                                   ("axisZ", axis[1]),
                                   ("worldX", delta[0]), ("worldZ", delta[1]),
                                   ("verticalForce", force),
                                   ("externalSagittalMoment", external_moment),
                                   ("fixedCopMeasuredForceMoment", fixed_cop_measured_force),
                                   ("fixedCopStaticHalfWeightMoment", fixed_cop_static_weight),
                                   ("horizontalForceCorrection", horizontal_correction),
                                   ("sourceNetAnkleMomentNm", source_moment *
                                    total_mass)):
                    row_out[key].append(float(value))
    finally:
        temporary.unlink(missing_ok=True)

    result = {"subject": subject, "load": load, "intervalS": [start, end],
              "feet": {}}
    for side, samples in output.items():
        if len(samples["ap"]) < 100:
            raise ValueError(f"Too few stance frames: {subject} {load} {side}")
        ap = np.asarray(samples["ap"])
        external = np.asarray(samples["externalSagittalMoment"])
        net_ankle = np.asarray(samples["sourceNetAnkleMomentNm"])
        residual = -external - net_ankle
        fixed_measured_force_residual = (
            -np.asarray(samples["fixedCopMeasuredForceMoment"]) - net_ankle)
        fixed_static_residual = (
            -np.asarray(samples["fixedCopStaticHalfWeightMoment"]) - net_ankle)
        foot_length = np.asarray(samples["length"])
        result["feet"][side] = {
            "stanceFrames": len(ap),
            "ankleToMtp": describe(foot_length),
            "copForwardFromAnkle": describe(ap),
            "copLateralFromFootAxis": describe(samples["ml"]),
            "copWorldXFromAnkle": describe(samples["worldX"]),
            "copWorldZFromAnkle": describe(samples["worldZ"]),
            "verticalForceN": {
                "median": round(float(np.median(samples["verticalForce"])), 1),
            },
            "plateExternalSagittalMomentAboutAnkleNm": {
                "median": round(float(np.median(samples["externalSagittalMoment"])), 1),
                "p05": round(float(np.percentile(samples["externalSagittalMoment"], 5)), 1),
                "p95": round(float(np.percentile(samples["externalSagittalMoment"], 95)), 1),
            },
            "horizontalPlateForceMomentCorrectionNm": {
                "median": round(float(np.median(samples["horizontalForceCorrection"])), 1),
            },
            "negativePlateMomentVsSourceNetAnkleNm": {
                "meanAbsoluteDifference": round(float(np.mean(np.abs(residual))), 2),
                "medianDifference": round(float(np.median(residual)), 2),
                "correlation": round(float(np.corrcoef(-external, net_ankle)[0, 1]), 3),
                "sourceMedian": round(float(np.median(net_ankle)), 1),
            },
            "fixedCop6cmMeasuredForceVsSourceNetAnkleNm": {
                "meanAbsoluteDifference": round(float(np.mean(np.abs(fixed_measured_force_residual))), 2),
                "medianDifference": round(float(np.median(fixed_measured_force_residual)), 2),
            },
            "fixedCop6cmStaticHalfWeightVsSourceNetAnkleNm": {
                "meanAbsoluteDifference": round(float(np.mean(np.abs(fixed_static_residual))), 2),
                "medianDifference": round(float(np.median(fixed_static_residual)), 2),
            },
            "footForwardAxisWorldXZMedian": [
                round(float(np.median(samples["axisX"])), 3),
                round(float(np.median(samples["axisZ"])), 3)],
            "fractionCopWithinExtendedFootRange": round(float(np.mean(
                (ap >= -0.05) & (ap <= foot_length + 0.10))), 3),
        }
    return result


def main():
    cases = [inspect(*case) for case in CASES]
    report = {
        "status": "source_coordinate_registration_audit_not_phone_or_muscle_force_validation",
        "source": "Scherpereel et al. 2023, doi:10.1038/s41597-023-02840-6",
        "method": "Replay original-marker IK in the source subject-scaled model; project processed force-plate COP minus OpenSim ankle joint origin onto ankle-to-MTP horizontal direction, for stance frames with vertical plate force >=100 N. External sagittal plate moment about the ankle is r_forward*F_vertical - r_vertical*F_forward, omitting plate free moments. Compare two illustrative fixed 6-cm anterior COP scenarios: one retains measured per-foot force and horizontal correction; the other replaces force by half static total weight (body plus 25-lb load when applicable) and drops horizontal force. The 6-cm choice was informed by a prior look at these four clips' COP medians, but was not optimized per frame or subject and is not an independent prediction test. Plausibility range extends from 5 cm behind the ankle to 10 cm beyond the MTP origin, because these joint origins are not heel and toe boundaries.",
        "limitations": "Only four two-second clips from two people; ankle-to-MTP joint origins approximate the sagittal foot axis; COP is measured while joint centers are model-derived. External plate moment is compared with the source inverse-dynamics net ankle moment using an expected opposite sign, but they need not coincide: foot mass, inertia, passive tissue, plate free moment and other forces are omitted. Fixed-COP scenarios still use experimental IK to locate the ankle and foot axis. No phone-input or individual muscle-force validation.",
        "cases": cases,
    }
    output = ROOT / "docs/data/squat_cop_registration.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
