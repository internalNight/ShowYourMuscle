"""Held-out-person test of phase-only squat net-joint-moment reference curves.

The phone can scrub a prescribed phase without measuring knee angle. This
checks whether a cohort phase curve transfers between people, then reports a
held-out coverage band. Source inverse-dynamics moments are N m/kg; they are
not muscle forces. Laboratory knee kinematics are used to *segment* reps, an
optimistic alignment that a phone with manual phase control cannot automate.
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from analyze_dynamic_squats import ROOT, load_trial
from benchmark_template_squat_grf import SUBJECTS, measured_repetitions


PHASES = np.arange(1, 100) / 100
TARGETS = ("hip_flexion_r_moment", "knee_angle_r_moment",
           "ankle_angle_r_moment")
OUTPUT = ROOT / "docs/data/squat_phase_joint_moment_loso.json"


def rounded(value):
    return round(float(value), 4)


def subject_curves(subject, load):
    trial = load_trial(subject, load)
    reps = measured_repetitions(trial, 50, 0.5)
    if not reps:
        return None
    t = trial["time"]
    curves = {}
    repetitions = {}
    for target in TARGETS:
        sampled = [np.interp(t[start] + PHASES * (t[end] - t[start]),
                             t, trial["moment"][target])
                   for start, _, end in reps]
        repetitions[target] = np.asarray(sampled)
        curves[target] = np.median(repetitions[target], axis=0)
    return {"reps": len(reps), "curves": curves,
            "repetitionCurves": repetitions}


def audit(load, subjects, masses):
    rows = []
    for person, held in subjects.items():
        others = [subject["curves"] for name, subject in subjects.items()
                  if name != person]
        for target in TARGETS:
            training = np.asarray([item[target] for item in others])
            observed = held["repetitionCurves"][target]
            phase_prediction = np.median(training, axis=0)
            training_names = [name for name in subjects if name != person]
            training_mass = np.asarray([masses[name] for name in training_names])
            center_mass = np.median(training_mass)
            centered_mass = training_mass - center_mass
            # Fixed strong shrinkage for only 11 independent training people.
            slope = centered_mass @ (training - phase_prediction) / (
                np.sum(centered_mass ** 2) + len(training_names) * 20 ** 2)
            mass_prediction = phase_prediction + slope * (masses[person] - center_mass)
            flat_prediction = np.full(len(PHASES), np.median(training))
            lower = np.quantile(training, 0.1, axis=0)
            upper = np.quantile(training, 0.9, axis=0)
            inner_p80_errors = []
            for inner_name in training_names:
                inner_training = np.asarray([
                    subjects[name]["curves"][target] for name in training_names
                    if name != inner_name])
                inner_prediction = np.median(inner_training, axis=0)
                inner_observed = subjects[inner_name]["repetitionCurves"][target]
                inner_p80_errors.append(np.quantile(
                    np.abs(inner_observed - inner_prediction), 0.8))
            # This training-only empirical radius is an audit, not a formal
            # patient/user prediction interval with a 12-person dataset.
            radius = float(np.quantile(inner_p80_errors, 0.9))
            rows.append({
                "subject": person, "load": load, "target": target,
                "reps": held["reps"],
                "phaseMaeNmPerKg": rounded(np.mean(np.abs(phase_prediction - observed))),
                "massAdjustedMaeNmPerKg": rounded(np.mean(np.abs(mass_prediction - observed))),
                "flatMaeNmPerKg": rounded(np.mean(np.abs(flat_prediction - observed))),
                "phaseP90ErrorNmPerKg": rounded(np.percentile(
                    np.abs(phase_prediction - observed), 90)),
                "trainingPersonP10P90Coverage": rounded(np.mean(
                    (observed >= lower) & (observed <= upper))),
                "trainingCalibratedRadiusNmPerKg": rounded(radius),
                "trainingCalibratedPointCoverage": rounded(np.mean(
                    np.abs(observed - phase_prediction) <= radius)),
                "observedMedianCurve": [rounded(v) for v in
                                        held["curves"][target]],
                "heldOutPrediction": [rounded(v) for v in phase_prediction],
                "heldOutMassAdjustedPrediction": [rounded(v) for v in mass_prediction],
            })
    summary = {}
    for target in TARGETS:
        subset = [row for row in rows if row["target"] == target]
        y = np.concatenate([subjects[row["subject"]]["repetitionCurves"][target].ravel()
                            for row in subset])
        prediction = np.concatenate([np.tile(row["heldOutPrediction"], row["reps"])
                                     for row in subset])
        phase_mae = np.asarray([row["phaseMaeNmPerKg"] for row in subset])
        mass_mae = np.asarray([row["massAdjustedMaeNmPerKg"] for row in subset])
        flat_mae = np.asarray([row["flatMaeNmPerKg"] for row in subset])
        summary[target] = {
            "participants": len(subset),
            "repetitions": int(sum(row["reps"] for row in subset)),
            "subjectMedianPhaseMaeNmPerKg": rounded(np.median(phase_mae)),
            "subjectMedianFlatMaeNmPerKg": rounded(np.median(flat_mae)),
            "phaseBeatsFlatSubjects": int(np.sum(phase_mae < flat_mae)),
            "subjectMedianMassAdjustedMaeNmPerKg": rounded(np.median(mass_mae)),
            "massAdjustmentBeatsPhaseSubjects": int(np.sum(mass_mae < phase_mae)),
            "pooledPhaseR2": rounded(1 - np.sum((prediction - y) ** 2) /
                                     np.sum((y - y.mean()) ** 2)),
            "subjectMedianP10P90Coverage": rounded(np.median([
                row["trainingPersonP10P90Coverage"] for row in subset])),
            "repetitionWeightedP10P90Coverage": rounded(np.average(
                [row["trainingPersonP10P90Coverage"] for row in subset],
                weights=[row["reps"] for row in subset])),
            "subjectMedianTrainingCalibratedRadiusNmPerKg": rounded(np.median([
                row["trainingCalibratedRadiusNmPerKg"] for row in subset])),
            "subjectMedianTrainingCalibratedPointCoverage": rounded(np.median([
                row["trainingCalibratedPointCoverage"] for row in subset])),
            "subjectsWithAtLeast80PercentCalibratedPointCoverage": int(sum(
                row["trainingCalibratedPointCoverage"] >= 0.8 for row in subset)),
        }
    group_shape = {}
    for target in TARGETS:
        training = np.asarray([row["curves"][target] for row in subjects.values()])
        group_shape[target] = {key: [rounded(v) for v in np.quantile(training, q, axis=0)]
                               for key, q in (("p10", 0.1), ("median", 0.5),
                                              ("p90", 0.9))}
    return rows, summary, group_shape


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    with (ROOT / ".cache/lower-limb-raw/Subject_masses.csv").open(
            newline="", encoding="utf-8-sig") as handle:
        masses = {row["Subject"]: float(row["Mass"]) for row in csv.DictReader(handle)}
    loads = {}
    for load in ("0lbs", "25lbs"):
        subjects = {name: data for name in SUBJECTS
                    if (data := subject_curves(name, load)) is not None}
        if len(subjects) != 12:
            raise ValueError(f"Expected 12 participants for {load}: {len(subjects)}")
        rows, summary, group_shape = audit(load, subjects, masses)
        loads[load] = {"summary": summary, "heldOutResults": rows,
                       "descriptiveGroupShape": group_shape}
    report = {
        "source": "Scherpereel et al. 2023, DOI 10.1038/s41597-023-02840-6",
        "status": "research_phase_reference_not_phone_personal_joint_or_muscle_force_validation",
        "protocol": "12 participants, each whole participant held out; 0 and 25 lb conditions separately. Complete repetitions segmented from measured knee angles and resampled to 99 interior phase points. Training uses one median curve per participant; the held-out prediction is tested against every repetition of that person. Flat baseline is the training-person overall median. A mass-adjusted exploratory variant fits a phasewise training-person slope around median mass with a fixed ridge penalty of 11*20^2 kg^2; no held-out data tune the slope. P10-P90 interval is recomputed only from the 11 training participants for each held-out person. A separate training-only radius uses nested leave-one-training-person-out fits: each inner person's 80th percentile absolute repetition/phase error, then the 90th percentile across the 11 inner people. Moments are source net inverse-dynamics N m/kg.",
        "limitations": [
            "Rep boundaries were identified from laboratory kinematics; no phone video or sensor provides this alignment automatically.",
            "Only bodyweight and an unspecified extra 25 lb source condition; cannot interpolate arbitrary barbell loads or infer a person's performance from body measurements.",
            "The P10-P90 envelope is empirical across training people, not a calibrated prediction interval. Coverage on held-out people is explicitly reported.",
            "The nested training radius is exploratory with just 11 calibration people; its held-out coverage and width are reported, not claimed as a guaranteed interval.",
            "Net joint moments do not identify individual muscle force or surface EMG.",
        ],
        "loads": loads,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({load: section["summary"] for load, section in loads.items()},
                     indent=2))


if __name__ == "__main__":
    main()
