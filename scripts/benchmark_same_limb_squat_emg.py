"""Independent lab test of the fixed Scherpereel bodyweight-squat RF EMG curve.

Run download_same_limb_squat.py first. SAME-Limb data remain in .cache;
this report contains only aggregate metrics and normalized, non-identifying curves.
"""

import json
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
from scipy.signal import find_peaks
from scipy.stats import binomtest, spearmanr


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/research/same_limb"
SOURCE = ROOT / "docs/data/squat_emg_phase_loso.json"
OUTPUT = ROOT / "docs/data/same_limb_squat_emg_external.json"
PHASE = np.arange(1, 100) / 100


def external_curve(path):
    with np.load(path, allow_pickle=False) as trial:
        if str(trial["schema_version"]) != "lower_limb_amg_semg_public_v1":
            raise ValueError(f"Unexpected SAME-Limb schema: {path}")
        knee_names = trial["joint_angle_names"].tolist()
        emg_names = trial["semg_channel_names"].tolist()
        knee_index = knee_names.index("left_knee_flexion")
        rf_index = emg_names.index("RF_sEMG")
        valid = trial["joint_angle_valid_mask"][:, knee_index]
        knee = trial["joint_angles_deg"][:, knee_index].astype(float)
        time_motion = trial["time_motion_s"].copy()
        time_semg = trial["time_semg_s"].copy()
        emg = trial["semg_preprocessed_basic"][:, rf_index].astype(float)

    if not np.all(valid) or not np.all(np.isfinite(knee)):
        raise ValueError(f"Invalid knee angle samples: {path}")
    if not np.all(np.isfinite(emg)):
        raise ValueError(f"Invalid EMG samples: {path}")
    if np.any(np.diff(time_motion) <= 0) or np.any(np.diff(time_semg) <= 0):
        raise ValueError(f"Nonmonotonic trial time: {path}")

    knee_smooth = gaussian_filter1d(knee, 3)
    peaks, _ = find_peaks(knee_smooth, prominence=25, distance=135)
    peaks = [int(i) for i in peaks if knee_smooth[i] >= 45]
    if len(peaks) != 3:
        raise ValueError(f"Expected 3 clear squat flexion peaks, got {len(peaks)}: {path}")
    start = peaks[0] + int(np.argmin(knee_smooth[peaks[0]:peaks[1] + 1]))
    end = peaks[1] + int(np.argmin(knee_smooth[peaks[1]:peaks[2] + 1]))
    if not start < peaks[1] < end or time_motion[end] - time_motion[start] < 1.5:
        raise ValueError(f"No valid middle squat repetition: {path}")
    if knee_smooth[peaks[1]] - max(knee_smooth[start], knee_smooth[end]) < 35:
        raise ValueError(f"Middle squat has insufficient excursion: {path}")

    # The released preprocessed channel is a 4th-order 20-450 Hz bandpass.
    # Match the source study's 100 ms centered RMS envelope; SAME-Limb is 1 kHz.
    rms = np.sqrt(np.maximum(uniform_filter1d(emg ** 2, size=100), 0))
    phase_times = time_motion[start] + PHASE * (time_motion[end] - time_motion[start])
    curve = np.interp(phase_times, time_semg, rms)
    scale = float(np.median(curve))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError(f"Invalid RF normalization: {path}")
    return curve / scale, {
        "durationS": round(float(time_motion[end] - time_motion[start]), 3),
        "kneeRangeDeg": round(float(knee_smooth[peaks[1]] -
                                    0.5 * (knee_smooth[start] + knee_smooth[end])), 1),
    }


def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    template = np.asarray(source["loads"]["0lbs"]["descriptiveGroupShape"]["RRF"]["median"], dtype=float)
    if template.shape != PHASE.shape:
        raise ValueError("Source RF group curve must have 99 phase points")
    template /= np.median(template)
    paths = sorted(CACHE.glob("user??_deep_squat_A1.npz"))
    if len(paths) != 30:
        raise ValueError(f"Expected one trial for 30 subjects, found {len(paths)}")
    curves = []
    rows = []
    for path in paths:
        observed, quality = external_curve(path)
        curves.append(observed)
        static_mae = float(np.mean(np.abs(observed - 1)))
        template_mae = float(np.mean(np.abs(observed - template)))
        rows.append({
            "subject": path.name[:6],
            **quality,
            "staticMae": round(static_mae, 4),
            "templateMae": round(template_mae, 4),
            "improvement": round(static_mae - template_mae, 4),
            "phaseSpearman": round(float(spearmanr(observed, template).statistic), 4),
        })
    improvement = np.asarray([r["improvement"] for r in rows])
    wins = int(np.sum(improvement > 0))
    same_lab_mae = []
    same_lab_spearman = []
    for i, observed in enumerate(curves):
        same_lab_template = np.median([curve for j, curve in enumerate(curves) if j != i], axis=0)
        same_lab_template /= np.median(same_lab_template)
        mae = float(np.mean(np.abs(observed - same_lab_template)))
        same_lab_mae.append(mae)
        same_lab_spearman.append(float(spearmanr(observed, same_lab_template).statistic))
        rows[i]["sameLabHeldOutMae"] = round(mae, 4)
    flat_mae = np.asarray([r["staticMae"] for r in rows])
    same_lab_improvement = flat_mae - np.asarray(same_lab_mae)
    same_lab_wins = int(np.sum(same_lab_improvement > 0))
    report = {
        "sourceTemplate": "Scherpereel et al. (2023), 0 lb group right rectus femoris phase-median EMG shape, fixed before this evaluation",
        "externalDataset": "SAME-Limb v2.0.3, Tang et al. (2026), Hugging Face dataset revision 233b0db6cfda8360338f92219e07fd3d3d1d7bdb, CC BY 4.0",
        "status": "external_no_standardized_load_squat_emg_shape_test_only_no_loaded_force_validation",
        "protocol": "One A1 deep-squat trial per each of 30 new participants. Use marker-derived left-knee flexion to identify three squat peaks; the two intervening extension minima bound the middle repetition. Released 20-450 Hz bandpassed left rectus femoris sEMG receives a centered 100 ms RMS envelope. Each observed 99-point phase curve is divided by its own temporal median. Compare the fixed normalized Scherpereel right rectus femoris group median against a flat 1 baseline. As a diagnostic, build a SAME-Limb template from the other 29 participants for each held-out person, normalized again by its temporal median. MAE and Spearman are calculated per participant; participants, not phase points, are independent units.",
        "summary": {
            "participants": len(rows),
            "templateBeatsStatic": wins,
            "oneSidedSignTestP": round(float(binomtest(wins, len(rows), 0.5, alternative="greater").pvalue), 5),
            "medianStaticMae": round(float(np.median([r["staticMae"] for r in rows])), 4),
            "medianTemplateMae": round(float(np.median([r["templateMae"] for r in rows])), 4),
            "medianPairedImprovement": round(float(np.median(improvement)), 4),
            "medianPhaseSpearman": round(float(np.median([r["phaseSpearman"] for r in rows])), 4),
            "medianDurationS": round(float(np.median([r["durationS"] for r in rows])), 3),
            "medianKneeRangeDeg": round(float(np.median([r["kneeRangeDeg"] for r in rows])), 1),
            "sameLabHeldOutTemplateBeatsStatic": same_lab_wins,
            "sameLabOneSidedSignTestP": round(float(binomtest(same_lab_wins, len(rows), 0.5, alternative="greater").pvalue), 5),
            "sameLabMedianTemplateMae": round(float(np.median(same_lab_mae)), 4),
            "sameLabMedianPairedImprovement": round(float(np.median(same_lab_improvement)), 4),
            "sameLabMedianPhaseSpearman": round(float(np.median(same_lab_spearman)), 4),
        },
        "templateCurve": [round(float(x), 3) for x in template],
        "externalGroupMedianCurve": [round(float(x), 3) for x in np.median(curves, axis=0)],
        "participantResults": rows,
        "limitations": [
            "The source condition is Scherpereel 0 lb. SAME-Limb's Deep Squat instruction used a height-adjusted box arrangement without the standardized load inside the box. SAME-Limb has no measured ground reaction or joint contact forces; this does not test loaded barbell dynamics or muscle force.",
            "The source template is right-leg RF while the external channel is left-leg RF; bilateral similarity is assumed only for this exploratory transfer test.",
            "The observed subject's own EMG median supplies normalization. Body measurements and lifting records cannot provide that quantity to the app.",
            "Surface EMG is electrical activity, not direct muscle tension, activation, or force. Protocol, depth, electrode placement, and population differ between datasets.",
            "Repetition phase is extracted from measured motion. A prescribed phone animation is not a measurement of the user's own phase.",
            "The within-SAME-Limb held-out diagnostic uses 29 template participants, versus 12 for the Scherpereel fixed external template. Differences cannot be attributed solely to laboratory protocol or laterality.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
