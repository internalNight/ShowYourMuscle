"""Animate six registered anatomical bone meshes from OpenSim body frames.

The standing registration uses bounding-box centers, so this is a research
overlay only. It does not fit joints, deform muscles or calculate force.

Two measured per-body offsets refine that registration. The patella carries a constant offset found by
blender/optimise_patella_registration.py, which removed almost all of the patellofemoral overlap. The
tibia group deliberately carries no offset: blender/optimise_knee_registration.py searched every
constant correction for it (translation, a pivot shift, a tilt and their combinations) and none clears
the femur-to-tibia overlap, while the translation-only variant that halves the bone-to-bone
intersections also pushes the OpenSim source points further from the bone surfaces, so it was rejected.
The offset read here therefore stays the only one, and the phone layer and this animator keep agreeing
because both read the same report.
"""

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/blender/opensim_anatomy_registration.blend"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
OPTIMISATION = ROOT / "docs/data/patella_registration_optimisation.json"
OUTPUT = ROOT / "assets/blender/opensim_anatomy_bone_motion.blend"
PREVIEW = ROOT / "assets/blender/opensim_anatomy_bone_motion.png"

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
frames = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"]
optimisation = json.loads(OPTIMISATION.read_text(encoding="utf-8"))
if optimisation["status"] != "research_only_patella_registration_search":
    raise AssertionError("unexpected patella registration search report")
bone_offsets = {"patella_r": Vector(optimisation["optimised"]["offsetM"])}
if bone_offsets["patella_r"].length < 0.005:
    raise AssertionError("the searched patella offset collapsed; the registration is unchanged")
objects = {
    "atlas_Hip bone.r": "pelvis",
    "atlas_Femur.r": "femur_r",
    "atlas_Tibia.r": "tibia_r",
    "atlas_Fibula.r": "tibia_r",
    "atlas_Patella.r": "patella_r",
    "atlas_Calcaneus.r": "calcn_r",
}


def body_matrix(data):
    result = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            result[row][col] = data["rotationRows"][row][col]
    result.translation = Vector(data["translationM"])
    return result


scene.frame_set(1)
standing_world = {name: bpy.data.objects[name].matrix_world.copy() for name in objects}
standing_body = {body: body_matrix(frames[0]["blenderBodyFrames"][body])
                 for body in set(objects.values())}
for name, body in objects.items():
    obj = bpy.data.objects[name]
    obj.rotation_mode = "QUATERNION"
    obj["opensim_body"] = body
    obj["registration_status"] = ("shared_standing_bbox_translation_plus_measured_offset"
                                 if body in bone_offsets else "standing_bbox_translation_only")
    obj["motion_status"] = "OpenSim_reference_rigid_body_motion"
    offset = bone_offsets.get(body)
    if offset:
        obj["registration_offset_m"] = tuple(offset)

scene.frame_start = 1
scene.frame_end = len(frames)
scene["status"] = "research_anatomy_bone_motion_only"
scene["notes"] = "Six Z-Anatomy right-leg bone meshes rigidly follow OpenSim body frames; shared standing bbox translation plus a measured constant offset on the patella. The searched tibia offset was rejected, see blender/optimise_knee_registration.py. No joint fitting or force."
scene["patella_registration_offset_m"] = tuple(bone_offsets["patella_r"])
for number, frame in enumerate(frames, start=1):
    scene.frame_set(number)
    for name, body in objects.items():
        obj = bpy.data.objects[name]
        current_body = body_matrix(frame["blenderBodyFrames"][body])
        offset = bone_offsets.get(body)
        placed = standing_world[name] if offset is None else Matrix.Translation(offset) @ standing_world[name]
        obj.matrix_world = current_body @ standing_body[body].inverted() @ placed
        obj.keyframe_insert(data_path="location", frame=number)
        obj.keyframe_insert(data_path="rotation_quaternion", frame=number)
        obj.keyframe_insert(data_path="scale", frame=number)

scene.frame_set(51)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print("SAVED_ANATOMY_BONE_MOTION", OUTPUT, "frames", len(frames), "bones", len(objects),
      "patella_offset_m", tuple(round(value, 5) for value in bone_offsets["patella_r"]))
