"""Inventory Z-Anatomy muscle meshes before expanding the mobile reference."""

import json
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".cache" / "z-anatomy-muscle-candidates.json"
meshes = []
for obj in bpy.data.objects:
    if obj.type != "MESH" or len(obj.data.vertices) < 100:
        continue
    if "muscle" not in obj.name.lower():
        continue
    meshes.append({"name": obj.name, "vertices": len(obj.data.vertices)})
meshes.sort(key=lambda item: item["name"].lower())
OUTPUT.write_text(json.dumps(meshes, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"MUSCLE_MESH_INVENTORY {len(meshes)} {OUTPUT}")
