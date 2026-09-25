"""Retrodictive muscle-allocation check against independent processed EMG.

Uses measured joint torques as input. It cannot run from the phone's few body
parameters and is not a bench-press or overhead-press validation.
"""

import json
import os
from pathlib import Path

import numpy as np
import opensim as osim
from scipy.optimize import linprog, minimize
from scipy.stats import rankdata


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".cache/upper-limb-torque"
OUTPUT = ROOT / "docs/data/upper_limb_force_prior_emg_screen.json"
SUBJECTS = tuple(f"S{number:02d}" for number in range(1, 18))
INPUT_COORDS = ("elv_angle", "shoulder_elv", "shoulder_rot", "elbow_flexion",
                "pro_sup", "deviation", "flexion")
TARGET_COORDS = ("shoulder_elv", "elbow_flexion")
STRIDE = 50


def rank_correlation(left, right):
    if np.ptp(left) < 1e-8 or np.ptp(right) < 1e-8:
        return None
    result = float(np.corrcoef(rankdata(left), rankdata(right))[0, 1])
    return round(result, 3) if np.isfinite(result) else None


def minimum_squared_activation(arms, fmax, torque):
    start = linprog(np.zeros(len(fmax)), A_eq=arms, b_eq=torque,
                    bounds=[(0, float(value)) for value in fmax], method="highs")
    if not start.success:
        raise RuntimeError("nominal torque is infeasible before prior optimization")
    scaled_arms = arms * fmax[None, :]
    scale = max(1.0, float(np.max(np.abs(torque))))
    equalities = scaled_arms / scale
    target = torque / scale
    result = minimize(lambda activity: .5 * float(activity @ activity),
                      start.x / fmax, jac=lambda activity: activity,
                      method="SLSQP", bounds=[(0, 1)] * len(fmax),
                      constraints=[{"type": "eq", "fun": lambda activity: equalities @ activity - target,
                                    "jac": lambda _activity: equalities}],
                      options={"ftol": 1e-10, "maxiter": 250})
    if not result.success:
        raise RuntimeError(f"minimum squared activation failed: {result.message}")
    residual = np.max(np.abs(scaled_arms @ result.x - torque))
    if residual > 1e-3:
        raise RuntimeError(f"prior solution torque residual {residual} N.m")
    return result.x, float(residual)


def inspect_subject(subject):
    base = DATA / subject / "MJ/T0"
    positions = np.genfromtxt(base / "humanPositions.csv", delimiter=",", names=True)
    torques = np.genfromtxt(base / "muscleTorque.csv", delimiter=",", names=True)
    emg = np.genfromtxt(base / "emgFilt.csv", delimiter=",", names=True)
    if len({len(positions), len(torques), len(emg)}) != 1:
        raise ValueError(f"{subject}: time series lengths differ")
    if max(float(np.max(np.abs(positions["TIME"] - item)))
           for item in (torques["time"], emg["TIME"])) > 1e-6:
        raise ValueError(f"{subject}: time series not synchronized")
    model = osim.Model(f".cache/upper-limb-torque/{subject}/scaledModel.osim")
    state = model.initSystem()
    coords = model.getCoordinateSet()
    muscles = [model.getMuscles().get(index) for index in range(model.getMuscles().getSize())]
    names = [muscle.getName() for muscle in muscles]
    fmax = np.array([muscle.getMaxIsometricForce() for muscle in muscles])
    if any(name not in emg.dtype.names for name in names):
        raise ValueError(f"{subject}: EMG muscle names differ from model")
    activity_rows = []
    length_rows = []
    emg_rows = []
    residuals = []
    for index in sorted(set(range(0, len(positions), STRIDE)) | {len(positions) - 1}):
        pose = positions[index]
        for name in INPUT_COORDS:
            coords.get(name).setValue(state, float(pose[name]), False)
        model.assemble(state)
        if max(abs(coords.get(name).getValue(state) - float(pose[name]))
               for name in INPUT_COORDS) > .01:
            raise ValueError(f"{subject} frame {index}: pose assembly shift exceeds .01 rad")
        model.realizePosition(state)
        arms = np.array([[muscle.computeMomentArm(state, coords.get(name))
                          for muscle in muscles] for name in TARGET_COORDS])
        torque = np.array([float(torques[name][index]) for name in TARGET_COORDS])
        activity, residual = minimum_squared_activation(arms, fmax, torque)
        activity_rows.append(activity)
        length_rows.append([muscle.getLength(state) for muscle in muscles])
        emg_rows.append([float(emg[name][index]) for name in names])
        residuals.append(residual)
    activity = np.asarray(activity_rows)
    lengths = np.asarray(length_rows)
    measured_emg = np.asarray(emg_rows)
    channels = []
    for index, name in enumerate(names):
        channels.append({
            "muscle": name,
            "activationVsEmgSpearman": rank_correlation(activity[:, index], measured_emg[:, index]),
            "pathLengthVsEmgSpearman": rank_correlation(lengths[:, index], measured_emg[:, index]),
            "activationRange": [round(float(activity[:, index].min()), 3),
                                round(float(activity[:, index].max()), 3)],
        })
    return {"subject": subject, "frames": len(activity),
            "largestTorqueResidualNm": max(residuals), "channels": channels}


def main():
    os.chdir(ROOT)
    subjects = [inspect_subject(subject) for subject in SUBJECTS]
    names = [channel["muscle"] for channel in subjects[0]["channels"]]
    summary = []
    rng = np.random.default_rng(42)
    for name in names:
        row = {"muscle": name}
        for field in ("activationVsEmgSpearman", "pathLengthVsEmgSpearman"):
            values = [next(channel for channel in subject["channels"] if channel["muscle"] == name)[field]
                      for subject in subjects]
            usable = [value for value in values if value is not None]
            bootstrap95 = None
            if usable:
                sample = np.asarray(usable)
                draws = rng.integers(0, len(sample), size=(10000, len(sample)))
                bootstrap95 = [round(float(value), 3) for value in np.quantile(
                    np.median(sample[draws], axis=1), (0.025, 0.975))]
            row[field] = {"participantsWithVariation": len(usable),
                          "participantMedian": round(float(np.median(usable)), 3) if usable else None,
                          "participantMedianBootstrap95": bootstrap95,
                          "positiveParticipants": sum(value > 0 for value in usable)}
        summary.append(row)
    report = {
        "status": "retrodictive_exploratory_emg_screen_not_personal_force_validation",
        "source": "https://zenodo.org/records/11209324",
        "license": "CC BY-SA 4.0",
        "method": "At every 0.5 s plus final sample, fit the two processed joint torques exactly using 12 muscle tensions bounded by nominal Fmax, choosing minimum sum of squared F/Fmax. Compare its activation trend and model path length separately with the matched MVC-normalized processed EMG using within-person Spearman rank correlation; no fitted parameters, no lag tuning.",
        "subjects": len(subjects), "frames": sum(subject["frames"] for subject in subjects),
        "largestTorqueResidualNm": max(subject["largestTorqueResidualNm"] for subject in subjects),
        "summary": summary, "participantResults": subjects,
        "limitations": [
            "The solver is given experimentally processed joint torques and poses unavailable to the phone; this is retrodiction, not prospective prediction.",
            "Only two joint torques constrain 12 muscle tensions; the minimum-squared-activation prior is a choice, not measured physiology.",
            "Fmax is identical across all 17 scaled models; force-length-velocity, passive force, external contact, and other coordinates are omitted.",
            "Surface EMG is an imperfect activation trend reference and is not a single-muscle force measurement; no electromechanical lag is tuned.",
            "The task is exoskeleton upper-limb tracking, not bench or overhead press.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"subjects": report["subjects"], "frames": report["frames"],
                      "largestTorqueResidualNm": report["largestTorqueResidualNm"],
                      "summary": summary}, indent=2))
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
