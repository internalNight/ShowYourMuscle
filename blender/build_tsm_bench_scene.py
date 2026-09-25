"""Build a scrubbable Blender 5.1 scene from the app's TSM bench study.

The scene shows a single right arm and model paths. It has no measured motion,
muscle force, activation, bilateral barbell, or bench contact mechanics.
"""

import json
import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--exercise", choices=("bench", "press"), default="bench")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
EXERCISE = args.exercise
LOOKUP = ROOT / "public" / "data" / f"{EXERCISE}_tsm_reference.json"
OUTPUT = ROOT / "assets" / "blender" / f"opensim_tsm_{EXERCISE}_reference.blend"
PREVIEW = ROOT / "assets" / "blender" / f"opensim_tsm_{EXERCISE}_preview.png"
source = json.loads(LOOKUP.read_text(encoding="utf-8"))
frames = source["frames"]
assert source["status"] == ("bench_research_kinematics_only" if EXERCISE == "bench"
                             else "shoulder_research_kinematics_only") and len(frames) == 101
muscle_names = list(frames[0]["muscles"])
assert len(muscle_names) == 33


def to_blender(point):
    x, y, z = point
    return Vector((x, -z, y))


def material(name, color):
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    shader = next((node for node in result.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if shader is None:
        shader = result.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        output = next((node for node in result.node_tree.nodes if node.type == "OUTPUT_MATERIAL"), None)
        if output is None:
            output = result.node_tree.nodes.new("ShaderNodeOutputMaterial")
        result.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = 0.58
    return result


def move_to_collection(obj, group):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    group.objects.link(obj)
    obj.rotation_mode = "QUATERNION"
    return obj


def cylinder(name, group, shade, radius):
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=1, depth=2)
    obj = move_to_collection(bpy.context.object, group)
    obj.name = name
    obj.data.materials.append(shade)
    obj["radius_m"] = radius
    obj["reference_only"] = True
    return obj


def place_segment(obj, a, b, frame):
    direction = b - a
    if direction.length > 1e-8:
        obj.location = (a + b) / 2
        obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
        obj.scale = (obj["radius_m"], obj["radius_m"], direction.length / 2)
    else:
        obj.scale = (0, 0, 0)
    for key in ("location", "rotation_quaternion", "scale"):
        obj.keyframe_insert(data_path=key, frame=frame)


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 101
scene.render.fps = 25
scene.timeline_markers.clear()
marker_names = (("推起端点", "下放端点", "回到起点") if EXERCISE == "bench"
                else ("上推起点", "上举端点", "回到起点"))
for name, frame in zip(marker_names, (1, 51, 101)):
    scene.timeline_markers.new(name, frame=frame)
scene["source_file"] = str(LOOKUP.relative_to(ROOT))
scene["source_model"] = source["model"]
scene["source_status"] = source["status"]
scene["force_status"] = "not_calculated"
if EXERCISE == "bench":
    scene["maximum_hand_path_error_m"] = source["maximumHandPathErrorM"]

bone_group = bpy.data.collections.new("01_TSM_Right_Arm_Bones_Reference")
muscle_group = bpy.data.collections.new("02_TSM_Muscle_Paths_Reference")
joint_group = bpy.data.collections.new("03_TSM_Joint_Centers")
frame_group = bpy.data.collections.new("05_TSM_Rigid_Body_Frames_Review")
groups = [bone_group, muscle_group, joint_group, frame_group]
if EXERCISE == "bench":
    bench_group = bpy.data.collections.new("04_Illustrative_Bench_No_Contact")
    groups.append(bench_group)
for group in groups:
    scene.collection.children.link(group)

bone_material = material("骨段 · 仅运动学", (0.81, 0.89, 0.94))
joint_material = material("关节 · 仅运动学", (0.94, 0.73, 0.34))
path_material = material("肌肉路径 · 不表示发力", (0.46, 0.63, 0.72))
pec_material = material("胸大肌路径 · 不表示发力", (0.95, 0.68, 0.40))
bench_material = material("卧推凳 · 示意位置", (0.12, 0.20, 0.28))
axis_materials = (
    material("刚体 X 轴 · 不表示肌力", (0.92, 0.30, 0.30)),
    material("刚体 Y 轴 · 不表示肌力", (0.32, 0.87, 0.47)),
    material("刚体 Z 轴 · 不表示肌力", (0.35, 0.53, 0.96)),
)

joint_names = ("thorax", "clavicle", "scapula", "shoulder", "elbow", "hand")
bones = {(a, b): cylinder(f"bone_{a}_{b}", bone_group, bone_material, 0.012)
         for a, b in zip(joint_names, joint_names[1:])}
joints = {}
for name in joint_names:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.014)
    obj = move_to_collection(bpy.context.object, joint_group)
    obj.name = f"joint_{name}"
    obj.data.materials.append(joint_material)
    joints[name] = obj

muscle_segments = {}
for name in muscle_names:
    maximum = max(len(frame["muscles"][name]["viewerPathM"]) - 1 for frame in frames)
    shade = pec_material if name.startswith("PectoralisMajor") else path_material
    muscle_segments[name] = []
    for index in range(maximum):
        obj = cylinder(f"muscle_{name}_segment_{index:02d}", muscle_group, shade, 0.004)
        obj["opensim_muscle"] = name
        obj["path_segment"] = index
        muscle_segments[name].append(obj)

frame_names = tuple(frames[0]["blenderBodyFrames"])
body_axes = {(body, axis): cylinder(f"body_frame_{body}_{axis}", frame_group,
                                    axis_materials[axis], 0.0015)
             for body in frame_names for axis in range(3)}
scene["body_frame_status"] = "OpenSim_body_transforms_for_registration_review_only"

for frame_index, data in enumerate(frames, start=1):
    locations = {name: to_blender(value) for name, value in data["viewerJointsM"].items()}
    for (a, b), obj in bones.items():
        place_segment(obj, locations[a], locations[b], frame_index)
    for name, obj in joints.items():
        obj.location = locations[name]
        obj.keyframe_insert(data_path="location", frame=frame_index)
    for name, objects in muscle_segments.items():
        path = [to_blender(point) for point in data["muscles"][name]["viewerPathM"]]
        for index, obj in enumerate(objects):
            if index < len(path) - 1:
                place_segment(obj, path[index], path[index + 1], frame_index)
            else:
                obj.scale = (0, 0, 0)
                obj.keyframe_insert(data_path="scale", frame=frame_index)
    for body, axes in data["blenderBodyFrames"].items():
        origin = Vector(axes["translationM"])
        rows = axes["rotationRows"]
        for axis in range(3):
            direction = Vector(tuple(rows[row][axis] for row in range(3)))
            place_segment(body_axes[(body, axis)], origin,
                          origin + direction * 0.045, frame_index)

if EXERCISE == "bench":
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.18, 0, 0.51))
    bench = move_to_collection(bpy.context.object, bench_group)
    bench.name = "bench_illustrative_no_contact"
    bench.dimensions = (0.55, 1.65, 0.12)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bench.data.materials.append(bench_material)

world = bpy.data.worlds.new("深色背景")
world.color = (0.02, 0.04, 0.07)
scene.world = world
scene.render.engine = "BLENDER_EEVEE"
camera_data = bpy.data.cameras.new("肩臂参考相机")
camera = bpy.data.objects.new("肩臂参考相机", camera_data)
scene.collection.objects.link(camera)
target = Vector((0.28, 0, 0.93 if EXERCISE == "bench" else 1.48))
camera.location = target + Vector((1.60, -1.75, 1.10))
camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
camera_data.type = "ORTHO"
camera_data.ortho_scale = 1.45
scene.camera = camera
light_data = bpy.data.lights.new("软光", type="AREA")
light = bpy.data.objects.new("软光", light_data)
scene.collection.objects.link(light)
light.location = (1.2, -1.0, 2.3)
light_data.energy = 100
light_data.shape = "DISK"
light_data.size = 3
scene.render.resolution_x = 1000
scene.render.resolution_y = 800
scene.render.resolution_percentage = 100

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
scene.frame_set(51)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print(f"SAVED_TSM_{EXERCISE.upper()} {OUTPUT} frames={len(frames)} "
      f"bones={len(bones)} muscles={len(muscle_segments)} "
      f"segments={sum(map(len, muscle_segments.values()))} "
      f"body_axes={len(body_axes)}")
