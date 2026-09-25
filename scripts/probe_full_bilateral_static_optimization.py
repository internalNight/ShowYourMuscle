"""Experimental full bilateral OpenSim static optimization on measured squat data.

Uses a published subject's measured force plates and replayed IK. This is a
diagnostic, not a prediction from phone inputs and not a validated force map.
"""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
INTERVALS = {"AB01": (50, 52), "AB02": (23, 25)}
PROBE_INTERVALS = {"AB01": (51.0, 51.5), "AB02": (23.4, 23.9)}


def add_reserves(model):
    for index in range(model.getCoordinateSet().getSize()):
        coordinate = model.getCoordinateSet().get(index)
        name = coordinate.getName()
        actuator = osim.CoordinateActuator(name)
        actuator.setName(f"reserve_{name}")
        actuator.setOptimalForce(100 if name.startswith("pelvis_") else 1)
        actuator.setMinControl(-1000)
        actuator.setMaxControl(1000)
        model.addForce(actuator)


def run(subject, start_time, end_time, use_muscle_physiology, max_iterations,
        run_tag):
    source = ROOT / ".cache/lower-limb-raw" / subject
    interval = INTERVALS[subject]
    ik = ROOT / ".cache/lower-limb" / f"{subject}_ik_{interval[0]}_{interval[1]}.mot"
    if not ik.exists():
        raise FileNotFoundError(ik)
    scratch = Path(tempfile.mkdtemp(prefix=f"muscle_atlas_so_{subject}_"))
    try:
        model_src = scratch / "base.osim"
        shutil.copyfile(source / "Models" / f"{subject}-Scaled1.osim", model_src)
        model = osim.Model(str(model_src))
        add_reserves(model)
        model.setName(f"{subject}_static_optimization_probe")
        model_path = scratch / "reserves.osim"
        model.printToXML(str(model_path))
        shutil.copyfile(ik, scratch / "ik.mot")
        shutil.copyfile(source / "ExtLoads" / "squats_1.mot", scratch / "forces.mot")
        loads = osim.ExternalLoads()
        for side in ("r", "l"):
            force = osim.ExternalForce()
            force.setName(f"{side}GroundForce")
            force.set_applied_to_body(f"calcn_{side}")
            force.set_force_expressed_in_body("ground")
            force.set_point_expressed_in_body("ground")
            force.set_force_identifier(f"{side}FP_v")
            force.set_point_identifier(f"{side}FP_p")
            force.set_torque_identifier(f"{side}FP_moment_")
            loads.cloneAndAppend(force)
        loads.setDataFileName("forces.mot")
        loads.printToXML(str(scratch / "loads.xml"))
        analysis = osim.StaticOptimization()
        analysis.setName("full_bilateral_static_optimization")
        analysis.setStartTime(start_time)
        analysis.setEndTime(end_time)
        analysis.setUseMusclePhysiology(use_muscle_physiology)
        analysis.setActivationExponent(2)
        analysis.setConvergenceCriterion(1e-4)
        analysis.setMaxIterations(max_iterations)
        tool = osim.AnalyzeTool()
        tool.setName(f"{subject}_static_optimization_probe")
        model.initSystem()
        tool.setModel(model)
        tool.setModelFilename(str(model_path))
        tool.setLoadModelAndInput(True)
        tool.setCoordinatesFileName(str(scratch / "ik.mot"))
        tool.setExternalLoadsFileName(str(scratch / "loads.xml"))
        tool.setLowpassCutoffFrequency(6)
        tool.setInitialTime(start_time)
        tool.setFinalTime(end_time)
        tool.setResultsDir(str(scratch / "results"))
        tool.updAnalysisSet().cloneAndAppend(analysis)
        tool.addAnalysisSetToModel()
        success = bool(tool.run())
        files = [file.name for file in (scratch / "results").glob("*")]
        outcome = {"subject": subject, "intervalS": [start_time, end_time],
                   "toolCompleted": success, "files": files,
                   "useMusclePhysiology": use_muscle_physiology,
                   "maxIterations": max_iterations,
                   "runTag": run_tag,
                   "status": "research_only_measured_input_not_phone_prediction"}
        if success:
            variant = "physiology" if use_muscle_physiology else "no-physiology"
            if run_tag:
                variant += f"-{run_tag}"
            destination = (ROOT / ".cache/lower-limb/full-bilateral-static-optimization"
                           / subject / variant)
            destination.mkdir(parents=True, exist_ok=True)
            for file in (scratch / "results").glob("*"):
                shutil.copyfile(file, destination / file.name)
            outcome["outputDir"] = str(destination.relative_to(ROOT))
        return outcome
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", choices=INTERVALS, default="AB01")
    parser.add_argument("--start", type=float)
    parser.add_argument("--end", type=float)
    parser.add_argument("--disable-muscle-physiology", action="store_true")
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument("--run-tag", default="")
    args = parser.parse_args()
    default_start, default_end = PROBE_INTERVALS[args.subject]
    start_time = args.start if args.start is not None else default_start
    end_time = args.end if args.end is not None else default_end
    interval_start, interval_end = INTERVALS[args.subject]
    if not interval_start <= start_time < end_time <= interval_end:
        parser.error("start must precede end")
    if args.max_iterations < 1:
        parser.error("max-iterations must be positive")
    if args.run_tag and (not args.run_tag.isascii() or
                         not args.run_tag.replace("-", "").isalnum()):
        parser.error("run-tag must use ASCII letters, digits or hyphens")
    result = run(args.subject, start_time, end_time,
                 not args.disable_muscle_physiology, args.max_iterations,
                 args.run_tag)
    print(json.dumps(result, indent=2))
    if not result["toolCompleted"]:
        raise RuntimeError("StaticOptimization failed")


if __name__ == "__main__":
    main()
