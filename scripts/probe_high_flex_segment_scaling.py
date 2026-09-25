"""Measure source/candidate lower-body dimensions before scaling research."""

import json
import math

import opensim as osim

from audit_high_flex_candidate import CANDIDATE, ROOT, SUBJECTS, read_ik, set_pose, xyz

OUTPUT = ROOT / "docs/data/high_flex_segment_probe.json"


def joint_point(model, state, joint_name, side):
    joint = model.getJointSet().get(joint_name)
    frame = joint.getParentFrame() if side == "parent" else joint.getChildFrame()
    return xyz(frame.getPositionInGround(state))


def distance(a, b):
    return float(math.dist(a, b))


def dimensions(model, state, knee_name):
    result = {}
    hips = []
    for side in ("r", "l"):
        hip = joint_point(model, state, f"hip_{side}", "child")
        knee_on_femur = joint_point(model, state, f"{knee_name}_{side}", "parent")
        knee_on_tibia = joint_point(model, state, f"{knee_name}_{side}", "child")
        ankle_on_tibia = joint_point(model, state, f"ankle_{side}", "parent")
        ankle_on_foot = joint_point(model, state, f"ankle_{side}", "child")
        metatarsal_on_foot = joint_point(model, state, f"mtp_{side}", "parent")
        result[side] = {
            "effectiveHipToKneeM": distance(hip, knee_on_tibia),
            "modelParentHipToKneeM": distance(hip, knee_on_femur),
            "tibiaKneeToAnkleM": distance(knee_on_tibia, ankle_on_tibia),
            "footAnkleToMtpM": distance(ankle_on_foot, metatarsal_on_foot),
            "kneeParentToChildFrameM": distance(knee_on_femur, knee_on_tibia),
        }
        hips.append(hip)
    result["hipCenterWidthM"] = distance(*hips)
    return result


def main():
    osim.Logger.setLevelString("Error")
    candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
    candidate_state = candidate.initSystem()
    report = {"status": "research_only_unscaled_dimension_probe", "subjects": {}}
    for subject, config in SUBJECTS.items():
        source = osim.Model(str(config["source"].relative_to(ROOT)))
        source_state = source.initSystem()
        row = read_ik(config["ik"], config["intervalS"])[0]
        set_pose(source, source_state, row)
        set_pose(candidate, candidate_state, row, flip_knee=True)
        source_size = dimensions(source, source_state, "knee")
        generic_size = dimensions(candidate, candidate_state, "walker_knee")
        report["subjects"][subject] = {
            "timeS": row["time"],
            "sourceMassKg": float(source.getTotalMass(source_state)),
            "candidateMassKg": float(candidate.getTotalMass(candidate_state)),
            "source": source_size,
            "candidate": generic_size,
        }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(report["subjects"], indent=2))


if __name__ == "__main__":
    main()
