"""Test a three-landmark thorax/clavicle/shoulder fit for atlas chest meshes.

The landmarks are geometric proxies, so this is only a candidate screen.
"""

import json
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
PAIRS = {
    "Clavicular head of pectoralis major muscle.r": "PectoralisMajorClavicle_S",
    "Sternocostal head of pectoralis major muscle.r": "PectoralisMajorThorax_M",
    "(Abdominal part of pectoralis major muscle).r": "PectoralisMajorThorax_I",
}


def centroid(obj):
    return sum((obj.matrix_world @ vertex.co for vertex in obj.data.vertices), Vector()) / len(obj.data.vertices)


def upper_humerus_proxy(obj):
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    upper = max(point.z for point in points)
    lower = min(point.z for point in points)
    band = 0.05 * (upper - lower)
    subset = [point for point in points if point.z >= upper - band]
    return sum(subset, Vector()) / len(subset)


def medial_clavicle_proxy(obj):
    # Atlas right side lies at negative X. The medial 5% of clavicle vertices
    # is a geometrical proxy for its sternoclavicular end, not an identified
    # anatomical joint center.
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    medial = max(point.x for point in points)
    lateral = min(point.x for point in points)
    band = .05 * (medial - lateral)
    subset = [point for point in points if point.x >= medial - band]
    return sum(subset, Vector()) / len(subset)


def medial_pectoral_origin_proxy(obj):
    # Geometric medial edge of the atlas sternocostal pectoralis mesh. Its
    # correspondence to the TSM path origin is a hypothesis being screened.
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    medial = max(point.x for point in points)
    lateral = min(point.x for point in points)
    band = .02 * (medial - lateral)
    subset = [point for point in points if point.x >= medial - band]
    return sum(subset, Vector()) / len(subset)


def to_blender(viewer):
    x, y, z = viewer
    return Vector((x, -z, y))


def path_point(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length > 0:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1]


def similarity(source, target):
    source = np.array([list(point) for point in source])
    target = np.array([list(point) for point in target])
    center_source = source.mean(axis=0)
    center_target = target.mean(axis=0)
    x = source - center_source
    y = target - center_target
    u, singular, vt = np.linalg.svd(x.T @ y)
    correction = np.eye(3)
    correction[-1, -1] = np.linalg.det(u @ vt)
    rotation = u @ correction @ vt
    scale = np.trace(np.diag(singular) @ correction) / np.sum(x * x)
    translation = center_target - scale * center_source @ rotation
    matrix = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            matrix[row][col] = scale * rotation[col, row]
    matrix.translation = Vector(translation)
    predicted = source @ (scale * rotation) + translation
    errors = np.linalg.norm(predicted - target, axis=1)
    triangle_area = np.linalg.norm(np.cross(source[1] - source[0],
                                        source[2] - source[0])) / 2
    landmark_singular = np.linalg.svd(x, compute_uv=False)
    return matrix, scale, errors, triangle_area, landmark_singular


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
source_candidates = {
    "clavicle_centroid": {
        "shoulder": upper_humerus_proxy(bpy.data.objects["Humerus.r"]),
        "clavicle": centroid(bpy.data.objects["Clavicle.r"]),
        "thorax": centroid(bpy.data.objects["Manubrium of sternum"]),
    },
    "medial_clavicle_end_proxy": {
        "shoulder": upper_humerus_proxy(bpy.data.objects["Humerus.r"]),
        "clavicle": medial_clavicle_proxy(bpy.data.objects["Clavicle.r"]),
        "thorax": centroid(bpy.data.objects["Manubrium of sternum"]),
    },
    "medial_clavicle_plus_pectoral_origin_proxy": {
        "shoulder": upper_humerus_proxy(bpy.data.objects["Humerus.r"]),
        "clavicle": medial_clavicle_proxy(bpy.data.objects["Clavicle.r"]),
        "thorax": centroid(bpy.data.objects["Manubrium of sternum"]),
        "middlePectoralisOrigin": medial_pectoral_origin_proxy(
            bpy.data.objects["Sternocostal head of pectoralis major muscle.r"]),
    },
}
records = []
for method, source in source_candidates.items():
    for exercise in ("bench", "press"):
        frame = json.loads((ROOT / "public/data" / f"{exercise}_tsm_reference.json")
                           .read_text(encoding="utf-8"))["frames"][0]
        target = {name: (to_blender(frame["muscles"]["PectoralisMajorThorax_M"]
                                    ["viewerPathM"][0]) if name == "middlePectoralisOrigin"
                         else to_blender(frame["viewerJointsM"][name]))
                  for name in source}
        fit, scale, errors, triangle_area, landmark_singular = similarity(
            list(source.values()), list(target.values()))
        muscles = []
        for atlas_name, model_name in PAIRS.items():
            obj = bpy.data.objects[atlas_name]
            vertices = [fit @ obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
            surface = BVHTree.FromPolygons(vertices, [tuple(poly.vertices) for poly in obj.data.polygons])
            path = [to_blender(point) for point in frame["muscles"][model_name]["viewerPathM"]]
            distances = []
            for index in range(21):
                nearest, _, _, distance = surface.find_nearest(path_point(path, index / 20))
                if nearest is None:
                    raise RuntimeError("No nearest surface")
                distances.append(distance)
            ordered = sorted(distances)
            muscles.append({"atlasMesh": atlas_name, "modelMuscle": model_name,
                            "medianUnsignedDistanceM": round(ordered[10], 6),
                            "p95UnsignedDistanceM": round(ordered[19], 6),
                            "maximumUnsignedDistanceM": round(ordered[-1], 6),
                            "distancesByPathFractionM": [round(value, 6) for value in distances],
                            "pathEndpointsBlenderM": [list(path[0]), list(path[-1])],
                            "meshBoundsBlenderM": {
                                "minimum": [min(vertex[axis] for vertex in vertices)
                                            for axis in range(3)],
                                "maximum": [max(vertex[axis] for vertex in vertices)
                                            for axis in range(3)],
                            }})
            print("PECTORALIS_LANDMARK_FIT", method, exercise, model_name,
                  round(ordered[10] * 100, 2), round(ordered[-1] * 100, 2))
        records.append({"method": method, "exercise": exercise,
                        "uniformScale": round(float(scale), 6),
                        "sourceLandmarkTriangleAreaCm2": round(float(triangle_area) * 1e4, 3),
                        "sourceLandmarkSingularValuesM": [round(float(value), 6)
                                                          for value in landmark_singular],
                        "landmarkResidualsM": {name: round(float(error), 6)
                                               for name, error in zip(source, errors)},
                        "atlasToModelBlenderRows": [list(row) for row in fit],
                        "muscles": muscles})

out = ROOT / "docs/data/tsm_pectoralis_landmark_fit_screen.json"
out.write_text(json.dumps({"status": "candidate_proxy_landmark_fit_only",
                           "sourceLandmarksByMethod": {name: list(points)
                                                       for name, points in source_candidates.items()},
                           "targetLandmarksByMethod": {name: list(points)
                                                       for name, points in source_candidates.items()},
                           "records": records,
                           "limits": ["Source centroids and medial mesh slices are geometric proxies, not anatomical markers",
                                      "Target TSM joint centers are not the same landmarks",
                                      "The four-point candidate uses the middle-pectoralis path origin as a fit target; its middle-bundle distance is in-sample",
                                      "Only the starting synthetic pose is compared",
                                      "Small proxy residuals do not validate the orientation or individual chest muscle surfaces",
                                      "Unsigned surface distance is not fiber or force validation"]},
                          ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
