"""Check a fixed known-load support-force formula on independent lifting trials.

INAIL Lifting Dataset 1 has box-marker trajectories, bilateral force plates,
participant mass, and synchronized sEMG. This evaluates only vertical external
support force in crate lifting, not barbell squats or individual muscle force.
Download raw data with download_inail_lifting_dataset.py --all first.
"""

import json
from pathlib import Path

import numpy as np
import openpyxl
from scipy.io import loadmat
from scipy.signal import butter, filtfilt, savgol_filter
from scipy.stats import binomtest


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/research/inail"
OUTPUT = ROOT / "docs/data/inail_loaded_lift_support_benchmark.json"
G = 9.81
LOAD_KG = {"LI1": 23.0, "LI2": 23.0, "LI3": 22.09}
LOAD_MARKERS = ("load_RL1", "load_RL2", "load_LL1", "load_LL2")
ACCELERATION_FILTERS = {
    "more_smoothing": (4, 131),
    "primary": (6, 101),
    "less_smoothing": (8, 71),
}


def profile_masses():
    workbook = openpyxl.load_workbook(CACHE / "Subjects_info.xlsx", read_only=True,
                                     data_only=True)
    rows = list(workbook.active.values)
    if rows[0][:3] != ("Participant", "Weight (kg)", "Height (m)"):
        raise ValueError("Unexpected INAIL participant metadata")
    return {row[0]: {"massKg": float(row[1]) if row[1] is not None else None,
                     "heightM": float(row[2]) if row[2] is not None else None}
            for row in rows[1:] if row[0]}


def load_vertical_acceleration(kinematics, start, stop, cutoff_hz=6, window_samples=101):
    markers = kinematics["data_3D"]
    point = np.mean(np.asarray([markers[name][:, 1] for name in LOAD_MARKERS]), axis=0)
    if not np.all(np.isfinite(point)):
        raise ValueError("Missing box markers")
    sample_rate = float(kinematics["fs_3D"])
    if sample_rate != 340:
        raise ValueError("Unexpected kinematic sampling rate")
    smoothed = filtfilt(*butter(4, cutoff_hz, fs=sample_rate), point)
    acceleration = savgol_filter(smoothed, window_samples, 3, deriv=2,
                                 delta=1 / sample_rate)
    travel = float(np.max(smoothed[start:stop]) - np.min(smoothed[start:stop]))
    return acceleration, travel


def trial_result(subject, mass, kinematics, force):
    name = kinematics["task"].removesuffix(".TDF")
    if force["task"] != kinematics["task"]:
        raise ValueError(f"Trial alignment mismatch: {name}")
    condition = next((item for item in name.split("_") if item.startswith("LI")), None)
    if condition not in LOAD_KG:
        raise ValueError(f"Unknown load condition: {name}")
    load = LOAD_KG[condition]
    events = kinematics["events"]
    start, stop = int(events["start"]), int(events["stop"])
    plate = force["platform_data"]
    left = np.asarray(plate["F_l"], dtype=float)
    right = np.asarray(plate["F_r"], dtype=float)
    if left.ndim != 2 or right.ndim != 2 or left.shape != right.shape or left.shape[1] != 3:
        return None, "missing_force_plate"
    resultant = np.asarray(plate["F_ris"], dtype=float)
    if resultant.shape != left.shape or np.nanmax(np.abs(left + right - resultant)) > 1e-3:
        return None, "inconsistent_resultant_force"
    fs_force = float(force["fs_forces"])
    fs_motion = float(kinematics["fs_3D"])
    if fs_force != 680 or fs_motion != 340:
        raise ValueError("Unexpected INAIL force or motion sample rate")
    n = len(kinematics["data_3D"]["c7"])
    if start < fs_motion or stop - start < fs_motion // 2 or stop > n - 15:
        return None, "invalid_lift_events"
    if stop / fs_motion >= len(left) / fs_force - .05:
        return None, "force_plate_shorter_than_lift"
    accelerations = {
        key: load_vertical_acceleration(kinematics, start, stop, *settings)
        for key, settings in ACCELERATION_FILTERS.items()
    }
    accel, travel = accelerations["primary"]
    if not .12 <= travel <= 1.5:
        return None, "implausible_load_travel"

    t_motion = np.arange(n) / fs_motion
    t_force = np.arange(len(left)) / fs_force
    observed = np.interp(t_motion, t_force, left[:, 1] + right[:, 1])
    if not np.all(np.isfinite(observed)):
        return None, "invalid_force_samples"
    pre = observed[max(0, start - int(.7 * fs_motion)):start - int(.2 * fs_motion)]
    if len(pre) < 100:
        return None, "short_pre_lift_baseline"
    pre_median = float(np.median(pre))
    if not .7 <= pre_median / (mass * G) <= 1.3:
        return None, "pre_lift_plate_mass_mismatch"

    # The subject mass comes from the released spreadsheet, never from the
    # force plate. No coefficient is learned from the test participants.
    static = np.full(stop - start, (mass + load) * G)
    dynamic = static + load * accel[start:stop]
    measured = observed[start:stop]
    norm = (mass + load) * G
    sensitivity_mae = {
        key: round(float(np.mean(np.abs(measured - static - load * candidate[start:stop])) / norm), 4)
        for key, (candidate, _) in accelerations.items() if key != "primary"
    }
    return {
        "subject": subject,
        "trial": name,
        "condition": condition,
        "boxKg": load,
        "subjectKg": mass,
        "ascentDurationS": round((stop - start) / fs_motion, 3),
        "boxVerticalTravelM": round(travel, 3),
        "preLiftSupportN": round(pre_median, 1),
        "preLiftSupportMinusBodyWeightN": round(pre_median - mass * G, 1),
        "ascentMeasuredMeanN": round(float(np.mean(measured)), 1),
        "ascentStaticMaeRatio": round(float(np.mean(np.abs(measured - static)) / norm), 4),
        "ascentBoxAccelerationMaeRatio": round(float(np.mean(np.abs(measured - dynamic)) / norm), 4),
        "moreSmoothedAccelerationMaeRatio": sensitivity_mae["more_smoothing"],
        "lessSmoothedAccelerationMaeRatio": sensitivity_mae["less_smoothing"],
        "ascentStaticBiasRatio": round(float(np.mean(measured - static) / norm), 4),
        "ascentBoxAccelerationBiasRatio": round(float(np.mean(measured - dynamic) / norm), 4),
    }, None


def median(rows, key):
    return round(float(np.median([row[key] for row in rows])), 4)


def main():
    profiles = profile_masses()
    paths = sorted(CACHE.glob("S*_all_trials.mat"))
    if len(paths) != 17 or len(profiles) != 17:
        raise ValueError("Expected 17 source subjects and anthropometric profiles")
    rows, exclusions = [], []
    for path in paths:
        subject = path.stem.split("_")[0]
        data = loadmat(path, simplify_cells=True)[path.stem]
        kinematics = data["Kinematic_data"]
        force = data["Ground_forces_and_moments"]
        if len(kinematics) != len(force):
            raise ValueError(f"Trial counts differ for {subject}")
        for motion, plates in zip(kinematics, force):
            if profiles[subject]["massKg"] is None:
                exclusions.append({"subject": subject, "trial": motion["task"],
                                   "reason": "missing_subject_mass_and_undocumented_LI1S_LI2S_load"})
                continue
            row, reason = trial_result(subject, profiles[subject]["massKg"], motion, plates)
            if row is None:
                exclusions.append({"subject": subject, "trial": motion["task"], "reason": reason})
            else:
                rows.append(row)
    by_person = []
    for subject in sorted(key for key in profiles if profiles[key]["massKg"] is not None):
        group = [row for row in rows if row["subject"] == subject]
        if not group:
            raise ValueError(f"No usable trial for {subject}")
        by_person.append({
            "subject": subject,
            "trials": len(group),
            "massKg": profiles[subject]["massKg"],
            "heightM": profiles[subject]["heightM"],
            "medianStaticMaeRatio": median(group, "ascentStaticMaeRatio"),
            "medianBoxAccelerationMaeRatio": median(group, "ascentBoxAccelerationMaeRatio"),
            "medianMoreSmoothedAccelerationMaeRatio": median(group, "moreSmoothedAccelerationMaeRatio"),
            "medianLessSmoothedAccelerationMaeRatio": median(group, "lessSmoothedAccelerationMaeRatio"),
            "medianPreLiftWeightErrorN": median(group, "preLiftSupportMinusBodyWeightN"),
        })
    better = sum(person["medianBoxAccelerationMaeRatio"] < person["medianStaticMaeRatio"]
                 for person in by_person)
    paired_improvement = [person["medianStaticMaeRatio"] -
                          person["medianBoxAccelerationMaeRatio"] for person in by_person]
    sensitivity = {}
    for key, setting, field in (
        ("moreSmoothing", ACCELERATION_FILTERS["more_smoothing"],
         "medianMoreSmoothedAccelerationMaeRatio"),
        ("primary", ACCELERATION_FILTERS["primary"], "medianBoxAccelerationMaeRatio"),
        ("lessSmoothing", ACCELERATION_FILTERS["less_smoothing"],
         "medianLessSmoothedAccelerationMaeRatio"),
    ):
        sensitivity[key] = {
            "lowpassHz": setting[0],
            "savitzkyGolayWindowSamples": setting[1],
            "participantMedianMaeRatio": median(by_person, field),
            "participantsBeatingStatic": sum(person[field] < person["medianStaticMaeRatio"]
                                              for person in by_person),
        }
    report = {
        "source": "INAIL Lifting Dataset 1, Human Data Corpus; public raw trial files from Dataset1.zip",
        "sourceUrl": "https://humandatacorpus.org/lifting-and-carrying-iso-11228/",
        "status": "external_vertical_support_force_only_not_barbell_or_muscle_force",
        "protocol": "The ZIP contains 17 participants, but its spreadsheet omits body mass and height for S11-S17, whose LI1S/LI2S crate loads are also not documented by the included task report. Restrict the forward benchmark to 10 participants with recorded mass and LI1/LI2/LI3 trials: 23/23/22.09 kg crate per the source report. Take each released lift-start to lift-stop event and interpolate summed left+right vertical force-plate signals from 680 to 340 Hz. Fixed static prediction is participant mass plus crate mass times 9.81. Dynamic candidate adds crate mass times measured crate-marker vertical acceleration after 6 Hz Butterworth filtering and 101-sample Savitzky-Golay differentiation. Two preselected filter alternatives (4 Hz/131 samples, 8 Hz/71 samples) test acceleration sensitivity on the same accepted trials. No plate signal is fitted to the prediction. Per-trial MAE is divided by total static weight; each participant's trial median is the independent summary unit.",
        "summary": {
            "sourceParticipants": len(profiles),
            "eligibleParticipants": len(by_person),
            "sourceTrials": len(rows) + len(exclusions),
            "eligibleTrials": sum(1 for row in rows + exclusions
                                  if row["subject"] in {p["subject"] for p in by_person}),
            "acceptedTrials": len(rows),
            "excludedTrials": len(exclusions),
            "participantsBoxAccelerationBeatsStatic": better,
            "oneSidedSignTestP": round(float(binomtest(better, len(by_person), 0.5,
                                                        alternative="greater").pvalue), 5),
            "participantMedianStaticMaeRatio": median(by_person, "medianStaticMaeRatio"),
            "participantMedianBoxAccelerationMaeRatio": median(by_person, "medianBoxAccelerationMaeRatio"),
            "participantMedianPairedImprovementRatio": round(float(np.median(paired_improvement)), 4),
            "participantMedianPreLiftWeightErrorN": median(by_person, "medianPreLiftWeightErrorN"),
        },
        "accelerationFilterSensitivity": sensitivity,
        "excluded": exclusions,
        "participants": by_person,
        "trials": rows,
        "limitations": [
            "This is two-handed crate lifting, not a barbell squat, bench press, or overhead press.",
            "Only the crate acceleration is modeled. Human body-segment center-of-mass acceleration and crate contact timing are not observed by the app's simple input form.",
            "The measured crate trajectory is an experimental input used in this benchmark. The phone prescribes an animation and does not measure a user's actual motion.",
            "Pre-lift force-plate support checks unit plausibility but is not used to tune the force prediction.",
            "Ground reaction is a sum of all external support forces. It does not identify any joint net moment or individual muscle tension.",
            "Source data may not grant redistribution rights; no original trial data or derived personal records are shipped in the app.",
            "Seven source participants have no recorded mass or height in the included spreadsheet; their LI1S/LI2S protocol is not defined in the included report, so these trials are excluded from this benchmark.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
