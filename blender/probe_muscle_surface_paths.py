"""Screen standing OpenSim paths against actual atlas muscle surfaces.

The older centroid screen can overstate separation for wide muscles. This
checks sampled path points to the mesh surface, still without treating the
nearest point as a biological attachment.
"""

import json
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
OUTPUT = ROOT / "docs/data/right_leg_muscle_surface_path_screen.json"
MAPPING = {
    "rect_fem_r": "Rectus femoris muscle.r",
    "vas_int_r": "Vastus intermedius muscle.r",
    "bifemsh_r": "Short head of biceps femoris.r",
    "semimem_r": "Semimembranosus muscle.r",
    "med_gas_r": "Medial head of gastrocnemius.r",
    "soleus_r": "Soleus muscle.r",
    "tib_ant_r": "Tibialis anterior muscle.r",
    "glut_max2_r": "Gluteus maximus muscle.r",
}


def to_blender(point):
    x, y, z = point
    return Vector((0.09 - x, -z, y))


def at_fraction(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length > 0:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
shift = Vector(json.loads(REGISTRATION.read_text(encoding="utf-8"))["translationM"])
frame = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"][0]
records = []
for muscle, atlas_name in MAPPING.items():
    obj = bpy.data.objects[atlas_name]
    vertices = [obj.matrix_world @ vertex.co + shift for vertex in obj.data.vertices]
    faces = [tuple(poly.vertices) for poly in obj.data.polygons]
    surface = BVHTree.FromPolygons(vertices, faces)
    low, high = min(point.z for point in vertices), max(point.z for point in vertices)
    path = [to_blender(point) for point in frame["muscles"][muscle]["viewerPathM"]]
    samples = []
    for fraction in [index / 20 for index in range(21)]:
        point = at_fraction(path, fraction)
        nearest, _, _, distance = surface.find_nearest(point)
        samples.append({"fraction": fraction, "distanceM": distance,
                        "withinMeshHeight": low <= point.z <= high,
                        "pathBlenderM": list(point), "nearestMeshM": list(nearest)})
    distances = sorted(sample["distanceM"] for sample in samples)
    records.append({"opensimMuscle": muscle, "atlasMesh": atlas_name,
                    "vertexCount": len(vertices), "meshHeightM": high - low,
                    "pathLengthM": sum((b - a).length for a, b in zip(path, path[1:])),
                    "samplesWithinMeshHeight": sum(sample["withinMeshHeight"] for sample in samples),
                    "medianSurfaceDistanceM": distances[len(distances) // 2],
                    "p95SurfaceDistanceM": distances[19],
                    "maximumSurfaceDistanceM": distances[-1], "samples": samples})

OUTPUT.write_text(json.dumps({"status": "standing_surface_proximity_only",
    "sampleCountPerMuscle": 21, "muscles": records,
    "limits": ["nearest mesh surface is not a muscle fiber or anatomical attachment",
               "one standing pose; common bone-bounding-box translation only",
               "path may run inside muscle volume; unsigned surface distance then overstates discrepancy",
               "no dynamic mesh deformation or force validation"]}, indent=2) + "\n", encoding="utf-8")
for record in records:
    print(record["opensimMuscle"], "median/p95/max cm",
          *[round(record[key] * 100, 1) for key in ("medianSurfaceDistanceM",
          "p95SurfaceDistanceM", "maximumSurfaceDistanceM")],
          "height overlap", record["samplesWithinMeshHeight"], "/ 21")
