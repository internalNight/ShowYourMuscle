"""Audit static squat EMG and IK/ID comparability in the Second Skin release.

The source's EMG MATLAB tables are decoded with mat-io, which supports MATLAB
MCOS tables. Numbers are descriptive and do not identify muscle force.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from matio import load_from_mat
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".cache/second-skin/OpenSource_Dataset/Data"
CONDITIONS = ("unweighted", "vest_25lb")
JOINTS = ("hip_flexion_r", "knee_angle_r", "ankle_angle_r")


def load_condition(subject, condition, begin, end):
    name = f"pseudo_static_sym_squat_{condition}"
    folder = DATA / subject
    mat = folder / "EMG" / name / f"{name}_01_EMG.mat"
    csv = folder / "MachineLearning" / name / f"{name}_01.csv"
    emg = load_from_mat(mat)["data"]
    ml = pd.read_csv(csv)
    if not isinstance(emg, pd.DataFrame) or not {"Header", "rect_fem_r", "vas_lat_r"}.issubset(emg):
        raise ValueError(f"Unexpected EMG table: {mat}")
    mask_emg = (emg.Header >= begin) & (emg.Header <= end)
    mask_ml = (ml.time >= begin) & (ml.time <= end)
    if mask_emg.sum() < 1000 or mask_ml.sum() < 100:
        raise ValueError(f"Insufficient steady samples: {subject} {condition}")
    e, k = emg.loc[mask_emg], ml.loc[mask_ml]
    if any(not np.isfinite(e[col]).all() for col in e.columns):
        raise ValueError(f"Nonfinite EMG during steady interval: {subject} {condition}")
    return {
        "emgSamples": int(len(e)), "kineticSamples": int(len(k)),
        "semitendinosusSemimembranosusSamplesExactlyEqual": bool(
            np.array_equal(e["semiten_r"].to_numpy(), e["semimem_r"].to_numpy())),
        "angleMedianDeg": {joint: round(float(np.degrees(k[joint].median())), 2)
                           for joint in JOINTS},
        "angleP5P95Deg": {joint: [round(float(np.degrees(k[joint].quantile(q))), 2)
                                 for q in (0.05, 0.95)] for joint in JOINTS},
        "netMomentMedianNmPerKg": {joint: round(float(k[joint + "_moment"].median()), 4)
                                   for joint in JOINTS},
        "emgMedianSourceMvcNormalized": {
            channel: round(float(e[channel].median()), 4)
            for channel in e.columns if channel != "Header"
        },
    }, e, k


def pose_match(unweighted, vest):
    _, emg_a, ml_a = unweighted
    _, emg_b, ml_b = vest
    angles_a = np.degrees(ml_a[list(JOINTS)].to_numpy())
    angles_b = np.degrees(ml_b[list(JOINTS)].to_numpy())
    distance, nearest = cKDTree(angles_a).query(angles_b)
    absolute_error = np.abs(angles_a[nearest] - angles_b)
    accepted = np.all(absolute_error <= 3, axis=1)
    indices = np.flatnonzero(accepted)
    result = {
        "angleToleranceDegEachJoint": 3,
        "acceptedVestFrames": int(len(indices)),
        "totalVestFrames": int(len(ml_b)),
        "uniqueUnweightedFrames": int(len(np.unique(nearest[accepted]))),
        "uniqueUnweightedCoverageFraction": round(
            float(len(np.unique(nearest[accepted])) / len(ml_a)), 4),
        "medianMaximumAngleErrorDeg": round(float(np.median(np.max(absolute_error[accepted], axis=1))), 3)
        if len(indices) else None,
    }
    if len(indices):
        channels = [channel for channel in emg_a.columns if channel != "Header"]
        result["emgVestToUnweightedMatchedMedianRatio"] = {}
        for channel in channels:
            a = np.interp(ml_a.time.iloc[nearest[accepted]], emg_a.Header, emg_a[channel])
            b = np.interp(ml_b.time.iloc[indices], emg_b.Header, emg_b[channel])
            denominator = float(np.median(a))
            result["emgVestToUnweightedMatchedMedianRatio"][channel] = (
                round(float(np.median(b) / denominator), 3) if denominator > 0 else None)
    # Reusing <1 s of one trial to describe most of the other trial is not
    # convincing posture coverage, even when thousands of target frames match.
    result["passesCoverageGate"] = bool(len(indices) / len(ml_b) >= 0.2 and
                                        len(np.unique(nearest[accepted])) / len(ml_a) >= 0.1)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", nargs="+", default=[
        "AB01", "AB02", "AB03", "AB04", "AB05", "AB06", "AB08", "AB09", "AB10", "AB11"])
    parser.add_argument("--begin", type=float, default=10)
    parser.add_argument("--end", type=float, default=20)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/data/second_skin_static_emg_audit.json")
    args = parser.parse_args()
    if not 0 <= args.begin < args.end <= 30:
        parser.error("Require 0 <= begin < end <= 30 seconds")
    subjects = {}
    for subject in args.subjects:
        loaded = {condition: load_condition(subject, condition, args.begin, args.end)
                  for condition in CONDITIONS}
        pair = {condition: loaded[condition][0] for condition in CONDITIONS}
        a, b = (pair[c] for c in CONDITIONS)
        pair["difference"] = {
            "angleMedianVestMinusUnweightedDeg": {
                joint: round(b["angleMedianDeg"][joint] - a["angleMedianDeg"][joint], 2)
                for joint in JOINTS},
            "angleP5P95OverlapDeg": {
                joint: round(max(0, min(a["angleP5P95Deg"][joint][1],
                                        b["angleP5P95Deg"][joint][1])
                                 - max(a["angleP5P95Deg"][joint][0],
                                       b["angleP5P95Deg"][joint][0])), 2)
                for joint in JOINTS},
            "netMomentVestMinusUnweightedNmPerKg": {
                joint: round(b["netMomentMedianNmPerKg"][joint]
                             - a["netMomentMedianNmPerKg"][joint], 4)
                for joint in JOINTS},
            "emgVestToUnweightedMedianRatio": {
                channel: round(b["emgMedianSourceMvcNormalized"][channel]
                               / a["emgMedianSourceMvcNormalized"][channel], 3)
                if a["emgMedianSourceMvcNormalized"][channel] > 0 else None
                for channel in a["emgMedianSourceMvcNormalized"]},
        }
        pair["poseMatched"] = pose_match(loaded["unweighted"], loaded["vest_25lb"])
        subjects[subject] = pair
    output = {
        "source": "Georgia Tech EPIC Lab The Second Skin; repository DOI 10.35090/gatech/78043; CC BY 4.0",
        "status": "static_posture_screen_only_not_load_effect_or_muscle_force_validation",
        "intervalSeconds": [args.begin, args.end],
        "protocol": "Symmetric ~30 s half squat at fixed hand-work height, unweighted versus 25 lb vest. EMG is source filtered and MVC-normalized MATLAB table; ML CSV contains OpenSim IK and inverse-dynamics values. Each condition is summarized over the same 10-20 s time window. A separate exploratory comparison nearest-matches each vest frame to an unweighted frame by right hip, knee and ankle angle within 3 degrees per joint; coverage gate requires >=20% of vest frames and >=10% unique unweighted frames in the 10 s windows. It does not control fatigue or other trial differences.",
        "caveats": [
            "The two condition trials are separate and posture can differ; medians are descriptive, not a controlled load effect.",
            "Surface EMG in source MVC units does not measure individual muscle force or mechanical tension.",
            "Net moments are source OpenSim outputs normalized by mass; they are not directly measured single-muscle forces.",
            "Static half squat with a vest is not the app's dynamic barbell squat.",
        ],
        "summary": {
            "subjects": len(subjects),
            "subjectsWithP5P95OverlapAtAllThreeJoints": sum(
                all(value > 0 for value in row["difference"]["angleP5P95OverlapDeg"].values())
                for row in subjects.values()),
            "subjectsPassingPoseMatchCoverageGate": sum(
                row["poseMatched"]["passesCoverageGate"] for row in subjects.values()),
            "trialsWithExactlyDuplicatedSemitendinosusSemimembranosus": sum(
                row[condition]["semitendinosusSemimembranosusSamplesExactlyEqual"]
                for row in subjects.values() for condition in CONDITIONS),
            "subjectsRightRectusFemorisMedianHigherWithVest": sum(
                row["difference"]["emgVestToUnweightedMedianRatio"]["rect_fem_r"] > 1
                for row in subjects.values()),
        },
        "subjects": subjects,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    for subject, pair in subjects.items():
        print(subject, pair["difference"], "matched", pair["poseMatched"]["acceptedVestFrames"],
              "unique", pair["poseMatched"]["uniqueUnweightedFrames"],
              "gate", pair["poseMatched"]["passesCoverageGate"])
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
