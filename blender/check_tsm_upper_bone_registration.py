"""Check saved upper-arm anatomical mesh proxies against TSM joints."""

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
lookup = json.loads((ROOT / "public/data" / f"{args.exercise}_tsm_reference.json")
                    .read_text(encoding="utf-8"))
report = json.loads((ROOT / "docs/data" / f"tsm_{args.exercise}_upper_bone_registration.json")
                    .read_text(encoding="utf-8"))
scene = bpy.context.scene
assert scene["upper_bone_registration_status"] == report["status"]
assert scene.frame_end == report["frameCount"] == len(lookup["frames"]) == 101
assert len(report["bones"]) == 3


def to_blender(point):
    x, y, z = point
    return Vector((x, -z, y))


checks = 0
for frame_number in (1, 26, 51, 76, 101):
    scene.frame_set(frame_number)
    frame = lookup["frames"][frame_number - 1]
    for row in report["bones"]:
        obj = bpy.data.objects[row["object"]]
        assert obj.type == "MESH" and len(obj.data.vertices) > 100
        assert obj["atlas_source"] in ("Humerus.r", "Radius.r", "Ulna.r")
        assert obj["tsm_body"] == row["modelBody"]
        assert obj["registration_status"] == "5_percent_end_slice_centroids_shared_forearm_fit"
        for label, joint in (("proximal", row["proximalJoint"]),
                             ("distal", row["distalJoint"])):
            actual = obj.matrix_world @ Vector(obj[f"atlas_{label}_local"])
            expected = to_blender(frame["viewerJointsM"][joint])
            error = (actual - expected).length
            assert error <= row["maximumJointProxyResidualM"][label] + 1e-4
            assert error < 0.03, f"{frame_number} {obj.name} {label}: {error:.6f} m"
            checks += 1
        scales = obj.matrix_world.to_scale()
        assert max(scales) - min(scales) < 1e-5
        assert abs(sum(scales) / 3 - row["uniformScale"]) < 1e-5
        checks += 2

print(f"CHECKED_TSM_{args.exercise.upper()}_UPPER_BONES {checks} saved endpoint and scale assertions")
