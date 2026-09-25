"""Check how simple body scaling propagates to squat geometry and moments.

Research probe only. A height ratio does not identify individual segment
proportions, and this single-leg model cannot be treated as a full user body.
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


def sample(model, state):
    for name in ("hip_flexion_r", "knee_angle_r", "ankle_angle_r"):
        model.getCoordinateSet().get(name).setValue(state, pose[name])
    model.assemble(state)
    model.realizePosition(state)
    joints = model.getJointSet()
    hip = joints.get("hip_r").getChildFrame().getPositionInGround(state)
    knee = joints.get("knee_r").getChildFrame().getPositionInGround(state)
    ankle = joints.get("ankle_r").getChildFrame().getPositionInGround(state)
    glute = model.getMuscles().get("glut_max2_r")
    vastus = model.getMuscles().get("vas_int_r")
    return {"massKg": model.getTotalMass(state),
            "femurM": math.dist([hip[i] for i in range(3)], [knee[i] for i in range(3)]),
            "tibiaM": math.dist([knee[i] for i in range(3)], [ankle[i] for i in range(3)]),
            "glutePathM": glute.getLength(state),
            "gluteHipMomentArmM": glute.computeMomentArm(state, model.getCoordinateSet().get("hip_flexion_r")),
            "vastusPathM": vastus.getLength(state)}


model = osim.Model("squatToStand_3dof9musc.osim")
state = model.initSystem()
before = sample(model, state)
factor = 1.10
scales = osim.ScaleSet()
for index in range(model.getBodySet().getSize()):
    body = model.getBodySet().get(index)
    scale = osim.Scale()
    scale.setSegmentName(body.getName())
    scale.setScaleFactors(osim.Vec3(factor, factor, factor))
    scale.setApply(True)
    scales.cloneAndAppend(scale)
if not model.scale(state, scales, False, before["massKg"]):
    raise RuntimeError("OpenSim Model.scale failed")
after = sample(model, state)
print(json.dumps({"status": "research_scaling_probe", "factor": factor,
                  "before": before, "after": after,
                  "ratios": {key: after[key] / before[key] for key in before}}, indent=2))
