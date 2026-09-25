"""Screen 101-frame chest path distances under rigid thorax/clavicle motion.

The four-proxy start-pose fit contains one middle-pectoralis path origin. This
is a geometry research audit, not held-out anatomy or muscle-force validation.
"""

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
FIT_REPORT = ROOT / "docs/data/tsm_pectoralis_landmark_fit_screen.json"
OUTPUT = ROOT / "docs/data/tsm_pectoralis_dynamic_registration_audit.json"
PAIRS = (
    ("Clavicular head of pectoralis major muscle.r", "PectoralisMajorClavicle_S", "clavicle"),
    ("Sternocostal head of pectoralis major muscle.r", "PectoralisMajorThorax_M", "thorax"),
    ("(Abdominal part of pectoralis major muscle).r", "PectoralisMajorThorax_I", "thorax"),
)


def to_blender(point):
    x, y, z = point
    return Vector((x, -z, y))


def body_matrix(frame, name):
    data = frame["blenderBodyFrames"][name]
    matrix = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            matrix[row][col] = data["rotationRows"][row][col]
    matrix.translation = Vector(data["translationM"])
    return matrix


def path_point(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length > 0:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


def inspect(exercise, records):
    frames = json.loads((ROOT / "public/data" / f"{exercise}_tsm_reference.json")
                        .read_text(encoding="utf-8"))["frames"]
    record = next(item for item in records if item["exercise"] == exercise and
                  item["method"] == "medial_clavicle_plus_pectoral_origin_proxy")
    fit = Matrix(record["atlasToModelBlenderRows"])
    results = []
    for atlas_name, model_name, parent in PAIRS:
        obj = bpy.data.objects[atlas_name]
        base_vertices = [fit @ obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
        polygons = [tuple(poly.vertices) for poly in obj.data.polygons]
        base_body_inverse = body_matrix(frames[0], parent).inverted()
        base_path = [to_blender(point) for point in frames[0]["muscles"]
                     [model_name]["viewerPathM"]]
        axis = base_path[-1] - base_path[0]
        axis_length_sq = axis.length_squared
        if axis_length_sq < .001:
            raise ValueError(f"Degenerate baseline path: {model_name}")
        fractions = [min(1, max(0, (vertex - base_path[0]).dot(axis) /
                                axis_length_sq)) for vertex in base_vertices]
        edges = sorted({tuple(sorted((poly[index], poly[(index + 1) % len(poly)])))
                        for poly in polygons for index in range(len(poly))})
        base_edge_lengths = [(a, b, (base_vertices[a] - base_vertices[b]).length)
                             for a, b in edges]
        base_edge_lengths = [(a, b, length) for a, b, length in base_edge_lengths
                             if length > 1e-7]
        per_frame = {"rigid": [], "endpoint_blend": [], "endpoint_blend_80": []}
        minimum_edge_ratio = 1.0
        maximum_edge_ratio = 1.0
        minimum_edge_ratio_80 = 1.0
        maximum_edge_ratio_80 = 1.0
        for index, frame in enumerate(frames):
            delta = body_matrix(frame, parent) @ base_body_inverse
            rigid_vertices = [delta @ vertex for vertex in base_vertices]
            path = [to_blender(point) for point in frame["muscles"][model_name]
                    ["viewerPathM"]]
            origin_delta = path[0] - delta @ base_path[0]
            insertion_delta = path[-1] - delta @ base_path[-1]
            blended_vertices = [vertex + origin_delta * (1 - fraction) +
                                insertion_delta * fraction
                                for vertex, fraction in zip(rigid_vertices, fractions)]
            blended_80_vertices = [vertex + .8 * (origin_delta * (1 - fraction) +
                                                  insertion_delta * fraction)
                                   for vertex, fraction in zip(rigid_vertices, fractions)]
            for a, b, length in base_edge_lengths:
                ratio = (blended_vertices[a] - blended_vertices[b]).length / length
                minimum_edge_ratio = min(minimum_edge_ratio, ratio)
                maximum_edge_ratio = max(maximum_edge_ratio, ratio)
                ratio_80 = (blended_80_vertices[a] - blended_80_vertices[b]).length / length
                minimum_edge_ratio_80 = min(minimum_edge_ratio_80, ratio_80)
                maximum_edge_ratio_80 = max(maximum_edge_ratio_80, ratio_80)
            for method, vertices in (("rigid", rigid_vertices),
                                     ("endpoint_blend", blended_vertices),
                                     ("endpoint_blend_80", blended_80_vertices)):
                surface = BVHTree.FromPolygons(vertices, polygons)
                distances = []
                for sample in range(21):
                    nearest, _, _, distance = surface.find_nearest(
                        path_point(path, sample / 20))
                    if nearest is None:
                        raise ValueError(f"No surface: {exercise} {model_name} {index}")
                    distances.append(distance)
                per_frame[method].append({
                    "frameIndex": index,
                    "medianCm": round(sorted(distances)[10] * 100, 2),
                    "maximumCm": round(max(distances) * 100, 2),
                    "originCm": round(distances[0] * 100, 2),
                    "insertionCm": round(distances[-1] * 100, 2),
                })
        scenarios = {}
        for method, rows in per_frame.items():
            scenarios[method] = {
                "initial": rows[0],
                "worst": max(rows, key=lambda item: item["maximumCm"]),
                "sampled": [rows[index] for index in (0, 25, 50, 75, 100)],
                "framesWithMaximumOver5cm": sum(item["maximumCm"] > 5
                                                     for item in rows),
                "framesWithMaximumOver10cm": sum(item["maximumCm"] > 10
                                                      for item in rows),
            }
        row = {"atlasMesh": atlas_name, "modelMuscle": model_name,
               "rigidParent": parent, "frameCount": len(frames),
               "endpointBlendMinimumEdgeLengthRatio": round(minimum_edge_ratio, 3),
               "endpointBlendMaximumEdgeLengthRatio": round(maximum_edge_ratio, 3),
               "endpointBlend80MinimumEdgeLengthRatio": round(minimum_edge_ratio_80, 3),
               "endpointBlend80MaximumEdgeLengthRatio": round(maximum_edge_ratio_80, 3),
               "scenarios": scenarios}
        results.append(row)
        print("PECTORALIS_DYNAMIC", exercise, model_name,
              "rigid", scenarios["rigid"]["worst"]["maximumCm"],
              "blend", scenarios["endpoint_blend"]["worst"]["maximumCm"],
              "edge", row["endpointBlendMinimumEdgeLengthRatio"],
              row["endpointBlendMaximumEdgeLengthRatio"],
              "edge80", row["endpointBlend80MinimumEdgeLengthRatio"],
              row["endpointBlend80MaximumEdgeLengthRatio"])
    return {"exercise": exercise, "muscles": results}


def main():
    records = json.loads(FIT_REPORT.read_text(encoding="utf-8"))["records"]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(ATLAS))
    cases = [inspect(exercise, records) for exercise in ("bench", "press")]
    OUTPUT.write_text(json.dumps({
        "status": "chest_mesh_rigid_and_endpoint_blend_geometry_audit_not_anatomical_or_force_validation",
        "fit": "four proxy landmarks at frame 0, including the middle pectoralis path origin",
        "method": "Apply the corresponding TSM clavicle or thorax rigid transform relative to frame 0 to each fitted atlas mesh. Endpoint-blend candidates add 100% or 80% of a linearly interpolated offset from rigidly transported baseline path endpoints to current TSM path endpoints, with vertex fraction projected onto the original endpoint axis and clamped to [0,1]. Compare 21 arc-length path samples with the nearest surface and all source mesh edge-length ratios at all 101 frames.",
        "cases": cases,
        "limits": [
            "The endpoint blend is a visual deformation heuristic, not measured muscle fiber strain",
            "The atlas points and TSM coordinates are only geometric proxies",
            "Path-to-surface proximity does not establish fiber direction, attachment, activation or force",
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
