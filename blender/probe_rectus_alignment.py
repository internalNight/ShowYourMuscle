"""Quantify the static right rectus femoris mesh to OpenSim path offset."""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
REPORT = ROOT / "docs/data/rectus_rest_alignment_probe.json"
TARGET = "Rectus femoris muscle.r"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
obj = bpy.data.objects[TARGET]
vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
shift = Vector(json.loads(REGISTRATION.read_text(encoding="utf-8"))["translationM"])
vertices = [point + shift for point in vertices]
low = min(point.z for point in vertices)
high = max(point.z for point in vertices)
frame = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"][0]
path = [Vector((0.09 - p[0], -p[2], p[1]))
        for p in frame["muscles"]["rect_fem_r"]["viewerPathM"]]
segments = [(b - a).length for a, b in zip(path, path[1:])]
path_length = sum(segments)


def on_path(fraction):
    remaining = max(0, min(1, fraction)) * path_length
    for (a, b), length in zip(zip(path, path[1:]), segments):
        if remaining <= length:
            return a.lerp(b, remaining / length)
        remaining -= length
    return path[-1]


samples = []
for t in (0.05, 0.25, 0.5, 0.75, 0.95):
    z = high - t * (high - low)
    points = [point for point in vertices if abs(point.z - z) < 0.008]
    if not points:
        raise RuntimeError(f"No mesh vertices near path fraction {t}")
    center = sum(points, Vector((0, 0, 0))) / len(points)
    target = on_path(t)
    samples.append({"fractionFromProximal": t, "meshCenterM": list(center),
                    "opensimPathM": list(target), "centerDistanceM": (center - target).length,
                    "sliceVertexCount": len(points)})

report = {
    "status": "static_mesh_to_model_path_probe_only",
    "mesh": TARGET,
    "opensimMuscle": "rect_fem_r",
    "vertexCount": len(vertices),
    "meshHeightRangeM": [low, high],
    "meshLongitudinalExtentM": high - low,
    "opensimPathLengthM": path_length,
    "samples": samples,
    "limitations": ["z-slice centroids are not measured muscle attachments",
                    "path fraction is not a verified correspondence to anatomical fibers",
                    "single right-side standing reference only"],
}
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("RECTUS_ALIGNMENT_PROBE", len(vertices), "vertices; sample distances cm",
      [round(sample["centerDistanceM"] * 100, 1) for sample in samples])
