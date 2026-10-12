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
            "pelvis_ty": 0.93 - 0.23 * depth,
            "pelvis_tilt": 0.10 * depth,
            "hip_flexion_r": 1.05 * depth,
            "hip_flexion_l": 1.05 * depth,
            "knee_angle_r": 1.35 * depth,
            "knee_angle_l": 1.35 * depth,
            "ankle_angle_r": 0.19 * depth,
            "ankle_angle_l": 0.19 * depth,
        }
    if action == "bench":
        # Model coordinates describe a supine teaching pose. There is no bar or
        # bench contact constraint and these angles are not measured bench data.
        return {
            "pelvis_tilt": -1.40,
            "pelvis_ty": 0.72,
            "hip_flexion_r": 0.25,
            "hip_flexion_l": 0.25,
            "knee_angle_r": 0.42,
            "knee_angle_l": 0.42,
            "shoulder_elv_r": 0.82 + 0.20 * depth,
            "shoulder_elv_l": -0.82 - 0.20 * depth,
            "elbow_flex_r": 1.45 - 1.10 * depth,
            "elbow_flex_l": 1.45 - 1.10 * depth,
        }
    if action == "press":
        return {
            "shoulder_elv_r": 0.25 + 1.50 * depth,
            "shoulder_elv_l": -0.25 - 1.50 * depth,
            "elbow_flex_r": 1.35 - 1.15 * depth,
            "elbow_flex_l": 1.35 - 1.15 * depth,
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=101)
    args = parser.parse_args()
    if args.samples < 3 or args.samples % 2 != 1:
        raise ValueError("samples must be an odd number >= 3")
    if not (SOURCE / MODEL_NAME).is_file():
        raise FileNotFoundError(f"clone source model first: {SOURCE}")
    os.chdir(SOURCE)
    model = osim.Model(MODEL_NAME)
    state = model.initSystem()
    body_names = [model.getBodySet().get(i).getName()
                  for i in range(model.getBodySet().getSize())]
    muscles = [model.getMuscles().get(i) for i in range(model.getMuscles().getSize())]
    names = [muscle.getName() for muscle in muscles]
    neutral = frame(model, state, body_names, muscles, {})
    actions = {}
    for action in ("squat", "bench", "press"):
        frames = []
        for index in range(args.samples):
            phase = index / (args.samples - 1)
            state = model.initSystem()
            frames.append(frame(model, state, body_names, muscles,
                                pose_values(action, phase)))
        actions[action] = frames
        print(f"{action}: {len(frames)} OpenSim frames", flush=True)
    report = {
        "schemaVersion": 1,
        "model": MODEL_NAME,
        "source": "https://github.com/ross-wilkinson/opensim-model-fullBodyMuscleActuated",
        "license": "MIT; Copyright (c) 2021 ross-wilkinson",
        "status": "OpenSim-evaluated positions and muscle-tendon lengths; prescribed teaching coordinates",
        "bodyNames": body_names,
        "muscleNames": names,
        "neutral": neutral,
        "actions": actions,
        "limitations": [
            "Motion coordinates are teaching presets, not fitted to measured exercise data",
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
