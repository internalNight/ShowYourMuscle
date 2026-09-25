"""Reopen and compare sampled Blender paths to OpenSim geometry export."""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache/high-flex-scene/ab02_high_flex_kinematics.json"
data = json.loads(SOURCE.read_text(encoding="utf-8"))
scene = bpy.context.scene
assert scene.frame_start == 1 and scene.frame_end == 21
assert scene["source_subject"] == "AB02"
assert scene["force_status"] == "not_calculated_or_displayed"
assert scene["source_status"] == data["status"]
assert "no force" in scene["path_color_meaning"]
origin = data["frames"][0]["jointsGroundM"]["ground_pelvis"]
checks = 0


def point(values):
    x, y, z = values
    return Vector((z - origin[2], -(x - origin[0]), y))


def check_segment(obj, first, second, label):
    global checks
    delta = second - first
    if delta.length < 5e-4:
        if obj.scale.length > 1e-8:
            raise AssertionError(f"{label}: short segment should be hidden")
        checks += 1
        return
    if (obj.location - (first + second) / 2).length > 1e-5:
        raise AssertionError(f"{label}: center mismatch")
    if abs(obj.scale.z * 2 - delta.length) > 1e-5:
        raise AssertionError(f"{label}: length mismatch")
    direction = obj.rotation_quaternion @ Vector((0, 0, 1))
    if (direction - delta.normalized()).length > 1e-4:
        raise AssertionError(f"{label}: orientation mismatch; length={delta.length}; "
                             f"stored={tuple(direction)} expected={tuple(delta.normalized())}")
    checks += 1


def expected_color(name, ratio):
    neutral = ((0.30, 0.28, 0.38) if name.endswith("_r") else
               (0.25, 0.35, 0.39))
    target = (0.04, 0.62, 0.84) if ratio >= 1 else (0.55, 0.09, 0.78)
    weight = min(abs(ratio - 1) / 0.07, 1.0)
    return tuple((1 - weight) * base + weight * peak
                 for base, peak in zip(neutral, target))


for number in (1, 12, 21):
    scene.frame_set(number)
    frame = data["frames"][number - 1]
    for name, path in frame["muscles"].items():
        line = [point(value) for value in path["pointsGroundM"]]
        objects = sorted((obj for obj in bpy.data.objects
                          if obj.get("opensim_muscle") == name),
                         key=lambda obj: obj["path_segment"])
        if not objects:
            raise AssertionError(f"Missing {name}")
        first_length = data["frames"][0]["muscles"][name]["opensimLengthM"]
        expected_ratio = path["opensimLengthM"] / first_length
        shade = objects[0].data.materials[0]
        actual_color = next(node for node in shade.node_tree.nodes
                            if node.type == "BSDF_PRINCIPLED").inputs[
                                "Base Color"].default_value
        if any(abs(actual_color[i] - expected_color(name, expected_ratio)[i]) > 1e-5
               for i in range(3)):
            raise AssertionError(f"frame {number} {name}: color mismatch")
        checks += 1
        for index, obj in enumerate(objects):
            if abs(obj["length_ratio_to_first_frame"] - expected_ratio) > 1e-6:
                raise AssertionError(f"frame {number} {name}: length ratio mismatch")
            checks += 1
            if index < len(line) - 1:
                check_segment(obj, line[index], line[index + 1],
                              f"frame {number} {name} {index}")
            elif obj.scale.length > 1e-8:
                raise AssertionError(f"frame {number} {name} unused segment visible")
            else:
                checks += 1
    for name in ("ground_pelvis", "hip_r", "hip_l", "walker_knee_r",
                 "walker_knee_l", "ankle_r", "ankle_l", "back"):
        obj = bpy.data.objects[f"joint_{name}"]
        if (obj.location - point(frame["jointsGroundM"][name])).length > 1e-5:
            raise AssertionError(f"frame {number} joint {name} mismatch")
        checks += 1

print(f"HIGH_FLEX_SCENE_REOPEN_OK frames=3 muscles=80 checks={checks}")
