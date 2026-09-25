"""Reload and verify the bilateral path scene against exported OpenSim data."""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
source = json.loads((ROOT / "assets/blender/ab01_bilateral_squat_kinematics.json")
                    .read_text(encoding="utf-8"))
scene = bpy.context.scene
assert scene.frame_start == 1 and scene.frame_end == 21
assert scene["force_status"] == "not_calculated_or_displayed"
assert scene["source_status"] == "measured_ik_model_kinematics_only_no_muscle_force"
origin = source["frames"][0]["jointsGroundM"]["ground_pelvis"]
checks = 0


def point(values):
    x, y, z = values
    return Vector((z - origin[2], -(x - origin[0]), y))


def check_segment(obj, a, b, label):
    global checks
    direction = b - a
    if (obj.location - (a + b) / 2).length > 1e-5:
        raise AssertionError(f"{label}: center mismatch")
    if abs(obj.scale.z * 2 - direction.length) > 1e-5:
        raise AssertionError(f"{label}: length mismatch")
    if (obj.rotation_quaternion @ Vector((0, 0, 1)) - direction.normalized()).length > 1e-4:
        raise AssertionError(f"{label}: orientation mismatch")
    checks += 1


for number in (1, 14, 21):
    scene.frame_set(number)
    frame = source["frames"][number - 1]
    for name, data in frame["muscles"].items():
        line = [point(value) for value in data["pointsGroundM"]]
        objects = sorted((obj for obj in bpy.data.objects
                          if obj.get("opensim_muscle") == name),
                         key=lambda obj: obj["path_segment"])
        for index, obj in enumerate(objects):
            if index < len(line) - 1:
                check_segment(obj, line[index], line[index + 1],
                              f"frame {number} {name} {index}")
            elif obj.scale.length > 1e-8:
                raise AssertionError(f"frame {number} {name} unused segment visible")
            else:
                checks += 1
    bar_a, bar_b = (point(value) for value in frame["barEndsGroundM"])
    check_segment(bpy.data.objects["assumed_welded_barbell"], bar_a, bar_b,
                  f"frame {number} barbell")
    for name, position in frame["jointsGroundM"].items():
        obj = bpy.data.objects.get(f"joint_{name}")
        if obj is not None:
            if (obj.location - point(position)).length > 1e-5:
                raise AssertionError(f"frame {number} joint {name} mismatch")
            checks += 1

print(f"BLENDER_BILATERAL_SQUAT_OK frames=3 muscles=54 checks={checks}")
