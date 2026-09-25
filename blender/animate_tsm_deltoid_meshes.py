"""Save three candidate atlas deltoid surfaces over 101 synthetic TSM poses.

Humerus rigid motion and a small proximal path correction are a visual study,
not measured tissue deformation, activation, or muscle force.
"""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
SCREEN = ROOT / "docs/data/tsm_deltoid_endpoint_deformation_screen.json"
MUSCLES = (
    ("DeltoideusClavicle_A", "Clavicular part of deltoid muscle.r", (.70, .54, .86)),
    ("DeltoideusScapula_M", "Acromial part of deltoid muscle.r", (.57, .67, .91)),
    ("DeltoideusScapula_P", "Scapular spinal part of deltoid muscle.r", (.44, .58, .80)),
)


def to_blender(point):
    x, y, z = point
    return Vector((x, -z, y))


def matrix(frame, body):
    entry = frame["blenderBodyFrames"][body]
    rows = entry["rotationRows"]
    x, y, z = entry["translationM"]
    return Matrix(((rows[0][0], rows[0][1], rows[0][2], x),
                   (rows[1][0], rows[1][1], rows[1][2], y),
                   (rows[2][0], rows[2][1], rows[2][2], z),
                   (0, 0, 0, 1)))


def at_fraction(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length > 0:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
exercise = args[0] if args else "press"
if exercise not in ("bench", "press"):
    raise ValueError("Expected bench or press")
scene_path = ROOT / f"assets/blender/opensim_tsm_{exercise}_upper_bones.blend"
output = ROOT / f"assets/blender/opensim_tsm_{exercise}_deltoid_atlas_probe.blend"
report_path = ROOT / f"docs/data/tsm_{exercise}_deltoid_atlas_probe.json"
lookup = json.loads((ROOT / f"public/data/{exercise}_tsm_reference.json")
                    .read_text(encoding="utf-8"))["frames"]
registration = json.loads((ROOT / f"docs/data/tsm_{exercise}_upper_bone_registration.json")
                          .read_text(encoding="utf-8"))
screen = json.loads(SCREEN.read_text(encoding="utf-8"))
audit_rows = [row for row in screen["muscles"] if row["exercise"] == exercise]
if len(lookup) != 101 or len(audit_rows) != 3 or any(
        row["minimumEdgeRatio"] < .5 or row["maximumEdgeRatio"] > 1.5 or
        row["maximumPathSurfaceCm"] > 7 for row in audit_rows):
    raise ValueError("Deltoid candidate failed coarse geometry audit")
humerus = next(row for row in registration["bones"] if row["modelBody"] == "humerus")
fit = Matrix(humerus["atlasToModelBlenderRows"])
bpy.ops.wm.open_mainfile(filepath=str(scene_path))
scene = bpy.context.scene
scene.frame_set(1)
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
imported = set(bpy.data.objects) - before
objects = {obj.name: obj for obj in imported}
group = bpy.data.collections.new("10_Atlas_Deltoid_Candidate_Not_Force")
scene.collection.children.link(group)
standing_humerus_inverse = matrix(lookup[0], "humerus").inverted()
report_rows = []
for muscle, atlas_name, color in MUSCLES:
    source = objects[atlas_name]
    rest = [fit @ source.matrix_world @ vertex.co for vertex in source.data.vertices]
    faces = [tuple(poly.vertices) for poly in source.data.polygons]
    paths = [[to_blender(point) for point in frame["muscles"][muscle]["viewerPathM"]]
             for frame in lookup]
    axis = paths[0][-1] - paths[0][0]
    if axis.length_squared < .001:
        raise ValueError(f"Path too short: {muscle}")
    fractions = [max(0, min(1, (vertex - paths[0][0]).dot(axis) /
                            axis.length_squared)) for vertex in rest]
    resting_path_points = [at_fraction(paths[0], fraction) for fraction in fractions]
    mesh = bpy.data.meshes.new(f"{muscle}_candidate_mesh")
    mesh.from_pydata(rest, [], faces)
    mesh.update()
    attr = mesh.attributes.new("model_path_fraction_proxy", type="FLOAT", domain="POINT")
    for index, fraction in enumerate(fractions):
        attr.data[index].value = fraction
    obj = bpy.data.objects.new(f"atlas_{muscle}_{exercise}_candidate", mesh)
    group.objects.link(obj)
    material = bpy.data.materials.new(f"{muscle} visual study, not force")
    material.diffuse_color = (*color, 1)
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = material.diffuse_color
    shader.inputs["Roughness"].default_value = .67
    mesh.materials.append(material)
    obj.shape_key_add(name="Atlas registered at first pose", from_mix=False)
    for frame_number, (frame, path) in enumerate(zip(lookup, paths), start=1):
        humerus_delta = matrix(frame, "humerus") @ standing_humerus_inverse
        key = obj.shape_key_add(name=f"TSM path correction {frame_number:03d}", from_mix=False)
        for index, (vertex, fraction, rest_path) in enumerate(zip(
                rest, fractions, resting_path_points)):
            rigid = humerus_delta @ vertex
            correction = at_fraction(path, fraction) - humerus_delta @ rest_path
            key.data[index].co = rigid + .25 * (1 - fraction) ** 2 * correction
        key.value = 0
        if frame_number > 1:
            key.keyframe_insert(data_path="value", frame=frame_number - 1)
        key.value = 1
        key.keyframe_insert(data_path="value", frame=frame_number)
        key.value = 0
        if frame_number < len(lookup):
            key.keyframe_insert(data_path="value", frame=frame_number + 1)
    obj["atlas_source"] = "Z-Anatomy / BodyParts3D, CC BY-SA 4.0"
    obj["model_path"] = f"TSM {muscle}, synthetic {exercise} pose"
    obj["status"] = "candidate surface motion, not tissue strain or force"
    report_rows.append({"muscle": muscle, "atlasMesh": atlas_name,
                        "vertexCount": len(rest), "shapeKeys": len(lookup) + 1,
                        "minimumEdgeRatio": next(row for row in audit_rows if row["muscle"] == muscle)["minimumEdgeRatio"],
                        "maximumEdgeRatio": next(row for row in audit_rows if row["muscle"] == muscle)["maximumEdgeRatio"],
                        "maximumPathSurfaceCm": next(row for row in audit_rows if row["muscle"] == muscle)["maximumPathSurfaceCm"]})
for obj in imported:
    bpy.data.objects.remove(obj, do_unlink=True)
scene["deltoid_candidate_status"] = "three candidate deltoid surfaces, not anatomical or force validation"
scene.frame_set(51)
bpy.ops.wm.save_as_mainfile(filepath=str(output))
report_path.write_text(json.dumps({"status": "research_only_unvalidated_deltoid_atlas_motion",
                             "exercise": exercise, "scene": str(output.relative_to(ROOT)),
                             "source": str(scene_path.relative_to(ROOT)),
                             "method": screen["method"], "muscles": report_rows,
                             "limitations": screen["limitations"]},
                            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("SAVED_DELTOID_ATLAS_PROBE", exercise, output)
