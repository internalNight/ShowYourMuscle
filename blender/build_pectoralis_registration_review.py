"""Make an editable press-pose atlas/TSM chest registration review scene.

Pink atlas surfaces and cyan model paths remain separate. The scene is a
geometric diagnostic, not a validated muscle attachment or force model.
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data/press_tsm_reference.json"
REPORT = ROOT / "docs/data/tsm_pectoralis_landmark_fit_screen.json"
THREE_POINT = "medial_clavicle_end_proxy"
FOUR_POINT = "medial_clavicle_plus_pectoral_origin_proxy"
PAIRS = {
    "Clavicular head of pectoralis major muscle.r": "PectoralisMajorClavicle_S",
    "Sternocostal head of pectoralis major muscle.r": "PectoralisMajorThorax_M",
    "(Abdominal part of pectoralis major muscle).r": "PectoralisMajorThorax_I",
}
BONES = {"Clavicle.r", "Humerus.r", "Manubrium of sternum", "Body of sternum"}


def material(name, color, emission=False):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    shader = tree.nodes.new("ShaderNodeEmission" if emission else "ShaderNodeBsdfPrincipled")
    if emission:
        shader.inputs["Color"].default_value = (*color, 1)
        shader.inputs["Strength"].default_value = 1.5
        tree.links.new(shader.outputs["Emission"], output.inputs["Surface"])
    else:
        shader.inputs["Base Color"].default_value = (*color, 1)
        shader.inputs["Roughness"].default_value = .68
        tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return mat


def to_blender(point):
    x, y, z = point
    return Vector((x, -z, y))


def marker(name, point, mat, radius):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=radius,
                                         location=point)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def path_curve(name, points, mat):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = .0035
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for item, point in zip(spline.points, points):
        item.co = (*point, 1)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    curve.materials.append(mat)
    return obj


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=(THREE_POINT, FOUR_POINT), default=FOUR_POINT)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    stem = "pectoralis_registration_review_press"
    if args.method == FOUR_POINT:
        stem += "_4point"
    output = ROOT / "assets/blender" / f"{stem}.blend"
    preview = ROOT / "assets/blender" / f"{stem}.png"
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    record = next(item for item in report["records"]
                  if item["method"] == args.method and
                  item["exercise"] == "press")
    frame = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"][0]
    fit = Matrix(record["atlasToModelBlenderRows"])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(ATLAS))
    keep = set(PAIRS) | BONES
    for obj in list(bpy.data.objects):
        if obj.name not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)
    if {obj.name for obj in bpy.data.objects if obj.type == "MESH"} != keep:
        raise ValueError("Missing an expected atlas chest mesh or bone")

    bone_mat = material("Bone · proxy registration", (.78, .84, .85))
    pinks = ((.82, .43, .53), (.93, .55, .60), (.74, .35, .52))
    cyan = material("TSM muscle path · not force", (.07, .94, .95), emission=True)
    origin_mat = material("TSM path origin", (.99, .77, .16), emission=True)
    end_mat = material("TSM path end", (.35, .97, .44), emission=True)
    joint_mat = material("TSM joint center proxy", (.96, .96, .96), emission=True)

    for index, (atlas_name, model_name) in enumerate(PAIRS.items()):
        obj = bpy.data.objects[atlas_name]
        obj.matrix_world = fit @ obj.matrix_world
        obj.data = obj.data.copy()
        obj.data.materials.clear()
        obj.data.materials.append(material(f"Atlas {model_name} · unvalidated", pinks[index]))
        obj["source"] = "Z-Anatomy atlas mesh, proxy landmark fit"
        obj["status"] = "path-to-surface distance is not attachment or force validation"
        row = next(item for item in record["muscles"] if item["modelMuscle"] == model_name)
        obj["maximum_path_surface_distance_cm"] = round(
            100 * row["maximumUnsignedDistanceM"], 2)
        path = [to_blender(point) for point in frame["muscles"][model_name]["viewerPathM"]]
        path_curve(f"TSM_{model_name}_path_not_force", path, cyan)
        marker(f"TSM_{model_name}_origin", path[0], origin_mat, .006)
        marker(f"TSM_{model_name}_end", path[-1], end_mat, .006)

    for name in BONES:
        obj = bpy.data.objects[name]
        obj.matrix_world = fit @ obj.matrix_world
        obj.data = obj.data.copy()
        obj.data.materials.clear()
        obj.data.materials.append(bone_mat)
    for name in ("thorax", "clavicle", "shoulder"):
        marker(f"TSM_{name}_joint_proxy", to_blender(frame["viewerJointsM"][name]),
               joint_mat, .0045)

    scene = bpy.context.scene
    scene["status"] = "unvalidated atlas/TSM chest registration review"
    scene["method"] = record["method"]
    scene["source_report"] = str(REPORT.relative_to(ROOT)).replace("\\", "/")
    world = bpy.data.worlds.new("Dark chest review")
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs[0].default_value = (.012, .023, .039, 1)
    world.node_tree.nodes.get("Background").inputs[1].default_value = .7
    scene.world = world
    target = Vector((.20, -.035, 1.42))
    bpy.ops.object.camera_add(location=(.68, -1.35, 1.63))
    camera = bpy.context.object
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = .58
    scene.camera = camera
    for location, energy, size in (((-.40, -.80, 2.10), 550, 1.5),
                                   ((.85, .35, 1.65), 430, 1.2)):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(preview)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    bpy.ops.render.render(write_still=True)
    print("PECTORALIS_REVIEW", output, preview)


if __name__ == "__main__":
    main()
