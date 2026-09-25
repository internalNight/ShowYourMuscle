"""Export a shoulder/scapula research path sweep from the CC BY 4.0 TSM model.

The sweep is synthetic and not a measured overhead press. It provides only
kinematics, muscle-tendon lengths, and moment arms. It never exports forces.
Run with .cache/opensim-venv/Scripts/python.exe.
"""

import json
import math
import os
from pathlib import Path

import opensim as osim
from tsm_body_frames import export_body_frames

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "assets" / "opensim" / "thoracoscapular" / "TSM_subject_noWeight.osim"
OUTPUT = ROOT / "public" / "data" / "press_tsm_reference.json"
SAMPLES = 101
DRIVEN = ("clav_elev", "scapula_upward_rot", "shoulder_elv", "elbow_flexion")
MOMENT_ARMS = ("scapula_upward_rot", "shoulder_elv", "elbow_flexion")

os.chdir(MODEL.parent)  # Keep OpenSim asset paths ASCII-safe on Windows.
model = osim.Model(MODEL.name)
initial = model.initSystem()
coordinates = model.getCoordinateSet()
defaults = {coordinates.get(i).getName(): coordinates.get(i).getValue(initial)
            for i in range(coordinates.getSize())}
muscles = [model.getMuscles().get(i) for i in range(model.getMuscles().getSize())]
shoulder = model.getJointSet().get("GlenoHumeral").getChildFrame()
elbow = model.getJointSet().get("elbow").getChildFrame()
bodies = model.getBodySet()

frames = []
maximum_error = 0.0
maximum_step = 0.0
previous_lengths = {}

for index in range(SAMPLES):
    phase = index / (SAMPLES - 1)
    fraction = math.sin(math.pi * phase) ** 2
    target = {
        "clav_elev": defaults["clav_elev"] + 0.20 * fraction,
        "scapula_upward_rot": defaults["scapula_upward_rot"] + 0.45 * fraction,
        "shoulder_elv": 0.40 + 1.95 * fraction,
        "elbow_flexion": 1.20 - 1.10 * fraction,
    }
    # Fresh state prevents closed-loop assembly from drifting between the
    # upward and downward halves of a geometrically symmetric test sweep.
    state = model.initSystem()
    for name, value in target.items():
        coordinate = coordinates.get(name)
        if not coordinate.getRangeMin() <= value <= coordinate.getRangeMax():
            raise ValueError(f"{name} outside model range: {value}")
        coordinate.setValue(state, value)
    model.assemble(state)
    model.realizePosition(state)
    shoulder_ground = shoulder.getPositionInGround(state)

    def viewer_position(point):
        return [0.30 + point[2] - shoulder_ground[2],
                1.45 + point[1] - shoulder_ground[1],
                point[0] - shoulder_ground[0]]

    joints = {
        "thorax": viewer_position(bodies.get("thorax").getPositionInGround(state)),
        "clavicle": viewer_position(bodies.get("clavicle").getPositionInGround(state)),
        "scapula": viewer_position(bodies.get("scapula").getPositionInGround(state)),
        "shoulder": viewer_position(shoulder_ground),
        "elbow": viewer_position(elbow.getPositionInGround(state)),
        "hand": viewer_position(bodies.get("hand").getPositionInGround(state)),
    }
    frame_muscles = {}
    for muscle in muscles:
        name = muscle.getName()
        length = muscle.getLength(state)
        current_path = muscle.getGeometryPath().getCurrentPath(state)
        points = [viewer_position(current_path.get(i).getLocationInGround(state))
                  for i in range(current_path.getSize())]
        if len(points) < 2:
            raise ValueError(f"Too few path points: {name}")
        discrepancy = abs(sum(math.dist(a, b) for a, b in zip(points, points[1:])) - length)
        maximum_error = max(maximum_error, discrepancy)
        if name in previous_lengths:
            maximum_step = max(maximum_step, abs(length - previous_lengths[name]))
        previous_lengths[name] = length
        frame_muscles[name] = {
            "lengthM": length,
            "momentArmsM": {coordinate_name: muscle.computeMomentArm(
                state, coordinates.get(coordinate_name)) for coordinate_name in MOMENT_ARMS},
            "viewerPathM": points,
        }
    frames.append({
        "phase": phase,
        "coordinatesRad": {name: coordinates.get(name).getValue(state) for name in DRIVEN},
        "viewerJointsM": joints,
        "blenderBodyFrames": export_body_frames(bodies, state, viewer_position, "press"),
        "muscles": frame_muscles,
    })

if maximum_error > 0.005:
    raise ValueError(f"Polyline discrepancy {maximum_error:.4f} m exceeds 5 mm")
if maximum_step > 0.010:
    raise ValueError(f"Path-length step {maximum_step:.4f} m exceeds 10 mm")
baseline = {name: muscle["lengthM"] for name, muscle in frames[0]["muscles"].items()}
for frame in frames:
    for name, muscle in frame["muscles"].items():
        muscle["ratioToStartingPose"] = muscle["lengthM"] / baseline[name]
for name in baseline:
    if abs(frames[-1]["muscles"][name]["lengthM"] - baseline[name]) > 1e-8:
        raise ValueError(f"Closed sweep did not return to start: {name}")

output = {
    "schemaVersion": 2,
    "status": "shoulder_research_kinematics_only",
    "model": MODEL.name,
    "source": "https://github.com/ComputationalBiomechanicsLab/rmr-solver/tree/main/OpenSim%20Models/for%20RMR%20solver",
    "license": "CC BY 4.0; see assets/opensim/thoracoscapular/LICENSE_data",
    "opensimVersion": osim.GetVersionAndDate(),
    "maximumPolylineErrorM": maximum_error,
    "maximumLengthStepM": maximum_step,
    "limits": [
        "single right shoulder and arm, study subject-specific model",
        "synthetic angle sweep, not measured or validated overhead-press kinematics",
        "no barbell, individual scaling, activation, or muscle forces",
        "triceps long head only; no lateral or medial head",
    ],
    "frames": frames,
}
OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n",
                  encoding="utf-8")
print(f"Exported {len(frames)} TSM frames, {len(muscles)} paths; "
      f"max polyline error {maximum_error * 1000:.2f} mm, "
      f"max length step {maximum_step * 1000:.2f} mm")
