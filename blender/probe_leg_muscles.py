"""Screen right-leg atlas meshes against OpenSim standing muscle paths."""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
REPORT = ROOT / "docs/data/right_leg_muscle_path_screen.json"
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


def to_blender(point):
    x, y, z = point
    return Vector((0.09 - x, -z, y))


def on_path(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
shift = Vector(json.loads(REGISTRATION.read_text(encoding="utf-8"))["translationM"])
frame = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"][0]
records = []
for muscle_name, mesh_name in MAPPING.items():
    obj = bpy.data.objects[mesh_name]
    vertices = [obj.matrix_world @ vertex.co + shift for vertex in obj.data.vertices]
    low, high = min(point.z for point in vertices), max(point.z for point in vertices)
    path = [to_blender(point) for point in frame["muscles"][muscle_name]["viewerPathM"]]
    samples = []
    for fraction in (0.05, 0.25, 0.5, 0.75, 0.95):
        z = high - fraction * (high - low)
        slice_points = [point for point in vertices if abs(point.z - z) < 0.008]
        if not slice_points:
            raise RuntimeError(f"No vertices at {mesh_name} fraction {fraction}")
        center = sum(slice_points, Vector((0, 0, 0))) / len(slice_points)
        target = on_path(path, fraction)
        samples.append({"fractionFromTop": fraction, "centerDistanceM": (center - target).length,
                        "sliceVertexCount": len(slice_points)})
    records.append({"opensimMuscle": muscle_name, "mesh": mesh_name,
                    "vertexCount": len(vertices), "meshHeightM": high - low,
                    "modelPathLengthM": sum((b - a).length for a, b in zip(path, path[1:])),
                    "samples": samples, "maximumCenterDistanceM": max(item["centerDistanceM"] for item in samples)})

report = {"status": "standing_mesh_path_screen_only", "muscles": records,
          "limits": ["z-slice centroids are not attachments or fiber paths",
                     "bbox registration is shared between bones, not fitted per muscle",
                     "one standing pose and right-side reference only"]}
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
for item in records:
    print(item["opensimMuscle"], "vertices", item["vertexCount"], "max offset cm",
          round(item["maximumCenterDistanceM"] * 100, 1))
