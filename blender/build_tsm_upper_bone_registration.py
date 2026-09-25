"""Fit three Z-Anatomy right-arm bones to TSM segments and animate them.

This is a geometric registration probe. End caps are mesh-slice centroids,
not anatomical joint landmarks. No muscle meshes, contact, or force is fitted.
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
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
EXERCISE = args.exercise
SOURCE = ROOT / "assets/blender" / f"opensim_tsm_{EXERCISE}_reference.blend"
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data" / f"{EXERCISE}_tsm_reference.json"
OUTPUT = ROOT / "assets/blender" / f"opensim_tsm_{EXERCISE}_upper_bones.blend"
PREVIEW = ROOT / "assets/blender" / f"opensim_tsm_{EXERCISE}_upper_bones.png"
REPORT = ROOT / "docs/data" / f"tsm_{EXERCISE}_upper_bone_registration.json"
SPECS = (
    ("Humerus.r", "humerus", "shoulder", "elbow"),
    ("Radius.r", "radius", "elbow", "hand"),
    ("Ulna.r", "ulna", "elbow", "hand"),
)


def to_blender(point):
    x, y, z = point
    return Vector((x, -z, y))


def body_matrix(data):
    result = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            result[row][col] = data["rotationRows"][row][col]
    result.translation = Vector(data["translationM"])
    return result


def endpoint_centroids(points):
    bottom = min(point.z for point in points)
    top = max(point.z for point in points)
    band = (top - bottom) * 0.05
    if band <= 0:
        raise AssertionError("Degenerate anatomical bone height")
    proximal = [point for point in points if point.z >= top - band]
    distal = [point for point in points if point.z <= bottom + band]
    if min(len(proximal), len(distal)) < 3:
        raise AssertionError("Too few vertices for bone endpoint slices")
    return (sum(proximal, Vector()) / len(proximal),
            sum(distal, Vector()) / len(distal),
            len(proximal), len(distal))


bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
frames = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"]
if len(frames) != 101:
    raise AssertionError("Expected 101 shoulder and arm frames")
scene.frame_set(1)
existing = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
imported = set(bpy.data.objects) - existing
source_by_name = {obj.name: obj for obj in imported}
atlas_endpoints = {}
for atlas_name, *_ in SPECS:
    source = source_by_name[atlas_name]
    points = [source.matrix_world @ vertex.co for vertex in source.data.vertices]
    atlas_endpoints[atlas_name] = endpoint_centroids(points)
forearm_proximal = (atlas_endpoints["Radius.r"][0] +
                    atlas_endpoints["Ulna.r"][0]) / 2
forearm_distal = (atlas_endpoints["Radius.r"][1] +
                  atlas_endpoints["Ulna.r"][1]) / 2
group = bpy.data.collections.new("06_Z_Anatomy_Right_Upper_Bones_Geometric_Fit")
scene.collection.children.link(group)
material = bpy.data.materials.new("解剖骨网格 · 几何配准待审")
material.diffuse_color = (0.98, 0.63, 0.25, 1)
material.use_nodes = True
shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
shader.inputs["Base Color"].default_value = (0.98, 0.63, 0.25, 1)

registered = []
for atlas_name, body, proximal_joint, distal_joint in SPECS:
    source = source_by_name[atlas_name]
    proximal, distal, proximal_count, distal_count = atlas_endpoints[atlas_name]
    fit_proximal, fit_distal = ((proximal, distal) if body == "humerus" else
                               (forearm_proximal, forearm_distal))
    source_axis = fit_distal - fit_proximal
    target_proximal = to_blender(frames[0]["viewerJointsM"][proximal_joint])
    target_distal = to_blender(frames[0]["viewerJointsM"][distal_joint])
    target_axis = target_distal - target_proximal
    scale = target_axis.length / source_axis.length
    rotation = source_axis.rotation_difference(target_axis)
    registration = (Matrix.Translation(target_proximal) @
                    rotation.to_matrix().to_4x4() @
                    Matrix.Scale(scale, 4) @ Matrix.Translation(-fit_proximal))
    obj = bpy.data.objects.new(f"atlas_{atlas_name}_tsm_fit", source.data.copy())
    group.objects.link(obj)
    obj.matrix_world = registration @ source.matrix_world
    obj.rotation_mode = "QUATERNION"
    obj.data.materials.clear()
    obj.data.materials.append(material)
    obj["atlas_source"] = atlas_name
    obj["tsm_body"] = body
    obj["registration_status"] = "5_percent_end_slice_centroids_shared_forearm_fit"
    obj["not_force_or_anatomical_attachment"] = True
    obj["atlas_proximal_local"] = tuple(source.matrix_world.inverted() @ proximal)
    obj["atlas_distal_local"] = tuple(source.matrix_world.inverted() @ distal)
    registered.append((obj, body, proximal_joint, distal_joint,
                       proximal, distal, proximal_count, distal_count,
                       scale, registration, obj.matrix_world.copy()))
for obj in imported:
    bpy.data.objects.remove(obj, do_unlink=True)

initial_body = {body: body_matrix(frames[0]["blenderBodyFrames"][body])
                for _, body, *_ in registered}
errors = {obj.name: {"proximal": [], "distal": []} for obj, *_ in registered}
for number, frame in enumerate(frames, start=1):
    scene.frame_set(number)
    for (obj, body, proximal_joint, distal_joint, proximal, distal,
         _proximal_count, _distal_count, _scale, registration, initial_world) in registered:
        motion = body_matrix(frame["blenderBodyFrames"][body]) @ initial_body[body].inverted()
        obj.matrix_world = motion @ initial_world
        for key in ("location", "rotation_quaternion", "scale"):
            obj.keyframe_insert(data_path=key, frame=number)
        for label, atlas_point, joint_name in (("proximal", proximal, proximal_joint),
                                                ("distal", distal, distal_joint)):
            predicted = motion @ (registration @ atlas_point)
            expected = to_blender(frame["viewerJointsM"][joint_name])
            errors[obj.name][label].append((predicted - expected).length)

report = {
    "status": "research_only_geometric_upper_bone_registration_not_anatomical_fit_or_force",
    "exercise": EXERCISE,
    "frameCount": len(frames),
    "model": "TSM_subject_noWeight.osim",
    "atlas": "Z-Anatomy CC BY-SA 4.0",
    "method": "fit humerus top/bottom 5% vertex-slice centroids to shoulder/elbow; fit the shared mean of radius and ulna slice centroids to elbow/hand to preserve their separation; use uniform scale and shortest-arc rotation, then follow each OpenSim body rigid motion",
    "bones": [],
    "limitations": [
        "mesh end-slice centroids are geometric proxies, not verified joint surfaces or attachment landmarks",
        "rotation about each bone long axis is undetermined by two endpoints",
        "synthetic single-arm bench/press paths are not measured exercises",
        "muscle meshes, tendon wrapping, individual bone proportions and forces are absent",
    ],
}
for obj, body, proximal_joint, distal_joint, proximal, distal, proximal_count, distal_count, scale, registration, _initial_world in registered:
    maximum_residual = {label: max(values) for label, values in errors[obj.name].items()}
    if max(maximum_residual.values()) > 0.03:
        raise AssertionError(f"Joint proxy residual exceeds 3 cm: {obj.name} {maximum_residual}")
    report["bones"].append({
        "object": obj.name,
        "atlasSource": obj["atlas_source"],
        "modelBody": body,
        "proximalJoint": proximal_joint,
        "distalJoint": distal_joint,
        "sourceSliceVertexCounts": {"proximal": proximal_count, "distal": distal_count},
        "sourceCentroidDistanceM": round((distal - proximal).length, 6),
        "uniformScale": round(scale, 6),
        "atlasToModelBlenderRows": [[round(registration[row][col], 10)
                                     for col in range(4)] for row in range(4)],
        "maximumJointProxyResidualM": {
            label: round(value, 6) for label, value in maximum_residual.items()},
    })
scene["upper_bone_registration_status"] = report["status"]
scene.frame_set(51)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("TSM_UPPER_BONE_REGISTRATION", EXERCISE,
      [(bone["object"], bone["uniformScale"], bone["maximumJointProxyResidualM"])
       for bone in report["bones"]])
