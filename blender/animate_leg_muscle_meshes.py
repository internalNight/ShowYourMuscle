"""Blender-only study of three right-thigh anatomy meshes on OpenSim squat paths.

The atlas and OpenSim paths have different attachment geometry. These shape
keys are a visible deformation hypothesis, not anatomical or force validation.
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/blender/opensim_anatomy_bone_motion.blend"
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
OUTPUT = ROOT / "assets/blender/opensim_thigh_mesh_motion.blend"
PREVIEW = ROOT / "assets/blender/opensim_thigh_mesh_motion.png"
REPORT = ROOT / "docs/data/right_thigh_mesh_motion_audit.json"
MUSCLES = (
    ("rect_fem_r", "Rectus femoris muscle.r", "atlas_rectus_femoris_r_research", (0.60, 0.46, 0.78, 1.0)),
    ("bifemsh_r", "Short head of biceps femoris.r", "atlas_biceps_femoris_short_r_research", (0.40, 0.70, 0.78, 1.0)),
    ("semimem_r", "Semimembranosus muscle.r", "atlas_semimembranosus_r_research", (0.76, 0.56, 0.70, 1.0)),
)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--thigh-cm", type=float, default=54)
parser.add_argument("--output", type=Path, default=OUTPUT)
parser.add_argument("--preview", type=Path, default=PREVIEW)
parser.add_argument("--report", type=Path, default=REPORT)
args = parser.parse_args(argv)
for name in ("output", "preview", "report"):
    value = getattr(args, name)
    setattr(args, name, value if value.is_absolute() else ROOT / value)
if not 25 <= args.thigh_cm <= 110:
    parser.error("thigh circumference must be 25-110 cm")
thickness_scale = max(0.8, min(1.2, args.thigh_cm / 54))


def to_blender(point):
    x, y, z = point
    return Vector((0.09 - x, -z, y))


def at_fraction(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    total = sum(lengths)
    if total <= 0:
        raise ValueError("OpenSim muscle path has no length")
    remaining = max(0, min(1, fraction)) * total
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


def endpoint_weight(fraction):
    return 0.5 * abs(2 * fraction - 1) ** 2


bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
scene.frame_set(1)
existing = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
new_objects = set(bpy.data.objects) - existing
source_by_name = {obj.name: obj for obj in new_objects}
shift = Vector(json.loads(REGISTRATION.read_text(encoding="utf-8"))["translationM"])
atlas_data = {}
for muscle_name, atlas_name, output_name, color in MUSCLES:
    source = source_by_name[atlas_name]
    atlas_data[muscle_name] = (
        [source.matrix_world @ vertex.co + shift for vertex in source.data.vertices],
        [tuple(poly.vertices) for poly in source.data.polygons],
    )
for obj in new_objects:
    bpy.data.objects.remove(obj, do_unlink=True)

frames = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"]
assert len(frames) == 101
standing_femur = body_matrix(frames[0]["blenderBodyFrames"]["femur_r"])
hip = to_blender(frames[0]["viewerJointsM"]["hip"])
femur_axis = (to_blender(frames[0]["viewerJointsM"]["knee"]) - hip).normalized()
group = bpy.data.collections.new("05_Three_Thigh_Muscle_Deformation_Study")
scene.collection.children.link(group)
records = []

for muscle_name, atlas_name, output_name, color in MUSCLES:
    original_vertices, faces = atlas_data[muscle_name]
    original_high = max(point.z for point in original_vertices)
    original_low = min(point.z for point in original_vertices)
    fractions = [(original_high - point.z) / (original_high - original_low)
                 for point in original_vertices]
    vertices = []
    for point in original_vertices:
        on_axis = hip + femur_axis * (point - hip).dot(femur_axis)
        vertices.append(on_axis + (point - on_axis) * thickness_scale)
    mesh = bpy.data.meshes.new(f"{muscle_name}_atlas_research_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    fraction_attribute = mesh.attributes.new("opensim_path_fraction", type="FLOAT", domain="POINT")
    for index, fraction in enumerate(fractions):
        fraction_attribute.data[index].value = fraction
    obj = bpy.data.objects.new(output_name, mesh)
    group.objects.link(obj)
    material = bpy.data.materials.new(f"{muscle_name} · research only, not force")
    material.diffuse_color = color
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = 0.65
    mesh.materials.append(material)

    paths = [[to_blender(point) for point in frame["muscles"][muscle_name]["viewerPathM"]]
             for frame in frames]
    high, low = max(point.z for point in vertices), min(point.z for point in vertices)
    if high - low < 0.2:
        raise ValueError(f"Atlas mesh too short for this longitudinal study: {muscle_name}")
    standing_path_points = [at_fraction(paths[0], fraction) for fraction in fractions]
    obj.shape_key_add(name="Standing atlas mesh", from_mix=False)
    for number, path in enumerate(paths, start=1):
        current_femur = body_matrix(frames[number - 1]["blenderBodyFrames"]["femur_r"])
        rigid_delta = current_femur @ standing_femur.inverted()
        key = obj.shape_key_add(name=f"OpenSim path displacement {number:03d}", from_mix=False)
        for index, (point, fraction, standing_path_point) in enumerate(zip(
                vertices, fractions, standing_path_points)):
            rigid_point = rigid_delta @ point
            path_correction = at_fraction(path, fraction) - rigid_delta @ standing_path_point
            key.data[index].co = rigid_point + endpoint_weight(fraction) * path_correction
        key.value = 0
        if number > 1:
            key.keyframe_insert(data_path="value", frame=number - 1)
        key.value = 1
        key.keyframe_insert(data_path="value", frame=number)
        key.value = 0
        if number < len(paths):
            key.keyframe_insert(data_path="value", frame=number + 1)
    obj["anatomy_source"] = "Z-Anatomy / BodyParts3D, CC BY-SA 4.0"
    obj["path_source"] = f"OpenSim reference {muscle_name}"
    obj["method"] = "rigid femur motion plus endpoint-weighted path correction"
    obj["status"] = "research_mesh_deformation_only_not_force"
    records.append({"opensimMuscle": muscle_name, "atlasMesh": atlas_name,
                    "object": output_name, "vertexCount": len(vertices),
                    "restMeshHeightM": round(high - low, 4), "shapeKeys": len(paths) + 1,
                    "referenceHighZ": round(original_high, 8),
                    "referenceLowZ": round(original_low, 8),
                    "radialMappingSamples": [{
                        "vertexIndex": index,
                        "originalBlenderM": [round(value, 8) for value in original_vertices[index]],
                        "personalizedBlenderM": [round(value, 8) for value in vertices[index]],
                        "pathFraction": round(fractions[index], 8),
                    } for index in sorted(set((0, len(vertices) // 4, len(vertices) // 2,
                                                3 * len(vertices) // 4, len(vertices) - 1)))],
                    "referenceMaximumRadialDistanceM": round(max((point - (
                        hip + femur_axis * (point - hip).dot(femur_axis))).length
                        for point in original_vertices), 5),
                    "personalizedMaximumRadialDistanceM": round(max((point - (
                        hip + femur_axis * (point - hip).dot(femur_axis))).length
                        for point in vertices), 5)})

scene["status"] = "research_three_thigh_mesh_deformations_only"
scene["notes"] = "Atlas meshes and OpenSim path endpoints are not attachment-registered; colors identify meshes, not length, activation, or force."
scene["requested_thigh_circumference_cm"] = args.thigh_cm
scene["applied_muscle_thickness_scale"] = thickness_scale
scene.frame_set(51)
args.output.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(args.output))
args.preview.parent.mkdir(parents=True, exist_ok=True)
scene.render.filepath = str(args.preview)
bpy.ops.render.render(write_still=True)
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps({"status": "research_only_unvalidated_deformation",
    "sourceScene": str(SOURCE.relative_to(ROOT)),
    "outputScene": str(args.output.relative_to(ROOT)),
    "reference": "Z-Anatomy static GLB plus app OpenSim squat lookup",
    "frameCount": len(frames), "requestedThighCircumferenceCm": args.thigh_cm,
    "appliedMuscleThicknessScale": thickness_scale,
    "muscles": records,
    "limitations": ["standing meshes registered by bone bounding boxes, not anatomical attachments",
                    "vertical mesh fraction is a deformation heuristic, not fiber direction",
                    "thigh girth scales all three mesh cross sections together; no individual muscle distribution inferred",
                    "no load, activation, or individual muscle force"]}, indent=2) + "\n", encoding="utf-8")
print("SAVED_THIGH_RESEARCH_MOTION", args.output, "muscles", len(records),
      "frames", len(frames), "thickness scale", thickness_scale)
