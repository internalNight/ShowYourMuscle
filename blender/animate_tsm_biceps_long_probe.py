"""Create a Blender-only right biceps-long-head deformation experiment.

This is a research mesh study, not a fiber strain or force model. The atlas
mesh has only a coarse humerus proxy registration against synthetic TSM poses.
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--exercise", choices=("bench", "press"), required=True)
parser.add_argument("--height-cm", type=float, default=175)
parser.add_argument("--arm-cm", type=float, default=32)
parser.add_argument("--output", type=Path)
parser.add_argument("--preview", type=Path)
parser.add_argument("--report", type=Path)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
exercise = args.exercise
scene_path = ROOT / "assets/blender" / f"opensim_tsm_{exercise}_upper_bones.blend"
lookup_path = ROOT / "public/data" / f"{exercise}_tsm_reference.json"
registration_path = ROOT / "docs/data" / f"tsm_{exercise}_upper_bone_registration.json"
output_path = args.output or Path("assets/blender") / f"opensim_tsm_{exercise}_biceps_long_probe.blend"
preview_path = args.preview or Path("assets/blender") / f"opensim_tsm_{exercise}_biceps_long_probe.png"
report_path = args.report or Path("docs/data") / f"tsm_{exercise}_biceps_long_probe.json"
output_path = output_path if output_path.is_absolute() else ROOT / output_path
preview_path = preview_path if preview_path.is_absolute() else ROOT / preview_path
report_path = report_path if report_path.is_absolute() else ROOT / report_path
atlas_path = ROOT / "public/models/z_anatomy_reference.glb"
source_name = "Long head of biceps brachii.r"
muscle_name = "BIC_long"


def to_blender(viewer_point):
    x, y, z = viewer_point
    return Vector((x, -z, y))


def body_matrix(data):
    rows = data["rotationRows"]
    p = data["translationM"]
    return Matrix(((rows[0][0], rows[0][1], rows[0][2], p[0]),
                   (rows[1][0], rows[1][1], rows[1][2], p[1]),
                   (rows[2][0], rows[2][1], rows[2][2], p[2]),
                   (0, 0, 0, 1)))


def path_at_fraction(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


bpy.ops.wm.open_mainfile(filepath=str(scene_path))
scene = bpy.context.scene
scene.frame_set(1)
frames = json.loads(lookup_path.read_text(encoding="utf-8"))["frames"]
assert len(frames) == 101
registration = json.loads(registration_path.read_text(encoding="utf-8"))
humerus = next(item for item in registration["bones"] if item["modelBody"] == "humerus")
atlas_to_model = Matrix(humerus["atlasToModelBlenderRows"])
existing = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(atlas_path))
imported = set(bpy.data.objects) - existing
source = next(obj for obj in imported if obj.name == source_name)
original_vertices = [atlas_to_model @ source.matrix_world @ vertex.co
                     for vertex in source.data.vertices]
faces = [tuple(polygon.vertices) for polygon in source.data.polygons]
for imported_object in imported:
    bpy.data.objects.remove(imported_object, do_unlink=True)

paths = [[to_blender(point) for point in frame["muscles"][muscle_name]["viewerPathM"]]
         for frame in frames]
if not (120 <= args.height_cm <= 220 and 15 <= args.arm_cm <= 70):
    raise ValueError("Height or arm circumference outside app input range")
reference_arm_cm = 32 * args.height_cm / 175
thickness_scale = min(1.2, max(0.8, args.arm_cm / reference_arm_cm))
shoulder = to_blender(frames[0]["viewerJointsM"]["shoulder"])
upper_axis = (to_blender(frames[0]["viewerJointsM"]["elbow"]) - shoulder).normalized()


def scale_from_upper_axis(point):
    on_axis = shoulder + upper_axis * (point - shoulder).dot(upper_axis)
    return on_axis + (point - on_axis) * thickness_scale


vertices = [scale_from_upper_axis(point) for point in original_vertices]
axis = paths[0][-1] - paths[0][0]
axis_length_squared = axis.length_squared
if axis_length_squared < 0.01:
    raise AssertionError("Biceps path axis too short")
fractions = [max(0.0, min(1.0, (vertex - paths[0][0]).dot(axis) / axis_length_squared))
             for vertex in original_vertices]
rest_path = [path_at_fraction(paths[0], fraction) for fraction in fractions]
standing_body = body_matrix(frames[0]["blenderBodyFrames"]["humerus"])

mesh = bpy.data.meshes.new(f"{muscle_name}_research_mesh")
mesh.from_pydata(vertices, [], faces)
mesh.update()
fraction_attribute = mesh.attributes.new("path_fraction_proxy", type="FLOAT", domain="POINT")
for index, fraction in enumerate(fractions):
    fraction_attribute.data[index].value = fraction
group = bpy.data.collections.new("07_Biceps_Long_Head_Research_Deformation")
scene.collection.children.link(group)
obj = bpy.data.objects.new(f"atlas_{muscle_name}_{exercise}_probe", mesh)
group.objects.link(obj)
material = bpy.data.materials.new("肱二头肌长头 · 路径形变研究非发力")
material.diffuse_color = (0.63, 0.30, 0.42, 1)
material.use_nodes = True
shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
shader.inputs["Base Color"].default_value = material.diffuse_color
shader.inputs["Roughness"].default_value = 0.62
mesh.materials.append(material)
obj.shape_key_add(name="Atlas mesh after geometric registration", from_mix=False)

sampled_frames = (0, 25, 50, 75, 100)
sampled_vertices = {}
for index, path in enumerate(paths):
    frame_number = index + 1
    current_body = body_matrix(frames[index]["blenderBodyFrames"]["humerus"])
    rigid = current_body @ standing_body.inverted()
    key = obj.shape_key_add(name=f"TSM path probe {frame_number:03d}", from_mix=False)
    positions = []
    for vertex_index, (vertex, fraction, initial_path_point) in enumerate(
            zip(vertices, fractions, rest_path)):
        correction = path_at_fraction(path, fraction) - rigid @ initial_path_point
        position = rigid @ vertex + 0.25 * abs(2 * fraction - 1) ** 2 * correction
        key.data[vertex_index].co = position
        if index in sampled_frames:
            positions.append(position)
    if index in sampled_frames:
        sampled_vertices[index] = positions
    key.value = 0
    if frame_number > 1:
        key.keyframe_insert(data_path="value", frame=frame_number - 1)
    key.value = 1
    key.keyframe_insert(data_path="value", frame=frame_number)
    key.value = 0
    if frame_number < len(paths):
        key.keyframe_insert(data_path="value", frame=frame_number + 1)

base_edge_lengths = {(edge.vertices[0], edge.vertices[1]):
                     (vertices[edge.vertices[0]] - vertices[edge.vertices[1]]).length
                     for edge in mesh.edges}
edge_audit = []
for index in sampled_frames:
    positions = sampled_vertices[index]
    ratios = [(positions[a] - positions[b]).length / length
              for (a, b), length in base_edge_lengths.items() if length > 1e-7]
    edge_audit.append({"frameIndex": index,
                       "minimumEdgeLengthRatio": round(min(ratios), 5),
                       "maximumEdgeLengthRatio": round(max(ratios), 5)})

obj["atlas_source"] = "Z-Anatomy / BodyParts3D, CC BY-SA 4.0"
obj["model_path"] = "TSM BIC_long synthetic single-side path"
obj["method"] = "humerus rigid motion plus 0.25 endpoint weighted path correction"
obj["arm_circumference_cm"] = args.arm_cm
obj["arm_thickness_scale"] = thickness_scale
obj["status"] = "unvalidated research deformation, not strain or force"
scene["biceps_probe_status"] = obj["status"]
scene.frame_set(51)
bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)
report = {"status": "research_mesh_only_not_anatomy_or_force", "exercise": exercise,
          "sourceScene": str(scene_path.relative_to(ROOT)),
          "outputScene": str(output_path.relative_to(ROOT)),
          "preview": str(preview_path.relative_to(ROOT)),
          "atlasMesh": source_name, "modelMuscle": muscle_name,
          "vertexCount": len(vertices), "shapeKeys": len(paths) + 1,
          "heightCm": args.height_cm,
          "requestedArmCircumferenceCm": args.arm_cm,
          "referenceArmCircumferenceCm": reference_arm_cm,
          "appliedThicknessScale": thickness_scale,
          "radialMappingSamples": [
              {"vertexIndex": index, "originalBlenderM": list(original_vertices[index]),
               "personalizedBlenderM": list(vertices[index]), "pathFraction": fractions[index]}
              for index in sorted(set((0, len(vertices) // 4, len(vertices) // 2,
                                       3 * len(vertices) // 4, len(vertices) - 1)))],
          "pathFractionMethod": "projection onto synthetic start path endpoint axis, clamped to 0-1",
          "pathCorrectionWeight": "0.25 * abs(2*fraction - 1)^2",
          "sampledEdgeLengthRatios": edge_audit,
          "limitations": ["Atlas surface and model fiber path have centimeter-scale mismatch",
                          "Synthetic single-side poses are not measured bench press or overhead press",
                          "No validated attachment, tissue strain, EMG, activation, or force"]}
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("SAVED_TSM_BICEPS_PROBE", exercise, len(vertices), edge_audit)
