"""Export AB02 measured squat poses on a generic high-flexion model.

Research artifact only. This exports geometry, not muscle activation or force.
The upstream model-specific redistribution rights have not been cleared.
"""

import json
import math

import opensim as osim

from audit_high_flex_candidate import CANDIDATE, ROOT, SUBJECTS, read_ik, set_pose, xyz

OUTPUT = ROOT / ".cache/high-flex-scene/ab02_high_flex_kinematics.json"
START, END, STEP = 23.4, 23.9, 0.025


def main():
    osim.Logger.setLevelString("Error")
    model = osim.Model(str(CANDIDATE.relative_to(ROOT)))
    state = model.initSystem()
    muscles = [model.getMuscles().get(index)
               for index in range(model.getMuscles().getSize())]
    rows = read_ik(SUBJECTS["AB02"]["ik"], (START, END))
    selected = []
    for index in range(round((END - START) / STEP) + 1):
        target = START + index * STEP
        row = min(rows, key=lambda item: abs(item["time"] - target))
        if abs(row["time"] - target) > 1e-6:
            raise ValueError(f"No measured IK frame at {target}")
        selected.append(row)
    if len(muscles) != 80 or len(selected) != 21:
        raise AssertionError("Unexpected candidate structure or frame count")

    frames = []
    max_polyline_error = 0.0
    for row in selected:
        set_pose(model, state, row, flip_knee=True)
        joints = {model.getJointSet().get(index).getName():
                  xyz(model.getJointSet().get(index).getChildFrame()
                      .getPositionInGround(state)).tolist()
                  for index in range(model.getJointSet().getSize())}
        paths = {}
        for muscle in muscles:
            path = muscle.getGeometryPath().getCurrentPath(state)
            points = [xyz(path.get(index).getLocationInGround(state)).tolist()
                      for index in range(path.getSize())]
            if len(points) < 2:
                raise ValueError(f"Missing geometry path for {muscle.getName()}")
            length = float(muscle.getLength(state))
            polyline = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
            max_polyline_error = max(max_polyline_error, abs(length - polyline))
            paths[muscle.getName()] = {"pointsGroundM": points,
                                       "opensimLengthM": length,
                                       "polylineLengthM": polyline}
        frames.append({"timeS": row["time"], "jointsGroundM": joints,
                       "kneeFlexionDeg": {side: -row[f"knee_angle_{side}"]
                                          for side in ("r", "l")},
                       "muscles": paths})
    result = {
        "status": "generic_candidate_geometry_on_measured_ik_no_muscle_force",
        "sourceModel": "opensim-org/opensim-models RajagopalLaiUhlrich2023.osim",
        "sourceIk": ".cache/lower-limb/AB02_ik_23_25.mot",
        "subject": "AB02",
        "muscleCount": len(muscles),
        "frameCount": len(frames),
        "timeRangeS": [START, END],
        "frameStepS": STEP,
        "maxStraightPolylineVsOpenSimLengthErrorM": max_polyline_error,
        "pathDisplay": "straight segments between OpenSim current path points; wrapping arcs are approximated",
        "redistribution": "local research only; model-specific rights not yet cleared",
        "frames": frames,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, separators=(",", ":")) + "\n",
                      encoding="utf-8")
    print(json.dumps({"frames": len(frames), "muscles": len(muscles),
                      "maxPolylineErrorM": max_polyline_error,
                      "output": str(OUTPUT.relative_to(ROOT))}, indent=2))


if __name__ == "__main__":
    main()
