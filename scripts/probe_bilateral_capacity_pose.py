"""Independently re-derive the deep-squat independent-coordinate capacity audit.

The repository's capacity audit reports that the experimental hip-rotation demand exceeds the
"optimistic independent upper bound" in 21/21 deep-squat frames, by a factor of 5-9. An upper bound
should be hard to exceed, so this probe re-checks the two inputs that could fabricate it:

1. the pose that the audit evaluates moment arms at, compared with the experimental IK row;
2. the capacity itself, decomposed per muscle, plus the same bound for the neighbouring axes
   (hip flexion, adduction, knee) as a control - if those sit comfortably inside capacity while only
   hip rotation does not, the violation is specific to that axis rather than a broken pose or unit.

It reuses the repository's own loaders so agreement or disagreement is about the audit's logic, not
about a second implementation of file parsing.
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
REPORT = ROOT / "docs/data/bilateral_deep_squat_capacity_pose_check.json"
POSE_COORDINATES = ("pelvis_tilt", "pelvis_list", "pelvis_rotation", "hip_flexion_r",
                    "hip_adduction_r", "hip_rotation_r", "knee_angle_r", "ankle_angle_r",
                    "lumbar_extension", "lumbar_bending", "lumbar_rotation")
CONTROL_COORDINATES = ("hip_flexion_r", "hip_adduction_r", "hip_rotation_r", "knee_angle_r",
                       "ankle_angle_r", "hip_flexion_l", "hip_rotation_l")
NAMED_MUSCLES = ("glut_max_r", "glut_med1_r", "glut_med2_r", "glut_med3_r", "glut_min1_r",
                 "glut_min2_r", "glut_min3_r", "quad_fem_r", "gem_r", "peri_r", "tfl_r",
                 "iliacus_r", "psoas_r", "add_mag2_r", "add_long_r", "bifemlh_r", "sar_r",
                 "semimem_r", "ercspn_r")

def read_ik_rows(ik_path):
    lines = ik_path.read_text(encoding="utf-8").splitlines()
    start = lines.index("endheader")
    names = lines[start + 1].split()
    return [dict(zip(names, [float(value) for value in line.split()]))
            for line in lines[start + 2:] if line.strip()]


def pose_context(subject):
    """Range of the pelvis and hip coordinates over a whole trial.

    The capacity audit quotes one frame. Whether its striking pelvis_rotation value is a real
    transverse rotation or a fixed global heading offset decides whether the hip-rotation demand can
    be read as an anatomical torque, so the whole trial is the relevant context.
    """
    config = CONFIGS[subject]
    ik_path = (ROOT / ".cache/lower-limb" /
               f"{subject}_ik_{config['ikInterval'][0]}_{config['ikInterval'][1]}.mot")
    rows = read_ik_rows(ik_path)
    tracked = ("pelvis_tilt", "pelvis_list", "pelvis_rotation", "hip_rotation_r", "hip_rotation_l",
               "hip_flexion_r", "hip_flexion_l", "hip_adduction_r", "knee_angle_r")
    context = {"frameCount": len(rows)}
    for name in tracked:
        values = np.array([row[name] for row in rows])
        context[name] = {"minDeg": round(float(values.min()), 3),
                         "medianDeg": round(float(np.median(values)), 3),
                         "maxDeg": round(float(values.max()), 3),
                         "spanDeg": round(float(values.max() - values.min()), 3)}
    # A near-constant pelvis_rotation that differs in sign between subjects is a capture-frame
    # heading convention rather than a transverse rotation, and it decides how the hip-rotation
    # coordinates (and therefore the hip-rotation demands) may be read.
    deepest = max(rows, key=lambda row: abs(row["knee_angle_r"]))
    context["deepestKneeFrame"] = {
        "timeS": deepest["time"], "kneeAngleRDeg": round(deepest["knee_angle_r"], 3),
        "coordinates": {name: round(deepest[name], 3) for name in tracked}}
    context["hipRotationAtDeepestFrameRatio"] = {
        side: round(abs(deepest[f"hip_rotation_{side}"]) / abs(deepest[f"hip_flexion_{side}"]), 3)
        for side in ("r", "l")}
    return context


subject = "AB01"
config = CONFIGS[subject]
target_time_s = config["targetTimeS"]
ik_path = ROOT / f".cache/lower-limb/{subject}_ik_{config['ikInterval'][0]}_{config['ikInterval'][1]}.mot"
model_path = ROOT / ".cache/lower-limb-raw" / subject / "Models" / f"{subject}-Scaled1.osim"
id_path = ROOT / ".cache/lower-limb/id-reproduction" / (
    f"{subject}_id_{config['ikInterval'][0]}_{config['ikInterval'][1]}.sto")
source_moment_path = ROOT / ".cache/lower-limb-raw" / subject / "CSV_Data/squats_1/Joint_Moments.csv"

osim.Logger.setLevelString("Error")
names, id_values = read_sto(id_path)
source_moments = read_csv(source_moment_path)
subject_mass = subject_masses()[subject]
target_index = int(np.argmin(abs(id_values[:, 0] - target_time_s)))
moments = dict(zip(names[1:], id_values[target_index, 1:]))
source_index = int(round(target_time_s / 0.005))
ik_row = read_ik_nearest(target_time_s, ik_path)

model = osim.Model(str(model_path.relative_to(ROOT)))
state = model.initSystem()
apply_row(model, state, ik_row)
muscles = [model.getMuscles().get(i) for i in range(model.getMuscles().getSize())]
strengths = np.array([muscle.getMaxIsometricForce() for muscle in muscles])
names_by_index = [muscle.getName() for muscle in muscles]

report = {"status": "research_only_capacity_pose_check",
          "subject": subject, "timeS": target_time_s,
          "modelPath": str(model_path.relative_to(ROOT)),
          "source": "re-derivation of audit_bilateral_joint_capacity.py inputs",
          "muscleCount": len(muscles),
          "poseContext": {name: pose_context(name) for name in CONFIGS},
          "totalMaxIsometricForceN": round(float(strengths.sum()), 1),
          "poseApplication": {}, "coordinates": {}}

# 1. Did apply_row actually put the model in the experimental pose?
for name in POSE_COORDINATES:
    coordinate = model.getCoordinateSet().get(name)
    report["poseApplication"][name] = {
        "experimentalIkDegrees": round(float(ik_row[name]), 4),
        "modelValueDegrees": round(float(np.degrees(coordinate.getValue(state))), 4),
        "appliedAsRequested": bool(abs(np.degrees(coordinate.getValue(state)) - ik_row[name]) < 1e-6)}

# 2. Recompute the bound and show which muscles supply it.
for name in CONTROL_COORDINATES:
    coordinate = model.getCoordinateSet().get(name)
    target = float(moments[name + "_moment"])
    arms = np.array([muscle.computeMomentArm(state, coordinate) for muscle in muscles])
    same_direction = arms if target >= 0 else -arms
    contributions = np.maximum(same_direction, 0) * strengths
    capacity = float(contributions.sum())
    source_target = float(source_moments[name + "_moment"][source_index] * subject_mass)
    source_direction = arms if source_target >= 0 else -arms
    source_capacity = float((np.maximum(source_direction, 0) * strengths).sum())
    # The bound is per direction: muscles whose arm points the other way cannot help. Quantify both
    # the opposite-direction bound and how well the two independent demand estimates agree, because
    # a comparison is only meaningful when the demand uncertainty stays below the bound itself.
    opposite_capacity = float((np.maximum(-same_direction, 0) * strengths).sum())
    disagreement = abs(target - source_target)
    report["coordinates"][name] = {
        "replayedIdMomentNm": round(target, 3),
        "sourceCsvMomentNm": round(source_target, 3),
        "optimisticCapacityNm": round(capacity, 3),
        "replayedDemandToCapacity": round(abs(target) / capacity, 3) if capacity > 1e-6 else None,
        "sourceDemandToCapacity": round(abs(source_target) / source_capacity, 3)
                                  if source_capacity > 1e-6 else None,
        "oppositeDirectionCapacityNm": round(opposite_capacity, 3),
        "directionAsymmetryRatio": round(max(capacity, opposite_capacity) /
                                         min(capacity, opposite_capacity), 2)
                                   if min(capacity, opposite_capacity) > 1e-6 else None,
        "demandEstimateDisagreementNm": round(disagreement, 3),
        "disagreementToCapacity": round(disagreement / capacity, 3) if capacity > 1e-6 else None,
        "musclesWithSameDirectionArm": int((contributions > 1e-6).sum()),
        "topContributors": [{"muscle": names_by_index[i],
                             "momentArmCm": round(float(same_direction[i]) * 100, 3),
                             "maxIsometricForceN": round(float(strengths[i]), 1),
                             "capacityNm": round(float(contributions[i]), 3)}
                            for i in np.argsort(contributions)[::-1][:6]
                            if contributions[i] > 1e-6],
        "namedMuscleMomentArmsCm": {muscle_name: round(float(same_direction[names_by_index.index(
            muscle_name)]) * 100, 3) for muscle_name in NAMED_MUSCLES
            if muscle_name in names_by_index},
    }

# 3. How much of the hip-rotation bound comes from the small deep rotators alone?
rotation = model.getCoordinateSet().get("hip_rotation_r")
rotation_target = float(moments["hip_rotation_r_moment"])
rotation_arms = np.array([muscle.computeMomentArm(state, rotation) for muscle in muscles])
signed = rotation_arms if rotation_target >= 0 else -rotation_arms
rotators = [index for index, muscle_name in enumerate(names_by_index)
            if muscle_name.startswith(("quad_fem", "gem_", "peri_"))]
report["hipRotationBoundDecomposition"] = {
    "smallRotatorsNm": round(float((np.maximum(signed[rotators], 0) * strengths[rotators]).sum()), 3),
    "allOtherMusclesNm": round(float((np.maximum(signed, 0) * strengths).sum())
                               - float((np.maximum(signed[rotators], 0) * strengths[rotators]).sum()), 3),
    "largestAbsoluteArmCm": round(float(np.max(np.abs(rotation_arms))) * 100, 3),
    "largestAbsoluteArmMuscle": names_by_index[int(np.argmax(np.abs(rotation_arms)))],
    "hipSpanningMusclesWithArmBelow1mm": int(np.sum(np.abs(rotation_arms) < 1e-3)),
    "muscleWithLargestIsometricForceN": {
        "muscle": names_by_index[int(np.argmax(strengths))],
        "maxIsometricForceN": round(float(np.max(strengths)), 1),
        "armAboutHipRotationCm": round(float(rotation_arms[int(np.argmax(strengths))]) * 100, 3)}}
report["limitations"] = [
    "optimistic independent coordinate bound: ignores force-length, passive tissue and coupling",
    "the demand is the experimental inverse-dynamics moment for one subject and one deep-squat segment",
    "moment arms are from the released scaled model, not from medical imaging of this subject",
    "no muscle force is solved here, so neither bound nor demand is a measured muscle force",
    "a high demand-to-capacity ratio is only interpretable while the two independent demand "
    "estimates agree to well below the bound; disagreementToCapacity records that margin"]

# The comparison is only informative when the demand is known much better than the bound is small.
unusable = [name for name, item in report["coordinates"].items()
            if (item["disagreementToCapacity"] or 0) > 0.5]
report["comparisonsUnderminedByDemandUncertainty"] = sorted(unusable)

REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"poseApplied": all(item["appliedAsRequested"] for item in
                                    report["poseApplication"].values()),
                  "pose": {name: item["modelValueDegrees"] for name, item in
                           report["poseApplication"].items()},
                  "ratios": {name: (item["replayedDemandToCapacity"], item["sourceDemandToCapacity"])
                             for name, item in report["coordinates"].items()},
                  "hipRotationBound": report["hipRotationBoundDecomposition"]}, indent=2))
print("SAVED_BILATERAL_CAPACITY_POSE_CHECK", REPORT)
