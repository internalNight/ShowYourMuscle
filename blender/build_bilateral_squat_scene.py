"""Blender 5.1 bilateral OpenSim squat path viewer, without muscle force color."""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/blender/ab01_bilateral_squat_kinematics.json"
OUTPUT = ROOT / "assets/blender/ab01_bilateral_squat_paths.blend"
PREVIEW = ROOT / "assets/blender/ab01_bilateral_squat_paths.png"
data = json.loads(SOURCE.read_text(encoding="utf-8"))
frames = data["frames"]
assert data["muscleCount"] == 54 and len(frames) == 21

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = len(frames)
scene.render.fps = 20
scene.timeline_markers.clear()
scene.timeline_markers.new("AB01 实验片段开始", frame=1)
scene.timeline_markers.new("AB01 右膝最深附近", frame=14)
scene.timeline_markers.new("实验片段结束", frame=21)
scene["source_file"] = str(SOURCE.relative_to(ROOT))
scene["source_subject"] = data["subject"]
scene["source_status"] = data["status"]
scene["bar_attachment"] = data["barAttachment"]
scene["barbell_mass_kg"] = data["barbellMassKg"]
scene["force_status"] = "not_calculated_or_displayed"
scene["max_path_error_m"] = data["maxMusclePolylineErrorM"]

ground_pelvis = frames[0]["jointsGroundM"]["ground_pelvis"]


def point(values):
    x, y, z = values
    return Vector((z - ground_pelvis[2], -(x - ground_pelvis[0]), y))


def collection(name):
    result = bpy.data.collections.new(name)
    scene.collection.children.link(result)
    return result


bone_group = collection("01_Bilateral_Bones")
muscle_group = collection("02_Bilateral_Muscle_Paths_54")
joint_group = collection("03_Joints")
bar_group = collection("04_Assumed_20kg_Barbell")


def material(name, color, metallic=0):
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    nodes = result.node_tree.nodes
    shader = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if shader is None:
        shader = nodes.new("ShaderNodeBsdfPrincipled")
        output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
        if output is None:
            output = nodes.new("ShaderNodeOutputMaterial")
        result.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = 0.43
    return result


bone_material = material("骨段 · 几何", (0.76, 0.83, 0.89))
joint_material = material("关节中心", (0.95, 0.70, 0.25))
right_material = material("右肌肉路径 · 无发力", (0.72, 0.45, 0.82))
left_material = material("左肌肉路径 · 无发力", (0.24, 0.76, 0.74))
axial_material = material("躯干肌肉路径 · 无发力", (0.9, 0.6, 0.32))
bar_material = material("假定固定杠铃 · 20 kg", (0.55, 0.64, 0.72), 0.65)


def put_in(obj, group):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    group.objects.link(obj)
    obj.rotation_mode = "QUATERNION"
    return obj


def cylinder(name, group, shade, radius):
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=1, depth=2)
    obj = put_in(bpy.context.object, group)
    obj.name = name
    obj.data.materials.append(shade)
    obj["radius_m"] = radius
    return obj


def place(obj, a, b, frame):
    direction = b - a
    if direction.length > 1e-8:
        obj.location = (a + b) / 2
        obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
        radius = obj["radius_m"]
        obj.scale = (radius, radius, direction.length / 2)
    else:
        obj.scale = (0, 0, 0)
    for prop in ("location", "rotation_quaternion", "scale"):
        obj.keyframe_insert(data_path=prop, frame=frame)


bone_links = (
    ("hip_r", "hip_l"), ("hip_r", "knee_r"), ("knee_r", "ankle_r"),
    ("ankle_r", "mtp_r"), ("hip_l", "knee_l"), ("knee_l", "ankle_l"),
    ("ankle_l", "mtp_l"), ("ground_pelvis", "back"),
    ("back", "barbell_to_torso"),
)
bones = {(a, b): cylinder(f"bone_{a}_{b}", bone_group, bone_material, 0.017)
         for a, b in bone_links}
joint_names = ("ground_pelvis", "hip_r", "knee_r", "ankle_r", "mtp_r",
               "hip_l", "knee_l", "ankle_l", "mtp_l", "back", "barbell_to_torso")
joints = {}
for name in joint_names:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.023)
    obj = put_in(bpy.context.object, joint_group)
    obj.name = f"joint_{name}"
    obj.data.materials.append(joint_material)
    joints[name] = obj

muscle_segments = {}
for name in frames[0]["muscles"]:
    count = max(len(frame["muscles"][name]["pointsGroundM"]) - 1
                for frame in frames)
    shade = (right_material if name.endswith("_r") else
             left_material if name.endswith("_l") else axial_material)
    muscle_segments[name] = []
    for index in range(count):
        obj = cylinder(f"muscle_{name}_{index:02d}", muscle_group, shade, 0.006)
        obj["opensim_muscle"] = name
        obj["path_segment"] = index
        muscle_segments[name].append(obj)
bar = cylinder("assumed_welded_barbell", bar_group, bar_material, 0.014)

for frame_index, frame in enumerate(frames, start=1):
    positions = {name: point(value) for name, value in frame["jointsGroundM"].items()}
    for (a, b), obj in bones.items():
        place(obj, positions[a], positions[b], frame_index)
    for name, obj in joints.items():
        obj.location = positions[name]
        obj.keyframe_insert(data_path="location", frame=frame_index)
    for name, objects in muscle_segments.items():
        line = [point(value) for value in frame["muscles"][name]["pointsGroundM"]]
        for index, obj in enumerate(objects):
            if index < len(line) - 1:
                place(obj, line[index], line[index + 1], frame_index)
            else:
                obj.scale = (0, 0, 0)
                obj.keyframe_insert(data_path="scale", frame=frame_index)
    place(bar, *(point(end) for end in frame["barEndsGroundM"]), frame_index)

world = bpy.data.worlds.new("深色背景")
world.color = (0.025, 0.035, 0.055)
scene.world = world
scene.render.engine = "BLENDER_EEVEE"
camera_data = bpy.data.cameras.new("双腿正侧视相机")
camera = bpy.data.objects.new("双腿正侧视相机", camera_data)
scene.collection.objects.link(camera)
target = Vector((0, 0, 0.66))
camera.location = target + Vector((0.35, -3.7, 0.95))
camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
camera_data.type = "ORTHO"
camera_data.ortho_scale = 2.75
scene.camera = camera
for name, position, energy, size in (
    ("主光", (0, -1.8, 3.2), 900, 3.5),
    ("补光", (1.6, 1.4, 2.4), 600, 3.2),
):
    light_data = bpy.data.lights.new(name, type="AREA")
    light = bpy.data.objects.new(name, light_data)
    scene.collection.objects.link(light)
    light.location = position
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = size

scene.render.resolution_x = 1100
scene.render.resolution_y = 800
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.frame_set(14)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print(f"BILATERAL_SCENE_OK frames={len(frames)} muscles={len(muscle_segments)}")
