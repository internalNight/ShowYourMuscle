"""Check saved rectus mesh against the path displacement rule at five frames."""

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
lookup = json.loads((ROOT / "public/data/squat_opensim_reference.json").read_text(encoding="utf-8"))
scene = bpy.context.scene
obj = bpy.data.objects["atlas_rectus_femoris_r_research"]
assert scene["status"] == "research_rectus_deformation_only"
assert scene.frame_start == 1 and scene.frame_end == 101
assert len(obj.data.vertices) == 4136
assert len(obj.data.shape_keys.key_blocks) == 102
base = [point.co.copy() for point in obj.data.shape_keys.key_blocks[0].data]
low = min(point.z for point in base)
high = max(point.z for point in base)


def path(number):
    points = lookup["frames"][number - 1]["muscles"]["rect_fem_r"]["viewerPathM"]
    return [Vector((0.09 - x, -z, y)) for x, y, z in points]


def at_fraction(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


def body_matrix(data):
    result = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            result[row][col] = data["rotationRows"][row][col]
    result.translation = Vector(data["translationM"])
    return result


rest_path = path(1)
standing_femur = body_matrix(lookup["frames"][0]["blenderBodyFrames"]["femur_r"])
sample_vertices = (0, 500, 1500, 3000, 4135)
checks = 0
distortion = {}
for number in (1, 26, 51, 76, 101):
    scene.frame_set(number)
    current_path = path(number)
    current_femur = body_matrix(lookup["frames"][number - 1]["blenderBodyFrames"]["femur_r"])
    rigid_delta = current_femur @ standing_femur.inverted()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        for index in sample_vertices:
            fraction = (high - base[index].z) / (high - low)
            rigid_point = rigid_delta @ base[index]
            correction = at_fraction(current_path, fraction) - rigid_delta @ at_fraction(rest_path, fraction)
            u = abs(2 * fraction - 1)
            expected = rigid_point + 0.5 * u * u * correction
            observed = obj.matrix_world @ mesh.vertices[index].co
            if (observed - expected).length > 1e-5:
                raise AssertionError(f"frame {number} vertex {index} displacement mismatch")
            checks += 1
        ratios = sorted((mesh.vertices[edge.vertices[0]].co - mesh.vertices[edge.vertices[1]].co).length /
                        (base[edge.vertices[0]] - base[edge.vertices[1]]).length
                        for edge in mesh.edges if (base[edge.vertices[0]] - base[edge.vertices[1]]).length > 1e-8)
        distortion[number] = {"minimumEdgeRatio": ratios[0],
                              "p01EdgeRatio": ratios[int(0.01 * (len(ratios) - 1))],
                              "p99EdgeRatio": ratios[int(0.99 * (len(ratios) - 1))],
                              "edgesBelowHalf": sum(ratio < 0.5 for ratio in ratios),
                              "maximumEdgeRatio": ratios[-1]}
        if ratios[0] < 0.5 or ratios[-1] > 1.5:
            raise AssertionError(f"frame {number} has excessive local edge distortion")
    finally:
        evaluated.to_mesh_clear()

print("BLENDER_RECTUS_MOTION_OK frames=5 vertices=5 checks=25")
print("RECTUS_EDGE_DISTORTION", json.dumps(distortion))
