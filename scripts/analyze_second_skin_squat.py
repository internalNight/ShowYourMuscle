"""Compare one public participant's unloaded and weighted static squat records.

The Second Skin dataset reports gait2392 inverse-dynamics moments in N m/kg.
This is an external validation candidate, not validation of our muscle forces or
of a dynamic barbell squat. Full source CSVs stay in ignored .cache/.
"""

import csv
import argparse
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".cache" / "second-skin" / "OpenSource_Dataset"
parser = argparse.ArgumentParser()
parser.add_argument("--subject", default="AB01")
args = parser.parse_args()
SUBJECT = args.subject.upper()
if not SUBJECT.startswith("AB") or not SUBJECT[2:].isdigit():
    raise ValueError("Expected a public Second Skin subject code such as AB01")
OUTPUT = ROOT / "docs" / "data" / f"second_skin_{SUBJECT.lower()}_static_squat_compare.json"
CONDITIONS = {
    "unweighted": "pseudo_static_sym_squat_unweighted",
    "vest_25lb": "pseudo_static_sym_squat_vest_25lb",
}
FIELDS = {
    "hipFlexionRad": "hip_flexion_r",
    "kneeAngleRad": "knee_angle_r",
    "ankleAngleRad": "ankle_angle_r",
    "hipMomentNmPerKg": "hip_flexion_r_moment",
    "kneeMomentNmPerKg": "knee_angle_r_moment",
    "ankleMomentNmPerKg": "ankle_angle_r_moment",
    "kneeReactionBodyWeights": "knee_angle_r_jrf_total",
}


def summarize(path):
    values = {name: [] for name in FIELDS}
    total = 0
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            total += 1
            time = float(row["time"])
            if not 5 <= time <= 25:
                continue
            for name, column in FIELDS.items():
                try:
                    value = float(row[column])
                except (ValueError, KeyError):
                    continue
                if math.isfinite(value):
                    values[name].append(value)
    return {
        "totalRows": total,
        "windowSeconds": [5, 25],
        "finiteSamples": {name: len(items) for name, items in values.items()},
        "median": {name: statistics.median(items) for name, items in values.items()},
        "range": {name: [min(items), max(items)] for name, items in values.items()},
    }


subjects = DATA / "Setup_Files" / "subject_physical_information.csv"
with subjects.open(encoding="utf-8-sig", newline="") as source:
    subject = next(row for row in csv.DictReader(source) if row["moniker"] == SUBJECT)
records = {}
for label, task in CONDITIONS.items():
    source = DATA / "Data" / SUBJECT / "MachineLearning" / task / f"{task}_01.csv"
    if not source.exists():
        raise FileNotFoundError(f"Extract the official ZIP member first: {source}")
    records[label] = summarize(source)
unweighted = records["unweighted"]["median"]
weighted = records["vest_25lb"]["median"]
angle_overlap = {}
for key in ("hipFlexionRad", "kneeAngleRad", "ankleAngleRad"):
    low_a, high_a = records["unweighted"]["range"][key]
    low_b, high_b = records["vest_25lb"]["range"][key]
    angle_overlap[key] = max(low_a, low_b) <= min(high_a, high_b)
output = {
    "status": "external_isometric_squat_comparison_not_model_validation",
    "source": "https://repository.gatech.edu/entities/publication/c7a857c8-79d8-4119-8ce0-be568d942f49",
    "sourceBitstream": "d56cbae7-5621-401d-9d93-0f9f6fb93045",
    "license": "CC BY 4.0",
    "subject": SUBJECT,
    "subjectHeightWithoutShoesCm": float(subject["height_without_shoes (cm)"]),
    "subjectMassWithoutShoesKg": float(subject["weight_without_shoes (kg)"]),
    "conditionNote": "30-second symmetric half-squat hold, unloaded versus 25 lb weighted vest",
    "units": {"angles": "rad", "moments": "N m/kg", "kneeReaction": "bodyweights"},
    "records": records,
    "weightedMinusUnweighted": {key: weighted[key] - unweighted[key] for key in FIELDS},
    "angleRangesOverlap": angle_overlap,
    "canAttemptPoseMatchFromAngleRanges": all(angle_overlap.values()),
    "poseMatchedForLoadComparison": False,
    "limits": [
        ("one participant and two separate isometric holds; at least one joint angle range does not overlap"
         if not all(angle_overlap.values()) else
         "one participant and two separate isometric holds; angle-range overlap does not establish matched posture"),
        "moment difference cannot be attributed to load alone; not a dynamic barbell squat",
        "published inverse-dynamics outputs are reference labels, not independently measured muscle forces",
        "vest mass and center of mass differ from a shoulder-supported barbell",
        "right-knee joint reaction is itself an OpenSim computation; EMG is not analyzed here",
    ],
}
OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"SAVED {OUTPUT}")
for field in ("hipMomentNmPerKg", "kneeMomentNmPerKg", "kneeReactionBodyWeights"):
    print(f"{field}: unloaded={unweighted[field]:.3f}, vest={weighted[field]:.3f}, "
          f"difference={weighted[field] - unweighted[field]:+.3f}")
print(f"All joint angle ranges overlap: {output['canAttemptPoseMatchFromAngleRanges']}")
