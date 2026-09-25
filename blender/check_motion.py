"""Check that the saved Blender action preview follows exported pose samples."""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
source_path = Path(arguments[arguments.index("--input") + 1]).resolve() if "--input" in arguments else ROOT / "assets/blender/animation_poses.json"
source = json.loads(source_path.read_text(encoding="utf-8"))
protocol = json.loads((ROOT / "src/data/demo_motion_protocol.json").read_text(encoding="utf-8"))
effective_fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
expected_fps = (protocol["samplesPerExercise"] - 1) / source.get("cycleDurationS", protocol["cycleDurationS"])
if abs(effective_fps - expected_fps) > 1e-5:
    raise AssertionError(f"Blender and phone playback tempo differ: {effective_fps} vs {expected_fps}")
samples = {item["frame"]: item for item in source["frames"]
                      if item["frame"] in (1, 26, 51, 61, 86, 111, 121, 129, 146, 171)}
for number, item in samples.items():
    bpy.context.scene.frame_set(number)
    joints = {name: Vector(value) for name, value in item["joints"].items()}
    barbell = bpy.data.objects["animated_barbell"]
    if (barbell.location - Vector(item["barCenter"])).length > 1e-5:
        raise AssertionError(f"Frame {number} barbell differs from exported load position")
    if abs(barbell["load_kg"] - source["loadKg"]) > 1e-5 or \
       abs(barbell["squat_bar_offset_cm"] - source["squatBarOffsetCm"]) > 1e-5:
        raise AssertionError("Barbell scenario metadata differs")
    for suffix, sign in (("l", -1), ("r", 1)):
        plate = bpy.data.objects[f"animated_plate_{suffix}"]
        if (plate.location - barbell.location - Vector((sign * 0.52, 0, 0))).length > 1e-5:
            raise AssertionError(f"Frame {number} {suffix} plate differs from barbell")
    for name, expected in joints.items():
        marker = bpy.data.objects[f"landmark_{name}"]
        if (marker.location - expected).length > 1e-5:
            raise AssertionError(f"Frame {number} landmark {name} differs from exported pose")
    assert len(item["muscles"]) == 23
    for name, measurement in item["muscles"].items():
        obj = bpy.data.objects[name]
        points = obj.data.splines[0].points
        source_points = [Vector(location) for location in measurement["points"]]
        expected_points = ([source_points[0], (source_points[0] + source_points[1]) / 2,
                            source_points[1]] if len(source_points) == 2 else source_points)
        if len(points) != len(expected_points) or len(points) != 3:
            raise AssertionError(f"Frame {number} muscle {name} path length differs")
        for index, expected in enumerate(expected_points):
            if (Vector(points[index].co[:3]) - expected).length > 1e-5:
                raise AssertionError(f"Frame {number} muscle {name} path point {index} differs")
        if abs(obj["length_ratio"] - measurement["ratio"]) > 1e-5:
            raise AssertionError(f"Frame {number} muscle {name} length ratio differs: {obj['length_ratio']} vs {measurement['ratio']}")
        if abs(obj["belly_radius_scale"] - measurement["bellyRadiusScale"]) > 1e-5:
            raise AssertionError(f"Frame {number} muscle {name} belly scale differs")
        if max(abs(points[index].radius - radius) for index, radius in
               enumerate((0.22, 1.0, 0.22))) > 1e-5:
            raise AssertionError(f"Frame {number} muscle {name} belly taper differs")
        expected_depth = source["radii"][measurement["category"]] * measurement["bellyRadiusScale"]
        if abs(obj.data.bevel_depth - expected_depth) > 1e-5:
            raise AssertionError(f"Frame {number} muscle {name} bevel depth differs")
        ratio = measurement["ratio"]
        color = ((0.26, 0.73, 0.86, 1) if ratio > 1.025 else
                 (0.78, 0.54, 0.85, 1) if ratio < 0.975 else
                 (0.69, 0.51, 0.55, 1))
        actual = obj.data.materials[0].diffuse_color
        if max(abs(actual[index] - color[index]) for index in range(4)) > 1e-5:
            raise AssertionError(f"Frame {number} muscle {name} length color differs")
        material = obj.data.materials[0]
        shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        rendered = shader.inputs["Base Color"].default_value
        if max(abs(rendered[index] - color[index]) for index in range(4)) > 1e-5:
            raise AssertionError(f"Frame {number} muscle {name} render color differs")
    for name in ("animated_bone_hip_r__knee_r", "animated_bone_shoulder_l__elbow_l"):
        obj = bpy.data.objects[name]
        _, link = name.removeprefix("animated_bone_").split("__")
        start = name.removeprefix("animated_bone_").split("__")[0]
        if (obj.location - (joints[start] + joints[link]) / 2).length > 1e-5:
            raise AssertionError(f"Frame {number} bone {name} position differs")
    torso = bpy.data.objects["profile_torso_contour"]
    if (torso.location - joints["pelvis"]).length > 1e-5:
        raise AssertionError(f"Frame {number} torso location differs")
    if abs(torso.scale.z - (joints["chest"] - joints["pelvis"]).length) > 1e-5:
        raise AssertionError(f"Frame {number} torso height differs")
    for category, start, end in (("upperArm", "shoulder_r", "elbow_r"),
                                 ("thigh", "hip_r", "knee_r"),
                                 ("calf", "knee_r", "ankle_r")):
        obj = bpy.data.objects[f"profile_{category}_r_contour"]
        expected_radius = source["outer"][category + "RadiusM"]
        if abs(obj.scale.x - expected_radius) > 1e-5 or abs(obj.scale.y - expected_radius) > 1e-5:
            raise AssertionError(f"Frame {number} {category} girth differs")
        if (obj.location - (joints[start] + joints[end]) / 2).length > 1e-5:
            raise AssertionError(f"Frame {number} {category} location differs")
for name, category in (("pectoralis_major_r", "chest"), ("latissimus_dorsi_r", "back"),
                       ("biceps_brachii_r", "upperArm"),
                       ("quadriceps_r", "thigh"), ("calf_r", "calf"),
                       ("rectus_abdominis", "waist")):
    if abs(bpy.data.objects[name].data.bevel_depth - source["radii"][category]) > 1e-6:
        raise AssertionError(f"Muscle radius differs: {name}")
if abs(bpy.data.objects["profile_torso_contour"]["waist_circumference_cm"] -
       source["outer"]["waistCircumferenceCm"]) > 1e-5:
    raise AssertionError("Waist circumference differs")
if abs(bpy.data.objects["profile_torso_contour"]["chest_circumference_cm"] -
       source["outer"]["chestCircumferenceCm"]) > 1e-5:
    raise AssertionError("Chest circumference differs")
torso_vertices = bpy.data.objects["profile_torso_contour"].data.vertices
chest_ring = [Vector(torso_vertices[4 * 32 + i].co) for i in range(32)]
chest_perimeter_cm = 100 * sum((chest_ring[(i + 1) % 32] - chest_ring[i]).length for i in range(32))
if abs(chest_perimeter_cm - source["outer"]["chestCircumferenceCm"]) > source["outer"]["chestCircumferenceCm"] * 0.002:
    raise AssertionError("Blender chest ring differs from input circumference")
profile = source["profile"]
for field, category in (("upperArmCm", "upperArm"), ("thighCm", "thigh"), ("calfCm", "calf")):
    if field in profile:
        measured_cm = 2 * math.pi * source["outer"][category + "RadiusM"] * 100
        if abs(measured_cm - profile[field]) > 1e-5:
            raise AssertionError(f"Input {field} not reflected in outer contour")
if "waistCm" in profile and abs(profile["waistCm"] - source["outer"]["waistCircumferenceCm"]) > 1e-5:
    raise AssertionError("Input waistCm not reflected in torso contour")
if "chestCm" in profile and abs(profile["chestCm"] - source["outer"]["chestCircumferenceCm"]) > 1e-5:
    raise AssertionError("Input chestCm not reflected in torso contour")
print(f"BLENDER_MOTION_OK {len(samples)} sampled frames")
