"""Add a right vastus intermedius mesh study to the six-muscle Blender scene.

The atlas mesh and the OpenSim path are not attachment-registered. These shape keys are a
visible deformation hypothesis, not an anatomical or force validation.
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/blender/opensim_six_muscle_motion.blend"
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
SURFACE_SCREEN = ROOT / "docs/data/right_leg_muscle_surface_path_screen.json"
OUTPUT = ROOT / "assets/blender/opensim_seven_muscle_motion.blend"
REPORT = ROOT / "docs/data/right_vastus_intermedius_mesh_motion_audit.json"
MUSCLE = "vas_int_r"
ATLAS_NAME = "Vastus intermedius muscle.r"
OBJECT_NAME = "atlas_vastus_intermedius_r_research"

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--thigh-cm", type=float, default=54)
parser.add_argument("--output", type=Path, default=OUTPUT)
parser.add_argument("--report", type=Path, default=REPORT)
args = parser.parse_args(argv)
for name in ("output", "report"):
    value = getattr(args, name)
    setattr(args, name, value if value.is_absolute() else ROOT / value)
if not 25 <= args.thigh_cm <= 110:
    parser.error("thigh circumference must be 25-110 cm")
thickness_scale = max(0.8, min(1.2, args.thigh_cm / 54))

# Carry the standing surface-proximity screen of this muscle into the audit so the recorded
# limitation stays traceable to the measurement that allowed the study.
screen = json.loads(SURFACE_SCREEN.read_text(encoding="utf-8"))
screen_entry = next(item for item in screen["muscles"] if item["opensimMuscle"] == MUSCLE)


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
standing_femur = body_matrix(frames[0]["blenderBodyFrames"]["femur_r"])
hip = to_blender(frames[0]["viewerJointsM"]["hip"])
axis = (to_blender(frames[0]["viewerJointsM"]["knee"]) - hip).normalized()
high = max(point.z for point in original_vertices)
low = min(point.z for point in original_vertices)
if high - low < 0.2:
    raise ValueError("Atlas mesh too short for this longitudinal study")
fractions = [(high - point.z) / (high - low) for point in original_vertices]
vertices = []
for point in original_vertices:
    on_axis = hip + axis * (point - hip).dot(axis)
    vertices.append(on_axis + (point - on_axis) * thickness_scale)
mesh = bpy.data.meshes.new("vastus_intermedius_r_atlas_research_mesh")
mesh.from_pydata(vertices, [], faces)
mesh.update()
fraction_attribute = mesh.attributes.new("opensim_path_fraction", type="FLOAT", domain="POINT")
for index, fraction in enumerate(fractions):
    fraction_attribute.data[index].value = fraction
group = bpy.data.collections.new("09_Vastus_Intermedius_Deformation_Study")
scene.collection.children.link(group)
obj = bpy.data.objects.new(OBJECT_NAME, mesh)
group.objects.link(obj)
material = bpy.data.materials.new("vas_int_r · research only, not force")
material.diffuse_color = (0.66, 0.71, 0.37, 1)
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
    current_femur = body_matrix(frames[number - 1]["blenderBodyFrames"]["femur_r"])
    rigid_delta = current_femur @ standing_femur.inverted()
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
obj["path_source"] = "OpenSim reference vas_int_r"
obj["method"] = "rigid femur motion plus endpoint-weighted path correction"
obj["status"] = "research_mesh_deformation_only_not_force"
scene["status"] = "research_seven_muscle_deformations_only"
scene["notes"] = ("Vastus intermedius is the deepest quadriceps head; the atlas mesh is a surface "
                  "shell and the model path runs inside it. Attachments and forces remain unvalidated.")
scene["requested_thigh_circumference_cm"] = args.thigh_cm
scene["applied_vastus_intermedius_thickness_scale"] = thickness_scale
scene.frame_set(51)
args.output.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(args.output))

sample_indices = sorted(set((0, len(vertices) // 4, len(vertices) // 2,
                             3 * len(vertices) // 4, len(vertices) - 1)))
report = {"status": "research_only_unvalidated_vastus_intermedius_deformation",
          "sourceScene": str(SOURCE.relative_to(ROOT)),
          "outputScene": str(args.output.relative_to(ROOT)),
          "opensimMuscle": MUSCLE, "atlasMesh": ATLAS_NAME, "body": "femur_r",
          "vertexCount": len(vertices), "shapeKeys": len(paths) + 1,
          "requestedThighCircumferenceCm": args.thigh_cm,
          "appliedThicknessScale": thickness_scale,
          "referenceHighZ": high, "referenceLowZ": low,
          "standingSurfaceScreen": {
              "source": str(SURFACE_SCREEN.relative_to(ROOT)),
              "medianSurfaceDistanceM": screen_entry["medianSurfaceDistanceM"],
              "p95SurfaceDistanceM": screen_entry["p95SurfaceDistanceM"],
              "maximumSurfaceDistanceM": screen_entry["maximumSurfaceDistanceM"],
              "samplesWithinMeshHeight": screen_entry["samplesWithinMeshHeight"],
              "sampleCountPerMuscle": screen["sampleCountPerMuscle"]},
          "radialMappingSamples": [{"vertexIndex": index,
              "originalBlenderM": list(original_vertices[index]),
              "personalizedBlenderM": list(vertices[index]),
              "pathFraction": fractions[index]} for index in sample_indices],
          "referenceMaximumRadialDistanceM": max((point - (
              hip + axis * (point - hip).dot(axis))).length for point in original_vertices),
          "personalizedMaximumRadialDistanceM": max((point - (
              hip + axis * (point - hip).dot(axis))).length for point in vertices),
          "limitations": [
              "standing registration uses bone bounding-box centres, not anatomical attachments",
              "standing path to atlas surface reaches %.2f cm (median %.2f cm) in the %d-sample screen"
              % (screen_entry["maximumSurfaceDistanceM"] * 100,
                 screen_entry["medianSurfaceDistanceM"] * 100, screen["sampleCountPerMuscle"]),
              "the atlas mesh is a surface shell; the model path runs inside the mesh, so surface "
              "proximity does not show whether the path sits inside the right head",
              "vertical mesh fraction is a deformation heuristic, not fiber direction",
              "thigh girth scales the mesh cross section only",
              "no measured fiber strain, EMG or muscle force"]}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("SAVED_VASTUS_INTERMEDIUS_MOTION", args.output, "vertices", len(vertices),
      "frames", len(frames), "thickness scale", thickness_scale)
