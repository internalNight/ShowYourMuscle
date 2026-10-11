"""Screen OpenSim path points against the parent Z-Anatomy bone surface.

Nearest surface points are geometric candidates for review, not confirmed
anatomical attachments. The patella carries the same measured constant offset as the animated scenes
and the phone layer; the searched tibia offset is evaluated in the same pass but deliberately not
applied, because it moves these distances the wrong way. The calcaneus still shares the provisional
global translation and has not been independently landmark-registered.
"""

import json
from pathlib import Path
from statistics import median

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
INVENTORY = ROOT / "docs/data/opensim_squat_attachment_inventory.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
OPTIMISATION = ROOT / "docs/data/patella_registration_optimisation.json"
KNEE_OPTIMISATION = ROOT / "docs/data/knee_registration_optimisation.json"
REPORT = ROOT / "docs/data/attachment_surface_screen.json"
BONES = {
    "/bodyset/pelvis": "Hip bone.r",
    "/bodyset/femur_r": "Femur.r",
    "/bodyset/tibia_r": "Tibia.r",
    "/bodyset/patella_r": "Patella.r",
    "/bodyset/calcn_r": "Calcaneus.r",
}


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
shift = Vector(json.loads(REGISTRATION.read_text(encoding="utf-8"))["translationM"])
optimisation = json.loads(OPTIMISATION.read_text(encoding="utf-8"))
knee_optimisation = json.loads(KNEE_OPTIMISATION.read_text(encoding="utf-8"))
# The shipped registration: the patella offset only. The searched tibia offset was rejected, so it is
# evaluated side by side here instead of being applied, which is the evidence for that decision.
bone_offsets = {"/bodyset/patella_r": Vector(optimisation["optimised"]["offsetM"])}
evaluated_offsets = {"/bodyset/tibia_r": Vector(knee_optimisation["optimised"]["offsetM"])}
inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))["muscles"]
trees = {}
evaluated_trees = {}
for frame, name in BONES.items():
    bone = bpy.data.objects[name]
    offset = bone_offsets.get(frame, Vector((0.0, 0.0, 0.0)))
    vertices = [bone.matrix_world @ item.co + shift + offset for item in bone.data.vertices]
    polygons = [tuple(poly.vertices) for poly in bone.data.polygons]
    trees[frame] = BVHTree.FromPolygons(vertices, polygons, all_triangles=False)
    evaluated = evaluated_offsets.get(frame, Vector((0.0, 0.0, 0.0)))
    if evaluated.length > 0.0:
        evaluated_vertices = [vertex + evaluated for vertex in vertices]
        evaluated_trees[frame] = BVHTree.FromPolygons(evaluated_vertices, polygons,
                                                      all_triangles=False)

records = []
unmatched = []
for muscle in inventory:
    for point in muscle["points"]:
        frame = point["parentFrame"]
        source = Vector(point["standingBlenderPositionM"])
        if frame not in trees:
            unmatched.append({"muscle": muscle["name"], "point": point["name"],
                              "parentFrame": frame, "reason": "no registered atlas parent bone"})
            continue
        candidate, normal, face_index, distance = trees[frame].find_nearest(source)
        if candidate is None:
            raise RuntimeError(f"No bone surface for {muscle['name']} {point['name']}")
        record = {"muscle": muscle["name"], "point": point["name"],
                  "parentFrame": frame, "atlasBone": BONES[frame],
                  "sourceBlenderM": list(source),
                  "nearestSurfaceBlenderM": list(candidate),
                  "nearestDistanceM": distance,
                  "nearestFaceIndex": face_index,
                  "nearestFaceNormal": list(normal)}
        if frame in evaluated_trees:
            _, _, _, evaluated_distance = evaluated_trees[frame].find_nearest(source)
            record["rejectedOffsetDistanceM"] = evaluated_distance
        records.append(record)

distances = sorted(item["nearestDistanceM"] for item in records)
evaluated = sorted(item["rejectedOffsetDistanceM"] for item in records
                   if "rejectedOffsetDistanceM" in item)
report = {"status": "surface_proximity_screen_not_anatomical_registration",
          "sourcePoints": sum(len(muscle["points"]) for muscle in inventory),
          "screenedPoints": len(records), "unmatchedPoints": len(unmatched),
          "distanceMedianM": median(distances), "distanceMaximumM": max(distances),
          "pointsOver20mm": sum(distance > 0.02 for distance in distances),
          "pointsOver50mm": sum(distance > 0.05 for distance in distances),
          "rejectedTibiaOffsetM": list(evaluated_offsets["/bodyset/tibia_r"]),
          "rejectedOffsetScreenedPoints": len(evaluated),
          "rejectedOffsetDistanceMedianM": median(evaluated) if evaluated else None,
          "rejectedOffsetDistanceMaximumM": max(evaluated) if evaluated else None,
          "rejectedOffsetPointsOver20mm": sum(distance > 0.02 for distance in evaluated),
          "points": records, "unmatched": unmatched,
          "limitations": [
              "bone registration uses a shared bounding-box translation plus the measured patella "
              "offset; the searched tibia offset is evaluated here but deliberately not applied",
              "nearest surface is not an identified origin, insertion, or tendon attachment",
              "OpenSim path points may be abstract model anchors away from bone cortex",
              "patella and calcaneus have no independent landmark registration",
              "single standing right-leg pose only",
          ]}
REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("ATTACHMENT_SURFACE_SCREEN", len(records), "screened", len(unmatched),
      "unmatched", "median_cm", round(median(distances) * 100, 2),
      "max_cm", round(max(distances) * 100, 2),
      "rejected_offset_median_cm", round(median(evaluated) * 100, 2) if evaluated else None)
