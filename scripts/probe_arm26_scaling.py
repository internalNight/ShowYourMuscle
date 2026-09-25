"""Verify uniform OpenSim scaling of the Arm26 press-path research model."""

import json
import os
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "assets" / "opensim"
os.chdir(MODEL_DIR)
model = osim.Model("arm26.osim")
state = model.initSystem()


def sample():
    coordinates = model.getCoordinateSet()
    coordinates.get("r_shoulder_elev").setValue(state, 2.6)
    coordinates.get("r_elbow_flex").setValue(state, 0.25)
    model.assemble(state)
    model.realizePosition(state)
    tri = model.getMuscles().get("TRIlong")
    bic = model.getMuscles().get("BICshort")
    return {"tricepsPathM": tri.getLength(state),
            "tricepsElbowMomentArmM": tri.computeMomentArm(state, coordinates.get("r_elbow_flex")),
            "bicepsPathM": bic.getLength(state)}


before = sample()
factor = 1.1
scales = osim.ScaleSet()
for index in range(model.getBodySet().getSize()):
    scale = osim.Scale()
    scale.setSegmentName(model.getBodySet().get(index).getName())
    scale.setScaleFactors(osim.Vec3(factor, factor, factor))
    scale.setApply(True)
    scales.cloneAndAppend(scale)
if not model.scale(state, scales, False, model.getTotalMass(state)):
    raise RuntimeError("Arm26 scaling failed")
after = sample()
print(json.dumps({"status": "research_scaling_probe", "factor": factor,
                  "before": before, "after": after,
                  "ratios": {name: after[name] / before[name] for name in before}}, indent=2))
