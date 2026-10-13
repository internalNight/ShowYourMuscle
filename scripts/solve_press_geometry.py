"""Author a close-to-body strict press path in the existing OpenSim rig."""

import os
from pathlib import Path

import numpy as np
import opensim as osim
from scipy.optimize import least_squares


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT / "assets/opensim")
model = osim.Model("cyclistFullBodyMuscle.osim")
model.getCoordinateSet().get("shoulder_elv_r").setRangeMax(3.1)
model.getCoordinateSet().get("shoulder_elv_l").setRangeMin(-3.1)
state = model.initSystem()
coords = model.getCoordinateSet()
body_set = model.getBodySet()
names = ("elv_angle_r", "shoulder_elv_r", "shoulder_rot_r", "elbow_flex_r")
lower = np.array([-1.57, 0, -.785, 0])
upper = np.array([1.57, 3.05, .785, 2.618])
start = np.array([.558, .716, -.785, 2.618])
end = np.array([0, 3, 0, .1])
targets = [
    (0, [.04, 1.49, .245]),
    (.25, [.08, 1.59, .245]),
    (.5, [.10, 1.70, .245]),
    (.625, [.16, 1.80, .245]),
    (.75, [.03, 1.83, .23]),
    (.875, [-.02, 1.91, .22]),
    (1, [-.075, 1.936, .22]),
]


def point(name):
    p = body_set.get(name).getTransformInGround(state).p()
    return np.array([p.get(i) for i in range(3)])


solutions = []
for depth, target in targets:
    expected = np.array(target)
    guide = start + (end - start) * depth
    previous = solutions[-1] if solutions else start

    def residual(tuning):
        values = np.array([tuning[0], guide[1], tuning[1], guide[3]])
        for name, value in zip(names, values):
            coords.get(name).setValue(state, float(value))
        model.realizePosition(state)
        hand = point("hand_r")
        elbow = point("ulna_r")
        return np.r_[np.array([5, 2, 8]) * (hand - expected),
                     .5 * max(0, elbow[1] - hand[1] + .10),
                     .05 * (values - previous),
                     .03 * (values - guide)]

    seeds = [previous[[0, 2]], guide[[0, 2]]]
    tuning_lower, tuning_upper = lower[[0, 2]], upper[[0, 2]]
    fits = [least_squares(residual, np.clip(seed, tuning_lower + 1e-5, tuning_upper - 1e-5),
                          bounds=(tuning_lower, tuning_upper), max_nfev=50)
            for seed in seeds]
    result = min(fits, key=lambda fit: np.linalg.norm(residual(fit.x)))
    residual(result.x)
    values = np.array([result.x[0], guide[1], result.x[1], guide[3]])
    solutions.append(values)
    print(depth, np.round(values, 5).tolist(),
          "hand", np.round(point("hand_r"), 3).tolist(),
          "elbow", np.round(point("ulna_r"), 3).tolist(), flush=True)
