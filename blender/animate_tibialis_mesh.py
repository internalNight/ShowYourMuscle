"""Add a right tibialis-anterior mesh study to the three-muscle Blender scene."""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/blender/opensim_thigh_mesh_motion.blend"
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
OUTPUT = ROOT / "assets/blender/opensim_four_muscle_motion.blend"
REPORT = ROOT / "docs/data/right_tibialis_mesh_motion_audit.json"
MUSCLE = "tib_ant_r"
ATLAS_NAME = "Tibialis anterior muscle.r"
OBJECT_NAME = "atlas_tibialis_anterior_r_research"

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--calf-cm", type=float, default=36)
parser.add_argument("--output", type=Path, default=OUTPUT)
parser.add_argument("--report", type=Path, default=REPORT)
args = parser.parse_args(argv)
for name in ("output", "report"):
    value = getattr(args, name)
    setattr(args, name, value if value.is_absolute() else ROOT / value)
if not 15 <= args.calf_cm <= 75:
    parser.error("calf circumference must be 15-75 cm")
thickness_scale = max(0.8, min(1.2, args.calf_cm / 36))


def to_blender(point):
    x, y, z = point
    return Vector((0.09 - x, -z, y))


def at_fraction(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = max(0, min(1, fraction)) * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length > 0:
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


bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
scene.frame_set(1)
existing = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
source_by_name = {obj.name: obj for obj in set(bpy.data.objects) - existing}
source = source_by_name[ATLAS_NAME]
shift = Vector(json.loads(REGISTRATION.read_text(encoding="utf-8"))["translationM"])
original_vertices = [source.matrix_world @ vertex.co + shift for vertex in source.data.vertices]
faces = [tuple(poly.vertices) for poly in source.data.polygons]
for obj in set(bpy.data.objects) - existing:
    bpy.data.objects.remove(obj, do_unlink=True)

frames = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"]
assert len(frames) == 101
standing_tibia = body_matrix(frames[0]["blenderBodyFrames"]["tibia_r"])
knee = to_blender(frames[0]["viewerJointsM"]["knee"])
axis = (to_blender(frames[0]["viewerJointsM"]["ankle"]) - knee).normalized()
high = max(point.z for point in original_vertices)
low = min(point.z for point in original_vertices)
fractions = [(high - point.z) / (high - low) for point in original_vertices]
vertices = []
for point in original_vertices:
    on_axis = knee + axis * (point - knee).dot(axis)
    vertices.append(on_axis + (point - on_axis) * thickness_scale)
mesh = bpy.data.meshes.new("tib_ant_r_atlas_research_mesh")
mesh.from_pydata(vertices, [], faces)
mesh.update()
fraction_attribute = mesh.attributes.new("opensim_path_fraction", type="FLOAT", domain="POINT")
for index, fraction in enumerate(fractions):
    fraction_attribute.data[index].value = fraction
group = bpy.data.collections.new("06_Tibialis_Anterior_Deformation_Study")
scene.collection.children.link(group)
obj = bpy.data.objects.new(OBJECT_NAME, mesh)
group.objects.link(obj)
material = bpy.data.materials.new("tib_ant_r · research only, not force")
material.diffuse_color = (0.50, 0.73, 0.58, 1)
material.use_nodes = True
shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
shader.inputs["Base Color"].default_value = material.diffuse_color
shader.inputs["Roughness"].default_value = 0.65
mesh.materials.append(material)

paths = [[to_blender(point) for point in frame["muscles"][MUSCLE]["viewerPathM"]]
         for frame in frames]
standing_path_points = [at_fraction(paths[0], fraction) for fraction in fractions]
obj.shape_key_add(name="Standing atlas mesh", from_mix=False)
for number, path in enumerate(paths, start=1):
    current_tibia = body_matrix(frames[number - 1]["blenderBodyFrames"]["tibia_r"])
    rigid_delta = current_tibia @ standing_tibia.inverted()
    key = obj.shape_key_add(name=f"OpenSim path displacement {number:03d}", from_mix=False)
    for index, (point, fraction, standing_path_point) in enumerate(zip(
            vertices, fractions, standing_path_points)):
        rigid_point = rigid_delta @ point
        correction = at_fraction(path, fraction) - rigid_delta @ standing_path_point
        key.data[index].co = rigid_point + 0.5 * abs(2 * fraction - 1) ** 2 * correction
    key.value = 0
    if number > 1:
        key.keyframe_insert(data_path="value", frame=number - 1)
    key.value = 1
    key.keyframe_insert(data_path="value", frame=number)
    key.value = 0
    if number < len(paths):
        key.keyframe_insert(data_path="value", frame=number + 1)
obj["anatomy_source"] = "Z-Anatomy / BodyParts3D, CC BY-SA 4.0"
obj["path_source"] = "OpenSim reference tib_ant_r"
obj["method"] = "rigid tibia motion plus endpoint-weighted path correction"
obj["status"] = "research_mesh_deformation_only_not_force"
scene["status"] = "research_four_muscle_deformations_only"
scene["notes"] = "Tibialis anterior path and atlas surface are close in standing; attachments and forces remain unvalidated."
scene["requested_calf_circumference_cm"] = args.calf_cm
scene["applied_tibialis_thickness_scale"] = thickness_scale
scene.frame_set(51)
args.output.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(args.output))

sample_indices = sorted(set((0, len(vertices) // 4, len(vertices) // 2,
                             3 * len(vertices) // 4, len(vertices) - 1)))
report = {"status": "research_only_unvalidated_tibialis_deformation",
          "sourceScene": str(SOURCE.relative_to(ROOT)),
          "outputScene": str(args.output.relative_to(ROOT)),
          "opensimMuscle": MUSCLE, "atlasMesh": ATLAS_NAME,
          "vertexCount": len(vertices), "shapeKeys": len(paths) + 1,
          "requestedCalfCircumferenceCm": args.calf_cm,
          "appliedThicknessScale": thickness_scale,
          "referenceHighZ": high, "referenceLowZ": low,
          "radialMappingSamples": [{"vertexIndex": index,
              "originalBlenderM": list(original_vertices[index]),
              "personalizedBlenderM": list(vertices[index]),
              "pathFraction": fractions[index]} for index in sample_indices],
          "referenceMaximumRadialDistanceM": max((point - (
              knee + axis * (point - knee).dot(axis))).length for point in original_vertices),
          "personalizedMaximumRadialDistanceM": max((point - (
              knee + axis * (point - knee).dot(axis))).length for point in vertices),
          "limitations": ["nearest surface/path agreement is a standing geometry screen, not an attachment validation",
                          "calf girth scales mesh cross section only",
                          "no measured fiber strain, EMG or muscle force"]}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("SAVED_TIBIALIS_MOTION", args.output, "vertices", len(vertices),
      "frames", len(frames), "thickness scale", thickness_scale)
