"""Screen the official Rajagopal-Lai-Uhlrich model for squat pose reuse.

This checks coordinate ranges and joint-axis compatibility, not dynamics or
muscle force. The source IK belongs to a different, subject-scaled model.
"""

import json
import math
import subprocess
from pathlib import Path

import numpy as np
import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / ".cache/model-candidates/opensim-models"
CANDIDATE = REPO / "Models/Rajagopal/RajagopalLaiUhlrich2023.osim"
OUTPUT = ROOT / "docs/data/high_flex_squat_candidate_audit.json"
SUBJECTS = {
    "AB01": {"ik": ROOT / ".cache/lower-limb/AB01_ik_50_52.mot",
             "source": ROOT / ".cache/lower-limb-raw/AB01/Models/AB01-Scaled1.osim",
             "intervalS": (51.0, 51.5), "deepestS": 51.32},
    "AB02": {"ik": ROOT / ".cache/lower-limb/AB02_ik_23_25.mot",
             "source": ROOT / ".cache/lower-limb-raw/AB02/Models/AB02-Scaled1.osim",
             "intervalS": (23.4, 23.9), "deepestS": 23.685},
}


def read_ik(path, interval):
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index("endheader")
    names = lines[start + 1].split()
    return [dict(zip(names, values)) for values in
            ([float(value) for value in line.split()]
             for line in lines[start + 2:] if line.strip())
            if interval[0] - 1e-7 <= values[0] <= interval[1] + 1e-7]


def set_pose(model, state, row, flip_knee=False):
    coordinates = model.getCoordinateSet()
    for name, value in row.items():
        if name == "time":
            continue
        candidate = coordinates.get(name)
        angular = not name.endswith(("_tx", "_ty", "_tz"))
        if flip_knee and name in ("knee_angle_r", "knee_angle_l"):
            value = -value
        candidate.setValue(state, math.radians(value) if angular else value,
                           False)
    state.setTime(row["time"])
    model.assemble(state)
    model.realizePosition(state)


def xyz(value):
    return np.array([value[index] for index in range(3)])


def landmark(model, state, name):
    joint = model.getJointSet().get(name)
    return xyz(joint.getChildFrame().getPositionInGround(state))


def vector_angle_deg(a, b):
    cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def main():
    osim.Logger.setLevelString("Error")
    candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
    candidate_state = candidate.initSystem()
    muscle_count = candidate.getMuscles().getSize()
    if muscle_count != 80:
        raise AssertionError("Expected 80 lower-body muscles")
    knee_max = candidate.getCoordinateSet().get("knee_angle_r").getRangeMax()
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    subjects = {}
    for subject, config in SUBJECTS.items():
        rows = read_ik(config["ik"], config["intervalS"])
        if len(rows) != 101:
            raise AssertionError(f"Expected 101 IK rows for {subject}")
        source = osim.Model(str(config["source"].relative_to(ROOT)))
        source_state = source.initSystem()
        outside = {side: [] for side in ("r", "l")}
        for row in rows:
            for side in ("r", "l"):
                flexion = math.radians(-row[f"knee_angle_{side}"])
                if flexion > knee_max + 1e-9:
                    outside[side].append((row["time"], math.degrees(flexion)))
        samples = []
        sample_times = (rows[0]["time"], config["deepestS"], rows[-1]["time"])
        for target_time in sample_times:
            row = min(rows, key=lambda item: abs(item["time"] - target_time))
            if abs(row["time"] - target_time) > 1e-6:
                raise AssertionError("Sample time not on IK grid")
            set_pose(source, source_state, row)
            set_pose(candidate, candidate_state, row, flip_knee=True)
            segment_angles = {}
            for side in ("r", "l"):
                src_hip = landmark(source, source_state, f"hip_{side}")
                src_knee = landmark(source, source_state, f"knee_{side}")
                src_ankle = landmark(source, source_state, f"ankle_{side}")
                cand_hip = landmark(candidate, candidate_state, f"hip_{side}")
                cand_knee = landmark(candidate, candidate_state,
                                     f"walker_knee_{side}")
                cand_ankle = landmark(candidate, candidate_state,
                                      f"ankle_{side}")
                segment_angles[side] = {
                    "femurAxisDifferenceDeg": round(vector_angle_deg(
                        src_knee - src_hip, cand_knee - cand_hip), 3),
                    "tibiaAxisDifferenceDeg": round(vector_angle_deg(
                        src_ankle - src_knee, cand_ankle - cand_knee), 3),
                }
            samples.append({"timeS": row["time"], "segmentAxisDifferences":
                            segment_angles})
        subjects[subject] = {
            "sourceMassKg": round(float(source.getTotalMass(source_state)), 3),
            "frameCount": len(rows),
            "kneeFlexionDegRange": {side: [
                round(min(-row[f"knee_angle_{side}"] for row in rows), 3),
                round(max(-row[f"knee_angle_{side}"] for row in rows), 3),
            ] for side in ("r", "l")},
            "kneeFramesOutsideModelRange": {side: len(items) for side, items
                                             in outside.items()},
            "maximumExcessKneeFlexionDeg": {side: round(max(
                (value - math.degrees(knee_max) for _, value in items),
                default=0), 3) for side, items in outside.items()},
            "sampleAxisComparisons": samples,
        }
    report = {
        "status": "research_only_high_flexion_range_and_joint_axis_screen",
        "source": "https://github.com/opensim-org/opensim-models/tree/master/Models/Rajagopal",
        "revision": revision,
        "model": "RajagopalLaiUhlrich2023.osim",
        "modelMassKg": round(float(candidate.getTotalMass(candidate_state)), 3),
        "bodies": candidate.getBodySet().getSize(),
        "joints": candidate.getJointSet().getSize(),
        "coordinates": candidate.getCoordinateSet().getSize(),
        "muscles": muscle_count,
        "kneeRangeDeg": [round(math.degrees(candidate.getCoordinateSet().get(
            "knee_angle_r").getRangeMin()), 3),
                         round(math.degrees(knee_max), 3)],
        "coordinateMapping": "source gait2354 knee angle sign inverted; other same-name IK coordinates tentatively copied; pelvis markers and body geometry not registered",
        "subjects": subjects,
        "productDecision": "candidate for deep-squat lower-limb research; no personal muscle-force use",
        "limitations": [
            "candidate is generic and not scaled to either participant",
            "joint-axis comparison does not validate muscle paths or force",
            "upper-body joints are present but the 80 muscles actuate the lower body",
            "model-specific redistribution rights need checking before bundling",
        ],
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(json.dumps({"model": report["model"], "muscles": muscle_count,
                      "kneeRangeDeg": report["kneeRangeDeg"],
                      "subjects": subjects}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
