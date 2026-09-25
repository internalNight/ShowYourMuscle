"""Audit reserves and saturation in measured-input high-flex OpenSim runs."""

import json
import re
from pathlib import Path

import numpy as np

from audit_full_bilateral_static_optimization import read_sto
from audit_high_flex_candidate import ROOT

BASE = ROOT / ".cache/lower-limb/high-flex-static-optimization"
OUTPUT = ROOT / "docs/data/high_flex_static_optimization_audit.json"
RUNS = (
    ("AB02_23_23.1_strength4.2_physiology", "high-flex-so-shallow-physiology-warn.log"),
    ("AB02_23.6_23.7_strength4.2_physiology", "high-flex-so-deep-physiology-warn.log"),
    ("AB02_23.6_23.7_strength4.2_no-physiology",
     "high-flex-so-deep-no-physiology-warn.log"),
    ("AB02_23.6_23.7_strength4.2_no-physiology_jointreserve0.01",
     "high-flex-so-deep-no-physiology-penalty-warn.log"),
    ("AB02_23.6_23.7_strength6_physiology",
     "high-flex-so-deep-physiology-6x-warn.log"),
)
FAILURE = re.compile(r"optimizer could not find a solution at time\s*=\s*([\d.]+)",
                     re.IGNORECASE)


def peak(values, names, columns):
    return {name: round(float(np.max(np.abs(values[:, columns.index(name)]))), 3)
            for name in names}


def audit_run(directory: Path, warning_log: str | None):
    probe = json.loads((directory / "probe.json").read_text(encoding="utf-8"))
    activation_names, activation = read_sto(next(directory.glob("*activation.sto")))
    force_names, forces = read_sto(next(directory.glob("*force.sto")))
    if not np.allclose(activation[:, 0], forces[:, 0]) or not np.isfinite(
            activation).all() or not np.isfinite(forces).all():
        raise AssertionError("Nonmatching times or nonfinite OpenSim output")
    if len(activation_names) < 81 or len(activation) != 21:
        raise AssertionError("Expected 80 model muscles and 21 frames")
    if any(name.startswith("reserve_") for name in activation_names[1:81]):
        raise AssertionError("First 80 activation columns are not muscles")
    muscles = activation[:, 1:81]
    if np.min(muscles) < -1e-5 or np.max(muscles) > 1.001:
        raise AssertionError("Muscle activation outside nominal bounds")
    if warning_log is None:
        failure_times = None
        valid = np.ones(len(activation), dtype=bool)
    else:
        log = (ROOT / ".cache/lower-limb" / warning_log).read_text(
            encoding="utf-8", errors="replace")
        failure_times = [float(match.rstrip(".")) for match in FAILURE.findall(log)]
        valid = np.array([not any(abs(time - failed) < 1e-4
                                  for failed in failure_times)
                          for time in activation[:, 0]], dtype=bool)
        if len(failure_times) != int(np.sum(~valid)):
            raise AssertionError("Optimizer warnings did not match output frames")
    if not np.any(valid):
        raise AssertionError("No converged frames to audit")
    valid_muscles = muscles[valid]
    valid_forces = forces[valid]
    pelvis_translation = [f"reserve_pelvis_{axis}" for axis in
                          ("tx", "ty", "tz")]
    pelvis_rotation = [f"reserve_pelvis_{axis}" for axis in
                       ("tilt", "list", "rotation")]
    lower_joints = [f"reserve_{name}_{side}" for side in ("r", "l")
                    for name in ("hip_flexion", "hip_adduction", "hip_rotation",
                                 "knee_angle", "ankle_angle")]
    built_in = ["lumbar_ext", "lumbar_bend", "lumbar_rot"]
    row = {
        "run": directory.name,
        "toolCompleted": probe["toolCompleted"],
        "intervalS": probe["intervalS"],
        "musclePhysiology": probe["useMusclePhysiology"],
        "strengthMultiplier": probe["strengthMultiplier"],
        "jointReserveOptimalForceNmPerControl": probe.get(
            "jointReserveOptimalForceNmPerControl", 1),
        "frameCount": len(activation),
        "frameConvergenceVerifiedByWarningLog": warning_log is not None,
        "failedFrameCount": len(failure_times) if failure_times is not None else None,
        "failedFrameTimesS": ([round(time, 3) for time in failure_times]
                              if failure_times is not None else None),
        "convergedFrameCount": int(np.sum(valid)) if warning_log else None,
        "muscleCount": 80,
        "musclesAtActivationUpperBoundConvergedFrames": int(np.sum(
            np.any(valid_muscles >= 0.99, axis=1))),
        "upperBoundMuscleFrameCountsConverged": {
            activation_names[index]: int(np.sum(valid_muscles[:, index - 1] >= 0.99))
            for index in range(1, 81)
            if np.any(valid_muscles[:, index - 1] >= 0.99)
        },
        "maximumConvergedMuscleActivation": round(float(np.max(valid_muscles)), 4),
        "pelvisTranslationReserveNConverged": peak(valid_forces, pelvis_translation,
                                            force_names),
        "pelvisRotationReserveNmConverged": peak(valid_forces, pelvis_rotation,
                                         force_names),
        "hipKneeAnkleReserveNmConverged": peak(valid_forces, lower_joints, force_names),
        "builtInLumbarActuatorNmConverged": peak(valid_forces, built_in, force_names),
    }
    return row


def main():
    report = {
        "status": "research_only_high_flex_static_optimization_rejected_for_personal_force",
        "method": "OpenSim 4.6 StaticOptimization on measured AB02 IK and force plates; no force-plate free moment; candidate segment scaled and generic max isometric forces uniformly multiplied by 4.2",
        "runs": [audit_run(BASE / name, warning_log)
                 for name, warning_log in RUNS],
        "limitations": [
            "tool completion and 21 output rows do not prove every frame converged; runs without captured warning logs are unverified",
            "metrics exclude warning-identified failed frames where warning logs are available",
            "force and muscle activation columns were parsed separately; reserve and built-in lumbar actuators are not muscle force",
            "candidate has generic pelvis/trunk mass properties and unregistered contact geometry",
            "measured kinematics and ground force are inputs, not predicted by phone data",
            "4.2x muscle strength is a numerical feasibility choice, not individual calibration",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(report["runs"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
