"""Screen right patella/heel proximity over the saved squat animation.

This is a geometric sanity check, not joint congruence or anatomy validation.
"""

import json
from pathlib import Path
from statistics import median

import bpy
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/data/animated_patella_calcaneus_gap_screen.json"
PAIRS = (("atlas_Patella.r", "atlas_Femur.r"),
         ("atlas_Calcaneus.r", "atlas_Tibia.r"))
FRAMES = (1, 26, 51, 76, 101)


def vertex_to_surface_distances(small, large):
    vertices = [large.matrix_world @ vertex.co for vertex in large.data.vertices]
    polygons = [tuple(poly.vertices) for poly in large.data.polygons]
    tree = BVHTree.FromPolygons(vertices, polygons, all_triangles=False)
    distances = []
    for vertex in small.data.vertices:
        point = small.matrix_world @ vertex.co
        _nearest, _normal, _face, distance = tree.find_nearest(point)
        distances.append(distance)
    return distances


scene = bpy.context.scene
assert scene["status"] == "research_anatomy_bone_motion_only"
records = []
for frame in FRAMES:
    scene.frame_set(frame)
    for small_name, large_name in PAIRS:
        small = bpy.data.objects[small_name]
        large = bpy.data.objects[large_name]
        distances = vertex_to_surface_distances(small, large)
        records.append({"frame": frame, "smallBone": small_name, "largeBone": large_name,
                        "smallVertexCount": len(distances),
                        "minimumDistanceM": min(distances),
                        "medianVertexDistanceM": median(distances),
                        "maximumVertexDistanceM": max(distances)})

report = {"status": "animated_bone_surface_proximity_screen_only",
          "frames": list(FRAMES), "records": records,
          "limitations": [
              "both atlas bones use the same standing translation fit only to femur/tibia bounding boxes",
              "minimum distance between sampled bone vertices and another bone surface is not a contact or collision test",
              "patella and calcaneus are not landmark-fitted to OpenSim bones",
              "single right-leg research motion and no tissue mechanics or force",
          ]}
REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
for small_name, large_name in PAIRS:
    values = [item["minimumDistanceM"] * 100 for item in records
              if item["smallBone"] == small_name]
    print("ANIMATED_BONE_GAP", small_name, large_name,
          "minimum_surface_cm_range", round(min(values), 2), round(max(values), 2))
