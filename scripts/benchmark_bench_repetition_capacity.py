"""Audit the app's fixed Epley 1RM proxy on published bench-press failure sets.

Ferri Marini et al., PLOS ONE 2022, supporting file S1 (CC BY 4.0):
https://doi.org/10.1371/journal.pone.0278909.s001

The workbook gives nominal percentages of a directly tested session 1RM and
repetitions to failure, but not individual absolute kilograms. Thus the
benchmark can check estimated / tested 1RM ratios, not absolute kilogram error.
Only sets with 1–10 reps match the phone estimator's defined domain.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = ("https://journals.plos.org/plosone/article/file?"
              "id=10.1371/journal.pone.0278909.s001&type=supplementary")
SOURCE_SHA256 = "bb35251d44626daf1c3fafff95055f6dbc3acd7f08764116ad555b2b86d5fdd0"
SOURCE = ROOT / ".cache/research/plos_bench_failure/source.xlsx"
OUTPUT = ROOT / "docs/data/bench_repetition_capacity_benchmark.json"


def source_rows():
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    if not SOURCE.exists():
        SOURCE.write_bytes(urlopen(SOURCE_URL, timeout=30).read())
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(f"Unexpected PLOS supporting-file SHA-256: {digest}")
    sheet = load_workbook(SOURCE, read_only=True, data_only=True).active
    rows = list(sheet.values)
    if sheet.max_row != 39 or sheet.max_column != 21 or rows[5][1] != "REPfailure":
        raise ValueError("Unexpected bench supporting-file layout")
    conditions = []
    for col in range(3, 21):  # zero-based D:U
        group = col - 3
        distribution = "wide" if group < 9 else "narrow"
        velocity = (50, 70, 90)[(group % 9) // 3]
        fraction = (0.50, 0.65, 0.80)[group % 3]
        if rows[4][col] != f"1-RM{int(fraction * 100)}":
            raise ValueError(f"Load header mismatch in column {col + 1}")
        conditions.append((col, distribution, velocity, fraction))
    observations = []
    for row in rows[6:16]:
        subject = row[2]
        if subject not in range(1, 11):
            raise ValueError("Expected anonymous subject IDs 1–10")
        for col, distribution, velocity, fraction in conditions:
            reps = row[col]
            if not isinstance(reps, int) or reps < 1:
                raise ValueError(f"Invalid failure repetitions for subject {subject}")
            observations.append({"subject": subject, "distribution": distribution,
                                 "velocityPercent": velocity, "nominalLoadFraction": fraction,
                                 "repetitions": reps})
    if len(observations) != 180:
        raise ValueError(f"Expected 180 sets; got {len(observations)}")
    return observations


def median(values):
    return round(float(np.median(values)), 4)


def summary(rows):
    errors = np.array([row["estimatedToMeasured1rm"] - 1 for row in rows])
    by_subject = defaultdict(list)
    for row, error in zip(rows, errors):
        by_subject[row["subject"]].append(float(error))
    subject_mae = np.array([np.mean(np.abs(values)) for values in by_subject.values()])
    return {
        "sets": len(rows), "subjects": len(by_subject),
        "setMedianSignedPercent": round(float(np.median(errors) * 100), 2),
        "setMedianAbsolutePercent": round(float(np.median(np.abs(errors)) * 100), 2),
        "subjectMedianMeanAbsolutePercent": round(float(np.median(subject_mae) * 100), 2),
        "subjectRangeMeanAbsolutePercent": [round(float(value * 100), 2)
                                            for value in (subject_mae.min(), subject_mae.max())],
        "setPercentWithinTenPercent": round(float(np.mean(np.abs(errors) <= .10) * 100), 1),
    }


def record_aggregation(rows):
    """Compare the app's best recorded set with a median of repeated sets.

    Restrict this check to the fixed 80% 1RM condition so changing the
    nominal load does not explain differences between aggregation rules.
    """
    by_subject = defaultdict(list)
    for row in rows:
        by_subject[row["subject"]].append(row["estimatedToMeasured1rm"])
    people = []
    for subject, ratios in sorted(by_subject.items()):
        if len(ratios) != 6:
            raise ValueError(f"Expected six eligible 80% sets for subject {subject}")
        maximum, middle = max(ratios), float(np.median(ratios))
        people.append({"subject": subject, "sets": len(ratios),
                       "bestSetRatio": round(maximum, 4),
                       "medianSetRatio": round(middle, 4),
                       "bestSetAbsoluteErrorPercent": round(abs(maximum - 1) * 100, 2),
                       "medianSetAbsoluteErrorPercent": round(abs(middle - 1) * 100, 2)})
    best_errors = [abs(max(ratios) - 1) for ratios in by_subject.values()]
    median_errors = [abs(float(np.median(ratios)) - 1) for ratios in by_subject.values()]
    return {
        "scope": "Only six failure sets at nominal 80% of each session's tested 1RM for each of ten people; all six conditions differ in prescribed speed or plate placement.",
        "participants": len(people), "setsPerParticipant": 6,
        "bestSetSubjectMedianAbsoluteErrorPercent": round(float(np.median(best_errors)) * 100, 2),
        "medianSetSubjectMedianAbsoluteErrorPercent": round(float(np.median(median_errors)) * 100, 2),
        "bestSetLowerAbsoluteErrorParticipants": sum(a < b for a, b in zip(best_errors, median_errors)),
        "individuals": people,
    }


def main():
    observations = source_rows()
    eligible = []
    for row in observations:
        if row["repetitions"] > 10:
            continue
        reps = row["repetitions"]
        ratio = row["nominalLoadFraction"] * (1 if reps == 1 else (1 + reps / 30))
        eligible.append({**row, "estimatedToMeasured1rm": ratio})
    loads = {}
    for fraction in (0.50, 0.65, 0.80):
        subset = [row for row in eligible if row["nominalLoadFraction"] == fraction]
        loads[str(int(fraction * 100))] = summary(subset) if subset else {"sets": 0}
    velocities = {str(value): summary([row for row in eligible
                                       if row["velocityPercent"] == value])
                  for value in (50, 70, 90)}
    distribution = {name: summary([row for row in eligible
                                   if row["distribution"] == name])
                    for name in ("wide", "narrow")}
    eighty = [row for row in eligible if row["nominalLoadFraction"] == .80]
    eighty_by_velocity = {str(value): summary([row for row in eighty
                                               if row["velocityPercent"] == value])
                          for value in (50, 70, 90)}
    eighty_by_distribution = {name: summary([row for row in eighty
                                             if row["distribution"] == name])
                              for name in ("wide", "narrow")}
    paired_tempo_percent = []
    paired_distribution_percent = []
    for subject in range(1, 11):
        subject_eighty = [row for row in eighty if row["subject"] == subject]
        mean_ratio = lambda chosen: float(np.mean([row["estimatedToMeasured1rm"]
                                                    for row in chosen]))
        paired_tempo_percent.append(100 * (mean_ratio([row for row in subject_eighty
                                                       if row["velocityPercent"] == 90]) -
                                           mean_ratio([row for row in subject_eighty
                                                       if row["velocityPercent"] == 50])))
        paired_distribution_percent.append(100 * (mean_ratio([row for row in subject_eighty
                                                              if row["distribution"] == "wide"]) -
                                                  mean_ratio([row for row in subject_eighty
                                                              if row["distribution"] == "narrow"])))
    subject_ranges = []
    for subject in range(1, 11):
        subset = [row for row in eighty if row["subject"] == subject]
        ratios = [row["estimatedToMeasured1rm"] for row in subset]
        subject_ranges.append({"subject": subject, "eligibleSets": len(subset),
                               "minEstimatedToMeasured1rm": round(min(ratios), 4),
                               "maxEstimatedToMeasured1rm": round(max(ratios), 4),
                               "medianAbsolutePercent": round(
                                   float(np.median(np.abs(np.asarray(ratios) - 1)) * 100), 2)})
    report = {
        "status": "independent_bench_action_capacity_audit_not_muscle_force_validation",
        "sourceArticle": "https://doi.org/10.1371/journal.pone.0278909",
        "sourceWorkbook": "https://doi.org/10.1371/journal.pone.0278909.s001",
        "sourceSha256": SOURCE_SHA256, "license": "CC BY 4.0",
        "method": "Ten participants x three nominal %1RM loads x three prescribed concentric velocities x two disc distributions. Directly tested 1RM each session; use only failure sets of 1–10 repetitions. Apply the app's fixed Epley proxy: load*(1+reps/30), except an observed 1RM is the load itself. Divide by the measured session 1RM; absolute loads are not disclosed. Conditions within a person are repeated measures, so subject MAE is calculated before the subject median.",
        "allSets": len(observations), "eligible": summary(eligible),
        "byNominalLoadPercent": loads, "byPrescribedVelocityPercent": velocities,
        "byDiscDistribution": distribution,
        "atEightyPercent": {
            "byPrescribedVelocityPercent": eighty_by_velocity,
            "byDiscDistribution": eighty_by_distribution,
            "withinSubjectFastMinusSlowEstimatePercent": {
                "median": median(paired_tempo_percent),
                "range": [round(min(paired_tempo_percent), 4),
                          round(max(paired_tempo_percent), 4)],
            },
            "withinSubjectWideMinusNarrowEstimatePercent": {
                "median": median(paired_distribution_percent),
                "range": [round(min(paired_distribution_percent), 4),
                          round(max(paired_distribution_percent), 4)],
            },
            "subjectEstimateRanges": subject_ranges,
        },
        "recordAggregationAtEightyPercent": record_aggregation(eighty),
        "limitations": [
            "The publication provides nominal percentages rather than each session's exact load in kilograms; ratio errors inherit this approximation.",
            "All participants were ten trained men; 180 repeated sets are not 180 independent people.",
            "Sets were performed to failure; the phone's 1-2 reps-in-reserve adjustment is not evaluated here.",
            "The experiment manipulated tempo and barbell disc distribution; neither is recorded in the phone's training log.",
            "The best-versus-median comparison uses all six sets from one session per participant; it cannot establish an optimal rule for a variable number of records across days.",
            "This evaluates an action-level 1RM proxy, not muscle mass, single-muscle strength, or personal force during an exercise.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"eligible": report["eligible"], "loads": loads,
                      "atEightyPercent": report["atEightyPercent"]}, indent=2))
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
