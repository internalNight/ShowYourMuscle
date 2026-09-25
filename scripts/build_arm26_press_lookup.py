"""Sample the CC BY 3.0 Arm26 model during a planar overhead arm raise.

This is a research candidate for the elbow/upper-arm portion of a press. It
does not model pectoralis, deltoid, scapular rotation, a barbell, or force.
Run with .cache/opensim-venv/Scripts/python.exe.
"""

import json
import math
import os
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "assets" / "opensim" / "arm26.osim"
OUTPUT = ROOT / "public" / "data" / "press_arm26_reference.json"

# Arm26 is a planar model. This trajectory is a controlled parameter sweep,
# not a measured overhead-press motion or inverse-kinematics solution.
SAMPLES = 101

os.chdir(MODEL.parent)  # OpenSim on Windows cannot reliably load CJK paths.
model = osim.Model(MODEL.name)
state = model.initSystem()
coords = {name: model.getCoordinateSet().get(name)
          for name in ("r_shoulder_elev", "r_elbow_flex")}
muscles = [model.getMuscles().get(i) for i in range(model.getMuscles().getSize())]
shoulder = model.getJointSet().get("r_shoulder").getChildFrame()
elbow = model.getJointSet().get("r_elbow").getChildFrame()
forearm = model.getBodySet().get("r_ulna_radius_hand")
frames = []
maximum_error = 0.0

for index in range(SAMPLES):
    phase = index / (SAMPLES - 1)
    raise_fraction = math.sin(math.pi * phase) ** 2
    values = {"r_shoulder_elev": 0.50 + 2.10 * raise_fraction,
              "r_elbow_flex": 1.55 - 1.30 * raise_fraction}
    for name, value in values.items():
        coordinate = coords[name]
        if not coordinate.getRangeMin() <= value <= coordinate.getRangeMax():
            raise ValueError(f"{name} outside Arm26 range: {value}")
        coordinate.setValue(state, value)
    model.assemble(state)
    model.realizePosition(state)
    shoulder_ground = shoulder.getPositionInGround(state)

    def viewer_position(point):
        return [0.30 + point[2] - shoulder_ground[2],
                1.45 + point[1] - shoulder_ground[1],
                point[0] - shoulder_ground[0]]

    joints = {"shoulder": viewer_position(shoulder_ground),
              "elbow": viewer_position(elbow.getPositionInGround(state)),
              # This station is a visual endpoint, not a measured wrist center.
              "distalForearm": viewer_position(
                  forearm.findStationLocationInGround(state, osim.Vec3(0, -0.25, 0)))}
    frame_muscles = {}
    for muscle in muscles:
        length = muscle.getLength(state)
        path = muscle.getGeometryPath().getCurrentPath(state)
        points = [viewer_position(path.get(i).getLocationInGround(state))
                  for i in range(path.getSize())]
        if len(points) < 2:
            raise ValueError(f"Too few points: {muscle.getName()}")
        error = abs(sum(math.dist(a, b) for a, b in zip(points, points[1:])) - length)
        maximum_error = max(maximum_error, error)
        frame_muscles[muscle.getName()] = {
            "lengthM": length,
            "momentArmsM": {name: muscle.computeMomentArm(state, coordinate)
                            for name, coordinate in coords.items()},
            "viewerPathM": points,
        }
    frames.append({"phase": phase, "coordinatesRad": values,
                   "viewerJointsM": joints, "muscles": frame_muscles})

if maximum_error > 0.005:
    raise ValueError(f"Path polyline error {maximum_error:.4f} m exceeds 5 mm")
baseline = {name: result["lengthM"] for name, result in frames[0]["muscles"].items()}
for frame in frames:
    for name, result in frame["muscles"].items():
        result["ratioToStartingPose"] = result["lengthM"] / baseline[name]

output = {
    "schemaVersion": 1,
    "status": "planar_research_kinematics_only",
    "model": MODEL.name,
    "source": "https://github.com/opensim-org/opensim-models/blob/master/Models/Arm26/arm26.osim",
    "license": "CC BY 3.0; see assets/opensim/NOTICE.txt",
    "opensimVersion": osim.GetVersionAndDate(),
    "maximumPolylineErrorM": maximum_error,
    "limits": ["single right arm, two planar coordinates, six elbow/upper-arm muscles",
               "no pectoralis, deltoid, scapular motion, barbell, person scaling, activation, or force",
               "synthetic angle sweep, not measured press kinematics"],
    "frames": frames,
}
OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n",
                  encoding="utf-8")
print(f"Exported {len(frames)} Arm26 frames, {len(muscles)} muscles, "
      f"max path error {maximum_error * 1000:.2f} mm")
