"""Add three synthetic pectoralis path volumes to a TSM action scene.

These tubes visualize model muscle-tendon paths. They are not atlas anatomy,
fiber strain, EMG, or a muscle force estimate.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--exercise", choices=("bench", "press"), required=True)
parser.add_argument("--output", type=Path)
parser.add_argument("--preview", type=Path)
parser.add_argument("--report", type=Path)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
exercise = args.exercise
base_scene = ROOT / "assets/blender" / f"opensim_tsm_{exercise}_biceps_long_probe.blend"
lookup = ROOT / "public/data" / f"{exercise}_tsm_reference.json"
output = args.output or Path("assets/blender") / f"opensim_tsm_{exercise}_pectoralis_path_proxies.blend"
preview = args.preview or Path("assets/blender") / f"opensim_tsm_{exercise}_pectoralis_path_proxies.png"
report = args.report or Path("docs/data") / f"tsm_{exercise}_pectoralis_path_proxies.json"
output = output if output.is_absolute() else ROOT / output
preview = preview if preview.is_absolute() else ROOT / preview
report = report if report.is_absolute() else ROOT / report

SPECS = (
    ("PectoralisMajorClavicle_S", 0.018),
    ("PectoralisMajorThorax_M", 0.027),
    ("PectoralisMajorThorax_I", 0.022),
)
RINGS = 21
SIDES = 8


def to_blender(point):
    return Vector((point.x, -point.z, point.y))


def point_on_path(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = max(0, min(1, fraction)) * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length > 0:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


def vertices_for_path(path, radius):
    points = [Vector(p) for p in path]
    vertices = []
    tangent = (points[-1] - points[0]).normalized()
    reference = Vector((0, 0, 1)) if abs(tangent.z) < 0.9 else Vector((0, 1, 0))
    normal = tangent.cross(reference).normalized()
    binormal = tangent.cross(normal).normalized()
    for ring in range(RINGS):
        fraction = ring / (RINGS - 1)
        center = point_on_path(points, fraction)
        ring_radius = radius * (0.15 + 0.85 * math.sin(math.pi * fraction) ** 0.8)
        for side in range(SIDES):
            angle = side * 2 * math.pi / SIDES
            vertex = center + ring_radius * (math.cos(angle) * normal + math.sin(angle) * binormal)
            vertices.append(to_blender(vertex))
    return vertices


bpy.ops.wm.open_mainfile(filepath=str(base_scene))
scene = bpy.context.scene
frames = json.loads(lookup.read_text(encoding="utf-8"))["frames"]
if len(frames) != 101:
    raise ValueError("Expected 101 TSM frames")
collection = bpy.data.collections.new("08_Pectoralis_Path_Volume_Proxies")
scene.collection.children.link(collection)
faces = []
for ring in range(RINGS - 1):
    for side in range(SIDES):
        nxt = (side + 1) % SIDES
        a = ring * SIDES + side
        b = ring * SIDES + nxt
        c = (ring + 1) * SIDES + side
        d = (ring + 1) * SIDES + nxt
        faces.append((a, c, b))
        faces.append((b, c, d))

muscles = []
for model_name, radius in SPECS:
    poses = [vertices_for_path(frame["muscles"][model_name]["viewerPathM"], radius)
             for frame in frames]
    mesh = bpy.data.meshes.new(f"{model_name}_proxy")
    mesh.from_pydata(poses[0], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"{model_name}_{exercise}_path_volume_proxy", mesh)
    collection.objects.link(obj)
    material = bpy.data.materials.new(f"{model_name} · 路径体非发力")
    material.diffuse_color = (0.70, 0.42, 0.56, 1)
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = material.diffuse_color
    shader.inputs["Roughness"].default_value = 0.67
    mesh.materials.append(material)
    obj.shape_key_add(name="Model path at initial pose", from_mix=False)
    for index, vertices in enumerate(poses):
        key = obj.shape_key_add(name=f"Path frame {index + 1:03d}", from_mix=False)
        for vertex_index, point in enumerate(vertices):
            key.data[vertex_index].co = point
        key.value = 0
        if index > 0:
            key.keyframe_insert(data_path="value", frame=index)
        key.value = 1
        key.keyframe_insert(data_path="value", frame=index + 1)
        key.value = 0
        if index < len(poses) - 1:
            key.keyframe_insert(data_path="value", frame=index + 2)
    obj["source"] = "synthetic TSM muscle-tendon path"
    obj["status"] = "teaching path volume; no atlas or force registration"
    obj["base_radius_m"] = radius
    obj["path_sampling"] = "21 arc-length rings, 8 sides, tapered radius"
    reference_edges = [(edge.vertices[0], edge.vertices[1]) for edge in mesh.edges]
    edge_ratios = []
    for index in (0, 25, 50, 75, 100):
        current = poses[index]
        ratios = [(current[a] - current[b]).length / (poses[0][a] - poses[0][b]).length
                  for a, b in reference_edges if (poses[0][a] - poses[0][b]).length > 1e-7]
        edge_ratios.append({"frameIndex": index, "minimum": round(min(ratios), 5),
                            "maximum": round(max(ratios), 5)})
    muscles.append({"modelMuscle": model_name, "radiusM": radius,
                    "vertexCount": len(poses[0]), "faceCount": len(faces),
                    "shapeKeyCount": len(poses) + 1,
                    "edgeLengthRatios": edge_ratios,
                    "sampledVertices": [
                        {"frameIndex": index, "verticesBlenderM": {
                            str(vertex_index): list(poses[index][vertex_index])
                            for vertex_index in (0, 4, 80, 84, 160, 167)}}
                        for index in (0, 50, 100)]})

scene["pectoralis_proxy_status"] = "Path-shaped teaching geometry only; no muscle force"
scene.frame_set(51)
bpy.ops.wm.save_as_mainfile(filepath=str(output))
scene.render.filepath = str(preview)
bpy.ops.render.render(write_still=True)
report.write_text(json.dumps({"status": "synthetic_path_volume_not_anatomy_or_force",
                              "exercise": exercise, "scene": str(output.relative_to(ROOT)),
                              "preview": str(preview.relative_to(ROOT)), "muscles": muscles,
                              "limitations": ["The tube radius and taper are visual assumptions",
                                              "The source trajectories are synthetic, not measured exercise",
                                              "Length change and mesh movement do not estimate muscle force"]},
                             ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("SAVED_PECTORALIS_PROXIES", exercise, len(muscles))
