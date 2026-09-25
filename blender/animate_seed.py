"""Add three scrubbable illustrative exercise clips to the Blender seed scene.

Run after `npm run build:blender-poses` and `blender/bootstrap_scene.py`:
  blender --background assets/blender/muscle_atlas_seed.blend --python blender/animate_seed.py
The resulting file is an authoring preview, not an anatomical simulation.
"""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def argument(name, default):
    return Path(arguments[arguments.index(name) + 1]).resolve() if name in arguments else default

POSES = argument("--input", ROOT / "assets" / "blender" / "animation_poses.json")
OUTPUT = argument("--output", ROOT / "assets" / "blender" / "muscle_atlas_motion.blend")
PREVIEW = argument("--preview", ROOT / "assets" / "blender" / "motion_preview.png")
source = json.loads(POSES.read_text(encoding="utf-8"))
frames = source["frames"]
assert len(frames) == 153 and frames[0]["frame"] == 1 and frames[-1]["frame"] == 171

scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 171
scene.render.fps = 25
protocol = json.loads((ROOT / "src/data/demo_motion_protocol.json").read_text(encoding="utf-8"))
assert protocol["samplesPerExercise"] == 51
scene.render.fps_base = scene.render.fps * source.get("cycleDurationS", protocol["cycleDurationS"]) / (protocol["samplesPerExercise"] - 1)
scene.unit_settings.system = "METRIC"
scene.timeline_markers.clear()
for name, number in (("深蹲 squat", 1), ("卧推 bench", 61), ("实力举 press", 121)):
    scene.timeline_markers.new(name, frame=number)

armature = bpy.data.objects.get("MuscleAtlasSkeleton")
if armature:
    armature.hide_set(True)
mobile_collection = bpy.data.collections.get("04_Mobile_Mesh_Kit")
if mobile_collection:
    mobile_collection.hide_viewport = True
    mobile_collection.hide_render = True

animated = bpy.data.collections.new("05_Animated_Bone_Segments")
scene.collection.children.link(animated)


def shaded(material: bpy.types.Material, rgba: tuple) -> None:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    shader = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if shader is None:
        shader = nodes.new("ShaderNodeBsdfPrincipled")
        output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
        if output is None:
            output = nodes.new("ShaderNodeOutputMaterial")
        material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Base Color"].default_value = rgba
    shader.inputs["Roughness"].default_value = 0.65


bone_material = bpy.data.materials.new("IllustrativeBone")
bone_material.diffuse_color = (0.82, 0.92, 0.94, 1)
shaded(bone_material, bone_material.diffuse_color)
connections = [
    ("pelvis", "chest"), ("chest", "neck"), ("neck", "head"),
    ("chest", "shoulder_l"), ("chest", "shoulder_r"),
    ("shoulder_l", "elbow_l"), ("shoulder_r", "elbow_r"),
    ("elbow_l", "wrist_l"), ("elbow_r", "wrist_r"),
    ("pelvis", "hip_l"), ("pelvis", "hip_r"),
    ("hip_l", "knee_l"), ("hip_r", "knee_r"),
    ("knee_l", "ankle_l"), ("knee_r", "ankle_r"),
]
bone_objects = {}
for start, end in connections:
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=1, depth=2)
    obj = bpy.context.object
    obj.name = f"animated_bone_{start}__{end}"
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    animated.objects.link(obj)
    obj.data.materials.append(bone_material)
    obj.rotation_mode = "QUATERNION"
    obj["status"] = "illustrative_segment_animation"
    bone_objects[(start, end)] = obj

muscles = [obj for obj in bpy.data.collections["02_Muscle_Paths_Illustrative"].objects
           if obj.type == "CURVE" and "origin_landmark" in obj]
assert len(muscles) == 23 and len(frames[0]["muscles"]) == 23
def muscle_category(name):
    if name.startswith(("pectoralis",)):
        return "chest"
    if name.startswith(("trapezius", "latissimus", "erector")):
        return "back"
    if name.startswith(("deltoid", "biceps", "triceps")):
        return "upperArm"
    if name.startswith(("quadriceps", "hamstrings")):
        return "thigh"
    if name.startswith("calf"):
        return "calf"
    return "waist"

for obj in muscles:
    obj.data.bevel_depth = source["radii"][muscle_category(obj.name)]
    obj["profile_category"] = muscle_category(obj.name)
    material = obj.data.materials[0].copy()
    material.name = f"LengthState_{obj.name}"
    obj.data.materials.clear()
    obj.data.materials.append(material)
    shaded(material, (0.69, 0.51, 0.55, 1))
    point_count = len(frames[0]["muscles"][obj.name]["points"])
    assert point_count in (2, 3)
    # Give both two- and three-landmark paths a tapered muscle-belly glyph.
    # A two-landmark path gets an interpolated middle point, preserving its route.
    obj.data.splines[0].points.add(1)
    for point, radius_fraction in zip(obj.data.splines[0].points, (0.22, 1.0, 0.22)):
        point.radius = radius_fraction
    obj["length_ratio"] = 1.0
    obj["belly_radius_scale"] = 1.0
    obj["length_color_meaning"] = "cyan=longer purple=shorter pink=near_start; never force"

# The phone and Blender use the same exported outer radii. These translucent
# surfaces constrain illustrative contours, not underlying muscle volumes.
outer = source["outer"]
profile_shells = bpy.data.collections.new("06_Profile_Outer_Contours")
scene.collection.children.link(profile_shells)
shell_material = bpy.data.materials.new("ProfileContour")
shell_material.diffuse_color = (0.24, 0.70, 0.73, 0.24)
shaded(shell_material, (0.24, 0.70, 0.73, 1))
shader = next(node for node in shell_material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
shader.inputs["Alpha"].default_value = 0.22
shader.inputs["Roughness"].default_value = 0.65
shell_material.surface_render_method = "DITHERED"
shell_material.use_transparency_overlap = False

def move_to_profile_collection(obj):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    profile_shells.objects.link(obj)
    obj.data.materials.append(shell_material)
    obj["status"] = "illustrative_outer_contour"

ring_positions = [0, 0.18, 0.45, 0.72, 0.94, 1.04]
stature_scale = source["profile"]["heightCm"] / 175
base_chest_width = max(0.225 * stature_scale, outer["waistHalfWidthM"] * 1.16)
base_chest_depth = max(0.165 * stature_scale, outer["waistHalfDepthM"] * 1.14)
width = [max(0.18 * source["profile"]["heightCm"] / 175, outer["waistHalfWidthM"] * 1.12),
         max(0.155 * source["profile"]["heightCm"] / 175, outer["waistHalfWidthM"] * 1.03),
         outer["waistHalfWidthM"],
         max(0.18 * source["profile"]["heightCm"] / 175, outer["waistHalfWidthM"] * 1.12),
         outer["chestHalfWidthM"],
         max(0.195 * stature_scale, outer["waistHalfWidthM"] * 1.08) * outer["chestHalfWidthM"] / base_chest_width]
depth = [max(0.13 * source["profile"]["heightCm"] / 175, outer["waistHalfDepthM"] * 1.08),
         max(0.12 * source["profile"]["heightCm"] / 175, outer["waistHalfDepthM"] * 1.03),
         outer["waistHalfDepthM"],
         max(0.145 * source["profile"]["heightCm"] / 175, outer["waistHalfDepthM"] * 1.09),
         outer["chestHalfDepthM"],
         max(0.135 * stature_scale, outer["waistHalfDepthM"] * 1.04) * outer["chestHalfDepthM"] / base_chest_depth]
sides = 32
vertices = [(width[r] * math.cos(2 * math.pi * s / sides),
             depth[r] * math.sin(2 * math.pi * s / sides), ring_positions[r])
            for r in range(6) for s in range(sides)]
faces = [(r*sides+s, r*sides+(s+1)%sides,
          (r+1)*sides+(s+1)%sides, (r+1)*sides+s)
         for r in range(5) for s in range(sides)]
mesh = bpy.data.meshes.new("PersonalizedTorsoRings")
mesh.from_pydata(vertices, [], faces)
mesh.update()
torso = bpy.data.objects.new("profile_torso_contour", mesh)
profile_shells.objects.link(torso)
torso.data.materials.append(shell_material)
torso["status"] = "illustrative_outer_contour"
torso["waist_circumference_cm"] = outer["waistCircumferenceCm"]
torso["chest_circumference_cm"] = outer["chestCircumferenceCm"]

limb_shells = {}
for side in ("l", "r"):
    for start, end, category in (("shoulder", "elbow", "upperArm"),
                                 ("hip", "knee", "thigh"), ("knee", "ankle", "calf")):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=1)
        obj = bpy.context.object
        obj.name = f"profile_{category}_{side}_contour"
        move_to_profile_collection(obj)
        obj["measured_radius_m"] = outer[category + "RadiusM"]
        obj.rotation_mode = "QUATERNION"
        limb_shells[obj.name] = (obj, f"{start}_{side}", f"{end}_{side}", outer[category + "RadiusM"])
bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=0.10)
head = bpy.context.object
head.name = "animated_head"
for old in list(head.users_collection):
    old.objects.unlink(head)
animated.objects.link(head)
head.data.materials.append(bone_material)
head.parent = bpy.data.objects["landmark_head"]
head.location = (0, 0, 0)
barbell_collection = bpy.data.collections.new("07_Animated_Barbell_Scenario")
scene.collection.children.link(barbell_collection)
bar_material = bpy.data.materials.new("IllustrativeBarbell")
bar_material.diffuse_color = (0.91, 0.70, 0.44, 1)
shaded(bar_material, bar_material.diffuse_color)
plate_material = bpy.data.materials.new("IllustrativePlate")
plate_material.diffuse_color = (0.24, 0.33, 0.38, 1)
shaded(plate_material, plate_material.diffuse_color)

def move_to_barbell_collection(obj, material):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    barbell_collection.objects.link(obj)
    obj.data.materials.append(material)
    obj.rotation_euler[1] = math.pi / 2
    obj["load_kg"] = source["loadKg"]
    obj["squat_bar_offset_cm"] = source["squatBarOffsetCm"]
    obj["status"] = "illustrative_load_position_not_measured"

bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.018, depth=1.35)
barbell = bpy.context.object
barbell.name = "animated_barbell"
move_to_barbell_collection(barbell, bar_material)
barbell.hide_render = source["loadKg"] <= 0
barbell.hide_set(source["loadKg"] <= 0)
plates = []
each_side_kg = max(0, (source["loadKg"] - 20) / 2)
for sign, suffix in ((-1, "l"), (1, "r")):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.12, depth=1)
    plate = bpy.context.object
    plate.name = f"animated_plate_{suffix}"
    move_to_barbell_collection(plate, plate_material)
    plate.scale = (0.7 + 0.3 * min(each_side_kg / 20, 1),
                   0.7 + 0.3 * min(each_side_kg / 20, 1),
                   min(0.018 + each_side_kg * 0.0012, 0.11))
    plate.hide_render = each_side_kg <= 0
    plate.hide_set(each_side_kg <= 0)
    plates.append((plate, sign))

for item in frames:
    frame = item["frame"]
    joints = {key: Vector(value) for key, value in item["joints"].items()}
    barbell.location = Vector(item["barCenter"])
    barbell.keyframe_insert(data_path="location", frame=frame)
    for plate, sign in plates:
        plate.location = barbell.location + Vector((sign * 0.52, 0, 0))
        plate.keyframe_insert(data_path="location", frame=frame)
    torso.location = joints["pelvis"]
    torso.scale = (1, 1, (joints["chest"] - joints["pelvis"]).length)
    torso.keyframe_insert(data_path="location", frame=frame)
    torso.keyframe_insert(data_path="scale", frame=frame)
    for obj, start, end, radius in limb_shells.values():
        direction = joints[end] - joints[start]
        obj.location = (joints[start] + joints[end]) / 2
        obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
        obj.scale = (radius, radius, direction.length / 2)
        for data_path in ("location", "rotation_quaternion", "scale"):
            obj.keyframe_insert(data_path=data_path, frame=frame)
    for name, position in joints.items():
        marker = bpy.data.objects.get(f"landmark_{name}")
        if marker:
            marker.location = position
            marker.keyframe_insert(data_path="location", frame=frame)
    for (start, end), obj in bone_objects.items():
        a, b = joints[start], joints[end]
        direction = b - a
        obj.location = (a + b) / 2
        obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
        obj.scale = (0.025, 0.025, direction.length / 2)
        obj.keyframe_insert(data_path="location", frame=frame)
        obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        obj.keyframe_insert(data_path="scale", frame=frame)
    for obj in muscles:
        measurement = item["muscles"][obj.name]
        points = obj.data.splines[0].points
        source_points = [Vector(location) for location in measurement["points"]]
        curve_points = ([source_points[0], (source_points[0] + source_points[1]) / 2,
                         source_points[1]] if len(source_points) == 2 else source_points)
        assert len(points) == len(curve_points) == 3
        for point, location in zip(points, curve_points):
            point.co = (*location, 1)
            point.keyframe_insert(data_path="co", frame=frame)
        ratio = measurement["ratio"]
        obj["length_ratio"] = float(ratio)
        obj.keyframe_insert(data_path='["length_ratio"]', frame=frame)
        obj["belly_radius_scale"] = float(measurement["bellyRadiusScale"])
        obj.keyframe_insert(data_path='["belly_radius_scale"]', frame=frame)
        obj.data.bevel_depth = source["radii"][muscle_category(obj.name)] * measurement["bellyRadiusScale"]
        obj.data.keyframe_insert(data_path="bevel_depth", frame=frame)
        color = ((0.26, 0.73, 0.86, 1) if ratio > 1.025 else
                 (0.78, 0.54, 0.85, 1) if ratio < 0.975 else
                 (0.69, 0.51, 0.55, 1))
        material = obj.data.materials[0]
        material.diffuse_color = color
        material.keyframe_insert(data_path="diffuse_color", frame=frame)
        shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        shader.inputs["Base Color"].default_value = color
        shader.inputs["Base Color"].keyframe_insert(data_path="default_value", frame=frame)

scene.frame_set(1)
scene["animation_source"] = str(POSES)
scene["profile_json"] = json.dumps(source["profile"], ensure_ascii=False)
scene["model_status"] = "personalized_illustrative_geometry_no_force_validation"
scene["length_legend"] = "cyan=longer purple=shorter pink=near starting length; no muscle force shown"
camera_data = bpy.data.cameras.new("PreviewCamera")
camera = bpy.data.objects.new("PreviewCamera", camera_data)
scene.collection.objects.link(camera)
camera.location = (2.2, -3.8, 2.1)
camera.rotation_euler = (Vector((0, 0, 0.95)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera_data.type = "ORTHO"
camera_data.ortho_scale = 2.3
scene.camera = camera
light_data = bpy.data.lights.new("PreviewKey", type="AREA")
light = bpy.data.objects.new("PreviewKey", light_data)
scene.collection.objects.link(light)
light.location = (1.5, -2.5, 4.0)
light_data.energy = 900
light_data.shape = "DISK"
light_data.size = 4
scene.render.resolution_x = 900
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.frame_set(1)
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print(f"SAVED_MOTION {OUTPUT} frames={len(frames)} bones={len(bone_objects)} muscles={len(muscles)} shell={len(limb_shells)+1}")
