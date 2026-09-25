"""Research-only OpenSim inverse-dynamics replay on one original squat trial.

Requires reproduce_dynamic_squat_ik.py output and the raw external-load .mot.
Used to audit physical units and pipeline compatibility, not phone estimates.
"""

import argparse
import os
from pathlib import Path

import opensim as osim

from analyze_dynamic_squats import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="AB01")
    parser.add_argument("--start", type=float, default=50)
    parser.add_argument("--end", type=float, default=52)
    parser.add_argument("--omit-free-moment", action="store_true",
                        help="Sensitivity probe: omit force-plate torque vectors")
    args = parser.parse_args()
    base = ROOT / ".cache/lower-limb-raw" / args.subject
    model_file = base / "Models" / f"{args.subject}-Scaled1.osim"
    ground_file = base / "ExtLoads/squats_1.mot"
    coordinates_file = ROOT / ".cache/lower-limb" / f"{args.subject}_ik_{args.start:g}_{args.end:g}.mot"
    if not all(x.exists() for x in (model_file, ground_file, coordinates_file)):
        parser.error("Extract model/ExtLoads and run the matching short IK interval first")
    output_dir = ROOT / ".cache/lower-limb/id-reproduction"
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_no_free_moment" if args.omit_free_moment else ""
    loads_file = output_dir / f"{args.subject}_external_loads{suffix}.xml"
    loads = osim.ExternalLoads()
    for side in ("r", "l"):
        force = osim.ExternalForce()
        force.setName(f"{side}GroundForce")
        force.set_applied_to_body(f"calcn_{side}")
        force.set_force_expressed_in_body("ground")
        force.set_point_expressed_in_body("ground")
        force.set_force_identifier(f"{side}FP_v")
        force.set_point_identifier(f"{side}FP_p")
        if not args.omit_free_moment:
            force.set_torque_identifier(f"{side}FP_moment_")
        loads.cloneAndAppend(force)
    loads.setDataFileName(os.path.relpath(ground_file, loads_file.parent))
    loads.printToXML(os.path.relpath(loads_file))
    tool = osim.InverseDynamicsTool()
    tool.setName(f"{args.subject}_squat_replay")
    tool.setModelFileName(os.path.relpath(model_file))
    tool.setCoordinatesFileName(os.path.relpath(coordinates_file))
    tool.setExternalLoadsFileName(os.path.relpath(loads_file))
    excluded = osim.ArrayStr()
    excluded.append("Muscles")
    tool.setExcludedForces(excluded)
    tool.setStartTime(args.start)
    tool.setEndTime(args.end)
    tool.setLowpassCutoffFrequency(6)
    tool.setResultsDir(os.path.relpath(output_dir))
    tool.setOutputGenForceFileName(
        f"{args.subject}_id_{args.start:g}_{args.end:g}{suffix}.sto")
    success = tool.run()
    output = output_dir / f"{args.subject}_id_{args.start:g}_{args.end:g}{suffix}.sto"
    print(f"ID success={success}; output={output}")
    if not success or not output.exists():
        raise RuntimeError("OpenSim inverse dynamics did not produce moments")


if __name__ == "__main__":
    main()
