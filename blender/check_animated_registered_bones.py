"""Check saved anatomical bone motion against OpenSim body frames."""

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
frames = json.loads((ROOT / "public/data/squat_opensim_reference.json").read_text(encoding="utf-8"))["frames"]
optimisation = json.loads((ROOT / "docs/data/patella_registration_optimisation.json").read_text(encoding="utf-8"))
scene = bpy.context.scene
assert scene["status"] == "research_anatomy_bone_motion_only"
assert scene.frame_start == 1 and scene.frame_end == 101
# The patella offset is a measured constant, so the scene must carry exactly the searched one.
expected_offset = Vector(optimisation["optimised"]["offsetM"])
recorded = Vector(scene["patella_registration_offset_m"])
assert (recorded - expected_offset).length < 1e-6, \
    f"scene patella offset {tuple(recorded)} differs from the search {tuple(expected_offset)}"
assert bpy.data.objects["atlas_Patella.r"]["registration_status"] == \
    "shared_standing_bbox_translation_plus_measured_offset"

# The searched tibia offset was rejected, so the scene must not carry one.
knee = json.loads((ROOT / "docs/data/knee_registration_optimisation.json").read_text(encoding="utf-8"))
assert "tibia_registration_offset_m" not in scene, \
    "the rejected tibia registration offset is being applied to the scene"
assert bpy.data.objects["atlas_Tibia.r"]["registration_status"] == "standing_bbox_translation_only"
assert bpy.data.objects["atlas_Fibula.r"]["registration_status"] == "standing_bbox_translation_only"
assert "registration_offset_m" not in bpy.data.objects["atlas_Tibia.r"]
assert knee["status"] == "research_only_knee_registration_search"
objects = {
    "atlas_Hip bone.r": "pelvis", "atlas_Femur.r": "femur_r",
    "atlas_Tibia.r": "tibia_r", "atlas_Fibula.r": "tibia_r",
    "atlas_Patella.r": "patella_r", "atlas_Calcaneus.r": "calcn_r",
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
checks = 0
for number in (1, 26, 51, 76, 101):
    scene.frame_set(number)
    for name, body in objects.items():
        obj = bpy.data.objects[name]
        assert obj["opensim_body"] == body
        expected = body_matrix(frames[number - 1]["blenderBodyFrames"][body]) \
            @ standing_body[body].inverted() @ standing_world[name]
        observed = obj.matrix_world
        largest = max(abs(observed[row][col] - expected[row][col])
                      for row in range(4) for col in range(4))
        if largest > 1e-4:
            raise AssertionError(f"frame {number} {name} matrix mismatch {largest}")
        checks += 1
print(f"BLENDER_ANATOMY_MOTION_OK frames=5 bones=6 matrix_checks={checks}")
