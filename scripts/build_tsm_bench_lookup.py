"""Export a synthetic supine bench-path study from the CC BY 4.0 TSM model.

This is a kinematic feasibility study. The shoulder and elbow endpoints were
chosen to keep the hand approximately over one grip location while the elbow
moves laterally during lowering. It is not measured bench-press motion or a
force/activation solution. Run with .cache/opensim-venv/Scripts/python.exe.
"""

import json
import math
import os
from pathlib import Path

import opensim as osim
from tsm_body_frames import export_body_frames

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "assets" / "opensim" / "thoracoscapular" / "TSM_subject_noWeight.osim"
OUTPUT = ROOT / "public" / "data" / "bench_tsm_reference.json"
KNOTS = ROOT / "assets" / "opensim" / "thoracoscapular" / "bench_trajectory_knots.json"
SAMPLES = 101
DRIVEN = ("plane_elv", "shoulder_elv", "axial_rot", "elbow_flexion")
# Upper position: near-extended elbow. Lower position: elbow flexed and lateral.
# Values are OpenSim joint coordinates, not experimentally observed angles.
TOP = {"plane_elv": 1.24, "shoulder_elv": 1.22, "axial_rot": -1.0,
       "elbow_flexion": 0.40}
BOTTOM = {"plane_elv": -0.10636711, "shoulder_elv": 1.26688518,
          "axial_rot": 0.50842435, "elbow_flexion": 1.94794776}
knots = json.loads(KNOTS.read_text(encoding="utf-8"))["knots"]


def fitted_coordinates(lowered):
    for left, right in zip(knots, knots[1:]):
        start, end = left["loweredFraction"], right["loweredFraction"]
        if lowered <= end + 1e-12:
            blend = max(0.0, min(1.0, (lowered - start) / (end - start)))
            return {name: (1 - blend) * left["coordinatesRad"][name]
                    + blend * right["coordinatesRad"][name] for name in DRIVEN}
    return knots[-1]["coordinatesRad"]

os.chdir(MODEL.parent)  # Keep OpenSim asset paths ASCII-safe on Windows.
model = osim.Model(MODEL.name)
model.initSystem()
coordinates = model.getCoordinateSet()
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
    lowered = math.sin(math.pi * phase) ** 2
    target = fitted_coordinates(lowered)
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
        # Original model is upright: Z is lateral, X is anterior, Y is cranial.
        # Supine view: lateral -> X, anterior -> up (Y), cranial -> bench axis Z.
        return [0.27 + point[2] - shoulder_ground[2],
                0.75 + point[0] - shoulder_ground[0],
                shoulder_ground[1] - point[1]]

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
                state, coordinates.get(coordinate_name)) for coordinate_name in DRIVEN},
            "viewerPathM": points,
        }
    frames.append({
        "phase": phase,
        "coordinatesRad": {name: coordinates.get(name).getValue(state) for name in DRIVEN},
        "viewerJointsM": joints,
        "blenderBodyFrames": export_body_frames(bodies, state, viewer_position, "bench"),
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

top = frames[0]["viewerJointsM"]
bottom = frames[50]["viewerJointsM"]
hand_drop = top["hand"][1] - bottom["hand"][1]
hand_lateral_drift = abs(top["hand"][0] - bottom["hand"][0])
elbow_lateral_change = bottom["elbow"][0] - top["elbow"][0]
maximum_hand_path_error = max(math.dist(
    frame["viewerJointsM"]["hand"],
    [top["hand"][axis] + (bottom["hand"][axis] - top["hand"][axis])
     * math.sin(math.pi * frame["phase"]) ** 2 for axis in range(3)])
    for frame in frames)
if not 0.15 < hand_drop < 0.35 or hand_lateral_drift > 0.04 or elbow_lateral_change < 0.12:
    raise ValueError("Endpoint motion does not resemble the intended bench geometry")
if maximum_hand_path_error > 0.015:
    raise ValueError(f"Full-sweep hand path deviates {maximum_hand_path_error:.4f} m from target")

output = {
    "schemaVersion": 2,
    "status": "bench_research_kinematics_only",
    "model": MODEL.name,
    "source": "https://github.com/ComputationalBiomechanicsLab/rmr-solver/tree/main/OpenSim%20Models/for%20RMR%20solver",
    "license": "CC BY 4.0; see assets/opensim/thoracoscapular/LICENSE_data",
    "opensimVersion": osim.GetVersionAndDate(),
    "maximumPolylineErrorM": maximum_error,
    "maximumLengthStepM": maximum_step,
    "maximumHandPathErrorM": maximum_hand_path_error,
    "handDropM": hand_drop,
    "handLateralDriftM": hand_lateral_drift,
    "elbowLateralChangeM": elbow_lateral_change,
    "limits": [
        "single right shoulder and arm, study subject-specific model",
        "synthetic supine joint sweep fitted to an illustrative hand path, not measured or validated bench-press kinematics",
        "no bilateral barbell, bench contact force, activation, or muscle forces",
        "triceps long head only; no lateral or medial head",
    ],
    "frames": frames,
}
OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n",
                  encoding="utf-8")
print(f"Exported {len(frames)} bench frames, {len(muscles)} paths; "
      f"max polyline error {maximum_error * 1000:.2f} mm, "
      f"max length step {maximum_step * 1000:.2f} mm, "
      f"max hand path error {maximum_hand_path_error * 1000:.2f} mm, "
      f"hand drop {hand_drop * 100:.1f} cm")
