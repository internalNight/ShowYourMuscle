"""Check saved attachment review markers and source labels."""

import json
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
inventory = json.loads((ROOT / "docs/data/opensim_squat_attachment_inventory.json").read_text(encoding="utf-8"))["muscles"]
surface_screen = json.loads((ROOT / "docs/data/attachment_surface_screen.json").read_text(encoding="utf-8"))
scene = bpy.context.scene
assert scene["status"] == "attachment_review_unvalidated"
assert scene.frame_start == scene.frame_end == 1
root = bpy.data.collections["06_OpenSim_Attachment_Review_UNVALIDATED"]
assert len(root.children) == 9
atlas_meshes = [obj for collection in root.children for obj in collection.objects
                if obj.name.startswith("atlas_")]
assert len(atlas_meshes) == 8
checks = 0
for muscle in inventory:
    collection = bpy.data.collections[muscle["name"] + "_review"]
    for point in muscle["points"]:
        obj = bpy.data.objects["attachment_" + muscle["name"] + "_" + point["name"]]
        assert obj.name in collection.objects
        assert obj["parent_frame"] == point["parentFrame"]
        if (obj.location - Vector(point["standingBlenderPositionM"])).length > 1e-6:
            raise AssertionError(f"{obj.name} location mismatch")
        checks += 1
assert checks == 30
surface_checks = 0
surface_trees = {}
for bone_name in {item["atlasBone"] for item in surface_screen["points"]}:
    bone = bpy.data.objects["atlas_" + bone_name]
    world_vertices = [bone.matrix_world @ vertex.co for vertex in bone.data.vertices]
    polygons = [tuple(poly.vertices) for poly in bone.data.polygons]
    surface_trees[bone_name] = BVHTree.FromPolygons(world_vertices, polygons, all_triangles=False)
for candidate in surface_screen["points"]:
    name = "surface_candidate_" + candidate["muscle"] + "_" + candidate["point"]
    obj = bpy.data.objects[name]
    guide = bpy.data.objects["surface_gap_" + candidate["muscle"] + "_" + candidate["point"]]
    assert obj["status"] == "nearest_surface_candidate_not_anatomical_attachment"
    assert obj["atlas_bone"] == candidate["atlasBone"]
    assert abs(obj["distance_m"] - candidate["nearestDistanceM"]) < 1e-6
    assert (obj.location - Vector(candidate["nearestSurfaceBlenderM"])).length < 1e-6
    assert guide["status"] == "source_to_nearest_surface_distance_only"
    source = Vector(candidate["sourceBlenderM"])
    assert abs((obj.location - source).length - candidate["nearestDistanceM"]) < 1e-6
    nearest, _normal, _face, distance = surface_trees[candidate["atlasBone"]].find_nearest(source)
    assert (nearest - obj.location).length < 1e-5
    assert abs(distance - candidate["nearestDistanceM"]) < 1e-5
    surface_checks += 1
assert surface_checks == scene["surface_candidate_count"] == 30
assert surface_screen["unmatchedPoints"] == 0
for name in ("atlas_Patella.r", "atlas_Calcaneus.r"):
    assert bpy.data.objects[name]["status"] == "shared_bbox_translation_only_not_landmark_registered"
print("BLENDER_ATTACHMENT_REVIEW_OK muscles=9 markers=30 surface_candidates=30 candidate_meshes=8")
