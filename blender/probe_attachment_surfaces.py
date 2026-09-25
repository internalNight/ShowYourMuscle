"""Screen OpenSim path points against the parent Z-Anatomy bone surface.

Nearest surface points are geometric candidates for review, not confirmed
anatomical attachments. Patella and calcaneus share the provisional global
translation and have not been independently landmark-registered.
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
inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))["muscles"]
trees = {}
for frame, name in BONES.items():
    bone = bpy.data.objects[name]
    vertices = [bone.matrix_world @ item.co + shift for item in bone.data.vertices]
    polygons = [tuple(poly.vertices) for poly in bone.data.polygons]
    trees[frame] = BVHTree.FromPolygons(vertices, polygons, all_triangles=False)

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
        records.append({"muscle": muscle["name"], "point": point["name"],
                        "parentFrame": frame, "atlasBone": BONES[frame],
                        "sourceBlenderM": list(source),
                        "nearestSurfaceBlenderM": list(candidate),
                        "nearestDistanceM": distance,
                        "nearestFaceIndex": face_index,
                        "nearestFaceNormal": list(normal)})

distances = sorted(item["nearestDistanceM"] for item in records)
report = {"status": "surface_proximity_screen_not_anatomical_registration",
          "sourcePoints": sum(len(muscle["points"]) for muscle in inventory),
          "screenedPoints": len(records), "unmatchedPoints": len(unmatched),
          "distanceMedianM": median(distances), "distanceMaximumM": max(distances),
          "pointsOver20mm": sum(distance > 0.02 for distance in distances),
          "pointsOver50mm": sum(distance > 0.05 for distance in distances),
          "points": records, "unmatched": unmatched,
          "limitations": [
              "bone registration uses only a shared bounding-box translation",
              "nearest surface is not an identified origin, insertion, or tendon attachment",
              "OpenSim path points may be abstract model anchors away from bone cortex",
              "patella and calcaneus have no independent landmark registration",
              "single standing right-leg pose only",
          ]}
REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("ATTACHMENT_SURFACE_SCREEN", len(records), "screened", len(unmatched),
      "unmatched", "median_cm", round(median(distances) * 100, 2),
      "max_cm", round(max(distances) * 100, 2))
