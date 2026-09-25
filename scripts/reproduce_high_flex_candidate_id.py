"""Replay measured force plates and IK through the segment-scaled candidate.

This checks how much inverse-dynamics torque changes when the source subject
model is replaced by RajagopalLaiUhlrich2023. No muscle force is estimated.
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
from probe_high_flex_static_optimization import convert_coordinates

WINDOWS = {"AB01": (50, 52), "AB02": (23, 25)}
OUTPUT_DIR = ROOT / ".cache/lower-limb/high-flex-candidate-id"


def run(subject):
    os.chdir(ROOT)
    osim.Logger.setLevelString("Error")
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
    target_mass = float(source.getTotalMass(source_state))
    scale_model(candidate, candidate_state, factors, target_mass)
    start, end = WINDOWS[subject]
    input_ik = ROOT / ".cache/lower-limb" / f"{subject}_ik_{start}_{end}.mot"
    ground = (ROOT / ".cache/lower-limb-raw" / subject /
              "ExtLoads/squats_1.mot")
    destination = OUTPUT_DIR / subject
    destination.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=f"high_flex_id_{subject}_"))
    try:
        model_path = scratch / "candidate.osim"
        candidate.printToXML(str(model_path))
        convert_coordinates(input_ik, scratch / "ik.mot")
        shutil.copyfile(ground, scratch / "forces.mot")
        loads = osim.ExternalLoads()
        for side in ("r", "l"):
            force = osim.ExternalForce()
            force.setName(f"{side}GroundForce")
            force.set_applied_to_body(f"calcn_{side}")
            force.set_force_expressed_in_body("ground")
            force.set_point_expressed_in_body("ground")
            force.set_force_identifier(f"{side}FP_v")
            force.set_point_identifier(f"{side}FP_p")
            loads.cloneAndAppend(force)
        loads.setDataFileName("forces.mot")
        loads.printToXML(str(scratch / "loads.xml"))
        tool = osim.InverseDynamicsTool()
        tool.setName(f"{subject}_high_flex_candidate_id")
        tool.setModelFileName(str(model_path))
        tool.setCoordinatesFileName(str(scratch / "ik.mot"))
        tool.setExternalLoadsFileName(str(scratch / "loads.xml"))
        excluded = osim.ArrayStr()
        excluded.append("Muscles")
        tool.setExcludedForces(excluded)
        tool.setStartTime(start)
        tool.setEndTime(end)
        tool.setLowpassCutoffFrequency(6)
        tool.setResultsDir(str(scratch / "results"))
        tool.setOutputGenForceFileName("candidate_id.sto")
        success = bool(tool.run())
        result = scratch / "results/candidate_id.sto"
        if not success or not result.exists():
            raise RuntimeError("Candidate ID did not produce a torque table")
        shutil.copyfile(result, destination / "candidate_id.sto")
        report = {
            "status": "research_only_candidate_inverse_dynamics_measured_input",
            "subject": subject,
            "intervalS": [start, end],
            "sourceAndCandidateTotalMassKg": round(target_mass, 6),
            "coordinateConversion": "candidate knee flexion sign reversed; locked subtalar/MTP set to zero",
            "forcePlateFreeMomentIncluded": False,
            "lowpassCutoffHz": 6,
            "muscleForcesExcluded": True,
            "limitations": [
                "uses measured IK and force plates; not a phone-input prediction",
                "source and candidate differ in pelvis/trunk inertias and contact geometry despite matched total mass and selected joint distances",
                "candidate subtalar/MTP are locked, so those source degrees of freedom are not replayed",
            ],
        }
        (destination / "replay.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        return report, destination
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", choices=WINDOWS, default="AB02")
    args = parser.parse_args()
    report, directory = run(args.subject)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("saved", directory)


if __name__ == "__main__":
    main()
