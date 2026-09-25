"""Build an editable Blender 5.1 size-preview from the shipped Z-Anatomy GLB.

Usage: blender -b --factory-startup --python blender/build_reference_profile_scene.py
       -- --height-cm 190 --upper-arm-cm 40 --thigh-cm 66 --calf-cm 44
The source and this derivative require Z-Anatomy/BodyParts3D attribution under
CC BY-SA 4.0; see public/models/NOTICE-z-anatomy.txt. Widths are visual only.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "public/models/z_anatomy_reference.glb"
ARM = {"Long head of biceps brachii", "Short head of biceps brachii",
       "Lateral head of triceps brachii", "Long head of triceps brachii",
       "Medial head of triceps brachii", "Brachialis muscle"}
CHEST = {"(Abdominal part of pectoralis major muscle)",
         "Clavicular head of pectoralis major muscle",
         "Sternocostal head of pectoralis major muscle"}
WAIST = {"External abdominal oblique muscle", "Rectus abdominis muscle"}
THIGH = {"Rectus femoris muscle", "Vastus intermedius muscle",
         "Vastus lateralis muscle", "Vastus medialis muscle",
         "Long head of biceps femoris", "Short head of biceps femoris",
         "Semimembranosus muscle", "Semitendinosus muscle"}
CALF = {"Lateral head of gastrocnemius", "Medial head of gastrocnemius",
        "Soleus muscle", "Tibialis anterior muscle"}


def group_of(name):
    base = name.replace("_", " ")
    if base.endswith((".l", ".r")):
        base = base[:-2]
    if base in ARM:
        return "arm"
    if base in CHEST:
        return "chest"
    if base in WAIST:
        return "waist"
    if base in THIGH:
        return "thigh"
    if base in CALF:
        return "calf"
    return None


def thickness(mesh, scale):
    points = [vertex.co.copy() for vertex in mesh.vertices]
    center = sum(points, Vector()) / len(points)
    low = [min(point[i] for point in points) for i in range(3)]
    high = [max(point[i] for point in points) for i in range(3)]
    axis = Vector((0, 0, 0))
    axis[max(range(3), key=lambda i: high[i] - low[i])] = 1
    covariance = Matrix(((0.0, 0.0, 0.0),) * 3)
    for point in points:
        d = point - center
        for i in range(3):
            for j in range(3):
                covariance[i][j] += d[i] * d[j]
    for _ in range(16):
        axis = (covariance @ axis).normalized()
    projections = [(point - center).dot(axis) for point in points]
    first, last = min(projections), max(projections)
    if last - first < .01:
        raise ValueError("Muscle has no valid long axis")
    maximum_displacement = 0.0
    end_displacement = 0.0
    for vertex, point, axial in zip(mesh.vertices, points, projections):
        fraction = min(1, max(0, (axial - first) / (last - first)))
        gain = (scale - 1) * math.sin(math.pi * fraction) ** 2
        radial = point - center - axis * axial
        vertex.co = point + radial * gain
        moved = (vertex.co - point).length
        maximum_displacement = max(maximum_displacement, moved)
        if fraction < .001 or fraction > .999:
            end_displacement = max(end_displacement, moved)
    mesh.update()
    return maximum_displacement, end_displacement


def clamp(value, low, high):
    return min(high, max(low, value))


def ellipse_perimeter(a, b):
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


def trunk_width_ratios(height_cm, weight_kg, body_fat_pct, waist_cm, chest_cm):
    # Same visual fallback and cross-section rule as profileOuterDimensions in
    # src/model.ts. Circumference still cannot identify individual muscle mass.
    stature = height_cm / 175
    fat = clamp(body_fat_pct, 3, 65)
    mass_prior = clamp((weight_kg / (72 * stature ** 3)) ** (1 / 3), .76, 1.35)
    soft_tissue_prior = clamp(1 + (fat - 20) * .004, .82, 1.18)
    default_waist_cm = 82 * stature * mass_prior * soft_tissue_prior
    effective_waist_cm = waist_cm if waist_cm is not None else default_waist_cm
    waist_aspect = 1.25
    waist_half_depth_m = (effective_waist_cm / 100) / ellipse_perimeter(waist_aspect, 1)
    waist_half_width_m = waist_half_depth_m * waist_aspect
    chest_half_width_m = max(.225 * stature, waist_half_width_m * 1.16)
    chest_half_depth_m = max(.165 * stature, waist_half_depth_m * 1.14)
    default_chest_cm = 100 * ellipse_perimeter(chest_half_width_m, chest_half_depth_m)
    return {
        "chest": clamp((chest_cm if chest_cm is not None else default_chest_cm) /
                       default_chest_cm, .8, 1.2),
        "waist": clamp(effective_waist_cm / default_waist_cm, .8, 1.2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--height-cm", type=float, default=190)
    parser.add_argument("--weight-kg", type=float, default=72)
    parser.add_argument("--body-fat-pct", type=float, default=20)
    parser.add_argument("--chest-cm", type=float)
    parser.add_argument("--waist-cm", type=float)
    parser.add_argument("--upper-arm-cm", type=float, default=40)
    parser.add_argument("--thigh-cm", type=float, default=66)
    parser.add_argument("--calf-cm", type=float, default=44)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if not (120 <= args.height_cm <= 220 and 30 <= args.weight_kg <= 250 and
            3 <= args.body_fat_pct <= 65 and
            (args.chest_cm is None or 55 <= args.chest_cm <= 180) and
            (args.waist_cm is None or 45 <= args.waist_cm <= 180) and
            15 <= args.upper_arm_cm <= 70 and 25 <= args.thigh_cm <= 110 and
            15 <= args.calf_cm <= 75):
        raise ValueError("Body parameters outside mobile-app input ranges")
    token = lambda value: f"{value:g}".replace(".", "p")
    stem = "z_anatomy_profile_" + "_".join(token(value) for value in
        (args.height_cm, args.upper_arm_cm, args.thigh_cm, args.calf_cm))
    if args.chest_cm is not None or args.waist_cm is not None:
        stem += f"_chest{token(args.chest_cm) if args.chest_cm is not None else 'default'}"
        stem += f"_waist{token(args.waist_cm) if args.waist_cm is not None else 'default'}"
    blend = ROOT / "assets/blender" / f"{stem}.blend"
    preview = ROOT / "assets/blender" / f"{stem}.png"
    report_path = ROOT / "docs/data" / f"{stem}.json"

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(SOURCE))
    objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if len(objects) != 165:
        raise ValueError(f"Expected 165 named reference meshes, found {len(objects)}")
    stature = args.height_cm / 175
    ratios = {
        "arm": min(1.2, max(.8, args.upper_arm_cm / (32 * stature))),
        "thigh": min(1.2, max(.8, args.thigh_cm / (54 * stature))),
        "calf": min(1.2, max(.8, args.calf_cm / (36 * stature))),
    }
    ratios.update(trunk_width_ratios(args.height_cm, args.weight_kg,
                                     args.body_fat_pct, args.waist_cm, args.chest_cm))
    material_bone = bpy.data.materials.new("Bone · reference")
    material_bone.diffuse_color = (.79, .86, .86, 1)
    material_bone.use_nodes = True
    material_bone.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = material_bone.diffuse_color
    material_muscle = bpy.data.materials.new("Muscle · visual width only")
    material_muscle.diffuse_color = (.68, .36, .45, 1)
    material_muscle.use_nodes = True
    material_muscle.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = material_muscle.diffuse_color
    counts = {key: 0 for key in ratios}
    maximum_displacement = {key: 0.0 for key in ratios}
    end_displacement = 0.0
    for obj in objects:
        group = group_of(obj.name)
        obj.data = obj.data.copy()
        if group:
            counts[group] += 1
            maximum, end = thickness(obj.data, ratios[group])
            maximum_displacement[group] = max(maximum_displacement[group], maximum)
            end_displacement = max(end_displacement, end)
        obj.data.materials.clear()
        obj.data.materials.append(material_muscle if "muscle" in obj.name.lower() or group else material_bone)
    if counts != {"arm": 12, "chest": 6, "waist": 4, "thigh": 16, "calf": 8}:
        raise ValueError(f"Unexpected girth mesh counts: {counts}")
    bounds = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    floor = min(point.z for point in bounds)
    resize = Matrix.Translation((0, 0, floor)) @ Matrix.Diagonal((stature, stature, stature, 1)) @ Matrix.Translation((0, 0, -floor))
    for obj in objects:
        obj.matrix_world = resize @ obj.matrix_world

    # Render and save the editable Blender scene for visual review.
    world = bpy.data.worlds.new("Dark anatomical review")
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs[0].default_value = (.012, .025, .043, 1)
    world.node_tree.nodes.get("Background").inputs[1].default_value = .7
    bpy.context.scene.world = world
    bpy.ops.object.camera_add(location=(2.2, -3.9, 1.55))
    camera = bpy.context.object
    target = Vector((0, 0, .85 * stature))
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 2.2 * stature
    bpy.context.scene.camera = camera
    for location, energy, size in (((-1.6, -2.3, 3), 900, 3), ((1.8, 1.2, 2.4), 650, 2)):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.rotation_euler = (target - light.location).to_track_quat('-Z', 'Y').to_euler()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(preview)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.render.render(write_still=True)

    report = {
        "status": "static_visual_profile_not_anatomical_personalization_or_muscle_force",
        "source": "public/models/z_anatomy_reference.glb",
        "attribution": "public/models/NOTICE-z-anatomy.txt",
        "profile": {"heightCm": args.height_cm, "weightKg": args.weight_kg,
                    "bodyFatPct": args.body_fat_pct, "chestCm": args.chest_cm,
                    "upperArmCm": args.upper_arm_cm, "waistCm": args.waist_cm,
                    "thighCm": args.thigh_cm, "calfCm": args.calf_cm},
        "statureScale": stature, "girthWidthScales": ratios, "changedMeshCounts": counts,
        "totalReferenceMeshes": len(objects),
        "maximumLocalVertexDisplacementM": maximum_displacement,
        "maximumEndpointDisplacementM": end_displacement,
        "blend": str(blend.relative_to(ROOT)).replace("\\", "/"),
        "preview": str(preview.relative_to(ROOT)).replace("\\", "/"),
        "limits": "Generic atlas geometry; fixed muscle identity and attachment topology; width-only visual change, no muscle volume or force calibration.",
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PROFILE_REFERENCE", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
