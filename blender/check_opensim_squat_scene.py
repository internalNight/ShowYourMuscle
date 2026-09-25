"""Check saved Blender OpenSim reference against the app's lookup JSON."""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
source = json.loads((ROOT / "public/data/squat_opensim_reference.json").read_text(encoding="utf-8"))
scene = bpy.context.scene
assert scene.frame_start == 1 and scene.frame_end == 101
assert scene["source_status"] == "reference_model_kinematics_only"
assert scene["force_status"] == "not_calculated"
assert len(source["frames"]) == 101
sample_numbers = (1, 26, 51, 76, 101)
bone_names = (("foot", "ankle"), ("ankle", "knee"), ("knee", "hip"), ("hip", "back"))
checks = 0


def to_blender(point):
    x, y, z = point
    return Vector((0.09 - x, -z, y))


def check_segment(obj, a, b, label):
    global checks
    direction = b - a
    if (obj.location - (a + b) / 2).length > 1e-5:
        raise AssertionError(f"{label}: center mismatch")
    if abs(obj.scale.z * 2 - direction.length) > 1e-5:
        raise AssertionError(f"{label}: length mismatch")
    oriented = obj.rotation_quaternion @ Vector((0, 0, 1))
    if (oriented - direction.normalized()).length > 1e-4:
        raise AssertionError(f"{label}: direction mismatch")
    checks += 1


for number in sample_numbers:
    scene.frame_set(number)
    frame = source["frames"][number - 1]
    joints = {name: to_blender(value) for name, value in frame["viewerJointsM"].items()}
    for (a, b) in bone_names:
        check_segment(bpy.data.objects[f"bone_{a}_{b}"], joints[a], joints[b],
                      f"frame {number} bone {a}-{b}")
    for name in ("foot", "ankle", "knee", "hip", "back"):
        if (bpy.data.objects[f"joint_{name}"].location - joints[name]).length > 1e-5:
            raise AssertionError(f"frame {number} joint {name} mismatch")
        checks += 1
    for muscle, data in frame["muscles"].items():
        path = [to_blender(point) for point in data["viewerPathM"]]
        candidates = [obj for obj in bpy.data.objects if obj.get("opensim_muscle") == muscle]
        for obj in candidates:
            segment_index = obj["path_segment"]
            if segment_index < len(path) - 1:
                check_segment(obj, path[segment_index], path[segment_index + 1],
                              f"frame {number} muscle {muscle} segment {segment_index}")
            elif obj.scale.length > 1e-8:
                raise AssertionError(f"frame {number} muscle {muscle} unused segment is visible")
            else:
                checks += 1

print(f"BLENDER_OPENSIM_SQUAT_OK frames={len(sample_numbers)} checks={checks}")
