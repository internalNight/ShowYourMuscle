"""Verify saved deltoid research meshes against TSM lookup and edge bounds."""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
MUSCLES = ("DeltoideusClavicle_A", "DeltoideusScapula_M", "DeltoideusScapula_P")
SAMPLES = (0, 25, 50, 75, 100)


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


args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
exercise = args[0] if args else "press"
if exercise not in ("bench", "press"):
    raise ValueError("Expected bench or press")
report_path = ROOT / f"docs/data/tsm_{exercise}_deltoid_atlas_probe.json"
report = json.loads(report_path.read_text(encoding="utf-8"))
lookup = json.loads((ROOT / f"public/data/{exercise}_tsm_reference.json")
                    .read_text(encoding="utf-8"))["frames"]
assert bpy.context.scene["deltoid_candidate_status"] == \
    "three candidate deltoid surfaces, not anatomical or force validation"
assert bpy.context.scene.frame_start == 1 and bpy.context.scene.frame_end == 101
standing_inverse = matrix(lookup[0], "humerus").inverted()
checked = []
for muscle in MUSCLES:
    obj = bpy.data.objects[f"atlas_{muscle}_{exercise}_candidate"]
    assert obj["status"] == "candidate surface motion, not tissue strain or force"
    row = next(item for item in report["muscles"] if item["muscle"] == muscle)
    keys = obj.data.shape_keys.key_blocks
    assert len(keys) == 102 and len(obj.data.vertices) == row["vertexCount"]
    rest = [point.co.copy() for point in keys[0].data]
    fractions = [value.value for value in obj.data.attributes["model_path_fraction_proxy"].data]
    assert len(fractions) == len(rest) and all(0 <= f <= 1 for f in fractions)
    base_path = [to_blender(point) for point in lookup[0]["muscles"][muscle]["viewerPathM"]]
    sample_vertices = sorted(set((0, len(rest) // 4, len(rest) // 2,
                                  3 * len(rest) // 4, len(rest) - 1)))
    row["sampledVerticesBlenderM"] = {}
    for frame_index in SAMPLES:
        bpy.context.scene.frame_set(frame_index + 1)
        frame = lookup[frame_index]
        path = [to_blender(point) for point in frame["muscles"][muscle]["viewerPathM"]]
        rigid = matrix(frame, "humerus") @ standing_inverse
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            coordinates = {}
            for vertex_index in sample_vertices:
                fraction = fractions[vertex_index]
                expected = rigid @ rest[vertex_index] + .25 * (1 - fraction) ** 2 * (
                    at_fraction(path, fraction) - rigid @ at_fraction(base_path, fraction))
                observed = obj.matrix_world @ mesh.vertices[vertex_index].co
                if (expected - observed).length > 1e-5:
                    raise AssertionError(f"{exercise} {muscle} frame {frame_index} vertex {vertex_index}")
                coordinates[str(vertex_index)] = [round(value, 8) for value in observed]
            row["sampledVerticesBlenderM"][str(frame_index)] = coordinates
            ratios = [(mesh.vertices[a].co - mesh.vertices[b].co).length /
                      (rest[a] - rest[b]).length for a, b in
                      (edge.vertices for edge in mesh.edges) if (rest[a] - rest[b]).length > 1e-7]
            if min(ratios) < .5 or max(ratios) > 1.5:
                raise AssertionError(f"{exercise} {muscle} frame {frame_index} edge distortion")
            checked.append({"muscle": muscle, "frameIndex": frame_index,
                            "checkedVertices": len(sample_vertices),
                            "minimumEdgeRatio": round(min(ratios), 5),
                            "maximumEdgeRatio": round(max(ratios), 5)})
        finally:
            evaluated.to_mesh_clear()
report["reopenedSceneAudit"] = checked
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("BLENDER_DELTOID_ATLAS_AUDIT_OK", exercise, len(checked), "muscle-frames")
