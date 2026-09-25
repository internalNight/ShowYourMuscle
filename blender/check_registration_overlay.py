"""Check the saved standing overlay's two-bone center registration."""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / "docs/data/standing_registration_probe.json").read_text(encoding="utf-8"))
frame = json.loads((ROOT / "public/data/squat_opensim_reference.json").read_text(encoding="utf-8"))["frames"][0]
assert bpy.context.scene["status"] == "static_standing_registration_review_only"
assert bpy.context.scene.frame_start == bpy.context.scene.frame_end == 1
assert report["status"] == "standing_bbox_translation_probe_only"
assert len(bpy.data.collections["04_Z_Anatomy_Standing_Bone_Overlay"].objects) == 6


def convert(point):
    x, y, z = point
    return Vector((0.09 - x, -z, y))


def bounds_center(obj):
    corners = [obj.matrix_world @ Vector(point) for point in obj.bound_box]
    return Vector(tuple((min(point[axis] for point in corners) +
                         max(point[axis] for point in corners)) / 2 for axis in range(3)))


for name, a, b in (("Femur.r", "hip", "knee"), ("Tibia.r", "knee", "ankle")):
    target = (convert(frame["viewerJointsM"][a]) + convert(frame["viewerJointsM"][b])) / 2
    residual = (target - bounds_center(bpy.data.objects["atlas_" + name])).length
    if abs(residual - report["centerResidualsM"][name]) > 1e-5 or residual > 0.01:
        raise AssertionError(f"{name} standing bbox center mismatch: {residual}")

print("BLENDER_REGISTRATION_OK six static bones; femur/tibia bbox-center residuals < 1 cm")
