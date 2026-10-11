"""Add a right medial gastrocnemius mesh study to the seven-muscle Blender scene.

The atlas mesh and the OpenSim path are not attachment-registered, and the model path continues far
past the belly mesh as the calcaneal tendon. These shape keys are a visible deformation hypothesis,
not an anatomical or force validation.
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/blender/opensim_seven_muscle_motion.blend"
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
ALIGNMENT_PROBE = ROOT / "docs/data/right_leg_mesh_alignment_probe.json"
OUTPUT = ROOT / "assets/blender/opensim_eight_muscle_motion.blend"
REPORT = ROOT / "docs/data/right_medial_gastrocnemius_mesh_motion_audit.json"
MUSCLE = "med_gas_r"
ATLAS_NAME = "Medial head of gastrocnemius.r"
OBJECT_NAME = "atlas_medial_gastrocnemius_r_research"

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--calf-cm", type=float, default=36)
parser.add_argument("--output", type=Path, default=OUTPUT)
parser.add_argument("--report", type=Path, default=REPORT)
parser.add_argument("--report-only", action="store_true",
                    help="write the audit without saving another scene, for girth variants")
args = parser.parse_args(argv)
for name in ("output", "report"):
    value = getattr(args, name)
    setattr(args, name, value if value.is_absolute() else ROOT / value)
if not 15 <= args.calf_cm <= 75:
    parser.error("calf circumference must be 15-75 cm")
thickness_scale = max(0.8, min(1.2, args.calf_cm / 36))

# Carry the probe numbers that allowed this study into the audit so the limitation stays traceable.
alignment = json.loads(ALIGNMENT_PROBE.read_text(encoding="utf-8"))["muscles"][MUSCLE]


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
source = {obj.name: obj for obj in set(bpy.data.objects) - existing}[ATLAS_NAME]
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
if high - low < 0.2:
    raise ValueError("Atlas mesh too short for this longitudinal study")
fractions = [(high - point.z) / (high - low) for point in original_vertices]
vertices = []
for point in original_vertices:
    on_axis = knee + axis * (point - knee).dot(axis)
    vertices.append(on_axis + (point - on_axis) * thickness_scale)
mesh = bpy.data.meshes.new("medial_gastrocnemius_r_atlas_research_mesh")
mesh.from_pydata(vertices, [], faces)
mesh.update()
fraction_attribute = mesh.attributes.new("opensim_path_fraction", type="FLOAT", domain="POINT")
for index, fraction in enumerate(fractions):
    fraction_attribute.data[index].value = fraction
group = bpy.data.collections.new("10_Medial_Gastrocnemius_Deformation_Study")
scene.collection.children.link(group)
obj = bpy.data.objects.new(OBJECT_NAME, mesh)
group.objects.link(obj)
material = bpy.data.materials.new("med_gas_r · research only, not force")
material.diffuse_color = (0.78, 0.45, 0.42, 1)
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
obj["path_source"] = "OpenSim reference med_gas_r"
obj["method"] = "rigid tibia motion plus endpoint-weighted path correction"
obj["status"] = "research_mesh_deformation_only_not_force"
scene["status"] = "research_eight_muscle_deformations_only"
scene["notes"] = ("The model med_gas_r path continues about 16 cm past the belly mesh as the "
                  "calcaneal tendon, so the mesh only represents the belly. Attachments and forces "
                  "remain unvalidated.")
scene["requested_calf_circumference_cm"] = args.calf_cm
scene["applied_medial_gastrocnemius_thickness_scale"] = thickness_scale
scene.frame_set(51)
if not args.report_only:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output))

sample_indices = sorted(set((0, len(vertices) // 4, len(vertices) // 2,
                             3 * len(vertices) // 4, len(vertices) - 1)))
report = {"status": "research_only_unvalidated_medial_gastrocnemius_deformation",
          "sourceScene": str(SOURCE.relative_to(ROOT)),
          "outputScene": None if args.report_only else str(args.output.relative_to(ROOT)),
          "sceneStored": not args.report_only,
          "opensimMuscle": MUSCLE, "atlasMesh": ATLAS_NAME, "body": "tibia_r",
          "vertexCount": len(vertices), "shapeKeys": len(paths) + 1,
          "requestedCalfCircumferenceCm": args.calf_cm,
          "appliedThicknessScale": thickness_scale,
          "referenceHighZ": high, "referenceLowZ": low,
          "standingAlignmentProbe": {
              "source": str(ALIGNMENT_PROBE.relative_to(ROOT)),
              "surfaceDistanceInsideMeshHeightM": alignment["surfaceScreenInsideMeshHeight"],
              "surfaceDistanceBeyondMeshHeightM": alignment["surfaceScreenBeyondMeshHeight"],
              "meshHeightM": alignment["meshHeightM"], "pathLengthM": alignment["pathLengthM"],
              "publishedCentreDistanceM": alignment["publishedCentreDistanceM"]},
          "radialMappingSamples": [{"vertexIndex": index,
              "originalBlenderM": list(original_vertices[index]),
              "personalizedBlenderM": list(vertices[index]),
              "pathFraction": fractions[index]} for index in sample_indices],
          "referenceMaximumRadialDistanceM": max((point - (
              knee + axis * (point - knee).dot(axis))).length for point in original_vertices),
          "personalizedMaximumRadialDistanceM": max((point - (
              knee + axis * (point - knee).dot(axis))).length for point in vertices),
          "limitations": [
              "standing registration uses bone bounding-box centres, not anatomical attachments",
              "inside the mesh height the standing path stays %.2f cm (median %.2f cm) from the "
              "surface, but the model path continues %.2f cm past the mesh as the calcaneal tendon"
              % (alignment["surfaceScreenInsideMeshHeight"]["maximumDistanceM"] * 100,
                 alignment["surfaceScreenInsideMeshHeight"]["medianDistanceM"] * 100,
                 alignment["surfaceScreenBeyondMeshHeight"]["maximumDistanceM"] * 100),
              "the mesh is a belly shell without tendon; the path's distal %.0f%% excess is distal "
              "extension rather than lateral offset"
              % (alignment["surfaceScreenBeyondMeshHeight"]["medianDistalShareOfDistance"] * 100),
              "the model path is %.2f times the mesh height, so the vertical mesh fraction compresses "
              "a longer arc; it is a deformation heuristic, not fiber direction"
              % (alignment["pathLengthM"] / alignment["meshHeightM"]),
              "calf girth scales the mesh cross section only",
              "no measured fiber strain, EMG or muscle force"]}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("SAVED_MEDIAL_GASTROCNEMIUS_MOTION", args.output if not args.report_only else "(report only)",
      "vertices", len(vertices), "frames", len(frames), "thickness scale", thickness_scale)
