"""Sample OpenSim's official 3-DOF, 9-muscle squat reference at viewer poses.

Run with .cache/opensim-venv/Scripts/python.exe after npm run build:squat-angles.
This is a kinematic lookup: muscle path lengths and moment arms, not forces.
"""

import json
import math
import os
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "assets" / "opensim" / "squatToStand_3dof9musc.osim"
ANGLES = ROOT / "assets" / "opensim" / "squat_angles.json"
OUTPUT = ROOT / "public" / "data" / "squat_opensim_reference.json"
COORDINATES = ROOT / "assets" / "opensim" / "squat_coordinates.sto"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

angles = json.loads(ANGLES.read_text(encoding="utf-8"))
# OpenSim's Windows file loader does not reliably accept non-ASCII directories.
os.chdir(MODEL.parent)
model = osim.Model(MODEL.name)
state = model.initSystem()
coordinates = {name: model.getCoordinateSet().get(name) for name in
               ("hip_flexion_r", "knee_angle_r", "ankle_angle_r")}
muscles = [model.getMuscles().get(index) for index in range(model.getMuscles().getSize())]
joint_frames = {name: model.getJointSet().get(joint_name).getChildFrame() for name, joint_name in
                (("hip", "hip_r"), ("knee", "knee_r"), ("ankle", "ankle_r"),
                 ("back", "back"), ("foot", "foot_ground_r"))}
bone_bodies = {name: model.getBodySet().get(name)
               for name in ("pelvis", "femur_r", "tibia_r", "patella_r", "calcn_r")}
frames = []
max_path_polyline_error = 0.0
for source in angles["frames"]:
    values = {name: source[name] for name in coordinates}
    for name, value in values.items():
        coordinate = coordinates[name]
        if not coordinate.getRangeMin() <= value <= coordinate.getRangeMax():
            raise ValueError(f"{name}={value} outside model range")
        coordinate.setValue(state, value)
    model.assemble(state)
    model.realizePosition(state)
    ankle_ground = joint_frames["ankle"].getPositionInGround(state)

    def viewer_position(point):
        # OpenSim: x fore/aft, y up, z lateral. Viewer: x lateral, y up,
        # z fore/aft. Anchor this fixed-size reference model at right ankle.
        return [0.18 + point[2] - ankle_ground[2],
                0.10 + point[1] - ankle_ground[1],
                point[0] - ankle_ground[0]]

    def blender_position(point):
        x, y, z = viewer_position(point)
        return [0.09 - x, -z, y]

    # OpenSim ground is x forward, y up, z right. The registered Blender
    # study uses x left, y back, z up. Q has determinant +1 and converts
    # body orientations into that same frame. Positions share the moving
    # right-ankle anchor used by the viewer lookup.
    q_rows = ((0, 0, -1), (-1, 0, 0), (0, 1, 0))
    body_frames = {}
    for name, body in bone_bodies.items():
        transform = body.getTransformInGround(state)
        rotation = transform.R()
        matrix = [[sum(q_rows[row][k] * rotation.get(k, col) for k in range(3))
                   for col in range(3)] for row in range(3)]
        body_frames[name] = {"translationM": blender_position(transform.p()),
                             "rotationRows": matrix}

    viewer_joints = {name: viewer_position(frame.getPositionInGround(state))
                     for name, frame in joint_frames.items()}
    values["knee_angle_r_beta"] = model.getCoordinateSet().get("knee_angle_r_beta").getValue(state)
    frame_muscles = {}
    for muscle in muscles:
        length = muscle.getLength(state)
        current_path = muscle.getGeometryPath().getCurrentPath(state)
        points = [viewer_position(current_path.get(index).getLocationInGround(state))
                  for index in range(current_path.getSize())]
        if len(points) < 2:
            raise ValueError(f"Too few path points for {muscle.getName()}")
        polyline_length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
        max_path_polyline_error = max(max_path_polyline_error, abs(polyline_length - length))
        arms = {name: muscle.computeMomentArm(state, coordinate)
                for name, coordinate in coordinates.items()}
        if not math.isfinite(length) or not all(math.isfinite(value) for value in arms.values()):
            raise ValueError(f"Non-finite result for {muscle.getName()}")
        frame_muscles[muscle.getName()] = {"lengthM": length, "momentArmsM": arms,
                                          "viewerPathM": points}
    frames.append({"phase": source["phase"], "coordinatesRad": values,
                   "viewerJointsM": viewer_joints, "blenderBodyFrames": body_frames,
                   "muscles": frame_muscles})

if max_path_polyline_error > 0.005:
    raise ValueError(f"Displayed muscle path differs from model length by {max_path_polyline_error:.4f} m")

baseline = {name: result["lengthM"] for name, result in frames[0]["muscles"].items()}
for frame in frames:
    for name, result in frame["muscles"].items():
        result["ratioToStanding"] = result["lengthM"] / baseline[name]

output = {
    "schemaVersion": 3,
    "status": "reference_model_kinematics_only",
    "model": MODEL.name,
    "modelSource": "https://github.com/opensim-org/opensim-core/tree/main/Bindings/Java/Matlab/examples/Moco/exampleSquatToStand",
    "opensimVersion": osim.GetVersionAndDate(),
    "poseSource": angles["source"],
    "profile": angles["profile"],
    "maximumPolylineErrorM": max_path_polyline_error,
    "limits": ["single right leg model; mirrored labels are not independently calculated",
               "Blender body frames are for research registration, not fitted anatomical joints",
               "no individual scaling, barbell load, muscle activation or force solution"],
    "frames": frames,
}
OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
columns = [
    "/jointset/hip_r/hip_flexion_r/value",
    "/jointset/knee_r/knee_angle_r/value",
    "/jointset/ankle_r/ankle_angle_r/value",
    "/jointset/patellofemoral_r/knee_angle_r_beta/value",
]
lines = ["squat_coordinates", "version=1", f"nRows={len(frames)}", "nColumns=5", "inDegrees=no",
         "endheader", "time\t" + "\t".join(columns)]
for frame in frames:
    q = frame["coordinatesRad"]
    lines.append("\t".join(str(value) for value in [2.8 * frame["phase"], q["hip_flexion_r"],
                                                   q["knee_angle_r"], q["ankle_angle_r"],
                                                   q["knee_angle_r_beta"]]))
COORDINATES.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Exported {len(frames)} frames and {len(muscles)} muscles to {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")
print(f"Exported kinematics to {COORDINATES}")
print(f"Maximum displayed path approximation error: {max_path_polyline_error:.6f} m")
for name in baseline:
    print(name, "deep-squat ratio", round(frames[50]["muscles"][name]["ratioToStanding"], 3))
