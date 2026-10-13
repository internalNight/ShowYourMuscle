"""Precompute OpenSim pose samples for immediate browser slider preview.

The browser combines these single-control samples only while the authoritative
OpenSim service recomputes the full pose. The preview is not a second model.
"""

import json
import os
from pathlib import Path

import opensim as osim

from export_unified_opensim import plant_heels, vec3
from live_pose_server import coordinate_values


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "public/data/unified_pose_basis.json"
MODEL_DIR = ROOT / "assets/opensim"
os.chdir(MODEL_DIR)
model = osim.Model("cyclistFullBodyMuscle.osim")
coordinates = model.getCoordinateSet()
coordinates.get("shoulder_elv_r").setRangeMax(3.1)
coordinates.get("shoulder_elv_l").setRangeMin(-3.1)
state = model.initSystem()
body_names = [model.getBodySet().get(i).getName() for i in range(model.getBodySet().getSize())]
muscles = [model.getMuscles().get(i) for i in range(model.getMuscles().getSize())]
neutral_feet = [model.getBodySet().get(f"calcn_{side}").getTransformInGround(state).p()
                for side in ("r", "l")]
ground = (sum(p.get(0) for p in neutral_feet) / 2,
          sum(p.get(1) for p in neutral_feet) / 2)


def sample(name, angle):
    pose = coordinate_values({name: angle})
    state = model.initSystem()
    pose.update({"pelvis_tx": 0, "pelvis_ty": 0.93})
    plant_heels(model, state, pose, ground[1], ground[0])
    state = model.initSystem()
    for key, value in pose.items():
        coordinates.get(key).setValue(state, value)
    model.realizePosition(state)
    bodies = []
    for body_name in body_names:
        transform = model.getBodySet().get(body_name).getTransformInGround(state)
        rotation = transform.R()
        bodies.append({"p": vec3(transform.p()),
                       "r": [round(rotation.get(row, col), 6)
                             for row in range(3) for col in range(3)]})
    return {"bodies": bodies,
            "lengthsM": [round(muscle.getLength(state), 6) for muscle in muscles]}


knots = {
    "pelvis_tilt": [-1.3, -0.65, 0, 0.65, 1.3],
    "hip_flexion": [-0.4, 0, 0.75, 1.5, 1.99],
    "knee_angle": [0, 0.6, 1.2, 1.8, 2.35],
    "ankle_angle": [-0.55, -0.25, 0, 0.25, 0.48],
    "elv_angle": [-1.48, -0.75, 0, 0.75, 1.48],
    "shoulder_elv": [0, 0.75, 1.5, 2.3, 3.03],
    "elbow_flex": [0, 0.6, 1.2, 1.8, 2.44],
}
reference = json.loads((ROOT / "public/data/unified_opensim_reference.json").read_text())
if body_names != reference["bodyNames"] or [m.getName() for m in muscles] != reference["muscleNames"]:
    raise ValueError("Pose basis model differs from viewer model")
controls = {}
for name, angles in knots.items():
    controls[name] = {"angles": angles, "frames": [sample(name, angle) for angle in angles]}
    print(name, len(angles), flush=True)
OUTPUT.write_text(json.dumps({"schemaVersion": 1, "model": reference["model"],
                              "bodyNames": body_names, "muscleNames": reference["muscleNames"],
                              "controls": controls}, separators=(",", ":")), encoding="utf-8")
print(OUTPUT, OUTPUT.stat().st_size, flush=True)
