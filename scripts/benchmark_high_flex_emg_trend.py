"""Pilot: compare a feasible model's activation prior to independent squat EMG.

The optimization receives measured IK and net ID torques, then imposes an
arbitrary uniform muscle-strength multiplier. The comparison tests whether
this particular force-sharing prior tracks electrical activity; it cannot
validate subject muscle forces or phone-only personalization.
"""

import argparse
import json
import math
import os

import numpy as np
import opensim as osim
from scipy.optimize import linprog, minimize
from scipy.stats import spearmanr

from analyze_dynamic_squat_emg import emg_envelopes
from analyze_dynamic_squat_id_replay import read_storage
from analyze_dynamic_squats import load_trial
from audit_high_flex_candidate import CANDIDATE, ROOT, SUBJECTS, read_ik, set_pose
from audit_high_flex_hip_knee_ankle_capacity import COORDINATES, SIDES, mapped_targets
from audit_high_flex_full_squat_capacity import WINDOWS
from probe_high_flex_scaled_capacity import ratios_from_dimensions, scale_model
from probe_high_flex_segment_scaling import dimensions

OUTPUT = ROOT / "docs/data/high_flex_squat_emg_prior_pilot.json"
DEFAULT_STRENGTH_MULTIPLIER = 4.2
CHANNEL_MUSCLES = {
    "RF": ("recfem",), "VL": ("vaslat",),
    "GMAX": ("glmax1", "glmax2", "glmax3"),
    "BF": ("bflh", "bfsh"),
    "GMED": ("glmed1", "glmed2", "glmed3"),
    "MGAS": ("gasmed",), "TA": ("tibant",), "GRAC": ("grac",),
}


def minimum_squared_tension(arms, fmax, target, strength_multiplier):
    """Return the bounded min-squared-normalized-force solution at fixed s."""
    coefficients = arms * fmax[None, :] / 100
    demand = target / 100
    initial = linprog(np.zeros(len(fmax)), A_eq=coefficients, b_eq=demand,
                      bounds=[(0, strength_multiplier)] * len(fmax),
                      method="highs")
    if not initial.success:
        return None, f"LP: {initial.message}"
    result = minimize(lambda value: value @ value / 2, initial.x,
                      jac=lambda value: value,
                      bounds=[(0, strength_multiplier)] * len(fmax),
                      constraints={"type": "eq",
                                   "fun": lambda value: coefficients @ value - demand,
                                   "jac": lambda value: coefficients},
                      method="SLSQP", options={"ftol": 1e-9, "maxiter": 200})
    if not result.success:
        return None, f"SLSQP: {result.message}"
    residual = float(np.max(np.abs(arms @ (fmax * result.x) - target)))
    if residual > 1e-4:
        return None, f"torque residual {residual:.6g} Nm"
    return result.x, None


def compare_channel(model_values, knee_angles, emg_values):
    model = np.asarray(model_values)
    knees = np.asarray(knee_angles)
    emg = np.asarray(emg_values)
    knee_correlation = round(float(spearmanr(knees, emg).statistic), 4)
    if len(model) < 10 or max(model) - min(model) < 1e-5:
        return {"spearman": None, "kneeFlexionBaselineSpearman": knee_correlation,
                "reason": "insufficient nonconstant model activity"}
    return {"spearman": round(float(spearmanr(model, emg).statistic), 4),
            "kneeFlexionBaselineSpearman": knee_correlation,
            "modelNonzeroFrames": int(np.sum(model > 1e-4)),
            "modelRange": [round(float(min(model)), 4),
                           round(float(max(model)), 4)],
            "emgRangeV": [round(float(min(emg)), 8),
                          round(float(max(emg)), 8)]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strength-multiplier", type=float,
                        default=DEFAULT_STRENGTH_MULTIPLIER)
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    if not 1 <= args.strength_multiplier <= 20:
        parser.error("--strength-multiplier must be between 1 and 20")
    output = ROOT / args.output
    os.chdir(ROOT)
    osim.Logger.setLevelString("Error")
    report = {
        "status": "research_only_emg_trend_screen_not_personal_muscle_force",
        "strengthMultiplier": args.strength_multiplier,
        "strengthMultiplierMeaning": "arbitrary uniform multiplier of nominal maximum isometric force to make the ten-axis problem feasible; not subject calibration",
        "forceSharingPrior": "minimize sum of squared normalized muscle tensions at each measured pose and net joint moment; passive torque from 1% activation and zero-speed equilibrium is subtracted first",
        "emgProcessing": "same-trial 20-450 Hz zero-phase bandpass and centered 100 ms RMS; no MVC normalization",
        "sampling": "one frame every 100 ms across each two-second measured squat window, excluding candidate knee out-of-range poses",
        "limitations": [
            "measured poses and force-plate ID torques are inputs; the phone has neither",
            "surface EMG is electrical activity, not direct muscle force, and channels do not uniquely identify modeled heads",
            "the strength multiplier is a numerical feasibility choice; fiber force-length-velocity, contact and individual anatomy remain uncalibrated",
            "two subjects and about twenty highly correlated frames each are insufficient for product validation",
        ],
        "subjects": {},
    }
    for subject, config in SUBJECTS.items():
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
        muscles = [candidate.getMuscles().get(i)
                   for i in range(candidate.getMuscles().getSize())]
        muscle_indices = {muscle.getName(): i for i, muscle in enumerate(muscles)}
        fmax = np.array([muscle.getMaxIsometricForce() for muscle in muscles])
        replay = read_storage(ROOT / ".cache/lower-limb/id-reproduction" /
                              f"{subject}_id_{'50_52' if subject == 'AB01' else '23_25'}_no_free_moment.sto")
        rows = read_ik(config["ik"], WINDOWS[subject])[::20]
        if len(rows) != 21:
            raise AssertionError("Unexpected 100 ms sampling count")
        trial = load_trial(subject, "0lbs")
        envelopes = emg_envelopes(subject, "0lbs", trial["time"], 100)
        knee_max = candidate.getCoordinateSet().get("knee_angle_r").getRangeMax()
        solved = []
        excluded = []
        failures = []
        for row in rows:
            if any(math.radians(-row[f"knee_angle_{side}"]) > knee_max + 1e-9
                   for side in SIDES):
                excluded.append(round(row["time"], 3))
                continue
            set_pose(source, source_state, row)
            set_pose(candidate, candidate_state, row, flip_knee=True)
            index = int(round((row["time"] - replay["time"][0]) / 0.005))
            if abs(replay["time"][index] - row["time"]) > 1e-6:
                raise AssertionError("IK/ID time grids differ")
            torques = {name: float(replay[name + "_moment"][index])
                       for name in COORDINATES}
            targets, _ = mapped_targets(source, source_state, candidate,
                                        candidate_state, torques)
            arms = np.array([[muscle.computeMomentArm(
                candidate_state, candidate.getCoordinateSet().get(name))
                for muscle in muscles] for name in COORDINATES])
            for coordinate_index in range(candidate.getCoordinateSet().getSize()):
                candidate.getCoordinateSet().get(coordinate_index).setSpeedValue(
                    candidate_state, 0.0)
            for muscle in muscles:
                muscle.setActivation(candidate_state, 0.01)
            candidate.equilibrateMuscles(candidate_state)
            candidate.realizeDynamics(candidate_state)
            passive_forces = np.array([
                muscle.getPassiveFiberForceAlongTendon(candidate_state)
                for muscle in muscles])
            solution, error = minimum_squared_tension(
                arms, fmax, targets - arms @ passive_forces,
                args.strength_multiplier)
            if error:
                failures.append({"timeS": round(row["time"], 3), "error": error})
                continue
            solved.append({"timeS": round(row["time"], 3),
                           "rightKneeFlexionDeg": -row["knee_angle_r"],
                           "leftKneeFlexionDeg": -row["knee_angle_l"],
                           "tensionFractionOfNominalFmax": solution})
        times = np.array([frame["timeS"] for frame in solved])
        channel_results = {}
        for side in SIDES:
            for channel, heads in CHANNEL_MUSCLES.items():
                key = side.upper() + channel
                indices = [muscle_indices[name + "_" + side] for name in heads]
                predicted = [float(np.mean(frame[
                    "tensionFractionOfNominalFmax"][indices])) for frame in solved]
                knees = [frame["rightKneeFlexionDeg" if side == "r"
                                else "leftKneeFlexionDeg"] for frame in solved]
                observed = np.interp(times, trial["time"], envelopes[key])
                channel_results[key] = compare_channel(predicted, knees, observed)
        report["subjects"][subject] = {
            "sampledFrames": len(rows),
            "excludedOutsideKneeRange": excluded,
            "solverFailures": failures,
            "solvedFrames": len(solved),
            "channelTrends": channel_results,
        }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({subject: {"solvedFrames": data["solvedFrames"],
                                "excludedOutsideKneeRange": data["excludedOutsideKneeRange"],
                                "solverFailures": data["solverFailures"],
                                "channelSpearman": {name: {
                                    "model": item["spearman"],
                                    "kneeDepth": item["kneeFlexionBaselineSpearman"]}
                                    for name, item in data["channelTrends"].items()}}
                      for subject, data in report["subjects"].items()},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
