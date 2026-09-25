"""Build a scrubbable Blender scene from the app's OpenSim squat lookup.

The lookup contains a single right-leg model's bone centers and nine muscle
paths. This scene visualizes kinematics only; it contains no activation/force.
Run with Blender 5.1: blender --background --python blender/build_opensim_squat_scene.py
"""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "public" / "data" / "squat_opensim_reference.json"
OUTPUT = ROOT / "assets" / "blender" / "opensim_squat_reference.blend"
PREVIEW = ROOT / "assets" / "blender" / "opensim_squat_preview.png"
source = json.loads(LOOKUP.read_text(encoding="utf-8"))
frames = source["frames"]
assert source["status"] == "reference_model_kinematics_only" and len(frames) == 101
muscle_names = list(frames[0]["muscles"])
assert len(muscle_names) == 9


def to_blender(point):
    """Viewer: x lateral, y up, z forward. Blender atlas: x lateral, y back, z up.

    The right ankle's viewer x=0.18 is mapped to atlas x=-0.09. This is a
    coordinate-registration seed, not a fitted anatomical landmark solution.
    """
    x, y, z = point
    return Vector((0.09 - x, -z, y))

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = len(frames)
scene.render.fps = 25
scene.timeline_markers.clear()
scene.timeline_markers.new("站立", frame=1)
scene.timeline_markers.new("最深姿态", frame=51)
scene.timeline_markers.new("回到站立", frame=101)
scene["source_file"] = str(LOOKUP.relative_to(ROOT))
scene["source_model"] = source["model"]
scene["source_status"] = "reference_model_kinematics_only"
scene["max_path_polyline_error_m"] = source["maximumPolylineErrorM"]
scene["force_status"] = "not_calculated"


def collection(name):
    group = bpy.data.collections.new(name)
    scene.collection.children.link(group)
    return group


bone_group = collection("01_OpenSim_Bones_Right_Leg")
muscle_group = collection("02_OpenSim_Muscle_Paths_Right_Leg")
joint_group = collection("03_Joint_Centers")


def material(name, color):
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
    shader.inputs["Roughness"].default_value = 0.6
    return result


bone_material = material("骨段 · 不含力", (0.82, 0.9, 0.94))
joint_material = material("关节中心 · 不含力", (0.95, 0.77, 0.38))
muscle_colors = {
    "bifemsh_r": (0.76, 0.39, 0.58),
    "med_gas_r": (0.62, 0.52, 0.82),
    "glut_max2_r": (0.84, 0.42, 0.43),
    "psoas_r": (0.76, 0.51, 0.32),
    "rect_fem_r": (0.4, 0.7, 0.78),
    "semimem_r": (0.67, 0.36, 0.63),
    "soleus_r": (0.56, 0.57, 0.82),
    "tib_ant_r": (0.43, 0.7, 0.65),
    "vas_int_r": (0.33, 0.59, 0.85),
}
muscle_materials = {name: material(name + "_path_only", color)
                    for name, color in muscle_colors.items()}


def put_in(obj, group):
    for previous in list(obj.users_collection):
        previous.objects.unlink(obj)
    group.objects.link(obj)
    obj.rotation_mode = "QUATERNION"
    return obj


def segment(name, group, shade, radius):
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=1, depth=2)
    obj = put_in(bpy.context.object, group)
    obj.name = name
    obj.data.materials.append(shade)
    obj["radius_m"] = radius
    obj["display_only"] = True
    return obj


def place_segment(obj, a, b, radius, frame):
    direction = b - a
    if direction.length > 1e-8:
        obj.location = (a + b) / 2
        obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
        obj.scale = (radius, radius, direction.length / 2)
    else:
        obj.scale = (0, 0, 0)
    for path in ("location", "rotation_quaternion", "scale"):
        obj.keyframe_insert(data_path=path, frame=frame)


bone_names = [("foot", "ankle"), ("ankle", "knee"), ("knee", "hip"), ("hip", "back")]
bones = {(a, b): segment(f"bone_{a}_{b}", bone_group, bone_material, 0.012)
         for a, b in bone_names}
joint_names = ("foot", "ankle", "knee", "hip", "back")
joints = {}
for name in joint_names:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.015)
    obj = put_in(bpy.context.object, joint_group)
    obj.name = f"joint_{name}"
    obj.data.materials.append(joint_material)
    joints[name] = obj

muscle_segments = {}
for name in muscle_names:
    maximum = max(len(frame["muscles"][name]["viewerPathM"]) - 1 for frame in frames)
    muscle_segments[name] = []
    for index in range(maximum):
        obj = segment(f"muscle_{name}_segment_{index:02d}", muscle_group,
                      muscle_materials[name], 0.006)
        obj["opensim_muscle"] = name
        obj["path_segment"] = index
        muscle_segments[name].append(obj)

for frame_index, data in enumerate(frames, start=1):
    points = {name: to_blender(position) for name, position in data["viewerJointsM"].items()}
    for (a, b), obj in bones.items():
        place_segment(obj, points[a], points[b], obj["radius_m"], frame_index)
    for name, obj in joints.items():
        obj.location = points[name]
        obj.keyframe_insert(data_path="location", frame=frame_index)
    for name, objects in muscle_segments.items():
        path = [to_blender(position) for position in data["muscles"][name]["viewerPathM"]]
        for segment_index, obj in enumerate(objects):
            if segment_index < len(path) - 1:
                place_segment(obj, path[segment_index], path[segment_index + 1],
                              obj["radius_m"], frame_index)
            else:
                obj.scale = (0, 0, 0)
                obj.keyframe_insert(data_path="scale", frame=frame_index)

# A local authoring preview; the phone view continues to use the lookup JSON.
world = bpy.data.worlds.new("深色背景")
world.color = (0.02, 0.04, 0.07)
scene.world = world
scene.render.engine = "BLENDER_EEVEE"
camera_data = bpy.data.cameras.new("参考侧视相机")
camera = bpy.data.objects.new("参考侧视相机", camera_data)
scene.collection.objects.link(camera)
target = Vector((-0.09, 0.02, 0.43))
camera.location = target + Vector((1.70, -2.20, 0.95))
camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
camera_data.type = "ORTHO"
camera_data.ortho_scale = 1.32
scene.camera = camera
light_data = bpy.data.lights.new("软光", type="AREA")
light = bpy.data.objects.new("软光", light_data)
scene.collection.objects.link(light)
light.location = (1.2, 2.3, 2.0)
light_data.energy = 850
light_data.shape = "DISK"
light_data.size = 3
scene.render.resolution_x = 900
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
scene.frame_set(51)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print(f"SAVED_OPENSIM_SQUAT {OUTPUT} frames={len(frames)} "
      f"bones={len(bones)} muscles={len(muscle_segments)} "
      f"segments={sum(map(len, muscle_segments.values()))}")
