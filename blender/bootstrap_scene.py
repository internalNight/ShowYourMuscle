"""Create a named Blender seed scene for the muscle-atlas authoring workflow.

Run with: blender --background --python blender/bootstrap_scene.py
This creates an illustrative authoring scene and a small GLB mesh kit used by
the mobile viewer. Anatomical paths and muscle mechanics require review.
"""

from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "blender" / "muscle_atlas_seed.blend"
MOBILE_OUTPUT = ROOT / "public" / "models" / "prototype_parts.glb"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
MOBILE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)


def collection(name: str) -> bpy.types.Collection:
    result = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(result)
    return result


bones_collection = collection("01_Skeleton")
muscles_collection = collection("02_Muscle_Paths_Illustrative")
landmarks_collection = collection("03_Landmarks")
mobile_collection = collection("04_Mobile_Mesh_Kit")

# Metres; Blender uses Z as vertical. Left/right are from the model's view.
landmarks = {
    "pelvis": (0.0, 0.0, 0.98),
    "chest": (0.0, 0.0, 1.42),
    "neck": (0.0, 0.0, 1.56),
    "head": (0.0, 0.0, 1.72),
    "shoulder_l": (-0.27, 0.0, 1.45),
    "shoulder_r": (0.27, 0.0, 1.45),
    "elbow_l": (-0.47, 0.0, 1.19),
    "elbow_r": (0.47, 0.0, 1.19),
    "wrist_l": (-0.57, 0.0, 0.96),
    "wrist_r": (0.57, 0.0, 0.96),
    "hip_l": (-0.16, 0.0, 0.98),
    "hip_r": (0.16, 0.0, 0.98),
    "knee_l": (-0.17, 0.0, 0.52),
    "knee_r": (0.17, 0.0, 0.52),
    "ankle_l": (-0.18, 0.0, 0.10),
    "ankle_r": (0.18, 0.0, 0.10),
}

connections = [
    ("pelvis", "chest"), ("chest", "neck"), ("neck", "head"),
    ("chest", "shoulder_l"), ("chest", "shoulder_r"),
    ("shoulder_l", "elbow_l"), ("shoulder_r", "elbow_r"),
    ("elbow_l", "wrist_l"), ("elbow_r", "wrist_r"),
    ("pelvis", "hip_l"), ("pelvis", "hip_r"),
    ("hip_l", "knee_l"), ("hip_r", "knee_r"),
    ("knee_l", "ankle_l"), ("knee_r", "ankle_r"),
]

armature_data = bpy.data.armatures.new("MuscleAtlasSkeleton")
armature = bpy.data.objects.new("MuscleAtlasSkeleton", armature_data)
bones_collection.objects.link(armature)
bpy.context.view_layer.objects.active = armature
armature.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for start, end in connections:
    bone = armature_data.edit_bones.new(f"{start}__{end}")
    bone.head = landmarks[start]
    bone.tail = landmarks[end]
bpy.ops.object.mode_set(mode="OBJECT")
armature.select_set(False)
armature.show_in_front = True
armature["status"] = "illustrative_static_scaffold"

for name, position in landmarks.items():
    marker = bpy.data.objects.new(f"landmark_{name}", None)
    marker.empty_display_type = "SPHERE"
    marker.empty_display_size = 0.025
    marker.location = position
    marker["status"] = "illustrative_landmark"
    landmarks_collection.objects.link(marker)

muscle_material = bpy.data.materials.new("IllustrativeMuscle")
muscle_material.diffuse_color = (0.63, 0.30, 0.40, 1.0)


def make_muscle(name: str, display_name: str, origin: str, insertion: str, depth: float = 0.035) -> None:
    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = depth
    curve.bevel_resolution = 4
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (*landmarks[origin], 1.0)
    spline.points[1].co = (*landmarks[insertion], 1.0)
    obj = bpy.data.objects.new(name, curve)
    obj.data.materials.append(muscle_material)
    obj["display_name_zh"] = display_name
    obj["origin_landmark"] = origin
    obj["insertion_landmark"] = insertion
    obj["status"] = "illustrative_path_not_anatomically_validated"
    muscles_collection.objects.link(obj)


for side, label in (("l", "左"), ("r", "右")):
    make_muscle(f"pectoralis_major_{side}", f"{label}胸大肌", "chest", f"shoulder_{side}", 0.052)
    make_muscle(f"deltoid_{side}", f"{label}三角肌", f"shoulder_{side}", f"elbow_{side}", 0.044)
    make_muscle(f"biceps_brachii_{side}", f"{label}肱二头肌", f"shoulder_{side}", f"elbow_{side}")
    make_muscle(f"triceps_brachii_{side}", f"{label}肱三头肌", f"shoulder_{side}", f"elbow_{side}")
    make_muscle(f"trapezius_upper_{side}", f"{label}斜方肌上束", "neck", f"shoulder_{side}", 0.03)
    make_muscle(f"latissimus_dorsi_{side}", f"{label}背阔肌", "pelvis", f"shoulder_{side}", 0.035)
    make_muscle(f"erector_spinae_{side}", f"{label}竖脊肌", "pelvis", "chest", 0.03)
    make_muscle(f"gluteus_maximus_{side}", f"{label}臀大肌", f"hip_{side}", f"knee_{side}", 0.052)
    make_muscle(f"quadriceps_{side}", f"{label}股四头肌", f"hip_{side}", f"knee_{side}", 0.055)
    make_muscle(f"hamstrings_{side}", f"{label}腘绳肌", f"hip_{side}", f"knee_{side}", 0.04)
    make_muscle(f"calf_{side}", f"{label}小腿肌群", f"knee_{side}", f"ankle_{side}", 0.04)
make_muscle("rectus_abdominis", "腹直肌", "chest", "pelvis", 0.043)


def mesh_object(name: str, vertices: list, faces: list) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    mobile_collection.objects.link(obj)
    obj["status"] = "illustrative_mesh_template"
    return obj


# The mobile viewer scales these unit meshes between moving joint/path points.
# A spindle gives muscle paths distinct tapered ends instead of uniform rods.
import math

segments = 16
rings = 13
spindle_vertices = []
for ring in range(rings):
    t = ring / (rings - 1)
    y = -1.0 + 2.0 * t
    radius = 0.10 + 0.90 * math.sin(math.pi * t) ** 0.8
    for segment in range(segments):
        angle = 2.0 * math.pi * segment / segments
        spindle_vertices.append((radius * math.cos(angle), y, radius * math.sin(angle)))
spindle_faces = []
for ring in range(rings - 1):
    for segment in range(segments):
        nxt = (segment + 1) % segments
        a = ring * segments + segment
        b = ring * segments + nxt
        c = (ring + 1) * segments + nxt
        d = (ring + 1) * segments + segment
        spindle_faces.append((a, b, c, d))
spindle_faces += [tuple(reversed(range(segments))), tuple((rings - 1) * segments + i for i in range(segments))]
spindle = mesh_object("muscle_spindle", spindle_vertices, spindle_faces)
for polygon in spindle.data.polygons:
    polygon.use_smooth = True


def add_primitive(name: str, kind: str) -> bpy.types.Object:
    if kind == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=1, depth=2)
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=12, radius=1)
    obj = bpy.context.object
    obj.name = name
    for old_collection in list(obj.users_collection):
        old_collection.objects.unlink(obj)
    mobile_collection.objects.link(obj)
    obj["status"] = "illustrative_mesh_template"
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


bone_shaft = add_primitive("bone_shaft", "cylinder")
joint_sphere = add_primitive("joint_sphere", "sphere")
body_shell = add_primitive("body_shell", "sphere")
skin_segment = add_primitive("skin_segment", "sphere")
mobile_objects = [spindle, bone_shaft, joint_sphere, body_shell, skin_segment]

scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0
scene["project"] = "Muscle Atlas"
scene["model_status"] = "illustrative_static_scaffold"
scene["next_step"] = "Replace paths with reviewed origin, insertion, wrapping and joint definitions"
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
print(f"Saved Blender seed scene: {OUTPUT}")

bpy.ops.object.select_all(action="DESELECT")
for obj in mobile_objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = spindle
bpy.ops.export_scene.gltf(filepath=str(MOBILE_OUTPUT), export_format="GLB", use_selection=True)
print(f"Exported mobile mesh kit: {MOBILE_OUTPUT}")
