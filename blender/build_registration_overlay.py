"""Overlay right-leg Z-Anatomy bones on the OpenSim standing pose for review.

This is a static registration study, not a completed anatomical rig.
"""

from pathlib import Path
import json

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
MOTION = ROOT / "assets/blender/opensim_squat_reference.blend"
ANATOMY = ROOT / "public/models/z_anatomy_reference.glb"
OUTPUT = ROOT / "assets/blender/opensim_anatomy_registration.blend"
PREVIEW = ROOT / "assets/blender/opensim_anatomy_registration.png"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REPORT = ROOT / "docs/data/standing_registration_probe.json"
bpy.ops.wm.open_mainfile(filepath=str(MOTION))
scene = bpy.context.scene
scene.frame_set(1)
existing = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(ANATOMY))
new_objects = set(bpy.data.objects) - existing
keep = {"Femur.r", "Tibia.r", "Fibula.r", "Hip bone.r", "Patella.r", "Calcaneus.r"}
overlay = bpy.data.collections.new("04_Z_Anatomy_Standing_Bone_Overlay")
scene.collection.children.link(overlay)
for obj in new_objects:
    if obj.type != "MESH" or obj.name not in keep:
        bpy.data.objects.remove(obj, do_unlink=True)
        continue
    source_name = obj.name
    for group in list(obj.users_collection):
        group.objects.unlink(obj)
    overlay.objects.link(obj)
    obj.name = "atlas_" + source_name
    obj["source_name"] = source_name
    obj["static_registration_only"] = True
    shade = bpy.data.materials.new("Z-Anatomy 静态骨骼 " + source_name)
    shade.diffuse_color = (0.95, 0.64, 0.18, 1)
    shade.use_nodes = True
    nodes = shade.node_tree.nodes
    shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = (0.95, 0.64, 0.18, 1)
    shader.inputs["Roughness"].default_value = 0.65
    obj.data.materials.clear()
    obj.data.materials.append(shade)


def center_of_bounds(obj):
    corners = [obj.matrix_world @ Vector(point) for point in obj.bound_box]
    return Vector(tuple((min(point[axis] for point in corners) +
                         max(point[axis] for point in corners)) / 2 for axis in range(3)))


def to_blender(point):
    x, y, z = point
    return Vector((0.09 - x, -z, y))


standing = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"][0]["viewerJointsM"]
targets = {
    "Femur.r": (to_blender(standing["hip"]) + to_blender(standing["knee"])) / 2,
    "Tibia.r": (to_blender(standing["knee"]) + to_blender(standing["ankle"])) / 2,
}
shifts = [target - center_of_bounds(bpy.data.objects["atlas_" + name])
          for name, target in targets.items()]
shift = sum(shifts, Vector((0, 0, 0))) / len(shifts)
for obj in overlay.objects:
    world_matrix = obj.matrix_world.copy()
    world_matrix.translation += shift
    obj.matrix_world = world_matrix
residuals = {name: (target - center_of_bounds(bpy.data.objects["atlas_" + name])).length
             for name, target in targets.items()}
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps({
    "status": "standing_bbox_translation_probe_only",
    "anatomySource": "Z-Anatomy / BodyParts3D, CC BY-SA 4.0",
    "opensimSource": LOOKUP.relative_to(ROOT).as_posix(),
    "translationM": list(shift),
    "centerResidualsM": residuals,
    "limitations": ["femur and tibia bounding boxes are not joint landmarks",
                    "no rotation, bone-length fitting, muscle attachments, or deformation",
                    "single right-leg standing comparison only"],
}, indent=2) + "\n", encoding="utf-8")

scene.frame_start = 1
scene.frame_end = 1
scene["status"] = "static_standing_registration_review_only"
scene["anatomy_source"] = "Z-Anatomy / BodyParts3D, CC BY-SA 4.0"
scene["registration_translation_m"] = tuple(shift)
scene["registration_residuals_m"] = json.dumps(residuals)
scene["notes"] = "Translation from femur/tibia bbox centers only; no joint/attachment fitting, deformation or force."
scene.camera.data.ortho_scale = 1.6
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
selected = [obj.name for obj in overlay.objects]
if len(selected) != len(keep):
    raise RuntimeError(f"Expected six right-leg reference meshes, got {selected}")
print("SAVED_REGISTRATION", OUTPUT, selected, "translation_m", tuple(round(v, 4) for v in shift),
      "residuals_m", {name: round(value, 4) for name, value in residuals.items()})
