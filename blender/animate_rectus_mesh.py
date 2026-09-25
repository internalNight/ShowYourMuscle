"""Transfer OpenSim rectus-path displacement to one anatomical muscle mesh.

This preserves the atlas mesh in the standing pose, follows the OpenSim femur
body transform, and partly blends path displacement at the muscle ends.
It is a geometry experiment,
not a validated attachment, fiber architecture, or force visualization.
"""

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/blender/opensim_anatomy_bone_motion.blend"
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
OUTPUT = ROOT / "assets/blender/opensim_rectus_mesh_motion.blend"
PREVIEW = ROOT / "assets/blender/opensim_rectus_mesh_motion.png"
TARGET = "Rectus femoris muscle.r"
MUSCLE = "rect_fem_r"


def to_blender(point):
    x, y, z = point
    return Vector((0.09 - x, -z, y))


def path_at_fraction(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = max(0, min(1, fraction)) * sum(lengths)
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


def endpoint_weight(fraction):
    # The central muscle belly follows the femur rigidly. Correction from
    # OpenSim's path is blended in near the proximal/distal ends only.
    u = abs(2 * fraction - 1)
    return 0.5 * u * u


bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
scene.frame_set(1)
existing = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
new_objects = set(bpy.data.objects) - existing
source = next(obj for obj in new_objects if obj.name == TARGET)
shift = Vector(json.loads(REGISTRATION.read_text(encoding="utf-8"))["translationM"])
vertices = [source.matrix_world @ vertex.co + shift for vertex in source.data.vertices]
faces = [tuple(poly.vertices) for poly in source.data.polygons]
for obj in new_objects:
    bpy.data.objects.remove(obj, do_unlink=True)

mesh = bpy.data.meshes.new("股直肌研究形变网格")
mesh.from_pydata(vertices, [], faces)
mesh.update()
muscle = bpy.data.objects.new("atlas_rectus_femoris_r_research", mesh)
group = bpy.data.collections.new("05_Rectus_Femoris_Path_Displacement_Study")
scene.collection.children.link(group)
group.objects.link(muscle)
material = bpy.data.materials.new("股直肌研究叠加 · 非发力")
material.diffuse_color = (0.6, 0.46, 0.78, 1)
material.use_nodes = True
shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
shader.inputs["Base Color"].default_value = (0.6, 0.46, 0.78, 1)
shader.inputs["Roughness"].default_value = 0.65
mesh.materials.append(material)

frames = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"]
paths = [[to_blender(point) for point in frame["muscles"][MUSCLE]["viewerPathM"]]
         for frame in frames]
high = max(point.z for point in vertices)
low = min(point.z for point in vertices)
fractions = [(high - point.z) / (high - low) for point in vertices]
standing = [path_at_fraction(paths[0], fraction) for fraction in fractions]
standing_femur = body_matrix(frames[0]["blenderBodyFrames"]["femur_r"])

muscle.shape_key_add(name="Standing atlas mesh", from_mix=False)
for number, path in enumerate(paths, start=1):
    current_femur = body_matrix(frames[number - 1]["blenderBodyFrames"]["femur_r"])
    rigid_delta = current_femur @ standing_femur.inverted()
    key = muscle.shape_key_add(name=f"OpenSim path displacement {number:03d}", from_mix=False)
    for index, (point, fraction, rest_path_point) in enumerate(zip(vertices, fractions, standing)):
        rigid_point = rigid_delta @ point
        path_correction = path_at_fraction(path, fraction) - rigid_delta @ rest_path_point
        key.data[index].co = rigid_point + endpoint_weight(fraction) * path_correction
    key.value = 0
    if number > 1:
        key.keyframe_insert(data_path="value", frame=number - 1)
    key.value = 1
    key.keyframe_insert(data_path="value", frame=number)
    key.value = 0
    if number < len(paths):
        key.keyframe_insert(data_path="value", frame=number + 1)

muscle["anatomy_source"] = "Z-Anatomy / BodyParts3D, CC BY-SA 4.0"
muscle["path_source"] = "OpenSim reference rect_fem_r"
muscle["method"] = "rigid femur motion plus endpoint-weighted path correction"
muscle["status"] = "research_mesh_deformation_only_not_force"
scene["status"] = "research_rectus_deformation_only"
scene["notes"] = "Atlas standing rectus centerline differs 2.1-4.7 cm from OpenSim path in five sampled slices; belly follows femur, ends blend to path motion; no anatomical or force validation."
scene.frame_set(51)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print("SAVED_RECTUS_RESEARCH_MOTION", OUTPUT, "vertices", len(vertices), "frames", len(paths))
