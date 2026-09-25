"""Screen atlas pectoralis surfaces against the synthetic TSM chest paths.

This uses the already established humerus proxy transform only to test whether
the current atlas and TSM coordinate systems are near enough to continue.
Unsigned nearest-surface distances are not attachment or fiber validation.
"""

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
PAIRS = {
    "Clavicular head of pectoralis major muscle.r": "PectoralisMajorClavicle_S",
    "Sternocostal head of pectoralis major muscle.r": "PectoralisMajorThorax_M",
    "(Abdominal part of pectoralis major muscle).r": "PectoralisMajorThorax_I",
}


def sample_polyline(points, fraction):
    segments = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(segments)
    for (a, b), segment_length in zip(zip(points, points[1:]), segments):
        if remaining <= segment_length and segment_length > 0:
            return a.lerp(b, remaining / segment_length)
        remaining -= segment_length
    return points[-1]


def to_blender(point):
    return Vector((point[0], -point[2], point[1]))


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
rows = []
for exercise in ("bench", "press"):
    frame = json.loads((ROOT / "public/data" / f"{exercise}_tsm_reference.json")
                       .read_text(encoding="utf-8"))["frames"][0]
    registration = json.loads((ROOT / "docs/data" / f"tsm_{exercise}_upper_bone_registration.json")
                              .read_text(encoding="utf-8"))
    humerus = next(bone for bone in registration["bones"] if bone["modelBody"] == "humerus")
    atlas_to_model = Matrix(humerus["atlasToModelBlenderRows"])
    for atlas_name, model_name in PAIRS.items():
        obj = bpy.data.objects.get(atlas_name)
        if obj is None:
            raise ValueError(atlas_name)
        vertices = [atlas_to_model @ obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
        polygons = [tuple(p.vertices) for p in obj.data.polygons]
        surface = BVHTree.FromPolygons(vertices, polygons)
        path = [to_blender(point) for point in frame["muscles"][model_name]["viewerPathM"]]
        samples = []
        for index in range(21):
            nearest, _, _, distance = surface.find_nearest(sample_polyline(path, index / 20))
            if nearest is None:
                raise RuntimeError("No nearby atlas surface")
            samples.append(round(distance, 6))
        sorted_distances = sorted(samples)
        row = {
            "exercise": exercise,
            "atlasMesh": atlas_name,
            "modelMuscle": model_name,
            "vertexCount": len(vertices),
            "pathPointCount": len(path),
            "medianUnsignedSurfaceDistanceM": sorted_distances[10],
            "p95UnsignedSurfaceDistanceM": sorted_distances[19],
            "maximumUnsignedSurfaceDistanceM": sorted_distances[-1],
            "distancesAtPathFractionsM": samples,
        }
        rows.append(row)
        print("PECTORALIS_SCREEN", exercise, model_name,
              *(round(row[key] * 100, 2) for key in (
                  "medianUnsignedSurfaceDistanceM", "p95UnsignedSurfaceDistanceM",
                  "maximumUnsignedSurfaceDistanceM")))

report = {
    "status": "static_geometric_candidate_screen_only",
    "registration": "right humerus endpoint proxy transform, shared with chest mesh",
    "pathSampleCount": 21,
    "rows": rows,
    "limitations": [
        "Only the first synthetic pose is compared; no chest mesh deformation is implied",
        "Humerus proxy alignment is not a thorax or clavicle registration",
        "Unsigned surface distance cannot establish muscle fiber, attachment, activation, or force",
    ],
}
out = ROOT / "docs/data/tsm_pectoralis_registration_screen.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
