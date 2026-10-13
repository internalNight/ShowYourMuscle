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
            "hip_flexion_r": 1.35 * depth,
            "hip_flexion_l": 1.35 * depth,
            "knee_angle_r": 1.65 * depth,
            "knee_angle_l": 1.65 * depth,
            "ankle_angle_r": 0.30 * depth,
            "ankle_angle_l": 0.30 * depth,
            "elv_angle_r": 1.40 * depth,
            "elv_angle_l": 1.40 * depth,
            "shoulder_elv_r": 1.15 * depth,
            "shoulder_elv_l": -1.15 * depth,
            "elbow_flex_r": 0.15 * depth,
            "elbow_flex_l": 0.15 * depth,
        }
    if action == "bench":
        # Supine torso, planted feet and symmetric vertical hand travel.
        # The source model is for cycling, so this remains a teaching pose.
        return {
            "pelvis_tilt": -1.40,
            "pelvis_ty": 0.58,
            "hip_flexion_r": 1.50,
            "hip_flexion_l": 1.50,
            "knee_angle_r": 1.00,
            "knee_angle_l": 1.00,
            "elv_angle_r": -1.50,
            "elv_angle_l": -1.50,
            "shoulder_elv_r": 0.70,
            "shoulder_elv_l": -0.70,
            "elbow_flex_r": 1.30 - 1.10 * depth,
            "elbow_flex_l": 1.30 - 1.10 * depth,
        }
    if action == "press":
        return {
            "elv_angle_r": 0.50 * (1 - depth),
            "elv_angle_l": 0.50 * (1 - depth),
            "shoulder_elv_r": 1.00 + 2.00 * depth,
            "shoulder_elv_l": -1.00 - 2.00 * depth,
            "elbow_flex_r": 1.80 - 1.70 * depth,
            "elbow_flex_l": 1.80 - 1.70 * depth,
        }
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
