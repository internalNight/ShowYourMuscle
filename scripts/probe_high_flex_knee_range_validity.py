"""Where the candidate model's knee capacity claim is actually valid, and why its curve bumps at 120 deg.

The previous round compared the deepest squat frame's knee demand against the research-purpose
candidate model and reported a surviving shortfall (AB01 1.40, AB02 0.36). That comparison used the
candidate's maximum-valid knee angle, and the candidate's capacity curve is not monotonic: it falls to
100 deg, rises to a local maximum at 120 deg, then falls again. This probe answers the two questions
that the comparison left open.

1. Why the bump. Every patellofemoral transform function in the candidate model is a SimmSpline whose
   independent variable range ends at 2.0944 rad (120 deg); its tibiofemoral joint uses polynomials,
   which have no such limit. The probe reads those ranges out of the model file and measures the knee
   extensor moment arm on a 0.25 deg grid across the boundary, so the kink can be attributed rather
   than guessed.
2. Whether the shortfall survives inside that range. The knee demand is taken from the experimental
   joint moment of each frame, so the comparison can be made frame by frame and split at 120 deg
   instead of being made only at the deepest, clamped frame.

Research only: same capacity definition, same pose convention and the same generic maximum isometric
forces as the cross-model probe; this is a validity-range question, not a force prediction.
"""

import json
import math
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import numpy as np
import opensim as osim

from analyze_dynamic_squats import read_csv
from audit_high_flex_candidate import CANDIDATE, ROOT, SUBJECTS, read_ik, set_pose
from probe_dynamic_squat_muscle_capacity import subject_masses
from probe_high_flex_length_capacity import (apply_pose, coordinate_capacity,
                                             repository_revision)
from probe_high_flex_scaled_capacity import ratios_from_dimensions, scale_model
from probe_high_flex_segment_scaling import dimensions

OUTPUT = ROOT / "docs/data/high_flex_knee_range_validity.json"
FINE_HALF_WIDTH_DEG = 2.0
FINE_STEP_DEG = 0.25
PROBE_MUSCLE = "vaslat_r"


def spline_ranges(path):
    """Independent-variable ranges of the patellofemoral transform functions, from the model file."""
    joint_name = "patellofemoral_r"
    root = ElementTree.parse(path).getroot()
    for joint in root.iter("CustomJoint"):
        if joint.get("name") != joint_name:
            continue
        report = {}
        for axis in joint.iter("TransformAxis"):
            spline = axis.find("SimmSpline")
            if spline is None:
                report[axis.get("name")] = {"function": "constant_or_polynomial"}
                continue
            values = [float(value) for value in spline.find("x").text.split()]
            report[axis.get("name")] = {
                "function": "SimmSpline",
                "knotCount": len(values),
                "rangeRad": [values[0], values[-1]],
                "rangeDeg": [round(math.degrees(values[0]), 4),
                             round(math.degrees(values[-1]), 4)],
            }
        return report
    raise AssertionError(f"{joint_name} not found in {path}")


def build(subject):
    config = SUBJECTS[subject]
    source = osim.Model(str(config["source"].relative_to(ROOT)))
    source_state = source.initSystem()
    candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
    candidate_state = candidate.initSystem()
    rows = read_ik(config["ik"], config["intervalS"])
    set_pose(source, source_state, rows[0])
    set_pose(candidate, candidate_state, rows[0], flip_knee=True)
    factors = ratios_from_dimensions(dimensions(source, source_state, "knee"),
                                     dimensions(candidate, candidate_state, "walker_knee"))
    scale_model(candidate, candidate_state, factors, float(source.getTotalMass(source_state)))
    return source, source_state, candidate, candidate_state, rows


def arm_profile(candidate, state, deepest, centre_deg):
    """Knee extensor moment arm on a fine grid across the patellofemoral spline boundary."""
    coordinate = candidate.getCoordinateSet().get("knee_angle_r")
    muscles = candidate.getMuscles()
    names = [muscles.get(index).getName() for index in range(muscles.getSize())]
    index = names.index(PROBE_MUSCLE)
    samples = []
    steps = int(round(2 * FINE_HALF_WIDTH_DEG / FINE_STEP_DEG))
    for step in range(steps + 1):
        angle = -(centre_deg - FINE_HALF_WIDTH_DEG + FINE_STEP_DEG * step)
        apply_pose(candidate, state, deepest, override=("knee_angle_r", angle), flip_knee=True)
        applied = math.degrees(float(coordinate.getValue(state)))
        arm_cm = muscles.get(index).computeMomentArm(state, coordinate) * 100
        samples.append({"requestedFlexionDeg": round(-angle, 3),
                        "appliedFlexionDeg": round(applied, 4),
                        "momentArmCm": round(arm_cm, 5)})
    if any(sample["appliedFlexionDeg"] == 0.0 for sample in samples):
        raise AssertionError("fine grid pose was not applied")
    peak = max(samples, key=lambda item: abs(item["momentArmCm"]))
    before = [item for item in samples if item["appliedFlexionDeg"] < centre_deg - 1e-9]
    after = [item for item in samples if item["appliedFlexionDeg"] > centre_deg + 1e-9]
    if len(before) < 2 or len(after) < 2:
        raise AssertionError("fine grid does not straddle the spline boundary")
    slope_before = (abs(before[-1]["momentArmCm"]) - abs(before[-2]["momentArmCm"])) / (
        before[-1]["appliedFlexionDeg"] - before[-2]["appliedFlexionDeg"])
    slope_after = (abs(after[1]["momentArmCm"]) - abs(after[0]["momentArmCm"])) / (
        after[1]["appliedFlexionDeg"] - after[0]["appliedFlexionDeg"])
    return {
        "muscle": PROBE_MUSCLE,
        "probedFlexionRangeDeg": [round(centre_deg - FINE_HALF_WIDTH_DEG, 3),
                                  round(centre_deg, 3),
                                  round(centre_deg + FINE_HALF_WIDTH_DEG, 3)],
        "gridStepDeg": FINE_STEP_DEG,
        "samples": samples,
        "maximumAbsoluteArm": {"momentArmCm": peak["momentArmCm"],
                               "appliedFlexionDeg": peak["appliedFlexionDeg"]},
        "slopeAtBoundaryCmPerDeg": {"before": round(slope_before, 5),
                                    "after": round(slope_after, 5),
                                    "signFlip": slope_before > 0 > slope_after},
    }


def main():
    osim.Logger.setLevelString("Error")
    ranges = spline_ranges(CANDIDATE)
    spline_limit = max(item["rangeDeg"][1] for item in ranges.values()
                       if item.get("function") == "SimmSpline")
    masses = subject_masses()
    report = {
        "status": "research_only_knee_capacity_validity_range",
        "sourceModel": "gait2354-family subject-scaled models in .cache/lower-limb-raw",
        "candidateModel": "RajagopalLaiUhlrich2023.osim scaled to the same segment ratios and mass",
        "candidateRepositoryRevision": repository_revision(ROOT / ".cache/model-candidates/opensim-models"),
        "patellofemoralTransformRanges": ranges,
        "patellofemoralSplineLimitDeg": round(spline_limit, 4),
        "capacityDefinition": ("per coordinate, the sum over muscles whose moment arm points the same "
                              "way as the demand of maximum isometric force times the active "
                              "force-length multiplier and the cosine of the pennation angle at the "
                              "equilibrated posed state"),
        "subjects": {},
        "limitations": [
            "maximum isometric forces stay generic after geometric scaling in both models",
            "no tendon compliance, passive force, activation dynamics or multi-joint feasibility",
            "the demand is the experimental joint moment times body mass, so it inherits the source "
            "model's own validity limits at deep flexion",
            "the tibiofemoral joint of the candidate uses polynomials and therefore has no range "
            "limit; only the patellofemoral splines end at 120 deg",
            "a moment-arm kink at exactly the last spline knot identifies the model's own "
            "patellofemoral data range as the cause, but does not establish what the knee extensor "
            "geometry beyond 120 deg should be",
            "moment arms are read before equilibrating the muscles, matching the capacity audit",
        ],
    }
    for subject, config in SUBJECTS.items():
        source, source_state, candidate, candidate_state, rows = build(subject)
        moments = read_csv(ROOT / ".cache/lower-limb-raw" / subject /
                           "CSV_Data/squats_1/Joint_Moments.csv")
        mass = masses[subject]
        deepest = min(rows, key=lambda row: row["knee_angle_r"])
        range_max = math.degrees(float(
            candidate.getCoordinateSet().get("knee_angle_r").getRangeMax()))
        profile = arm_profile(candidate, candidate_state, deepest, spline_limit)
        frames = []
        for row in rows:
            index = int(round(row["time"] / 0.005))
            if abs(moments["time"][index] - row["time"]) > 1e-6:
                raise AssertionError("Moment time grid mismatch")
            demand = float(moments["knee_angle_r_moment"][index] * mass)
            set_pose(source, source_state, row)
            _, source_bound = coordinate_capacity(source, source_state, "knee_angle_r", demand)
            set_pose(candidate, candidate_state, row, flip_knee=True)
            _, candidate_bound = coordinate_capacity(candidate, candidate_state, "knee_angle_r",
                                                     -demand)
            frames.append({
                "timeS": round(row["time"], 4),
                "flexionDeg": round(-row["knee_angle_r"], 3),
                "demandNm": round(demand, 2),
                "sourceBoundNm": round(source_bound, 2),
                "candidateBoundNm": round(candidate_bound, 2),
                "sourceRatio": round(abs(demand) / source_bound, 3),
                "candidateRatio": round(abs(demand) / candidate_bound, 3),
            })
        summary = {}
        for label, group in (("within", [item for item in frames
                                         if item["flexionDeg"] <= spline_limit]),
                             ("beyond", [item for item in frames
                                         if item["flexionDeg"] > spline_limit])):
            if not group:
                summary[label] = {"frames": 0}
                continue
            worst_source = max(group, key=lambda item: item["sourceRatio"])
            worst_candidate = max(group, key=lambda item: item["candidateRatio"])
            summary[label] = {
                "frames": len(group),
                "maximumFlexionDeg": round(max(item["flexionDeg"] for item in group), 3),
                "sourceMaximumRatio": worst_source["sourceRatio"],
                "sourceMaximumRatioTimeS": worst_source["timeS"],
                "sourceMaximumRatioFlexionDeg": worst_source["flexionDeg"],
                "sourceFramesOverOne": sum(1 for item in group if item["sourceRatio"] > 1),
                "candidateMaximumRatio": worst_candidate["candidateRatio"],
                "candidateMaximumRatioTimeS": worst_candidate["timeS"],
                "candidateMaximumRatioFlexionDeg": worst_candidate["flexionDeg"],
                "candidateFramesOverOne": sum(1 for item in group if item["candidateRatio"] > 1),
            }
        report["subjects"][subject] = {
            "subjectMassKg": mass,
            "deepestFrameTimeS": deepest["time"],
            "deepestKneeFlexionDeg": round(-deepest["knee_angle_r"], 3),
            "candidateMaximumFlexionDeg": round(range_max, 3),
            "momentArmProfile": profile,
            "summary": summary,
            "frames": frames,
        }
        print(f"== {subject}: deepest {-deepest['knee_angle_r']:.3f} deg")
        print(f"   {PROBE_MUSCLE} peak {profile['maximumAbsoluteArm']['momentArmCm']:.4f} cm at "
              f"{profile['maximumAbsoluteArm']['appliedFlexionDeg']:.3f} deg, slope "
              f"{profile['slopeAtBoundaryCmPerDeg']['before']} -> "
              f"{profile['slopeAtBoundaryCmPerDeg']['after']} cm/deg")
        for label, entry in summary.items():
            print(f"   {label:>7} {spline_limit:.0f} deg: {entry['frames']} frames, source max "
                  f"{entry.get('sourceMaximumRatio')} ({entry.get('sourceFramesOverOne')} over 1), "
                  f"candidate max {entry.get('candidateMaximumRatio')} "
                  f"({entry.get('candidateFramesOverOne')} over 1)")
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("SAVED_KNEE_RANGE_VALIDITY", OUTPUT)


if __name__ == "__main__":
    main()
