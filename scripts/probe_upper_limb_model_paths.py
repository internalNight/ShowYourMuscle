"""Check whether one dataset-scaled OpenSim arm model follows measured poses.

This audits path length and joint moment arms, not muscle activation or force.
Run with the local OpenSim research Python environment.
"""

import json
import math
import os
from pathlib import Path

import numpy as np
import opensim as osim


ROOT = Path(__file__).resolve().parents[1]
SUBJECT = "S01"
SOURCE = ROOT / ".cache/upper-limb-torque" / SUBJECT
OUTPUT = ROOT / "docs/data/upper_limb_opensim_path_probe.json"
COORDINATES = ("elv_angle", "shoulder_elv", "shoulder_rot", "elbow_flexion",
               "pro_sup", "deviation", "flexion")
MOMENT_ARM_COORDINATES = ("shoulder_elv", "elbow_flexion")


def main():
    positions = np.genfromtxt(SOURCE / "MJ/T0/humanPositions.csv", delimiter=",", names=True)
    # OpenSim's Windows C++ file loader cannot open this workspace's Chinese
    # absolute path, while an ASCII relative path from the project root works.
    os.chdir(ROOT)
    model = osim.Model(f".cache/upper-limb-torque/{SUBJECT}/scaledModel.osim")
    state = model.initSystem()
    muscles = model.getMuscles()
    coords = model.getCoordinateSet()
    indices = sorted(set((0, len(positions) // 4, len(positions) // 2,
                          3 * len(positions) // 4, len(positions) - 1)))
    frames = []
    for index in indices:
        row = positions[index]
        for name in COORDINATES:
            coords.get(name).setValue(state, float(row[name]), False)
        model.assemble(state)
        max_angle_error = max(abs(coords.get(name).getValue(state) - float(row[name]))
                              for name in COORDINATES)
        if max_angle_error > 1e-5:
            raise ValueError(f"coordinate mismatch at frame {index}: {max_angle_error}")
        model.realizePosition(state)
        measurements = []
        for number in range(muscles.getSize()):
            muscle = muscles.get(number)
            length = muscle.getLength(state)
            arms = {name: muscle.computeMomentArm(state, coords.get(name))
                    for name in MOMENT_ARM_COORDINATES}
            if not all(math.isfinite(value) for value in (length, *arms.values())) or length <= 0:
                raise ValueError(f"invalid OpenSim path at frame {index}: {muscle.getName()}")
            measurements.append({"muscle": muscle.getName(), "pathLengthM": round(length, 6),
                                 "momentArmM": {key: round(value, 6) for key, value in arms.items()}})
        frames.append({"sourceFrame": index, "timeS": round(float(row["TIME"]), 3),
                       "maximumAppliedCoordinateErrorRad": max_angle_error,
                       "muscles": measurements})
    report = {
        "status": "pose_to_path_feasibility_only_not_bench_or_muscle_force_validation",
        "source": "https://zenodo.org/records/11209324",
        "subject": SUBJECT, "task": "MJ/T0 multi-joint tracking",
        "modelName": model.getName(), "bodyCount": model.getBodySet().getSize(),
        "jointCount": model.getJointSet().getSize(), "muscleCount": muscles.getSize(),
        "modelMassKg": model.getTotalMass(state),
        "frames": frames,
        "limitations": [
            "Only 5 frames from one person; no torque balance or external-force replay.",
            "The archive lacks referenced VTP display meshes; OpenSim path computation succeeds without them.",
            "The task is not bench press or overhead press, and path lengths/moment arms are not single-muscle forces.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("model", report["modelName"], "frames", len(frames),
          "muscles", report["muscleCount"], "saved", OUTPUT)


if __name__ == "__main__":
    main()
