"""Verify sampled evaluated shape keys after reopening a research scene."""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
exercise = args[0] if args else "press"
if exercise not in ("bench", "press"):
    raise ValueError("Expected bench or press")
REPORT = ROOT / f"docs/data/tsm_{exercise}_pectoralis_atlas_probe.json"
report = json.loads(REPORT.read_text(encoding="utf-8"))
scene = bpy.context.scene
if scene.get("pectoralis_atlas_probe_status") != "research geometry, not fiber strain or force":
    raise AssertionError("Research status was not saved")
checked = 0
for row in report["muscles"]:
    obj = bpy.data.objects.get(f"atlas_{row['modelMuscle']}_{exercise}_probe")
    if obj is None or len(obj.data.vertices) != row["vertexCount"]:
        raise AssertionError(f"Missing saved mesh: {row['modelMuscle']}")
    if not obj.data.shape_keys or len(obj.data.shape_keys.key_blocks) != 102:
        raise AssertionError(f"Incomplete shape keys: {row['modelMuscle']}")
    if obj.get("status") != "geometric research deformation; not attachment, strain or force":
        raise AssertionError("Mesh status was not saved")
    for index_text, samples in row["sampledVerticesBlenderM"].items():
        scene.frame_set(int(index_text) + 1)
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            for vertex_text, expected in samples.items():
                actual = mesh.vertices[int(vertex_text)].co
                if (actual - Vector(expected)).length > 1e-5:
                    raise AssertionError(f"Saved pose differs: {row['modelMuscle']} "
                                         f"frame {index_text} vertex {vertex_text}")
                checked += 1
        finally:
            evaluated.to_mesh_clear()
print("CHECKED_TSM_PECTORALIS_ATLAS", exercise, checked,
      "sampled vertices across three meshes and five reopened poses")
