"""Create a Blender workbench for reviewing source-model attachment points.

All atlas muscles are visible in the Outliner, but only rectus femoris is
shown in the initial render. Markers are source OpenSim points, not verified
landmarks on the anatomical meshes.
"""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/blender/opensim_anatomy_bone_motion.blend"
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
INVENTORY = ROOT / "docs/data/opensim_squat_attachment_inventory.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
SURFACES = ROOT / "docs/data/attachment_surface_screen.json"
OUTPUT = ROOT / "assets/blender/opensim_attachment_review.blend"
PREVIEW = ROOT / "assets/blender/opensim_attachment_review.png"
MAPPING = {
    "rect_fem_r": "Rectus femoris muscle.r",
    "vas_int_r": "Vastus intermedius muscle.r",
    "bifemsh_r": "Short head of biceps femoris.r",
    "semimem_r": "Semimembranosus muscle.r",
    "med_gas_r": "Medial head of gastrocnemius.r",
    "soleus_r": "Soleus muscle.r",
    "tib_ant_r": "Tibialis anterior muscle.r",
    "glut_max2_r": "Gluteus maximus muscle.r",
}

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
scene.frame_set(1)
existing = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
new_objects = set(bpy.data.objects) - existing
atlas = {obj.name: obj for obj in new_objects if obj.type == "MESH"}
shift = Vector(json.loads(REGISTRATION.read_text(encoding="utf-8"))["translationM"])
inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))["muscles"]
surface_screen = json.loads(SURFACES.read_text(encoding="utf-8"))
surface_by_point = {(item["muscle"], item["point"]): item for item in surface_screen["points"]}

root = bpy.data.collections.new("06_OpenSim_Attachment_Review_UNVALIDATED")
scene.collection.children.link(root)
collections = {}
for muscle in inventory:
    name = muscle["name"]
    collection = bpy.data.collections.new(name + "_review")
    root.children.link(collection)
    collections[name] = collection

for name, source_name in MAPPING.items():
    obj = atlas[source_name]
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)
    collections[name].objects.link(obj)
    obj.name = "atlas_" + source_name
    obj["opensim_comparison"] = name
    obj["status"] = "unvalidated_mesh_to_path_comparison"
    world = obj.matrix_world.copy()
    world.translation += shift
    obj.matrix_world = world
    shade = bpy.data.materials.new("解剖网格研究对照 " + name)
    shade.diffuse_color = (0.60, 0.46, 0.78, 1)
    shade.use_nodes = True
    shader = next(node for node in shade.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = (0.60, 0.46, 0.78, 1)
    obj.data.materials.clear()
    obj.data.materials.append(shade)
    obj.hide_render = name != "rect_fem_r"
    obj.hide_set(name != "rect_fem_r")

for obj in new_objects:
    if obj.name in {"Patella.r", "Calcaneus.r"}:
        bpy.data.objects.remove(obj, do_unlink=True)
    elif obj.name not in {"atlas_" + source for source in MAPPING.values()}:
        bpy.data.objects.remove(obj, do_unlink=True)
for name in ("Patella.r", "Calcaneus.r"):
    bpy.data.objects["atlas_" + name]["status"] = "shared_bbox_translation_only_not_landmark_registered"

colors = {"proximal": (0.25, 0.85, 0.48, 1),
          "intermediate": (0.55, 0.76, 0.94, 1),
          "distal": (0.26, 0.56, 0.96, 1)}
materials = {}
for role, color in colors.items():
    material = bpy.data.materials.new("OpenSim 点 " + role)
    material.diffuse_color = color
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = color
    if shader.inputs.get("Emission Color"):
        shader.inputs["Emission Color"].default_value = color
        shader.inputs["Emission Strength"].default_value = 2
    materials[role] = material

for role, color in {"near": (0.92, 0.83, 0.27, 1),
                    "far": (0.96, 0.51, 0.20, 1),
                    "guide": (0.66, 0.70, 0.72, 1)}.items():
    material = bpy.data.materials.new("骨面候选点 " + role)
    material.diffuse_color = color
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = color
    materials[role] = material

marker_count = 0
candidate_count = 0
for muscle in inventory:
    points = muscle["points"]
    for index, point in enumerate(points):
        role = "proximal" if index == 0 else "distal" if index == len(points) - 1 else "intermediate"
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.012,
                                             location=point["standingBlenderPositionM"])
        obj = bpy.context.object
        obj.name = "attachment_" + muscle["name"] + "_" + point["name"]
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        collections[muscle["name"]].objects.link(obj)
        obj.data.materials.append(materials[role])
        obj["opensim_muscle"] = muscle["name"]
        obj["source_point"] = point["name"]
        obj["parent_frame"] = point["parentFrame"]
        obj["local_position_m"] = tuple(point["localPositionM"])
        obj["status"] = "source_model_point_not_atlas_landmark"
        obj.hide_render = muscle["name"] != "rect_fem_r"
        obj.hide_set(muscle["name"] != "rect_fem_r")
        marker_count += 1
        candidate = surface_by_point.get((muscle["name"], point["name"]))
        if candidate is None:
            continue
        surface_position = Vector(candidate["nearestSurfaceBlenderM"])
        source_position = Vector(point["standingBlenderPositionM"])
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.007,
                                             location=surface_position)
        surface_marker = bpy.context.object
        surface_marker.name = "surface_candidate_" + muscle["name"] + "_" + point["name"]
        for collection in list(surface_marker.users_collection):
            collection.objects.unlink(surface_marker)
        collections[muscle["name"]].objects.link(surface_marker)
        surface_marker.data.materials.append(materials["far" if candidate["nearestDistanceM"] > 0.02 else "near"])
        surface_marker["source_point"] = point["name"]
        surface_marker["atlas_bone"] = candidate["atlasBone"]
        surface_marker["distance_m"] = candidate["nearestDistanceM"]
        surface_marker["status"] = "nearest_surface_candidate_not_anatomical_attachment"
        surface_marker.hide_render = muscle["name"] != "rect_fem_r"
        surface_marker.hide_set(muscle["name"] != "rect_fem_r")

        guide_vector = surface_position - source_position
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.0015,
                                            depth=guide_vector.length,
                                            location=(surface_position + source_position) / 2)
        guide = bpy.context.object
        guide.name = "surface_gap_" + muscle["name"] + "_" + point["name"]
        guide.rotation_euler = guide_vector.to_track_quat("Z", "Y").to_euler()
        for collection in list(guide.users_collection):
            collection.objects.unlink(guide)
        collections[muscle["name"]].objects.link(guide)
        guide.data.materials.append(materials["guide"])
        guide["status"] = "source_to_nearest_surface_distance_only"
        guide.hide_render = muscle["name"] != "rect_fem_r"
        guide.hide_set(muscle["name"] != "rect_fem_r")
        candidate_count += 1

scene.frame_start = 1
scene.frame_end = 1
scene["status"] = "attachment_review_unvalidated"
scene["notes"] = "30 source path points and nearest parent-bone surface candidates; patella and calcaneus use only shared bbox translation, not independent landmark registration."
scene["surface_candidate_count"] = candidate_count
scene.camera.data.ortho_scale = 1.6
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
scene.render.filepath = str(PREVIEW)
bpy.ops.render.render(write_still=True)
print("SAVED_ATTACHMENT_REVIEW", OUTPUT, "markers", marker_count,
      "surface_candidates", candidate_count, "candidate_meshes", len(MAPPING))
