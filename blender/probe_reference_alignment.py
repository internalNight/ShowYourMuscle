"""Inventory source bone bounds before fitting Z-Anatomy to the OpenSim rig."""

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "public" / "models" / "z_anatomy_reference.glb"
OUTPUT = ROOT / "docs" / "data" / "reference_bone_bounds.json"
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(SOURCE))

keys = ("Femur", "Tibia", "Fibula", "Hip bone", "Sacrum", "Humerus", "Radius", "Ulna")
records = []
for obj in bpy.data.objects:
    if obj.type != "MESH" or obj.name.removesuffix(".l").removesuffix(".r") not in keys:
        continue
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = [min(corner[axis] for corner in corners) for axis in range(3)]
    high = [max(corner[axis] for corner in corners) for axis in range(3)]
    records.append({"name": obj.name, "min": low, "max": high,
                    "center": [(a + b) / 2 for a, b in zip(low, high)]})

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps({"source": SOURCE.relative_to(ROOT).as_posix(), "bounds": records},
                             indent=2) + "\n", encoding="utf-8")
print(f"REFERENCE_BOUNDS {len(records)} objects {OUTPUT}")
for record in records:
    print(record["name"], [round(value, 3) for value in record["center"]],
          [round(b - a, 3) for a, b in zip(record["min"], record["max"])])
