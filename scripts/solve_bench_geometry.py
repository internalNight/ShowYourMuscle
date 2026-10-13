"""Find OpenSim bench arm coordinates from geometric wrist/elbow targets.

Targets describe a flat bench setup, not a fit to measured athletes. This is
an offline authoring aid; the exported poses are re-evaluated by OpenSim.
"""

import json
import os
from pathlib import Path

import numpy as np
import opensim as osim
from scipy.optimize import least_squares


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT / "assets/opensim")
model = osim.Model("cyclistFullBodyMuscle.osim")
for side in ("r", "l"):
    coordinates_to_extend = model.getCoordinateSet().get(f"shoulder_rot_{side}")
    coordinates_to_extend.setRangeMin(-1.55)
    coordinates_to_extend.setRangeMax(1.55)
state = model.initSystem()
coordinates = model.getCoordinateSet()
bodies = model.getBodySet()
fixed = {"pelvis_tilt": -1.55, "pelvis_ty": 0.69,
         "hip_flexion_r": 1.25, "hip_flexion_l": 1.25,
         "knee_angle_r": 0.3, "knee_angle_l": 0.3,
         "ankle_angle_r": 0.5, "ankle_angle_l": 0.5}
for name, value in fixed.items():
    coordinates.get(name).setValue(state, value)


def point(name):
    p = bodies.get(name).getTransformInGround(state).p()
    return np.array([p.get(i) for i in range(3)])


model.realizePosition(state)
print("fixed", {name: point(name).round(3).tolist() for name in
                ("sternum", "head_neck", "tibia_r", "calcn_r")}, flush=True)

# Wrist travels upward over mid-chest while the bar grip width remains fixed.
# Elbow is laterally outside the wrist at the bottom, below it at all phases.
targets = {
    "bottom": {"hand": [0.44, 0.97, 0.34], "elbow": [0.43, 0.73, 0.42]},
    "middle": {"hand": [0.47, 1.14, 0.34], "elbow": [0.45, 0.92, 0.38]},
    "top": {"hand": [0.50, 1.35, 0.34], "elbow": [0.47, 1.11, 0.32]},
}


def solve(side, target, seed):
    names = [f"elv_angle_{side}", f"shoulder_elv_{side}",
             f"shoulder_rot_{side}", f"elbow_flex_{side}"]
    lower = [-1.55, 0 if side == "r" else -2.0, -1.55, 0]
    upper = [1.55, 2.0 if side == "r" else 0, 1.55, 2.5]
    sign = 1 if side == "r" else -1
    wrist = np.array([target["hand"][0], target["hand"][1], sign * target["hand"][2]])
    elbow = np.array([target["elbow"][0], target["elbow"][1], sign * target["elbow"][2]])

    def residual(values):
        for name, value in zip(names, values):
            coordinates.get(name).setValue(state, float(value))
        model.realizePosition(state)
        return np.r_[2.0 * (point(f"hand_{side}") - wrist),
                     1.2 * (point(f"ulna_{side}") - elbow),
                     0.015 * (values - seed)]

    rng = np.random.default_rng(20 if side == "r" else 21)
    seeds = [seed, np.array([-1.25, 0.6 if side == "r" else -0.6, 0, 1.5])]
    seeds.extend(rng.uniform(np.asarray(lower) + 0.01,
                             np.asarray(upper) - 0.01, size=(100, 4)))
    ranked = sorted(seeds, key=lambda guess: float(np.linalg.norm(residual(guess))))
    fits = [least_squares(residual, guess, bounds=(lower, upper),
                          max_nfev=45, ftol=1e-5, xtol=1e-5)
            for guess in ranked[:4]]
    result = min(fits, key=lambda fit: float(np.linalg.norm(residual(fit.x))))
    residual(result.x)
    return ({name: round(float(value), 5) for name, value in zip(names, result.x)},
            point(f"hand_{side}").round(3).tolist(),
            point(f"ulna_{side}").round(3).tolist())


solutions = {}
for key, target in targets.items():
    values = {}
    for side in ("r", "l"):
        previous = solutions.get("middle" if key == "top" else "bottom", {}).get(side, {}).get("values")
        seed = np.array(list(previous.values()) if previous else
                        [-1.1, 0.65 if side == "r" else -0.65, 0, 1.3])
        angles, wrist, elbow = solve(side, target, seed)
        values[side] = {"values": angles, "hand": wrist, "elbow": elbow}
    solutions[key] = values
    print(key, json.dumps(values), flush=True)
