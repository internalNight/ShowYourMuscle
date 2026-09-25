"""Create a Blender 5.1 static full-body structural review from MyoSim.

The mesh bones are the compiled MuJoCo visual assets. Muscle polylines use
runtime sites and wrapping tangency points; curved sections are drawn as
straight chords. Neither colors nor lengths represent personal muscle force.
"""

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache/myosim_fullbody_neutral_snapshot.json"
OUTPUT = ROOT / "assets/blender/myosim_fullbody_structural_review.blend"
PREVIEW = ROOT / "assets/blender/myosim_fullbody_structural_review.png"

data = json.loads(SOURCE.read_text(encoding="utf-8"))
assert data["muscleActuators"] == 416 and data["wrappedVisualPathCount"] == 98

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene["status"] = data["status"]
scene["source"] = data["source"]
scene["mesh_geometries"] = data["meshGeometries"]
scene["muscle_actuators"] = data["muscleActuators"]
scene["active_wrapped_chord_paths"] = data["wrappedVisualPathCount"]
scene["declared_wrapping_paths"] = data["declaredWrappingPathCount"]
scene["force_status"] = "not_computed_or_visualized"
scene["warning"] = (
    "Static generic anatomy only; curved wrapping sections are drawn as chords. "
    "No exercise motion, person scaling, muscle activation or force."
)


def group(name):
    result = bpy.data.collections.new(name)
    scene.collection.children.link(result)
    return result


bone_group = group("01_MyoSim_Compiled_Bone_Meshes")
leg_group = group("02_Leg_Muscle_Runtime_Paths_80")
right_arm_group = group("03_Right_Arm_Muscle_Runtime_Paths_63")
left_arm_group = group("04_Left_Arm_Muscle_Runtime_Paths_63")
torso_group = group("05_Torso_Muscle_Runtime_Paths_210_Toggle_To_View")


def material(name, color, roughness=0.5):
    result = bpy.data.materials.new(name)
    result.diffuse_color = (*color, 1)
    result.use_nodes = True
    node = result.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*color, 1)
    node.inputs["Roughness"].default_value = roughness
    return result


bone_material = material("模型骨骼 · 非个体", (0.78, 0.83, 0.89))
arm_material = material("肩臂路径点 · 未验证", (0.24, 0.76, 0.92))
leg_material = material("下肢路径点 · 未验证", (0.59, 0.72, 0.95))
torso_material = material("躯干路径点 · 未验证", (0.64, 0.58, 0.82))
wrapped_material = material("含包绕 · 连线不完整", (0.96, 0.61, 0.27))

mesh_cache = {}
for raw_id, source_mesh in data["meshes"].items():
    mesh = bpy.data.meshes.new(f"MyoSim mesh {raw_id}")
    mesh.from_pydata(source_mesh["vertices"], [], source_mesh["faces"])
    mesh.update()
    mesh.materials.append(bone_material)
    mesh_cache[int(raw_id)] = mesh

for entry in data["geoms"]:
    obj = bpy.data.objects.new(entry["name"] or f"geom_{entry['id']}",
                               mesh_cache[entry["meshId"]])
    bone_group.objects.link(obj)
    rotation = entry["worldRotation"]
    position = entry["worldPositionM"]
    obj.matrix_world = Matrix((
        (*rotation[0], position[0]),
        (*rotation[1], position[1]),
        (*rotation[2], position[2]),
        (0, 0, 0, 1),
    ))
    obj["mujoco_body"] = entry["body"]
    obj["source_geom_id"] = entry["id"]

regions = {
    "torso": (torso_group, torso_material),
    "right_arm": (right_arm_group, arm_material),
    "left_arm": (left_arm_group, arm_material),
    "legs": (leg_group, leg_material),
}
for path in data["paths"]:
    collection, shade = regions[path["modelRegion"]]
    curve = bpy.data.curves.new(path["name"] + " runtime path", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = 0.0025
    curve.bevel_resolution = 1
    line = curve.splines.new("POLY")
    line.points.add(len(path["displayPathWorldM"]) - 1)
    for index, xyz in enumerate(path["displayPathWorldM"]):
        line.points[index].co = (*xyz, 1)
    obj = bpy.data.objects.new(path["name"] + " · runtime path", curve)
    collection.objects.link(obj)
    curve.materials.append(wrapped_material if path["visualPathIncomplete"]
                           else shade)
    obj["muscle_actuator"] = path["name"]
    obj["region"] = path["modelRegion"]
    obj["tendon_length_m"] = path["modelTendonLengthM"]
    obj["visual_path_incomplete"] = path["visualPathIncomplete"]
    obj["declared_wrapping_object_count"] = path["declaredWrappingObjectCount"]
    obj["active_wrapping"] = path["activeWrapping"]

torso_group.hide_render = True
torso_group.hide_viewport = True

world = bpy.data.worlds.new("结构研究背景")
world.color = (0.025, 0.034, 0.05)
scene.world = world
scene.render.engine = "BLENDER_EEVEE"
camera_data = bpy.data.cameras.new("全身结构相机")
camera = bpy.data.objects.new("全身结构相机", camera_data)
scene.collection.objects.link(camera)
target = Vector((0, 0.12, 0.92))
camera.location = target + Vector((2.2, -3.8, 1.1))
camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
camera_data.type = "ORTHO"
camera_data.ortho_scale = 2.35
scene.camera = camera
for name, position, energy, size in (
    ("主光", (2.0, -2.3, 4.0), 850, 3.0),
    ("补光", (-2.0, 1.2, 2.8), 650, 3.0),
):
    light_data = bpy.data.lights.new(name, type="AREA")
    light = bpy.data.objects.new(name, light_data)
    scene.collection.objects.link(light)
    light.location = position
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = size
scene.render.resolution_x = 900
scene.render.resolution_y = 1050
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print(f"MYOSIM_FULLBODY_SCENE_OK meshes={len(data['geoms'])} paths={len(data['paths'])}")
