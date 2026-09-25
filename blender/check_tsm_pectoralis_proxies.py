"""Verify saved Blender shape keys against the pectoralis proxy report."""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--exercise", choices=("bench", "press"), required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
report = json.loads((ROOT / "docs/data" / f"tsm_{args.exercise}_pectoralis_path_proxies.json")
                    .read_text(encoding="utf-8"))
checked = 0
for muscle in report["muscles"]:
    obj = bpy.data.objects.get(f'{muscle["modelMuscle"]}_{args.exercise}_path_volume_proxy')
    if obj is None:
        raise AssertionError(f'Missing {muscle["modelMuscle"]}')
    if len(obj.data.vertices) != muscle["vertexCount"]:
        raise AssertionError('Vertex count changed')
    if len(obj.data.shape_keys.key_blocks) != muscle["shapeKeyCount"]:
        raise AssertionError('Shape key count changed')
    for sample in muscle["sampledVertices"]:
        scene_frame = sample["frameIndex"] + 1
        bpy.context.scene.frame_set(scene_frame)
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for key, expected in sample["verticesBlenderM"].items():
            actual = evaluated.data.vertices[int(key)].co
            if (actual - Vector(expected)).length > 1e-6:
                raise AssertionError(f'{obj.name} frame {scene_frame} vertex {key} mismatch')
            checked += 1
print('CHECKED_PECTORALIS_PROXIES', args.exercise, checked)
