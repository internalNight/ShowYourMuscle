"""Run OpenSim StaticOptimization on a segment-scaled high-flex squat model.

This is a measured-input model diagnostic. It uses recorded IK and force plates,
not body measurements or training records, and cannot generate phone force maps.
"""

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

import opensim as osim

from audit_high_flex_candidate import CANDIDATE, ROOT, SUBJECTS, read_ik, set_pose
from probe_high_flex_scaled_capacity import ratios_from_dimensions, scale_model
from probe_high_flex_segment_scaling import dimensions

SOURCE_WINDOWS = {"AB01": (50, 52), "AB02": (23, 25)}
DEFAULT_INTERVAL = {"AB01": (51.24, 51.32), "AB02": (23.60, 23.70)}
RESEARCH_OUTPUT = ROOT / ".cache/lower-limb/high-flex-static-optimization"


def convert_coordinates(source, target):
    """Use the same measured kinematics, with candidate knee convention."""
    lines = source.read_text(encoding="utf-8").splitlines()
    header = lines.index("endheader")
    names = lines[header + 1].split()
    knee = [names.index(f"knee_angle_{side}") for side in ("r", "l")]
    locked = [names.index(f"{name}_{side}") for side in ("r", "l")
              for name in ("subtalar_angle", "mtp_angle")]
    converted = lines[:header + 2]
    for line in lines[header + 2:]:
        if not line.strip():
            continue
        cells = [float(value) for value in line.split()]
        if len(cells) != len(names):
            raise AssertionError("Unexpected IK column count")
        for index in knee:
            cells[index] *= -1
        for index in locked:
            cells[index] = 0
        converted.append("\t".join(f"{value:.9f}" for value in cells))
    target.write_text("\n".join(converted) + "\n", encoding="utf-8")


def add_reserves(model, joint_reserve_optimal_force):
    count = 0
    for index in range(model.getCoordinateSet().getSize()):
        coordinate = model.getCoordinateSet().get(index)
        name = coordinate.getName()
        if coordinate.get_locked() or name.endswith("_beta"):
            continue
        actuator = osim.CoordinateActuator(name)
        actuator.setName(f"reserve_{name}")
        lower_joint = name.startswith(("hip_", "knee_", "ankle_"))
        optimal_force = (100 if name.startswith("pelvis_") else
                         joint_reserve_optimal_force if lower_joint else 1)
        actuator.setOptimalForce(optimal_force)
        actuator.setMinControl(-100000 if lower_joint else -1000)
        actuator.setMaxControl(100000 if lower_joint else 1000)
        model.addForce(actuator)
        count += 1
    return count


def run(subject, start_time, end_time, strength_multiplier, physiology,
        joint_reserve_optimal_force, verbose_warnings):
    os.chdir(ROOT)
    osim.Logger.setLevelString("Warn" if verbose_warnings else "Error")
    config = SUBJECTS[subject]
    source = osim.Model(str(config["source"].relative_to(ROOT)))
    source_state = source.initSystem()
    candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
    candidate_state = candidate.initSystem()
    reference = read_ik(config["ik"], config["intervalS"])[0]
    set_pose(source, source_state, reference)
    set_pose(candidate, candidate_state, reference, flip_knee=True)
    factors = ratios_from_dimensions(dimensions(source, source_state, "knee"),
                                     dimensions(candidate, candidate_state,
                                                "walker_knee"))
    scale_model(candidate, candidate_state, factors,
                float(source.getTotalMass(source_state)))
    for index in range(candidate.getMuscles().getSize()):
        muscle = candidate.getMuscles().get(index)
        muscle.set_max_isometric_force(
            muscle.getMaxIsometricForce() * strength_multiplier)
    reserve_count = add_reserves(candidate, joint_reserve_optimal_force)
    candidate.setName(f"{subject}_high_flex_static_optimization")
    source_start, source_end = SOURCE_WINDOWS[subject]
    input_ik = ROOT / ".cache/lower-limb" / f"{subject}_ik_{source_start}_{source_end}.mot"
    raw_force = (ROOT / ".cache/lower-limb-raw" / subject /
                 "ExtLoads/squats_1.mot")
    if not input_ik.exists() or not raw_force.exists():
        raise FileNotFoundError("Measured IK or force plates are absent")
    tag = (f"{subject}_{start_time:g}_{end_time:g}_strength{strength_multiplier:g}_"
           f"{'physiology' if physiology else 'no-physiology'}")
    if joint_reserve_optimal_force != 1:
        tag += f"_jointreserve{joint_reserve_optimal_force:g}"
    destination = RESEARCH_OUTPUT / tag
    scratch = Path(tempfile.mkdtemp(prefix=f"high_flex_so_{subject}_"))
    try:
        model_path = scratch / "candidate.osim"
        candidate.printToXML(str(model_path))
        convert_coordinates(input_ik, scratch / "ik.mot")
        shutil.copyfile(raw_force, scratch / "forces.mot")
        loads = osim.ExternalLoads()
        for side in ("r", "l"):
            force = osim.ExternalForce()
            force.setName(f"{side}GroundForce")
            force.set_applied_to_body(f"calcn_{side}")
            force.set_force_expressed_in_body("ground")
            force.set_point_expressed_in_body("ground")
            force.set_force_identifier(f"{side}FP_v")
            force.set_point_identifier(f"{side}FP_p")
            # The released source ID is best reproduced without free moment.
            loads.cloneAndAppend(force)
        loads.setDataFileName("forces.mot")
        loads.printToXML(str(scratch / "loads.xml"))
        analysis = osim.StaticOptimization()
        analysis.setName("high_flex_static_optimization")
        analysis.setStartTime(start_time)
        analysis.setEndTime(end_time)
        analysis.setUseMusclePhysiology(physiology)
        analysis.setActivationExponent(2)
        analysis.setConvergenceCriterion(1e-4)
        analysis.setMaxIterations(200)
        tool = osim.AnalyzeTool()
        tool.setName("high_flex_squat_probe")
        candidate.initSystem()
        tool.setModel(candidate)
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
        completed = bool(tool.run())
        files = list((scratch / "results").glob("*"))
        destination.mkdir(parents=True, exist_ok=True)
        for file in files:
            shutil.copyfile(file, destination / file.name)
        report = {
            "status": "research_only_measured_input_high_flex_static_optimization",
            "subject": subject,
            "intervalS": [start_time, end_time],
            "strengthMultiplier": strength_multiplier,
            "useMusclePhysiology": physiology,
            "candidateMuscles": candidate.getMuscles().getSize(),
            "reserveActuators": reserve_count,
            "jointReserveOptimalForceNmPerControl": joint_reserve_optimal_force,
            "warningsEmitted": verbose_warnings,
            "forcePlateFreeMomentsIncluded": False,
            "lockedSubtalarAndMtpInConvertedIK": True,
            "toolCompleted": completed,
            "resultFiles": [file.name for file in files],
            "limitations": [
                "uses measured kinematics and ground force; not a phone-input force prediction",
                "subject pelvis/lumbar and contact geometry are not registered to candidate",
                "strength multiplier is chosen for feasibility, not measured individual strength",
                "tool completion does not prove individual-frame convergence or valid muscle force",
            ],
        }
        (destination / "probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        return report, destination
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", choices=SUBJECTS, default="AB02")
    parser.add_argument("--start", type=float)
    parser.add_argument("--end", type=float)
    parser.add_argument("--strength-multiplier", type=float, default=4.2)
    parser.add_argument("--joint-reserve-optimal-force", type=float, default=1)
    parser.add_argument("--verbose-warnings", action="store_true")
    parser.add_argument("--disable-muscle-physiology", action="store_true")
    args = parser.parse_args()
    default_start, default_end = DEFAULT_INTERVAL[args.subject]
    start_time = args.start if args.start is not None else default_start
    end_time = args.end if args.end is not None else default_end
    if not SOURCE_WINDOWS[args.subject][0] <= start_time < end_time <= SOURCE_WINDOWS[args.subject][1]:
        parser.error("start/end outside the saved measured IK window")
    if not 0.1 <= args.strength_multiplier <= 20:
        parser.error("strength multiplier must be 0.1–20")
    if not 0.001 <= args.joint_reserve_optimal_force <= 10:
        parser.error("joint reserve optimal force must be 0.001–10 Nm/control")
    result, destination = run(args.subject, start_time, end_time,
                              args.strength_multiplier,
                              not args.disable_muscle_physiology,
                              args.joint_reserve_optimal_force,
                              args.verbose_warnings)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("result directory:", destination)
    if not result["toolCompleted"]:
        raise RuntimeError("OpenSim AnalyzeTool did not complete")


if __name__ == "__main__":
    main()
