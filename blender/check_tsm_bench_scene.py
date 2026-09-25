"""Verify the saved Blender bench scene against the app lookup at five frames."""

import json
import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--exercise", choices=("bench", "press"), default="bench")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
source = json.loads((ROOT / "public" / "data" / f"{args.exercise}_tsm_reference.json")
                    .read_text(encoding="utf-8"))
scene = bpy.context.scene
assert scene["source_status"] == ("bench_research_kinematics_only" if args.exercise == "bench"
                                  else "shoulder_research_kinematics_only")
assert scene["force_status"] == "not_calculated"
assert scene["body_frame_status"] == "OpenSim_body_transforms_for_registration_review_only"
assert scene.frame_end == 101


def to_blender(point):
    x, y, z = point
    return Vector((x, -z, y))


def assert_near(actual, expected, label):
    error = (actual - expected).length
    assert error < 1e-4, f"{label}: {error:.6f} m"


checks = 0
for frame_number in (1, 26, 51, 76, 101):
    scene.frame_set(frame_number)
    data = source["frames"][frame_number - 1]
    for name, point in data["viewerJointsM"].items():
        obj = bpy.data.objects[f"joint_{name}"]
        assert_near(obj.location, to_blender(point), f"{frame_number} {name}")
        checks += 1
    for name, muscle in data["muscles"].items():
        points = [to_blender(point) for point in muscle["viewerPathM"]]
        segment_index = 0
        while True:
            obj = bpy.data.objects.get(f"muscle_{name}_segment_{segment_index:02d}")
            if obj is None:
                break
            if segment_index < len(points) - 1:
                assert_near(obj.matrix_world @ Vector((0, 0, -1)), points[segment_index],
                            f"{frame_number} {name} {segment_index} start")
                assert_near(obj.matrix_world @ Vector((0, 0, 1)), points[segment_index + 1],
                            f"{frame_number} {name} {segment_index} end")
                checks += 2
            else:
                assert obj.scale.length < 1e-8
                checks += 1
            segment_index += 1
    for body, axes in data["blenderBodyFrames"].items():
        origin = Vector(axes["translationM"])
        rows = axes["rotationRows"]
        for axis in range(3):
            obj = bpy.data.objects[f"body_frame_{body}_{axis}"]
            direction = Vector(tuple(rows[row][axis] for row in range(3)))
            assert_near(obj.matrix_world @ Vector((0, 0, -1)), origin,
                        f"{frame_number} {body} {axis} origin")
            assert_near(obj.matrix_world @ Vector((0, 0, 1)), origin + direction * 0.045,
                        f"{frame_number} {body} {axis} end")
            checks += 2

print(f"CHECKED_TSM_{args.exercise.upper()} {checks} saved joint, path and body-frame assertions")
