"""Inspect where the current OpenSim squat places the torso relative to foot."""

import json
import os
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "assets" / "opensim"
all_angles = json.loads((MODEL_DIR / "squat_angles.json").read_text(encoding="utf-8"))["frames"]
angles = all_angles[50]
os.chdir(MODEL_DIR)
model = osim.Model("squatToStand_3dof9musc.osim")
state = model.initSystem()
coords = model.getCoordinateSet()
for name in ("knee_angle_r", "ankle_angle_r"):
    coords.get(name).setValue(state, angles[name])
frames = {name: model.getJointSet().get(joint).getChildFrame()
          for name, joint in (("ankle", "ankle_r"), ("back", "back"), ("hip", "hip_r"))}
print("hip angle rad | back forward from ankle cm | hip forward from ankle cm")
for hip_angle in (-2.0, -1.8, -1.64, -1.4, -1.2, -1.0, -0.8):
    coords.get("hip_flexion_r").setValue(state, hip_angle)
    model.assemble(state)
    model.realizePosition(state)
    ankle_x = frames["ankle"].getPositionInGround(state)[0]
    back_x = frames["back"].getPositionInGround(state)[0]
    hip_x = frames["hip"].getPositionInGround(state)[0]
    print(f"{hip_angle:>12.2f} | {(back_x - ankle_x) * 100:>26.1f} | {(hip_x - ankle_x) * 100:>25.1f}")

coords.get("hip_flexion_r").setValue(state, angles["hip_flexion_r"])
model.assemble(state)
model.realizePosition(state)
ankle_x = frames["ankle"].getPositionInGround(state)[0]
torso = model.getBodySet().get("torso")
print("\nLocal torso point x m | global load line forward from ankle cm")
for point_x in (0, 0.1, 0.2, 0.3):
    point = torso.findStationLocationInGround(state, osim.Vec3(point_x, 0.45, 0))
    print(f"{point_x:>21.2f} | {(point[0] - ankle_x) * 100:>39.1f}")

print("\nphase | original load line cm | +0.12m load line cm")
for index in (0, 25, 50, 75, 100):
    pose = all_angles[index]
    for name in ("hip_flexion_r", "knee_angle_r", "ankle_angle_r"):
        coords.get(name).setValue(state, pose[name])
    model.assemble(state)
    model.realizePosition(state)
    ankle_x = frames["ankle"].getPositionInGround(state)[0]
    load_lines = []
    for point_x in (0, 0.12):
        load_x = torso.findStationLocationInGround(state, osim.Vec3(point_x, 0.45, 0))[0]
        load_lines.append((load_x - ankle_x) * 100)
    print(f"{pose['phase']:>5.2f} | {load_lines[0]:>21.1f} | {load_lines[1]:>19.1f}")
