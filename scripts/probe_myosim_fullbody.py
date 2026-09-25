"""Audit the assembled MyoSim full-body candidate against our deep-squat data.

This is a structural/kinematic gate only. No muscle force or activation is
transferred to the app. MuJoCo currently cannot open mesh assets below a
non-ASCII Windows path, so an ignored candidate checkout is staged in TEMP.
"""

import json
import math
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache/model-candidates/myo_sim"
OUTPUT = ROOT / "docs/data/myosim_fullbody_candidate_audit.json"
IK = ROOT / ".cache/lower-limb/AB01_ik_50_52.mot"
FRAME_TIME_S = 51.32


def model_import_path():
    if not SOURCE.is_dir():
        raise FileNotFoundError(
            f"Clone https://github.com/MyoHub/myo_sim.git to {SOURCE} first"
        )
    if all(ord(char) < 128 for char in str(SOURCE)):
        return SOURCE
    staged = Path(tempfile.gettempdir()) / "muscle-atlas-myo-sim-candidate"
    # Copy only the model package; the checkout's .git metadata is not needed.
    shutil.copytree(SOURCE / "myo_sim", staged / "myo_sim", dirs_exist_ok=True)
    return staged


def ik_frame():
    lines = IK.read_text(encoding="utf-8").splitlines()
    start = lines.index("endheader")
    columns = lines[start + 1].split()
    rows = ([float(value) for value in line.split()]
            for line in lines[start + 2:] if line.strip())
    values = min(rows, key=lambda row: abs(row[0] - FRAME_TIME_S))
    if abs(values[0] - FRAME_TIME_S) > 1e-6:
        raise ValueError("AB01 target frame missing")
    return dict(zip(columns, values))


def main():
    sys.path.insert(0, str(model_import_path()))
    import mujoco
    import myo_sim

    model, data = myo_sim.load("myofullbody")
    mujoco.mj_forward(model, data)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()
    joints = {}
    for index in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
        joints[name] = {
            "qposIndex": int(model.jnt_qposadr[index]),
            "rangeRad": [float(value) for value in model.jnt_range[index]],
            "type": int(model.jnt_type[index]),
        }
    ik = ik_frame()
    checks = []
    for name in ("hip_flexion_r", "hip_adduction_r", "hip_rotation_r",
                 "knee_angle_r", "ankle_angle_r", "hip_flexion_l",
                 "hip_adduction_l", "hip_rotation_l", "knee_angle_l",
                 "ankle_angle_l"):
        value_deg = ik[name]
        low, high = joints[name]["rangeRad"]
        value_rad = math.radians(value_deg)
        # The OpenSim knee flexion sign differs from the MuJoCo model. This
        # is only a magnitude screen, not a claim that the poses correspond.
        compare = abs(value_rad) if name.startswith("knee_angle") else value_rad
        checks.append({
            "coordinate": name,
            "opensimIkDeg": round(value_deg, 3),
            "myosimRangeDeg": [round(math.degrees(low), 3),
                                  round(math.degrees(high), 3)],
            "rangeCheckConvention": ("knee flexion magnitude only" if
                                     name.startswith("knee_angle") else
                                     "raw angle; coordinate axes not yet aligned"),
            "outsideRange": bool(compare < low - 1e-6 or compare > high + 1e-6),
        })
    # Count actual MuJoCo actuator transmissions. A full-body model can have
    # more paths than anatomical muscle names because the spine is subdivided.
    transmission = Counter(int(value) for value in model.actuator_trntype)
    tendon_actuators = int(sum(value == int(mujoco.mjtTrn.mjTRN_TENDON)
                               for value in model.actuator_trntype))
    report = {
        "status": "full_body_candidate_compilation_and_range_audit_only",
        "source": "https://github.com/MyoHub/myo_sim",
        "revision": revision,
        "repositoryLicense": "Apache-2.0 on MyoSim repository; upstream MoBL-derived arm model rights unresolved for commercial use",
        "backend": "MuJoCo",
        "counts": {
            "generalizedCoordinatesNq": int(model.nq),
            "velocityCoordinatesNv": int(model.nv),
            "bodiesIncludingWorld": int(model.nbody),
            "joints": int(model.njnt),
            "geometries": int(model.ngeom),
            "meshAssets": int(model.nmesh),
            "meshVertices": int(model.nmeshvert),
            "meshFaces": int(model.nmeshface),
            "muscleActuators": int(model.nu),
            "tendons": int(model.ntendon),
            "tendonDrivenActuators": tendon_actuators,
            "sites": int(model.nsite),
            "sensors": int(model.nsensor),
            "defaultPoseContacts": int(data.ncon),
        },
        "defaultPoseModelMassKg": round(float(np.sum(model.body_mass)), 3),
        "transmissionTypes": dict(transmission),
        "ab01DeepSquat": {
            "timeS": FRAME_TIME_S,
            "source": "AB01 experimental IK fitted to a different gait2354 model",
            "rangeChecks": checks,
            "cannotReplayDirectly": True,
            "reasons": [
                "AB01 knees flex about 142 and 139 degrees, beyond MyoSim's 120-degree knee range",
                "OpenSim knee angle sign differs and joint coordinate axes need alignment",
                "MyoSim geometry and mass have not been scaled to AB01",
                "instrumented barbell and hand grip are absent",
            ],
        },
        "productDecision": "local research candidate only; do not bundle or publish until upstream model rights and physics validation are resolved",
    }
    if report["counts"]["muscleActuators"] != 416 or tendon_actuators != 416:
        raise AssertionError("Unexpected MyoSim model structure")
    if not all(item["outsideRange"] for item in checks if
               item["coordinate"].startswith("knee_angle")):
        raise AssertionError("Expected deep-knee flexion to exceed the model range")
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"counts": report["counts"],
                      "massKg": report["defaultPoseModelMassKg"],
                      "outsideRange": [item["coordinate"] for item in checks
                                       if item["outsideRange"]],
                      "output": str(OUTPUT.relative_to(ROOT))}, indent=2))


if __name__ == "__main__":
    main()
