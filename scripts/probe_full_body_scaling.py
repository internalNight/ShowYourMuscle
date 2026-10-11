"""Research probe: how a full-body OpenSim model responds to body-data scaling.

This is the measurement behind the decision to put an OpenSim full-body model behind the default view.
It runs the local OpenSim build against the already-downloaded RajagopalLaiUhlrich2023 model and records
three things, each of which the shipped check re-derives from the raw numbers instead of trusting a label:

1. the inventory of the model (bodies, joints, muscles, markers, coordinates, mass), so "full body" is a
   count and not a claim;
2. stature and body-mass scaling, which must move segment lengths in exact proportion to the height factor
   and must hit the requested total mass;
3. a girth-style per-axis widening of one segment, which is the honest response to a circumference input:
   it scales a whole segment (bone and every muscle in it) and therefore moves muscle paths and moment arms
   a little, but it can never set the size of one individual muscle.

Body fat has no representation in an OpenSim model, so the probe does not accept a fat input at all.

OpenSim's C++ layer cannot open a path that contains non-ASCII characters, and this repository lives under
one, so the model is opened by bare filename from its own directory — the same workaround the other scaling
probes in this directory use.
"""

import hashlib
import json
import math
import os
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / ".cache/model-candidates/opensim-models/Models/Rajagopal/RajagopalLaiUhlrich2023.osim"
OUTPUT = ROOT / "docs/data/full_body_scaling_probe.json"
BASELINE_HEIGHT_CM = 175.0
TOLERANCE = 1e-4  # relative tolerance for "the ratio followed the height factor"

MODEL_DIR = MODEL.parent
os.chdir(MODEL_DIR)


def load():
    model = osim.Model(MODEL.name)
    state = model.initSystem()
    return model, state


def body_position(model, state, name):
    return model.getBodySet().get(name).getPositionInGround(state)


def pick_body(model, candidates):
    names = {model.getBodySet().get(i).getName() for i in range(model.getBodySet().getSize())}
    for candidate in candidates:
        if candidate in names:
            return candidate
    return None


def body_distance(model, state, first, second):
    if not first or not second:
        return None
    a = body_position(model, state, first)
    b = body_position(model, state, second)
    return math.dist([a[i] for i in range(3)], [b[i] for i in range(3)])


def measure(model, state, muscle_name):
    muscle = model.getMuscles().get(muscle_name)
    moment_arms = {}
    for coordinate in ("knee_angle_r", "hip_flexion_r"):
        try:
            moment_arms[coordinate] = muscle.computeMomentArm(state, model.getCoordinateSet().get(coordinate))
        except Exception:
            moment_arms[coordinate] = None
    thigh = pick_body(model, ["femur_r", "femur"])
    shank = pick_body(model, ["tibia_r", "tibia"])
    foot = pick_body(model, ["talus_r", "calcaneus_r", "foot_r"])
    upper_arm = pick_body(model, ["humerus_r", "humerus"])
    forearm = pick_body(model, ["ulna_r", "radius_r", "ulna", "radius"])
    return {
        "pathLengthM": muscle.getLength(state),
        "momentArmsM": moment_arms,
        "thighLengthM": body_distance(model, state, thigh, shank),
        "shankLengthM": body_distance(model, state, shank, foot),
        "upperArmLengthM": body_distance(model, state, upper_arm, forearm),
        "totalMassKg": model.getTotalMass(state),
    }


model, state = load()
bodies = [model.getBodySet().get(i).getName() for i in range(model.getBodySet().getSize())]
joints = [model.getJointSet().get(i).getName() for i in range(model.getJointSet().getSize())]
muscles = [model.getMuscles().get(i).getName() for i in range(model.getMuscles().getSize())]
markers = [model.getMarkerSet().get(i).getName() for i in range(model.getMarkerSet().getSize())]
coordinates = [model.getCoordinateSet().get(i).getName() for i in range(model.getCoordinateSet().getSize())]

# The knee-crossing muscle is chosen from what the model actually contains, never assumed.
PREFERRED = ("vasint", "vaslat", "vasmed", "recfem", "gasmed", "gaslat", "bifemlh", "bifemsh", "semimem", "semiten")
knee_muscles = [name for name in muscles if name.endswith("_r") and name.split("_")[0] in PREFERRED]
probe_muscle = knee_muscles[0] if knee_muscles else next(name for name in muscles if name.endswith("_r"))

report = {
    "status": "full_body_scaling_probe_geometry_only",
    "probe": "scripts/probe_full_body_scaling.py",
    "openSimVersion": osim.GetVersion(),
    "model": {
        "path": str(MODEL.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest().upper(),
        "note": "本地已下载的全身候选模型；手骨几何缺 VTP，加载时会打印缺失警告",
    },
    "inventory": {
        "bodies": len(bodies),
        "joints": len(joints),
        "muscles": len(muscles),
        "markers": len(markers),
        "coordinates": len(coordinates),
        "totalMassKg": model.getTotalMass(state),
        "hasLowerLimb": any("femur" in name for name in bodies),
        "hasUpperLimb": any("humerus" in name for name in bodies),
        "hasTrunk": any(name in {"pelvis", "torso"} for name in bodies),
        "sampleBodies": bodies[:12],
        "sampleMuscles": muscles[:12],
        "sampleJoints": joints[:12],
    },
    "baselineHeightCm": BASELINE_HEIGHT_CM,
    "probeMuscle": probe_muscle,
    "tolerance": TOLERANCE,
}


def scaled(factors_by_body, target_mass=None):
    model, state = load()
    if target_mass is None:
        target_mass = model.getTotalMass(state)
    scales = osim.ScaleSet()
    for index in range(model.getBodySet().getSize()):
        name = model.getBodySet().get(index).getName()
        scale = osim.Scale()
        scale.setSegmentName(name)
        scale.setScaleFactors(osim.Vec3(*factors_by_body.get(name, (1.0, 1.0, 1.0))))
        scale.setApply(True)
        scales.cloneAndAppend(scale)
    if not model.scale(state, scales, False, target_mass):
        raise RuntimeError("OpenSim model scaling failed")
    state = model.initSystem()
    return model, state


def body_positions(model, state, names):
    return {name: [round(body_position(model, state, name)[axis], 9) for axis in range(3)] for name in names}


baseline = measure(*load(), probe_muscle)
report["baseline"] = baseline
report["baselineBodyPositionsM"] = body_positions(*load(), bodies)

uniform = {}
for height_cm, weight_kg in ((170.0, 65.0), (175.0, 72.0), (190.0, 95.0)):
    factor = height_cm / BASELINE_HEIGHT_CM
    model, state = scaled({name: (factor, factor, factor) for name in bodies}, target_mass=weight_kg)
    measured = measure(model, state, probe_muscle)
    measured["heightCm"] = height_cm
    measured["targetMassKg"] = weight_kg
    measured["heightFactor"] = factor
    measured["scaleFactors"] = [factor, factor, factor]
    # The scaled model's own body positions are the reference the runtime has to reproduce by scaling the
    # parent-relative translations of the exported skeleton; recording them is what makes that comparable.
    measured["appliedScaleFactors"] = {name: [factor, factor, factor] for name in bodies}
    measured["bodyPositionsInGroundM"] = body_positions(model, state, bodies)
    measured["ratiosToBaseline"] = {
        key: (measured[key] / baseline[key] if baseline.get(key) else None)
        for key in ("pathLengthM", "thighLengthM", "shankLengthM", "upperArmLengthM")
    }
    uniform[f"{height_cm:.0f}cm/{weight_kg:.0f}kg"] = measured
report["uniformScaling"] = uniform

girth = {}
for label, factors in (("thigh+10%", (1.10, 1.0, 1.10)), ("thigh+20%", (1.20, 1.0, 1.20))):
    model, state = scaled({name: (factors if name == "femur_r" else (1.0, 1.0, 1.0)) for name in bodies})
    measured = measure(model, state, probe_muscle)
    measured["scaledBody"] = "femur_r"
    measured["scaleFactors"] = list(factors)
    measured["appliedScaleFactors"] = {name: (list(factors) if name == "femur_r" else [1.0, 1.0, 1.0])
                                       for name in bodies}
    measured["bodyPositionsInGroundM"] = body_positions(model, state, bodies)
    girth[label] = measured
report["girthScaling"] = girth

report["limitations"] = [
    "等比身高缩放是一个假设，不等于识别出用户本人的体段比例",
    "围度只缩放整段（骨与段内全部肌肉），不能设定单块肌肉的体积或大小",
    "OpenSim 模型不表示体脂，体脂不得驱动肌肉几何或发力",
    "本探针只量几何与运动学，没有对照实测动作或肌力，不能据此声称个体化",
    "手骨几何缺 VTP，全身模型的“全身”指下肢＋躯干＋上肢，不含手部细网格",
    "设备端只能显示预先烘焙的网格，运行时缩放是应用自己按比例实现的近似，不是 OpenSim 本体",
]

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "status": report["status"],
    "inventory": report["inventory"],
    "probeMuscle": probe_muscle,
    "uniform": {key: value["ratiosToBaseline"] for key, value in uniform.items()},
    "girth": {key: {"pathLengthM": value["pathLengthM"],
                   "kneeMomentArmM": value["momentArmsM"]["knee_angle_r"]} for key, value in girth.items()},
    "output": str(OUTPUT),
}, ensure_ascii=False, indent=2))
