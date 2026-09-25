"""Verify reopened gluteus mesh positions and local edge distortion."""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REPORT = ROOT / "docs/data/right_gluteus_mesh_motion_audit.json"
OBJECT_NAME = "atlas_gluteus_maximus_r_research"
FRAMES = (1, 26, 51, 76, 101)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, default=REPORT)
args = parser.parse_args(argv)
report_path = args.report if args.report.is_absolute() else ROOT / args.report


def body_matrix(data):
    matrix = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            matrix[row][col] = data["rotationRows"][row][col]
    matrix.translation = Vector(data["translationM"])
    return matrix


def at_fraction(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length > 0:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


def to_blender(point):
    x, y, z = point
    return Vector((0.09 - x, -z, y))


lookup = json.loads(LOOKUP.read_text(encoding="utf-8"))
report = json.loads(report_path.read_text(encoding="utf-8"))
assert bpy.context.scene["status"] == "research_five_muscle_deformations_only"
assert bpy.context.scene.frame_start == 1 and bpy.context.scene.frame_end == 101
obj = bpy.data.objects[OBJECT_NAME]
assert obj["status"] == "research_mesh_deformation_only_not_force"
assert len(obj.data.vertices) == report["vertexCount"]
assert len(obj.data.shape_keys.key_blocks) == 102
base = [point.co.copy() for point in obj.data.shape_keys.key_blocks[0].data]
fractions = [item.value for item in obj.data.attributes["opensim_path_fraction"].data]
assert len(fractions) == len(base) and all(0 <= value <= 1 for value in fractions)
standing_pelvis = body_matrix(lookup["frames"][0]["blenderBodyFrames"]["pelvis"])
standing_path = [to_blender(point) for point in lookup["frames"][0]["muscles"]["glut_max2_r"]["viewerPathM"]]
sample = sorted(set((0, len(base) // 4, len(base) // 2, 3 * len(base) // 4, len(base) - 1)))
report["sampledFrameDistortion"] = {}
for number in FRAMES:
    bpy.context.scene.frame_set(number)
    frame = lookup["frames"][number - 1]
    path = [to_blender(point) for point in frame["muscles"]["glut_max2_r"]["viewerPathM"]]
    rigid_delta = body_matrix(frame["blenderBodyFrames"]["pelvis"]) @ standing_pelvis.inverted()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        for index in sample:
            fraction = fractions[index]
            correction = at_fraction(path, fraction) - rigid_delta @ at_fraction(standing_path, fraction)
            expected = rigid_delta @ base[index] + 0.1 * abs(2 * fraction - 1) ** 2 * correction
            observed = obj.matrix_world @ mesh.vertices[index].co
            if (observed - expected).length > 1e-5:
                raise AssertionError(f"frame {number} vertex {index} differs")
        ratios = sorted((mesh.vertices[edge.vertices[0]].co - mesh.vertices[edge.vertices[1]].co).length /
                        (base[edge.vertices[0]] - base[edge.vertices[1]]).length
                        for edge in mesh.edges if (base[edge.vertices[0]] - base[edge.vertices[1]]).length > 1e-8)
        report["sampledFrameDistortion"][str(number)] = {
            "minimumEdgeRatio": round(ratios[0], 4),
            "maximumEdgeRatio": round(ratios[-1], 4),
            "edgesBelowHalf": sum(value < 0.5 for value in ratios),
            "edgesAboveOneAndHalf": sum(value > 1.5 for value in ratios)}
        if ratios[0] < .5 or ratios[-1] > 1.5:
            raise AssertionError(f"frame {number} has excessive local edge distortion: {ratios[0]:.3f}–{ratios[-1]:.3f}")
    finally:
        evaluated.to_mesh_clear()
report["sampledFrames"] = list(FRAMES)
report["checkedVertices"] = len(FRAMES) * len(sample)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("BLENDER_GLUTEUS_MESH_AUDIT_OK", report["sampledFrameDistortion"])
