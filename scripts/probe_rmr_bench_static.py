"""Research-only static RMR compatibility and load sensitivity probe.

Requires the separate ComputationalBiomechanicsLab/rmr-solver-py checkout in
.cache/model-candidates/rmr-solver-py, OpenSim, NumPy, and SciPy. Its Python 3.13
GH constraint dataclass needs a local compatibility patch (see research notes).
No result from this file is shipped to or displayed in the application.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT / ".cache" / "model-candidates" / "rmr-solver-py"
MODEL = ROOT / "assets" / "opensim" / "thoracoscapular" / "TSM_subject_noWeight.osim"
LOOKUP = ROOT / "public" / "data" / "bench_tsm_reference.json"

parser = argparse.ArgumentParser()
parser.add_argument("--gh-constraint", action="store_true",
                    help="Use the solver's glenohumeral stability constraint (requires Python 3.13 patch).")
parser.add_argument("--bench-support-sweep", action="store_true",
                    help="Research sensitivity sweep with prescribed thorax reaction at three lateral points.")
args = parser.parse_args()
OUTPUT = ROOT / "docs" / "data" / (
    "rmr_bench_support_sweep.json" if args.bench_support_sweep else
    "rmr_bench_static_probe.json" if args.gh_constraint else
    "rmr_bench_static_probe_no_gh.json")

code_dir = CHECKOUT / "Code"
if not (code_dir / "RMRsolver.py").exists():
    raise FileNotFoundError("Clone ComputationalBiomechanicsLab/rmr-solver-py into " + str(CHECKOUT))
if args.gh_constraint and "@dataclass\n            class paramsGH:" in (code_dir / "RMRsolver.py").read_text(encoding="utf-8"):
    raise RuntimeError("For Python 3.13, remove the @dataclass line immediately before paramsGH "
                       "in the ignored research checkout; see docs/卧推负重研究.md")
sys.path.insert(0, str(code_dir))
from RMRsolver import RMRsolver  # noqa: E402
from utilsObjectives import ActSquared  # noqa: E402

source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=CHECKOUT,
                                        text=True).strip()
source_modified = bool(subprocess.check_output(["git", "status", "--porcelain"],
                                               cwd=CHECKOUT, text=True).strip())
frame = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"][50]


def run_case(load_kg, hand_effort_lateral_ratio, support_z_m=None):
    # Supine export mapped original model anterior X to viewer vertical Y and
    # original lateral Z to viewer lateral X. Gravity therefore points in -X.
    os.chdir(MODEL.parent)
    model = osim.Model(MODEL.name)
    model.setGravity(osim.Vec3(-9.80665, 0, 0))
    bodies = model.getBodySet()
    model_mass_kg = sum(bodies.get(index).getMass() for index in range(bodies.getSize()))
    vertical_force = load_kg * 9.80665 / 2
    load = osim.PrescribedForce()
    load.setName("research_hand_load")
    load.connectSocket_frame(model.getBodySet().get("hand"))
    load.setForceIsInGlobalFrame(True)
    load.setForceFunctions(osim.Constant(-vertical_force), osim.Constant(0),
                           osim.Constant(-hand_effort_lateral_ratio * vertical_force))
    load.setPointIsInGlobalFrame(False)
    load.setPointFunctions(osim.Constant(0), osim.Constant(0), osim.Constant(0))
    model.addForce(load)
    support_reaction_n = None
    if support_z_m is not None:
        # A prescribed static equilibrium force is a controlled sensitivity
        # experiment. Its magnitude is the model weight plus half the barbell
        # weight; the unknown bench center of pressure remains a free choice.
        support_reaction_n = model_mass_kg * 9.80665 + vertical_force
        support = osim.PrescribedForce()
        support.setName("research_bench_reaction")
        support.connectSocket_frame(bodies.get("thorax"))
        support.setForceIsInGlobalFrame(True)
        support.setForceFunctions(osim.Constant(support_reaction_n),
                                  osim.Constant(0), osim.Constant(0))
        support.setPointIsInGlobalFrame(False)
        support.setPointFunctions(osim.Constant(-0.10), osim.Constant(0),
                                  osim.Constant(support_z_m))
        model.addForce(support)
    solver = RMRsolver(model, constrainActDyn=False, constrainGHjoint=args.gh_constraint,
                       outputJoint=["GlenoHumeral", "scapulothoracic"], visualize=False)
    solver.setObjective(ActSquared(np.r_[np.ones(solver.muscleNum),
                                           10 * np.ones(solver.actuatorNum - solver.muscleNum)]))
    position = np.array([coordinate.getValue(solver.state) for coordinate in solver.coordinates])
    for name, value in frame["coordinatesRad"].items():
        position[solver.coordinateNames.index(name)] = value
    actuation, _, _, _, info = solver.solve(0.0, position, np.zeros(solver.coordinateNum),
                                            np.zeros(solver.coordinateNum))
    reserves = dict(zip(solver.actuatorNames[solver.muscleNum:],
                        map(float, actuation[solver.muscleNum:])))
    thorax_rotations = [reserves[f"ground_thorax_rot_{axis}_actuator"]
                        for axis in ("x", "y", "z")]
    return {
        "barbellKg": load_kg,
        "handEffortLateralRatio": hand_effort_lateral_ratio,
        "modelMassKg": model_mass_kg,
        "prescribedBenchReactionN": support_reaction_n,
        "benchContactPointThoraxM": [-0.10, 0, support_z_m] if support_z_m is not None else None,
        "success": bool(info["success"]),
        "message": str(info["message"]),
        "peakMuscleActivation": float(np.max(actuation[:solver.muscleNum])),
        "ghReactionMagnitudeN": float(info["GHjointForce"]) if args.gh_constraint else None,
        "ghReactionAngleDeg": float(info["GHjointAngle"]) if args.gh_constraint else None,
        "ghMaximumAllowedAngleDeg": float(info["GHjointMaxAngle"]) if args.gh_constraint else None,
        "reserveActuationSI": reserves,
        "thoraxRotationReserveNormNm": float(np.linalg.norm(thorax_rotations)),
        "note": "reserve units follow each model coordinate (translation N, rotation N m)",
    }


cases = ([run_case(load, lateral, offset)
          for load, lateral, offset in ((0, 0, -0.08), (0, 0, 0), (0, 0, 0.08),
                                        (20, 0, -0.08), (20, 0, 0), (20, 0, 0.08),
                                        (20, 0.4, 0))]
         if args.bench_support_sweep else
         [run_case(0, 0), run_case(20, 0), run_case(20, 0.4)])
output = {
    "status": ("research_only_prescribed_reaction_not_measured_contact"
               if args.bench_support_sweep else "research_only_missing_bench_contact_and_measured_kinetics"),
    "solverSource": "https://github.com/ComputationalBiomechanicsLab/rmr-solver-py",
    "solverCommit": source_commit,
    "solverCheckoutModified": source_modified,
    "pythonVersion": sys.version.split()[0],
    "opensimVersion": osim.GetVersionAndDate(),
    "ghConstraintEnabled": args.gh_constraint,
    "benchSupportSweepEnabled": args.bench_support_sweep,
    "model": str(MODEL.relative_to(ROOT)),
    "pose": "synthetic bench reference phase 0.5; zero speed and acceleration",
    "gravityModelFrameMPerS2": [-9.80665, 0, 0],
    "limits": [
        "single arm and synthetic static pose; no measured athlete motion or hand force",
        ("bench reaction magnitude prescribed from model weight and split barbell load; "
         "point of contact swept, not measured; no foot contact"
         if args.bench_support_sweep else
         "no bench or foot contact, so reserve actuators supply missing support"),
        "no bilateral barbell dynamics or personalized strength parameters",
        "convergence and shoulder stability do not validate individual muscle forces",
    ],
    "cases": cases,
}
OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for case in cases:
    print(f"RMR research only: {case['barbellKg']} kg, lateral {case['handEffortLateralRatio']:+.0%}, "
          f"success={case['success']}, "
          f"thorax reserve X={case['reserveActuationSI']['ground_thorax_tx_actuator']:.1f} N")
print(f"Wrote {OUTPUT}")
