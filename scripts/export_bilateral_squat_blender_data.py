"""Export measured bilateral squat kinematics and a welded bar for Blender.

No activation or muscle force is exported. The bar's torso weld is assumed.
"""

import json
import math
import shutil
import tempfile
from pathlib import Path

import opensim as osim

from probe_bilateral_barbell_model import add_barbell, reference_bar_rotation, xyz

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache/lower-limb-raw/AB01/Models/AB01-Scaled1.osim"
IK = ROOT / ".cache/lower-limb/AB01_ik_50_52.mot"
OUTPUT = ROOT / "assets/blender/ab01_bilateral_squat_kinematics.json"
START, END, STEP = 51.0, 51.5, 0.025


def ik_rows():
    lines = IK.read_text(encoding="utf-8").splitlines()
    header = lines.index("endheader")
    names = lines[header + 1].split()
    values = [[float(cell) for cell in line.split()]
              for line in lines[header + 2:] if line.strip()]
    selected = []
    for index in range(round((END - START) / STEP) + 1):
        target = START + index * STEP
        row = min(values, key=lambda item: abs(item[0] - target))
        if abs(row[0] - target) > 1e-5:
            raise ValueError(f"No IK frame near {target}")
        selected.append(dict(zip(names, row)))
    return selected


def apply_row(model, state, row):
    coordinates = model.getCoordinateSet()
    for name, value in row.items():
        if name == "time":
            continue
        angular = not name.endswith(("_tx", "_ty", "_tz"))
        coordinates.get(name).setValue(state, math.radians(value) if angular else value,
                                       False)
    state.setTime(row["time"])
    model.realizePosition(state)


def main():
    osim.Logger.setLevelString("Error")
    with tempfile.NamedTemporaryFile(prefix="muscle_atlas_blender_ab01_", suffix=".osim",
                                     delete=False) as handle:
        source_copy = Path(handle.name)
    shutil.copyfile(SOURCE, source_copy)
    try:
        model = osim.Model(str(source_copy))
        rows = ik_rows()
        reference_state = model.initSystem()
        apply_row(model, reference_state, min(rows, key=lambda row: row["knee_angle_r"]))
        bar_rotation = reference_bar_rotation(model, reference_state)
        bar = add_barbell(model, 20.0, 0.0, bar_rotation)
        state = model.initSystem()
        muscles = [model.getMuscles().get(index)
                   for index in range(model.getMuscles().getSize())]
        if len(muscles) != 54:
            raise ValueError("Expected 54 bilateral muscles")
        frames = []
        max_error = 0.0
        for row in rows:
            apply_row(model, state, row)
            joints = {model.getJointSet().get(index).getName():
                      xyz(model.getJointSet().get(index).getChildFrame()
                          .getPositionInGround(state))
                      for index in range(model.getJointSet().getSize())}
            bodies = {model.getBodySet().get(index).getName():
                      xyz(model.getBodySet().get(index).getPositionInGround(state))
                      for index in range(model.getBodySet().getSize())}
            paths = {}
            for muscle in muscles:
                current = muscle.getGeometryPath().getCurrentPath(state)
                points = [xyz(current.get(index).getLocationInGround(state))
                          for index in range(current.getSize())]
                if len(points) < 2:
                    raise ValueError(f"Missing path for {muscle.getName()}")
                path_length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
                model_length = float(muscle.getLength(state))
                max_error = max(max_error, abs(path_length - model_length))
                paths[muscle.getName()] = {"pointsGroundM": points,
                                           "lengthM": model_length}
            bar_ends = [xyz(bar.findStationLocationInGround(state, osim.Vec3(0, 0, z)))
                        for z in (-1.1, 1.1)]
            frames.append({"timeS": row["time"], "jointsGroundM": joints,
                           "bodiesGroundM": bodies, "muscles": paths,
                           "barEndsGroundM": bar_ends})
        if max_error > 1e-5:
            raise ValueError(f"Muscle polyline mismatch {max_error} m")
        max_end_height_difference = max(abs(frame["barEndsGroundM"][1][1] -
                                            frame["barEndsGroundM"][0][1])
                                        for frame in frames)
        result = {
            "status": "measured_ik_model_kinematics_only_no_muscle_force",
            "subject": "AB01",
            "model": "Scherpereel 2023 AB01-Scaled1 gait2354 with assumed 20 kg torso-weld bar",
            "sourceIk": ".cache/lower-limb/AB01_ik_50_52.mot",
            "barbellMassKg": 20.0,
            "barAttachment": "assumed torso WeldJoint; no measured bar path or grip",
            "barbellTorsoRotationRad": xyz(bar_rotation),
            "timeRangeS": [START, END],
            "frameStepS": STEP,
            "muscleCount": len(muscles),
            "maxMusclePolylineErrorM": max_error,
            "maxBarEndHeightDifferenceM": max_end_height_difference,
            "frames": frames,
        }
        OUTPUT.write_text(json.dumps(result, separators=(",", ":")) + "\n",
                          encoding="utf-8")
        print(json.dumps({"frames": len(frames), "muscles": len(muscles),
                          "maxPathErrorM": max_error,
                          "output": str(OUTPUT.relative_to(ROOT))}, indent=2))
    finally:
        source_copy.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
