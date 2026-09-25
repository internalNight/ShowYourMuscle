"""Inventory source-model muscle path points in their parent body frames.

These are OpenSim model coordinates, not anatomical landmarks validated
against the Z-Anatomy meshes. Wrap points are pose-dependent and excluded.
"""

import json
import os
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "assets/opensim/squatToStand_3dof9musc.osim"
ANGLES = ROOT / "assets/opensim/squat_angles.json"
OUTPUT = ROOT / "docs/data/opensim_squat_attachment_inventory.json"

os.chdir(MODEL.parent)
model = osim.Model(MODEL.name)
state = model.initSystem()
first = json.loads(ANGLES.read_text(encoding="utf-8"))["frames"][0]
for name in ("hip_flexion_r", "knee_angle_r", "ankle_angle_r"):
    model.getCoordinateSet().get(name).setValue(state, first[name])
model.assemble(state)
model.realizePosition(state)
ankle = model.getJointSet().get("ankle_r").getChildFrame().getPositionInGround(state)


def triples(point):
    return [float(point[index]) for index in range(3)]


def viewer(point):
    return [0.18 + point[2] - ankle[2],
            0.10 + point[1] - ankle[1],
            point[0] - ankle[0]]


def blender(point):
    x, y, z = viewer(point)
    return [0.09 - x, -z, y]


muscles = []
for index in range(model.getMuscles().getSize()):
    muscle = model.getMuscles().get(index)
    path = muscle.getGeometryPath()
    set_of_points = path.getPathPointSet()
    points = []
    for point_index in range(set_of_points.getSize()):
        point = set_of_points.get(point_index)
        world = point.getLocationInGround(state)
        points.append({"name": point.getName(), "class": point.getConcreteClassName(),
                       "parentFrame": point.getParentFrame().getAbsolutePathString(),
                       "localPositionM": triples(point.getLocation(state)),
                       "standingViewerPositionM": viewer(world),
                       "standingBlenderPositionM": blender(world)})
    wraps = []
    for wrap_index in range(path.getWrapSet().getSize()):
        wrap = path.getWrapSet().get(wrap_index)
        wraps.append({"name": wrap.getName(), "wrapObject": wrap.getWrapObjectName()})
    muscles.append({"name": muscle.getName(), "points": points, "wraps": wraps,
                    "standingMusculotendonLengthM": muscle.getLength(state)})

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps({
    "status": "source_model_attachment_inventory_only",
    "model": MODEL.name,
    "pose": "app squat reference frame 1",
    "muscles": muscles,
    "limits": ["path points belong to the OpenSim example and are not fitted to Z-Anatomy meshes",
               "pose-dependent wrap points are not listed as fixed attachments",
               "the model contains only one right leg and a simplified trunk"],
}, indent=2) + "\n", encoding="utf-8")
print("EXPORTED_SQUAT_ATTACHMENT_INVENTORY", len(muscles), "muscles",
      sum(len(item["points"]) for item in muscles), "source path points",
      sum(len(item["wraps"]) for item in muscles), "wrap associations")
