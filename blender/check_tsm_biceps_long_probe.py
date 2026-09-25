"""Reopen a saved TSM biceps probe and inspect its evaluated mesh animation."""

import argparse
import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--exercise", choices=("bench", "press"), required=True)
parser.add_argument("--report", type=Path)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
report_path = args.report or Path("docs/data") / f"tsm_{args.exercise}_biceps_long_probe.json"
report_path = report_path if report_path.is_absolute() else ROOT / report_path
report = json.loads(report_path.read_text(encoding="utf-8"))
obj = bpy.data.objects.get(f"atlas_BIC_long_{args.exercise}_probe")
if obj is None:
    raise AssertionError("Biceps research mesh missing from saved scene")
if len(obj.data.vertices) != report["vertexCount"] or len(obj.data.shape_keys.key_blocks) != 102:
    raise AssertionError("Saved biceps geometry or shape keys incomplete")
if abs(obj["arm_thickness_scale"] - report["appliedThicknessScale"]) > 1e-6:
    raise AssertionError("Saved arm scale differs from builder report")
base = [vertex.co.copy() for vertex in obj.data.vertices]
edges = [(edge.vertices[0], edge.vertices[1]) for edge in obj.data.edges]
base_lengths = [(base[a] - base[b]).length for a, b in edges]
checked = 0
for row in report["sampledEdgeLengthRatios"]:
    bpy.context.scene.frame_set(row["frameIndex"] + 1)
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    positions = [vertex.co.copy() for vertex in mesh.vertices]
    evaluated.to_mesh_clear()
    ratios = [(positions[a] - positions[b]).length / length
              for (a, b), length in zip(edges, base_lengths) if length > 1e-7]
    if abs(min(ratios) - row["minimumEdgeLengthRatio"]) > 0.0002:
        raise AssertionError("Saved minimum edge ratio differs from builder report")
    if abs(max(ratios) - row["maximumEdgeLengthRatio"]) > 0.0002:
        raise AssertionError("Saved maximum edge ratio differs from builder report")
    if min(ratios) < 0.5 or max(ratios) > 1.5:
        raise AssertionError("Coarse geometric edge-ratio gate failed")
    checked += len(ratios)
print(f"CHECKED_TSM_{args.exercise.upper()}_BICEPS_PROBE {checked} evaluated edges across five saved frames")
