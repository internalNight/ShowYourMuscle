"""Fit sparse supine arm-angle knots to a synthetic bench hand path.

This minimizes geometric mismatch only. It does not identify measured joint
motion, muscle recruitment, bench reaction force, or barbell dynamics. Requires
OpenSim, NumPy and SciPy in the research Python environment.
"""

import json
import os
from pathlib import Path

import numpy as np
import opensim as osim
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "assets" / "opensim" / "thoracoscapular" / "TSM_subject_noWeight.osim"
OUTPUT = MODEL.parent / "bench_trajectory_knots.json"
NAMES = ("plane_elv", "shoulder_elv", "axial_rot", "elbow_flexion")
TOP = np.array([1.24, 1.22, -1.0, 0.40])
# The ascent must bring the bar closer to the shoulder along the bench axis.
# This bottom posture puts the hand ~0.167 m caudal to the shoulder, consistent
# in direction and scale with Larsen et al. 2022's group-level bar path events.
# It remains a synthetic posture, not an individual trajectory fit.
BOTTOM = np.array([-0.10636711, 1.26688518, 0.50842435, 1.94794776])

os.chdir(MODEL.parent)
model = osim.Model(MODEL.name)
model.initSystem()
coordinates = model.getCoordinateSet()
shoulder = model.getJointSet().get("GlenoHumeral").getChildFrame()
elbow = model.getJointSet().get("elbow").getChildFrame()
hand = model.getBodySet().get("hand")


def joint_positions(q):
    state = model.initSystem()
    for name, value in zip(NAMES, q):
        coordinates.get(name).setValue(state, float(value))
    model.assemble(state)
    model.realizePosition(state)
    origin = shoulder.getPositionInGround(state)

    def viewer(point):
        return np.array([0.27 + point[2] - origin[2],
                         0.75 + point[0] - origin[0],
                         origin[1] - point[1]])

    return viewer(hand.getPositionInGround(state)), viewer(elbow.getPositionInGround(state))


top_hand, top_elbow = joint_positions(TOP)
bottom_hand, bottom_elbow = joint_positions(BOTTOM)
lower = np.array([coordinates.get(name).getRangeMin() + 0.0001 for name in NAMES])
upper = np.array([coordinates.get(name).getRangeMax() - 0.0001 for name in NAMES])
knots = []
for fraction in np.linspace(0, 1, 7):
    target_hand = top_hand * (1 - fraction) + bottom_hand * fraction
    target_elbow = top_elbow * (1 - fraction) + bottom_elbow * fraction
    linear = TOP * (1 - fraction) + BOTTOM * fraction

    if fraction == 0:
        fitted = TOP
    elif fraction == 1:
        fitted = BOTTOM
    else:
        def residual(q):
            actual_hand, actual_elbow = joint_positions(q)
            return np.r_[(actual_hand - target_hand) / 0.02,
                         (actual_elbow - target_elbow) / 0.08,
                         (q - linear) / 0.8]

        result = least_squares(residual, linear, bounds=(lower, upper), max_nfev=30)
        if not result.success:
            raise RuntimeError(f"Fit failed at {fraction:.3f}: {result.message}")
        fitted = result.x
    actual_hand, actual_elbow = joint_positions(fitted)
    hand_error = float(np.linalg.norm(actual_hand - target_hand))
    elbow_error = float(np.linalg.norm(actual_elbow - target_elbow))
    if hand_error > 0.015 or elbow_error > 0.10:
        raise ValueError(f"Knot error too large at {fraction:.3f}: "
                         f"hand {hand_error:.3f} m, elbow {elbow_error:.3f} m")
    knots.append({
        "loweredFraction": float(fraction),
        "coordinatesRad": dict(zip(NAMES, map(float, fitted))),
        "handTargetM": target_hand.tolist(),
        "handActualM": actual_hand.tolist(),
        "elbowTargetM": target_elbow.tolist(),
        "elbowActualM": actual_elbow.tolist(),
        "handErrorM": hand_error,
        "elbowErrorM": elbow_error,
    })

output = {
    "schemaVersion": 1,
    "status": "synthetic_bench_kinematic_fit_only",
    "model": MODEL.name,
    "coordinateNames": NAMES,
    "knots": knots,
}
OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
print(f"Fitted {len(knots)} bench knots; maximum hand error "
      f"{max(k['handErrorM'] for k in knots) * 1000:.1f} mm, "
      f"maximum elbow error {max(k['elbowErrorM'] for k in knots) * 1000:.1f} mm")
