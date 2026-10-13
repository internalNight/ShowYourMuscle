"""Export one OpenSim model's bone transforms and muscle paths for a shared viewer.

Run with the OpenSim 4.6 Python environment. The source model and its Geometry/
directory are obtained from ross-wilkinson/opensim-model-fullBodyMuscleActuated.
Every rendered pose is evaluated by OpenSim; this script does not invent bone or
muscle positions. The prescribed coordinate curves are teaching motions, not IK
fits to measured squat, bench or press trials.
"""

import argparse
import json
import math
import os
from pathlib import Path

import opensim as osim


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache/model-candidates/opensim-model-fullBodyMuscleActuated"
OUTPUT = ROOT / "public/data/unified_opensim_reference.json"
MODEL_NAME = "cyclistFullBodyMuscle.osim"


def vec3(value):
    return [round(value.get(i), 5) for i in range(3)]


def keyed_pose(depth, knots):
    for index in range(len(knots) - 1):
        start, values = knots[index]
        end, following = knots[index + 1]
        if depth <= end or index == len(knots) - 2:
            t = max(0, min(1, (depth - start) / (end - start)))
            return [a + (b - a) * t for a, b in zip(values, following)]
    raise ValueError("No pose knots")


def symmetric_arms(plane, elevation, rotation, elbow):
    return {"elv_angle_r": plane, "elv_angle_l": plane,
            "shoulder_elv_r": elevation, "shoulder_elv_l": -elevation,
            "shoulder_rot_r": rotation, "shoulder_rot_l": -rotation,
            "elbow_flex_r": elbow, "elbow_flex_l": elbow}


def pose_values(action, phase):
    # Smooth 0 -> 1 -> 0 cycle; zero is the same neutral model in every mode.
    depth = math.sin(math.pi * phase) ** 2
    if action == "neutral":
        return {}
    if action == "squat":
        return {
            "pelvis_ty": 0.93,
            "pelvis_tx": 0.0,
            "pelvis_tilt": -0.18 * depth,
            "hip_flexion_r": 1.55 * depth,
            "hip_flexion_l": 1.55 * depth,
            "knee_angle_r": 1.95 * depth,
            "knee_angle_l": 1.95 * depth,
            "ankle_angle_r": 0.50 * depth,
            "ankle_angle_l": 0.50 * depth,
            "elv_angle_r": 1.40 * depth,
            "elv_angle_l": 1.40 * depth,
            "shoulder_elv_r": 1.15 * depth,
            "shoulder_elv_l": -1.15 * depth,
            "elbow_flex_r": 0.15 * depth,
            "elbow_flex_l": 0.15 * depth,
        }
    if action == "bench":
        # The bench arm path is fitted to stable grip width at three key
        # positions of this same OpenSim model; no experimental trial is implied.
        arm = keyed_pose(depth, [(0.0, (-1.25, 0.60, 0.00, 1.50)),
                                 (0.5, (-1.225, 0.645, -0.05, 0.835)),
                                 (1.0, (-1.20, 0.69, 0.00, 0.17))])
        return {
            "pelvis_tilt": -1.40,
            "pelvis_ty": 0.58,
            "hip_flexion_r": 1.80,
            "hip_flexion_l": 1.80,
            "knee_angle_r": 0.90,
            "knee_angle_l": 0.90,
            "ankle_angle_r": 0.50,
            "ankle_angle_l": 0.50,
            **symmetric_arms(*arm)}
    if action == "press":
        # The forward bar clearance and later over-head lockout require a
        # curved 3D shoulder/elbow trajectory in this cycling-derived model.
        arm = keyed_pose(depth, [(0.0, (0.50, 1.00, 0.00, 1.80)),
                                 (0.25, (0.80, 1.55, -0.45, 1.40)),
                                 (0.50, (0.75, 1.90, -0.55, 1.15)),
                                 (0.75, (0.60, 2.50, -0.40, 0.70)),
                                 (0.90, (0.23, 2.81, -0.50, 0.33)),
                                 (1.0, (0.00, 3.00, 0.00, 0.10))])
        return symmetric_arms(*arm)
    raise ValueError(action)


def frame(model, state, body_names, muscles, values):
    coordinates = model.getCoordinateSet()
    for name, value in values.items():
        coordinate = coordinates.get(name)
        if value < coordinate.getRangeMin() - 1e-9 or value > coordinate.getRangeMax() + 1e-9:
            raise ValueError(f"{name}={value} is outside its OpenSim range")
        coordinate.setValue(state, value)
    model.realizePosition(state)
    transforms = []
    for name in body_names:
        transform = model.getBodySet().get(name).getTransformInGround(state)
        rotation = transform.R()
        transforms.append({
            "p": vec3(transform.p()),
            "r": [round(rotation.get(row, col), 6)
                  for row in range(3) for col in range(3)],
        })
    paths = []
    lengths = []
    for muscle in muscles:
        path = muscle.getGeometryPath().getCurrentPath(state)
        points = [vec3(path.get(i).getLocationInGround(state))
                  for i in range(path.getSize())]
        if len(points) < 2:
            raise ValueError(f"{muscle.getName()} has fewer than two path points")
        paths.append(points)
        lengths.append(round(muscle.getLength(state), 6))
    return {"bodies": transforms, "paths": paths, "lengthsM": lengths,
            "coordinates": {name: round(value, 6) for name, value in values.items()}}


def plant_heels(model, state, values, target_y, target_x=None):
    """Translate the OpenSim pelvis so both calcanei retain ground contact."""
    coordinates = model.getCoordinateSet()
    for name, value in values.items():
        coordinates.get(name).setValue(state, value)
    model.realizePosition(state)
    feet = [model.getBodySet().get(f"calcn_{side}").getTransformInGround(state).p()
            for side in ("r", "l")]
    heel_y = sum(foot.get(1) for foot in feet) / 2
    values["pelvis_ty"] += target_y - heel_y
    if target_x is not None:
        heel_x = sum(foot.get(0) for foot in feet) / 2
        values["pelvis_tx"] = values.get("pelvis_tx", 0.0) + target_x - heel_x
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=101)
    parser.add_argument("--actions", nargs="+", choices=("squat", "bench", "press"),
                        default=("squat", "bench", "press"))
    args = parser.parse_args()
    if args.samples < 3 or args.samples % 2 != 1:
        raise ValueError("samples must be an odd number >= 3")
    if not (SOURCE / MODEL_NAME).is_file():
        raise FileNotFoundError(f"clone source model first: {SOURCE}")
    os.chdir(SOURCE)
    model = osim.Model(MODEL_NAME)
    # The source cycling model caps shoulder elevation at 115°. The overhead
    # teaching pose uses the same geometry/path model with extended coordinate
    # bounds, but no claim of calibrated shoulder muscle mechanics above cap.
    coordinates = model.getCoordinateSet()
    coordinates.get("shoulder_elv_r").setRangeMax(3.1)
    coordinates.get("shoulder_elv_l").setRangeMin(-3.1)
    state = model.initSystem()
    body_names = [model.getBodySet().get(i).getName()
                  for i in range(model.getBodySet().getSize())]
    muscles = [model.getMuscles().get(i) for i in range(model.getMuscles().getSize())]
    names = [muscle.getName() for muscle in muscles]
    neutral = frame(model, state, body_names, muscles, {})
    body_index = {name: index for index, name in enumerate(body_names)}
    neutral_heel = [neutral["bodies"][body_index[f"calcn_{side}"]]["p"]
                    for side in ("r", "l")]
    target_x = sum(point[0] for point in neutral_heel) / 2
    target_y = sum(point[1] for point in neutral_heel) / 2
    actions = {}
    if set(args.actions) != {"squat", "bench", "press"}:
        previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if previous["model"] != MODEL_NAME or previous["bodyNames"] != body_names or previous["muscleNames"] != names:
            raise ValueError("Existing export is from a different model")
        actions.update(previous["actions"])
    for action in args.actions:
        frames = []
        for index in range(args.samples):
            phase = index / (args.samples - 1)
            state = model.initSystem()
            values = pose_values(action, phase)
            if action in ("squat", "bench"):
                values = plant_heels(model, state, values, target_y,
                                     target_x if action == "squat" else None)
                state = model.initSystem()
            frames.append(frame(model, state, body_names, muscles, values))
        actions[action] = frames
        print(f"{action}: {len(frames)} OpenSim frames", flush=True)
    report = {
        "schemaVersion": 1,
        "model": MODEL_NAME,
        "source": "https://github.com/ross-wilkinson/opensim-model-fullBodyMuscleActuated",
        "license": "MIT; Copyright (c) 2021 ross-wilkinson",
        "status": "OpenSim-evaluated positions and muscle-tendon lengths; prescribed teaching coordinates with heel contact",
        "bodyNames": body_names,
        "muscleNames": names,
        "neutral": neutral,
        "actions": actions,
        "limitations": [
            "Motion coordinates are teaching presets, not fitted to measured exercise data",
            "Press shoulder elevation extends the cycling model's original coordinate bounds; overhead muscle geometry is unvalidated",
            "No force, activation, joint contact, barbell or bench reaction is calculated",
            "The upstream source omits many vertebra/rib meshes; the source README also notes inaccurate vertebra display",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes, "
          f"{len(body_names)} bodies, {len(muscles)} muscles)", flush=True)


if __name__ == "__main__":
    main()
