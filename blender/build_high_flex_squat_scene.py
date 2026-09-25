"""Build a local-only Blender 5.1 review scene of 80 lower-limb paths."""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / ".cache/high-flex-scene"
SOURCE = OUTPUT_DIR / "ab02_high_flex_kinematics.json"
BLEND = OUTPUT_DIR / "ab02_high_flex_paths.blend"
PREVIEW = OUTPUT_DIR / "ab02_high_flex_paths.png"

data = json.loads(SOURCE.read_text(encoding="utf-8"))
frames = data["frames"]
assert data["muscleCount"] == 80 and len(frames) == 21

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = len(frames)
scene.render.fps = 20
scene.timeline_markers.clear()
scene.timeline_markers.new("AB02 experimental start", frame=1)
deepest = max(range(len(frames)), key=lambda index:
              sum(frames[index]["kneeFlexionDeg"].values())) + 1
scene.timeline_markers.new("Deepest sampled squat", frame=deepest)
scene.timeline_markers.new("Experimental segment end", frame=len(frames))
scene["source_file"] = str(SOURCE.relative_to(ROOT))
scene["source_subject"] = data["subject"]
scene["source_status"] = data["status"]
scene["force_status"] = "not_calculated_or_displayed"
scene["source_redistribution"] = data["redistribution"]
scene["max_straight_path_length_error_m"] = data[
    "maxStraightPolylineVsOpenSimLengthErrorM"]
scene["path_color_meaning"] = "cyan longer, violet shorter than first sampled frame; gray near equal; no force"

origin = frames[0]["jointsGroundM"]["ground_pelvis"]


def point(values):
    x, y, z = values
    return Vector((z - origin[2], -(x - origin[0]), y))


def collection(name):
    group = bpy.data.collections.new(name)
    scene.collection.children.link(group)
    return group


bone_group = collection("01_Bilateral_Lower_Bones")
muscle_group = collection("02_Lower_Muscle_Paths_80")
joint_group = collection("03_Joint_Centers")


def material(name, rgb):
    shader = bpy.data.materials.new(name)
    shader.diffuse_color = (*rgb, 1)
    shader.use_nodes = True
    principled = next(node for node in shader.node_tree.nodes
                      if node.type == "BSDF_PRINCIPLED")
    principled.inputs["Base Color"].default_value = (*rgb, 1)
    principled.inputs["Roughness"].default_value = 0.36
    return shader


bone_mat = material("Skeleton: geometry only", (0.80, 0.86, 0.91))
joint_mat = material("Joint centers", (0.96, 0.69, 0.24))


def length_color(name, ratio):
    neutral = ((0.30, 0.28, 0.38) if name.endswith("_r") else
               (0.25, 0.35, 0.39))
    target = (0.04, 0.62, 0.84) if ratio >= 1 else (0.55, 0.09, 0.78)
    weight = min(abs(ratio - 1) / 0.07, 1.0)
    return tuple((1 - weight) * base + weight * peak
                 for base, peak in zip(neutral, target))


def move_to(obj, group):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    group.objects.link(obj)
    obj.rotation_mode = "QUATERNION"
    return obj


def cylinder(name, group, shade, radius):
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=1, depth=2)
    obj = move_to(bpy.context.object, group)
    obj.name = name
    obj.data.materials.append(shade)
    obj["radius_m"] = radius
    return obj


def animate_segment(obj, first, second, number):
    delta = second - first
    if delta.length >= 5e-4:
        obj.location = (first + second) / 2
        obj.rotation_quaternion = delta.to_track_quat("Z", "Y")
        radius = obj["radius_m"]
        obj.scale = (radius, radius, delta.length / 2)
    else:
        obj.scale = (0, 0, 0)
    for prop in ("location", "rotation_quaternion", "scale"):
        obj.keyframe_insert(data_path=prop, frame=number)


links = (
    ("hip_r", "hip_l"),
    ("hip_r", "walker_knee_r"),
    ("walker_knee_r", "ankle_r"),
    ("ankle_r", "mtp_r"),
    ("hip_l", "walker_knee_l"),
    ("walker_knee_l", "ankle_l"),
    ("ankle_l", "mtp_l"),
    ("ground_pelvis", "back"),
)
bones = {(a, b): cylinder(f"bone_{a}_{b}", bone_group, bone_mat, 0.016)
         for a, b in links}
joint_names = sorted({name for pair in links for name in pair})
joints = {}
for name in joint_names:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.021)
    obj = move_to(bpy.context.object, joint_group)
    obj.name = f"joint_{name}"
    obj.data.materials.append(joint_mat)
    joints[name] = obj

segments = {}
muscle_materials = {}
for name in frames[0]["muscles"]:
    count = max(len(frame["muscles"][name]["pointsGroundM"]) - 1
                for frame in frames)
    shade = material(f"{name}: relative path length, no force",
                     length_color(name, 1.0))
    muscle_materials[name] = shade
    segments[name] = []
    for index in range(count):
        obj = cylinder(f"muscle_{name}_{index:02d}", muscle_group,
                       shade, 0.0045)
        obj["opensim_muscle"] = name
        obj["path_segment"] = index
        segments[name].append(obj)

for number, frame in enumerate(frames, start=1):
    centers = {name: point(location)
               for name, location in frame["jointsGroundM"].items()}
    for (first, second), obj in bones.items():
        animate_segment(obj, centers[first], centers[second], number)
    for name, obj in joints.items():
        obj.location = centers[name]
        obj.keyframe_insert(data_path="location", frame=number)
    for name, objects in segments.items():
        polyline = [point(location) for location in
                    frame["muscles"][name]["pointsGroundM"]]
        first_length = frames[0]["muscles"][name]["opensimLengthM"]
        ratio = frame["muscles"][name]["opensimLengthM"] / first_length
        shade = muscle_materials[name]
        color = length_color(name, ratio)
        base_color = next(node for node in shade.node_tree.nodes
                          if node.type == "BSDF_PRINCIPLED").inputs["Base Color"]
        base_color.default_value = (*color, 1)
        base_color.keyframe_insert(data_path="default_value", frame=number)
        for index, obj in enumerate(objects):
            obj["length_ratio_to_first_frame"] = ratio
            obj.keyframe_insert(data_path='["length_ratio_to_first_frame"]',
                                frame=number)
            if index < len(polyline) - 1:
                animate_segment(obj, polyline[index], polyline[index + 1],
                                number)
            else:
                obj.scale = (0, 0, 0)
                obj.keyframe_insert(data_path="scale", frame=number)

world = bpy.data.worlds.new("Deep blue background")
world.color = (0.025, 0.035, 0.055)
scene.world = world
scene.render.engine = "BLENDER_EEVEE"
camera_data = bpy.data.cameras.new("Side camera")
camera = bpy.data.objects.new("Side camera", camera_data)
scene.collection.objects.link(camera)
target = Vector((0, 0, 0.43))
camera.location = target + Vector((0.35, -3.5, 0.50))
camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
camera_data.type = "ORTHO"
camera_data.ortho_scale = 1.25
scene.camera = camera
for name, position, energy in (("Key", (0, -1.8, 3.1), 500),
                               ("Fill", (1.6, 1.2, 2.3), 300)):
    light_data = bpy.data.lights.new(name, type="AREA")
    light = bpy.data.objects.new(name, light_data)
    scene.collection.objects.link(light)
    light.location = position
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = 3.2

scene.render.resolution_x = 1100
scene.render.resolution_y = 800
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.frame_set(deepest)
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print(f"HIGH_FLEX_SCENE_OK frames={len(frames)} muscles={len(segments)} "
      f"segments={sum(map(len, segments.values()))} deepest={deepest}")
