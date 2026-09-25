"""Inspect saved three-muscle Blender shape keys and quantify mesh distortion."""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REPORT = ROOT / "docs/data/right_thigh_mesh_motion_audit.json"
MUSCLES = {
    "rect_fem_r": "atlas_rectus_femoris_r_research",
    "bifemsh_r": "atlas_biceps_femoris_short_r_research",
    "semimem_r": "atlas_semimembranosus_r_research",
}
FRAMES = (1, 26, 51, 76, 101)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, default=REPORT)
args = parser.parse_args(argv)
report_path = args.report if args.report.is_absolute() else ROOT / args.report


def body_matrix(data):
    result = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            result[row][col] = data["rotationRows"][row][col]
    result.translation = Vector(data["translationM"])
    return result


def path_at_fraction(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length > 0:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


lookup = json.loads(LOOKUP.read_text(encoding="utf-8"))
assert bpy.context.scene["status"] == "research_three_thigh_mesh_deformations_only"
assert bpy.context.scene.frame_start == 1 and bpy.context.scene.frame_end == 101
assert len(lookup["frames"]) == 101
standing_femur = body_matrix(lookup["frames"][0]["blenderBodyFrames"]["femur_r"])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert abs(bpy.context.scene["requested_thigh_circumference_cm"] - report["requestedThighCircumferenceCm"]) < 1e-8
assert abs(bpy.context.scene["applied_muscle_thickness_scale"] - report["appliedMuscleThicknessScale"]) < 1e-8
checked_vertices = 0
for row in report["muscles"]:
    radius_ratio = row["personalizedMaximumRadialDistanceM"] / row["referenceMaximumRadialDistanceM"]
    assert abs(radius_ratio - report["appliedMuscleThicknessScale"]) < 0.001
    muscle_name = row["opensimMuscle"]
    obj = bpy.data.objects[MUSCLES[muscle_name]]
    assert obj["status"] == "research_mesh_deformation_only_not_force"
    assert len(obj.data.vertices) == row["vertexCount"]
    assert len(obj.data.shape_keys.key_blocks) == 102
    base = [point.co.copy() for point in obj.data.shape_keys.key_blocks[0].data]
    fractions = [item.value for item in obj.data.attributes["opensim_path_fraction"].data]
    assert len(fractions) == len(base) and all(0 <= value <= 1 for value in fractions)
    rest_path = [Vector((0.09 - x, -z, y)) for x, y, z in
                 lookup["frames"][0]["muscles"][muscle_name]["viewerPathM"]]
    sample = sorted(set((0, len(base) // 4, len(base) // 2,
                         3 * len(base) // 4, len(base) - 1)))
    row["sampledFrameDistortion"] = {}
    for number in FRAMES:
        bpy.context.scene.frame_set(number)
        frame = lookup["frames"][number - 1]
        current_path = [Vector((0.09 - x, -z, y)) for x, y, z in
                        frame["muscles"][muscle_name]["viewerPathM"]]
        rigid_delta = body_matrix(frame["blenderBodyFrames"]["femur_r"]) @ standing_femur.inverted()
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            for index in sample:
                fraction = fractions[index]
                rigid = rigid_delta @ base[index]
                correction = (path_at_fraction(current_path, fraction)
                              - rigid_delta @ path_at_fraction(rest_path, fraction))
                expected = rigid + 0.5 * abs(2 * fraction - 1) ** 2 * correction
                observed = obj.matrix_world @ mesh.vertices[index].co
                if (observed - expected).length > 1e-5:
                    raise AssertionError(f"{muscle_name} frame {number} vertex {index} mismatch")
                checked_vertices += 1
            ratios = sorted((mesh.vertices[edge.vertices[0]].co - mesh.vertices[edge.vertices[1]].co).length /
                            (base[edge.vertices[0]] - base[edge.vertices[1]]).length
                            for edge in mesh.edges if (base[edge.vertices[0]] - base[edge.vertices[1]]).length > 1e-8)
            row["sampledFrameDistortion"][str(number)] = {
                "minimumEdgeRatio": round(ratios[0], 4),
                "p01EdgeRatio": round(ratios[int(.01 * (len(ratios) - 1))], 4),
                "p99EdgeRatio": round(ratios[int(.99 * (len(ratios) - 1))], 4),
                "maximumEdgeRatio": round(ratios[-1], 4),
                "edgesBelowHalf": sum(value < .5 for value in ratios),
                "edgesAboveOneAndHalf": sum(value > 1.5 for value in ratios),
            }
            if ratios[0] < .5 or ratios[-1] > 1.5:
                raise AssertionError(f"{muscle_name} frame {number} has excessive local edge distortion")
        finally:
            evaluated.to_mesh_clear()
report["sampledFrames"] = list(FRAMES)
report["checkedVertices"] = checked_vertices
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("BLENDER_THIGH_MESH_AUDIT_OK", "sampled vertices", checked_vertices)
for row in report["muscles"]:
    print(row["opensimMuscle"], row["sampledFrameDistortion"])
