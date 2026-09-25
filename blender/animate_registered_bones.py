"""Animate six registered anatomical bone meshes from OpenSim body frames.

The standing registration uses bounding-box centers, so this is a research
overlay only. It does not fit joints, deform muscles or calculate force.
"""

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/blender/opensim_anatomy_registration.blend"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
OUTPUT = ROOT / "assets/blender/opensim_anatomy_bone_motion.blend"
PREVIEW = ROOT / "assets/blender/opensim_anatomy_bone_motion.png"

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
frames = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"]
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
    obj["registration_status"] = "standing_bbox_translation_only"
    obj["motion_status"] = "OpenSim_reference_rigid_body_motion"

scene.frame_start = 1
scene.frame_end = len(frames)
scene["status"] = "research_anatomy_bone_motion_only"
scene["notes"] = "Six Z-Anatomy right-leg bone meshes rigidly follow OpenSim body frames; shared standing bbox translation only. Patella and calcaneus lack independent landmark registration; no joint fitting or force."
for number, frame in enumerate(frames, start=1):
    scene.frame_set(number)
    for name, body in objects.items():
        obj = bpy.data.objects[name]
        current_body = body_matrix(frame["blenderBodyFrames"][body])
        obj.matrix_world = current_body @ standing_body[body].inverted() @ standing_world[name]
        obj.keyframe_insert(data_path="location", frame=number)
        obj.keyframe_insert(data_path="rotation_quaternion", frame=number)
        obj.keyframe_insert(data_path="scale", frame=number)

scene.frame_set(51)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print("SAVED_ANATOMY_BONE_MOTION", OUTPUT, "frames", len(frames), "bones", len(objects))
