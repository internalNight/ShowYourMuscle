"""Screen two-bone deltoid skinning on both synthetic TSM motions.

The result is a candidate surface-motion audit, not anatomical or force validation.
"""

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
OUTPUT = ROOT / "docs/data/tsm_deltoid_two_bone_deformation_screen.json"
MUSCLES = (
    ("DeltoideusClavicle_A", "Clavicular part of deltoid muscle.r", "clavicle"),
    ("DeltoideusScapula_M", "Acromial part of deltoid muscle.r", "scapula"),
    ("DeltoideusScapula_P", "Scapular spinal part of deltoid muscle.r", "scapula"),
)


def to_blender(point):
    x, y, z = point
    return Vector((x, -z, y))


def matrix(frame, body):
    entry = frame["blenderBodyFrames"][body]
    rows = entry["rotationRows"]
    x, y, z = entry["translationM"]
    return Matrix(((rows[0][0], rows[0][1], rows[0][2], x),
                   (rows[1][0], rows[1][1], rows[1][2], y),
                   (rows[2][0], rows[2][1], rows[2][2], z),
                   (0, 0, 0, 1)))


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
objects = {obj.name: obj for obj in bpy.data.objects if obj.type == "MESH"}
results = []
for exercise in ("bench", "press"):
    frames = json.loads((ROOT / f"public/data/{exercise}_tsm_reference.json")
                        .read_text(encoding="utf-8"))["frames"]
    assert len(frames) == 101
    registration = json.loads((ROOT / f"docs/data/tsm_{exercise}_upper_bone_registration.json")
                              .read_text(encoding="utf-8"))
    humerus = next(row for row in registration["bones"] if row["modelBody"] == "humerus")
    fit = Matrix(humerus["atlasToModelBlenderRows"])
    for muscle, atlas_name, origin in MUSCLES:
        source = objects[atlas_name]
        rest = [fit @ source.matrix_world @ vertex.co for vertex in source.data.vertices]
        edges = [tuple(edge.vertices) for edge in source.data.edges]
        faces = [tuple(poly.vertices) for poly in source.data.polygons]
        base_path = [to_blender(point) for point in frames[0]["muscles"][muscle]["viewerPathM"]]
        path_axis = base_path[-1] - base_path[0]
        if path_axis.length_squared < .001:
            raise ValueError(f"Path too short: {muscle}")
        fractions = [max(0, min(1, (vertex - base_path[0]).dot(path_axis) /
                                path_axis.length_squared)) for vertex in rest]
        origin_start = matrix(frames[0], origin).inverted()
        humerus_start = matrix(frames[0], "humerus").inverted()
        edge_lengths = [(a, b, (rest[a] - rest[b]).length) for a, b in edges]
        frame_rows = []
        for index, frame in enumerate(frames):
            origin_delta = matrix(frame, origin) @ origin_start
            humerus_delta = matrix(frame, "humerus") @ humerus_start
            moved = [(origin_delta @ vertex).lerp(humerus_delta @ vertex, fraction)
                     for vertex, fraction in zip(rest, fractions)]
            ratios = [(moved[a] - moved[b]).length / length
                      for a, b, length in edge_lengths if length > 1e-7]
            surface = BVHTree.FromPolygons(moved, faces)
            path = [to_blender(point) for point in frame["muscles"][muscle]["viewerPathM"]]
            distances = []
            for j in range(21):
                nearest, _, _, distance = surface.find_nearest(at_fraction(path, j / 20))
                if nearest is None:
                    raise ValueError(f"No surface for {muscle}")
                distances.append(distance)
            frame_rows.append({"frameIndex": index,
                               "minimumEdgeRatio": round(min(ratios), 5),
                               "maximumEdgeRatio": round(max(ratios), 5),
                               "medianPathSurfaceCm": round(sorted(distances)[10] * 100, 3),
                               "maximumPathSurfaceCm": round(max(distances) * 100, 3)})
        row = {"exercise": exercise, "muscle": muscle, "atlasMesh": atlas_name,
               "originBody": origin, "distalBody": "humerus",
               "vertices": len(rest), "edges": len(edges),
               "fractionsAtZero": sum(value == 0 for value in fractions),
               "fractionsAtOne": sum(value == 1 for value in fractions),
               "minimumEdgeRatio": min(item["minimumEdgeRatio"] for item in frame_rows),
               "maximumEdgeRatio": max(item["maximumEdgeRatio"] for item in frame_rows),
               "maximumPathSurfaceCm": max(item["maximumPathSurfaceCm"] for item in frame_rows),
               "frames": frame_rows}
        results.append(row)
        print(exercise, muscle, "edge ratio", row["minimumEdgeRatio"],
              row["maximumEdgeRatio"], "max path cm", row["maximumPathSurfaceCm"],
              "fractions clamp", row["fractionsAtZero"], row["fractionsAtOne"])

OUTPUT.write_text(json.dumps({
    "status": "exploratory_two_bone_deltoid_surface_screen_not_anatomy_or_force_validation",
    "method": "Humerus-proxy atlas fit at first pose; each vertex projects onto first model path origin-to-insertion axis. Origin-bone and humerus rigid positions are linearly blended by the clamped projected fraction; all 101 synthetic poses per exercise audited.",
    "limitations": ["Source mesh does not have validated individual attachment landmarks",
                    "The TSM paths and bench/press poses are model-generated, not measured workouts",
                    "Nearest path-surface distance does not validate skinning, tissue strain, activation or force"],
    "muscles": results,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUTPUT)
