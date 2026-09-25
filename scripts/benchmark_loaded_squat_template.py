"""Compare the phone's fixed support-force scenario with public 0/25-lb plates.

The source reports an added 25-lb weight but not its placement. This is a
research comparison of total vertical force, never a muscle-force validation.
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from analyze_dynamic_squats import load_trial
from benchmark_template_squat_grf import G, SUBJECTS, measured_repetitions


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREDICTIONS = ROOT / ".cache/lower-limb/loaded_squat_template_predictions.json"
DEFAULT_OUTPUT = ROOT / "docs/data/loaded_squat_template_grf_benchmark.json"


def summarize(rows, key):
    values = np.array([row[key] for row in rows])
    return round(float(np.median(values)), 4)


def condition_summary(rows, subjects, label):
    relevant = [row for row in rows if row["condition"] == label]
    per_person = []
    for subject in subjects:
        reps = [row for row in relevant if row["subject"] == subject]
        if not reps:
            continue
        per_person.append({
            "subject": subject, "reps": len(reps),
            "medianDurationS": summarize(reps, "durationS"),
            "medianStaticMaeRatio": summarize(reps, "staticMaeRatio"),
            "medianBodyMotionPlusStaticLoadMaeRatio": summarize(
                reps, "bodyMotionPlusStaticLoadMaeRatio"),
            "medianFixedMaeRatio": summarize(reps, "fixedMaeRatio"),
            "medianTimedMaeRatio": summarize(reps, "timedMaeRatio"),
            "medianObservedMeanWeightRatio": summarize(reps, "observedMeanWeightRatio"),
        })
    improvements = np.array([r["medianStaticMaeRatio"] - r["medianFixedMaeRatio"]
                             for r in per_person])
    timed_improvements = np.array([r["medianStaticMaeRatio"] - r["medianTimedMaeRatio"]
                                   for r in per_person])
    bar_motion_improvements = np.array([
        r["medianBodyMotionPlusStaticLoadMaeRatio"] - r["medianFixedMaeRatio"]
        for r in per_person])
    rng = np.random.default_rng(77)
    indices = rng.integers(len(per_person), size=(10000, len(per_person)))
    ci = np.quantile(np.median(improvements[indices], axis=1), [.025, .975])
    return {
        "subjects": len(per_person), "reps": len(relevant),
        "subjectMedianDurationS": summarize(per_person, "medianDurationS"),
        "subjectMedianStaticMaeRatio": summarize(per_person, "medianStaticMaeRatio"),
        "subjectMedianBodyMotionPlusStaticLoadMaeRatio": summarize(
            per_person, "medianBodyMotionPlusStaticLoadMaeRatio"),
        "subjectMedianFixedMaeRatio": summarize(per_person, "medianFixedMaeRatio"),
        "subjectMedianTimedMaeRatio": summarize(per_person, "medianTimedMaeRatio"),
        "subjectMedianObservedMeanWeightRatio": summarize(per_person, "medianObservedMeanWeightRatio"),
        "pairedSubjectMedianFixedImprovementRatio": round(float(np.median(improvements)), 4),
        "pairedSubjectMedianFixedImprovementBootstrap95": [round(float(x), 4) for x in ci],
        "pairedSubjectMedianTimedImprovementRatio": round(float(np.median(timed_improvements)), 4),
        "subjectsFixedBeatsStatic": int(np.sum(improvements > 0)),
        "subjectsTimedBeatsStatic": int(np.sum(timed_improvements > 0)),
        "pairedSubjectMedianBarMotionImprovementRatio": round(float(np.median(
            bar_motion_improvements)), 4),
        "subjectsBarMotionBeatsStaticLoad": int(np.sum(bar_motion_improvements > 0)),
        "perSubject": per_person,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-depth-deg", type=float, default=50)
    parser.add_argument("--minimum-active-fraction", type=float, default=.5)
    args = parser.parse_args()
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    phases = np.asarray(predictions["phases"], dtype=float)
    if len(phases) != 99 or not np.allclose(phases, np.arange(1, 100) / 100):
        raise ValueError("Expected 99 interior phases from the exact app formula")
    if predictions["durationS"] != 2.8 or predictions["loadKg"] != 25 * .45359237:
        raise ValueError("Unexpected template duration or 25-lb conversion")
    lookup = {(r["subject"], "0lbs" if r["extraLoadKg"] == 0 else "25lbs"): r
              for r in predictions["rows"]}
    with (ROOT / ".cache/lower-limb-raw/Subject_masses.csv").open(
            newline="", encoding="utf-8-sig") as handle:
        masses = {r["Subject"]: float(r["Mass"]) for r in csv.DictReader(handle)}
    rows = []
    for subject in SUBJECTS:
        for label in ("0lbs", "25lbs"):
            trial = load_trial(subject, label)
            time = trial["time"]
            plate = trial["grf"]["RForceY_Vertical"] + trial["grf"]["LForceY_Vertical"]
            load_kg = 0 if label == "0lbs" else predictions["loadKg"]
            static_n = (masses[subject] + load_kg) * G
            template = np.asarray(lookup[subject, label]["ratioToStaticTotalWeight"])
            no_load_acceleration = (masses[subject] * np.asarray(
                lookup[subject, "0lbs"]["ratioToStaticTotalWeight"]) + load_kg) / (
                    masses[subject] + load_kg)
            for number, (start, peak, end) in enumerate(measured_repetitions(
                    trial, args.minimum_depth_deg, args.minimum_active_fraction), 1):
                duration = float(time[end] - time[start])
                observed = np.interp(time[start] + phases * duration, time, plate) / static_n
                fixed_mae = float(np.mean(np.abs(observed - template)))
                timed = 1 + (template - 1) * (predictions["durationS"] / duration) ** 2
                rows.append({
                    "subject": subject, "condition": label, "rep": number,
                    "startS": round(float(time[start]), 3),
                    "deepestS": round(float(time[peak]), 3),
                    "endS": round(float(time[end]), 3),
                    "durationS": round(duration, 3),
                    "peakKneeFlexionDeg": round(float(-trial["angle"][peak, 1]), 2),
                    "observedMeanWeightRatio": round(float(np.mean(observed)), 4),
                    "observedMinMaxWeightRatio": [round(float(np.min(observed)), 3),
                                                  round(float(np.max(observed)), 3)],
                    "staticMaeRatio": round(float(np.mean(np.abs(observed - 1))), 4),
                    "bodyMotionPlusStaticLoadMaeRatio": round(float(np.mean(
                        np.abs(observed - no_load_acceleration))), 4),
                    "fixedMaeRatio": round(fixed_mae, 4),
                    "timedMaeRatio": round(float(np.mean(np.abs(observed - timed))), 4),
                })
    summary = {label: condition_summary(rows, SUBJECTS, label)
               for label in ("0lbs", "25lbs")}
    result = {
        "status": "research_only_not_validated_personal_force_or_muscle_force",
        "source": "Scherpereel et al. 2023 public 0/25-lb squat angle and bilateral force-plate CSVs",
        "viewerDurationS": predictions["durationS"],
        "viewerHeightAssumptionCm": predictions["heightCm"],
        "appTemplate": "Exact squatVerticalSupportScenario at 175 cm, measured subject mass, app 2.8-s cycle, zero bar offset, 25 lb converted to kg; actual load placement is unreported",
        "observedNormalization": "bilateral vertical GRF divided by (subject mass + condition load) * 9.80665",
        "maeRatio": "99 phase-point mean absolute error versus observed normalized GRF; static baseline equals 1",
        "barMotionAblation": "For 25 lb, compare exact app scenario against (body mass * 0-lb app support ratio + added-load static mass) / total mass; both share the same prescribed body motion",
        "segmentation": f"Consecutive standing-like right-knee valleys enclosing one deep peak; 0.9-4 s, peak >= {args.minimum_depth_deg:g} deg, >=40 deg excursion, >= {args.minimum_active_fraction:.0%} bilateral activity flags; align experimental boundaries to app phases",
        "summary": summary,
        "limitations": [
            "The 25-lb weight placement and trajectory are not reported, so the app's load path is an unverified assumption.",
            "The source lacks participant heights; all app predictions use 175 cm and a prescribed symmetric motion.",
            "Experimental repetition boundaries provide optimistic alignment unavailable from user-entered body and training parameters.",
            "The measured-duration scaling uses laboratory timing and is diagnostic only.",
            "Total vertical force does not determine a joint net moment or individual muscle force.",
            "Bootstrap resamples people, not correlated repetitions, and describes only this sample.",
        ],
        "repetitions": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: {x: y for x, y in v.items() if x != "perSubject"}
                      for k, v in summary.items()}, ensure_ascii=False, indent=2))
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
