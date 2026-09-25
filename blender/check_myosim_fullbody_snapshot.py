"""Verify the saved Blender structural review against the MuJoCo export."""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / ".cache/myosim_fullbody_neutral_snapshot.json")
                  .read_text(encoding="utf-8"))
scene = bpy.context.scene
assert scene["status"] == "neutral_static_structure_only_no_personalization_or_force"
assert scene["force_status"] == "not_computed_or_visualized"
assert scene["muscle_actuators"] == 416
assert bpy.data.collections["05_Torso_Muscle_Runtime_Paths_210_Toggle_To_View"].hide_render
assert scene["active_wrapped_chord_paths"] == 98
checks = 0
max_rotation_error = 0.0

for geom in data["geoms"]:
    obj = next(obj for obj in bpy.data.objects
               if obj.get("source_geom_id") == geom["id"])
    assert obj["mujoco_body"] == geom["body"]
    if (obj.matrix_world.translation - Vector(geom["worldPositionM"])).length > 1e-6:
        raise AssertionError(f"Geometry {geom['id']} world position mismatch")
    for row in range(3):
        for column in range(3):
            error = abs(obj.matrix_world[row][column] -
                        geom["worldRotation"][row][column])
            max_rotation_error = max(max_rotation_error, error)
            if error > 1e-4:
                raise AssertionError(f"Geometry {geom['id']} rotation mismatch "
                                     f"at {row},{column}: {error}")
    checks += 1

for path in data["paths"]:
    obj = next(obj for obj in bpy.data.objects
               if obj.get("muscle_actuator") == path["name"])
    assert obj["visual_path_incomplete"] == path["visualPathIncomplete"]
    assert obj["declared_wrapping_object_count"] == path["declaredWrappingObjectCount"]
    assert obj["active_wrapping"] == path["activeWrapping"]
    assert abs(obj["tendon_length_m"] - path["modelTendonLengthM"]) < 1e-8
    points = obj.data.splines[0].points
    assert len(points) == len(path["displayPathWorldM"])
    for point, expected in zip(points, path["displayPathWorldM"]):
        if (Vector(point.co[:3]) - Vector(expected)).length > 1e-6:
            raise AssertionError(f"Muscle {path['name']} site mismatch")
        checks += 1

print(f"MYOSIM_FULLBODY_SNAPSHOT_OK geoms={len(data['geoms'])} "
      f"paths={len(data['paths'])} checks={checks} "
      f"maxRotationError={max_rotation_error:.8f}")
