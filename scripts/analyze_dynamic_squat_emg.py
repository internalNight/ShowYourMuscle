"""Exploratory EMG envelope contrast at the matched squat frames.

Raw surface EMG is electrical activity, not muscle force. The filtering here is
an explicit analysis choice, not part of the Georgia Tech source data.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, sosfiltfilt

from analyze_dynamic_squats import (
    ANGLE_LIMITS_DEG, CACHE, ROOT, TRIAL_OVERRIDES, load_trial, match_phase,
    read_csv,
)


CHANNELS = ("RF", "VL", "GMAX", "BF", "GMED", "MGAS", "TA", "GRAC")


def emg_envelopes(subject, load, angle_time, rms_ms):
    trial = TRIAL_OVERRIDES.get((subject, load), f"squats_1_{load}")
    path = CACHE / subject / trial / f"{subject}_{trial}_emg.csv"
    table = read_csv(path)
    time = table["time"]
    dt = float(np.median(np.diff(time)))
    if not np.isclose(dt, 0.0005, atol=1e-6):
        raise ValueError(f"Unexpected EMG sample interval in {path}: {dt}")
    if abs(time[0] - angle_time[0]) > 1e-5 or abs(time[-1] - angle_time[-1]) > 1e-5:
        raise ValueError(f"EMG and angle time ranges differ in {path}")
    names = [side + name for side in ("R", "L") for name in CHANNELS]
    raw = np.column_stack([table[name] for name in names])
    if not np.isfinite(raw).all():
        raise ValueError(f"Nonfinite EMG values in {path}")
    sos = butter(4, [20, 450], btype="bandpass", fs=2000, output="sos")
    filtered = sosfiltfilt(sos, raw, axis=0)
    # Centered RMS at each EMG sample, then interpolate to the 200 Hz angle grid.
    rms = np.sqrt(np.maximum(uniform_filter1d(
        filtered ** 2, size=round(rms_ms * 2), axis=0), 0))
    return {name: np.interp(angle_time, time, rms[:, j])
            for j, name in enumerate(names)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", nargs="+", default=[
        "AB01", "AB02", "AB03", "AB05", "AB06", "AB07", "AB08", "AB09",
        "AB10", "AB11", "AB12", "AB13"])
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs" / "data" / "dynamic_squat_emg_pilot.json")
    parser.add_argument("--rms-ms", type=float, default=100,
                        help="Centered EMG RMS window in milliseconds")
    args = parser.parse_args()
    if args.rms_ms <= 0:
        parser.error("--rms-ms must be positive")
    report = {
        "source": "Scherpereel et al. (2023) raw 2000 Hz surface EMG; same squat trials as dynamic_squat_angle_match.json",
        "processing": f"4th-order zero-phase Butterworth 20-450 Hz bandpass; centered {args.rms_ms:g} ms RMS; interpolated to 200 Hz angle grid; median loaded RMS / median unloaded RMS at matched frames",
        "limitations": "Exploratory signal-envelope contrast; no MVC normalization, electrode placement review, fatigue control, or muscle-force inference. A simple active/inactive signal ratio gate is applied only to cross-subject summaries",
        "subjects": {},
    }
    for subject in args.subjects:
        no_load, loaded = load_trial(subject, "0lbs"), load_trial(subject, "25lbs")
        envelopes = (emg_envelopes(subject, "0lbs", no_load["time"], args.rms_ms),
                     emg_envelopes(subject, "25lbs", loaded["time"], args.rms_ms))
        report["subjects"][subject] = {}
        for phase in ("descent", "ascent"):
            i, j, _, query_count, _, _ = match_phase(
                no_load, loaded, phase, ANGLE_LIMITS_DEG, 50)
            values = {"accepted_matches": len(j), "loaded_frames": query_count}
            if len(j):
                baseline = {name: float(np.median(envelopes[0][name][i]))
                            for name in envelopes[0]}
                if any(value <= 0 for value in baseline.values()):
                    raise ValueError(f"Nonpositive EMG RMS in {subject} {phase}")
                values["unloaded_median_rms_v"] = {
                    name: round(value, 8) for name, value in baseline.items()}
                inactive = ~no_load["task_active"]
                values["unloaded_matched_to_inactive_rms_ratio"] = {
                    name: round(float(baseline[name] /
                                      np.median(envelopes[0][name][inactive])), 3)
                    for name in envelopes[0]}
                loaded_inactive = ~loaded["task_active"]
                values["loaded_matched_to_inactive_rms_ratio"] = {
                    name: round(float(np.median(envelopes[1][name][j]) /
                                      np.median(envelopes[1][name][loaded_inactive])), 3)
                    for name in envelopes[0]}
                values["loaded_to_unloaded_rms_ratio"] = {
                    name: round(float(np.median(envelopes[1][name][j]) /
                                      baseline[name]), 3)
                    for name in envelopes[0]}
            report["subjects"][subject][phase] = values
    report["cross_subject_summary"] = {}
    for phase in ("descent", "ascent"):
        accepted = {subject: x[phase] for subject, x in report["subjects"].items()
                    if x[phase]["accepted_matches"] >= 30 and
                    x[phase]["accepted_matches"] / max(x[phase]["loaded_frames"], 1) >= 0.2}
        summary = {"accepted_subjects": list(accepted),
                   "excluded_subjects": [x for x in report["subjects"] if x not in accepted]}
        if accepted:
            summary["channel_ratios"] = {}
            for channel in next(iter(accepted.values()))["loaded_to_unloaded_rms_ratio"]:
                eligible = {subject: x for subject, x in accepted.items()
                            if x["unloaded_matched_to_inactive_rms_ratio"][channel] >= 1.5
                            and x["loaded_matched_to_inactive_rms_ratio"][channel] >= 1.5}
                if not eligible:
                    summary["channel_ratios"][channel] = {"eligible_subjects": []}
                    continue
                vals = np.array([x["loaded_to_unloaded_rms_ratio"][channel]
                                 for x in eligible.values()])
                summary["channel_ratios"][channel] = {
                    "eligible_subjects": list(eligible),
                    "median": round(float(np.median(vals)), 3),
                    "subjects_above_one": int(np.sum(vals > 1)),
                    "range": [round(float(np.min(vals)), 3),
                              round(float(np.max(vals)), 3)],
                }
        report["cross_subject_summary"][phase] = summary
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(report["cross_subject_summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
