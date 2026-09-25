"""Research probe: uniform stature and body-mass scaling of the single-leg squat model.

The model is not validated as a personalized force predictor. Its torso and
pelvis are divided by two to approximate one side of a symmetric person;
input weight is then mapped to one half of the person's total body mass.
"""

import json
import math
import os
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "assets" / "opensim"
pose = json.loads((MODEL_DIR / "squat_angles.json").read_text(encoding="utf-8"))["frames"][50]
os.chdir(MODEL_DIR)


def sample(height_cm, weight_kg):
    model = osim.Model("squatToStand_3dof9musc.osim")
    for name in ("pelvis", "torso"):
        body = model.updBodySet().get(name)
        body.setMass(body.getMass() / 2)
        inertia = body.get_inertia()
        halved = osim.Vec6(0)
        for index in range(6):
            halved.set(index, inertia.get(index) / 2)
        body.set_inertia(halved)
    state = model.initSystem()
    factor = height_cm / 175
    scales = osim.ScaleSet()
    for index in range(model.getBodySet().getSize()):
        scale = osim.Scale()
        scale.setSegmentName(model.getBodySet().get(index).getName())
        scale.setScaleFactors(osim.Vec3(factor, factor, factor))
        scale.setApply(True)
        scales.cloneAndAppend(scale)
    target_mass = weight_kg / 2
    if not model.scale(state, scales, False, target_mass):
        raise RuntimeError("OpenSim model scaling failed")
    for name in ("hip_flexion_r", "knee_angle_r", "ankle_angle_r"):
        model.getCoordinateSet().get(name).setValue(state, pose[name])
    model.assemble(state)
    model.realizePosition(state)
    joints = model.getJointSet()
    hip = joints.get("hip_r").getChildFrame().getPositionInGround(state)
    knee = joints.get("knee_r").getChildFrame().getPositionInGround(state)
    ankle = joints.get("ankle_r").getChildFrame().getPositionInGround(state)
    muscle = model.getMuscles().get("vas_int_r")
    return {
        "heightCm": height_cm,
        "personWeightKg": weight_kg,
        "singleSideTargetMassKg": target_mass,
        "singleSideActualMassKg": model.getTotalMass(state),
        "bodyMassesKg": {name: model.getBodySet().get(name).getMass()
                         for name in ("torso", "pelvis", "femur_r", "tibia_r")},
        "femurLengthM": math.dist([hip[i] for i in range(3)], [knee[i] for i in range(3)]),
        "tibiaLengthM": math.dist([knee[i] for i in range(3)], [ankle[i] for i in range(3)]),
        "vastusPathM": muscle.getLength(state),
        "vastusKneeMomentArmM": muscle.computeMomentArm(state, model.getCoordinateSet().get("knee_angle_r")),
    }


cases = [sample(175, 72), sample(175, 90), sample(190, 72), sample(190, 90)]
baseline = cases[0]
for case in cases:
    if abs(case["singleSideActualMassKg"] - case["singleSideTargetMassKg"]) > 1e-8:
        raise AssertionError("Scaled model did not meet its target total mass")
    ratio = case["heightCm"] / baseline["heightCm"]
    for key in ("femurLengthM", "tibiaLengthM", "vastusPathM", "vastusKneeMomentArmM"):
        if abs(case[key] / baseline[key] - ratio) > 1e-6:
            raise AssertionError(f"{key} did not follow uniform geometry scaling")
report = {
    "status": "single_leg_anthropometric_scaling_probe_only",
    "model": "squatToStand_3dof9musc.osim",
    "poseFrame": 50,
    "cases": cases,
    "ratiosToBaseline": [
        {key: case[key] / baseline[key] for key in
         ("singleSideActualMassKg", "femurLengthM", "tibiaLengthM", "vastusPathM", "vastusKneeMomentArmM")}
        for case in cases
    ],
    "limitations": [
        "model has one leg and simplified axial bodies",
        "half-axial mass and symmetric body-weight split are research assumptions",
        "uniform stature scaling does not identify segment proportions",
        "muscle strength and body-fat distribution are not personalized",
        "no validation against measured human motion or forces",
    ],
}
output = ROOT / "docs" / "data" / "person_scaling_probe.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"status": report["status"], "cases": cases, "output": str(output)}, ensure_ascii=False))
