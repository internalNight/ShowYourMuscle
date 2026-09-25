"""Compare the bench demo's mean ascent speed with published per-rep LPT data.

Input is Balsalobre-Fernandez et al. 2023's CC BY 4.0 Figshare CSV, downloaded
separately into .cache/research/data_VBTapp.csv. This is a kinematic scale
check only: the CSV has no frame-wise bar path, hand forces, or bench reactions.
"""

import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / ".cache/research/data_VBTapp.csv"
LOOKUP = ROOT / "public/data/bench_tsm_reference.json"
OUTPUT = ROOT / "src/data/bench_velocity_benchmark.json"

with INPUT.open(encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter=";"))
expected = {"50%LPT", "50%APP", "75%LPT", "75%APP"}
if len(rows) != 135 or set(rows[0]) != expected:
    raise ValueError("Expected 135 paired repetitions and the four Figshare velocity columns")

series = {
    key: [float(row[key].replace(",", ".")) for row in rows]
    for key in expected
}
if any(not 0 < value < 5 for values in series.values() for value in values):
    raise ValueError("Unexpected mean concentric velocity outside 0-5 m/s")

lookup = json.loads(LOOKUP.read_text(encoding="utf-8"))
if len(lookup["frames"]) != 101:
    raise ValueError("Bench reference must have 101 phase frames")
top = lookup["frames"][0]["viewerJointsM"]["hand"][1]
bottom = lookup["frames"][50]["viewerJointsM"]["hand"][1]
end = lookup["frames"][100]["viewerJointsM"]["hand"][1]
if abs(top - end) > 1e-8 or top <= bottom:
    raise ValueError("Bench hand reference must descend then return to its start height")
stroke_m = top - bottom

def describe(key):
    data = series[key]
    return {"repetitions": len(data), "medianMPerS": statistics.median(data),
            "meanMPerS": statistics.mean(data), "minimumMPerS": min(data),
            "maximumMPerS": max(data)}

result = {
    "status": "group_repetition_velocity_comparison_only",
    "sourceArticle": "https://doi.org/10.1519/JSC.0000000000004593",
    "sourceData": "https://figshare.com/articles/dataset/22615546",
    "sourceFile": "data_VBTapp.csv",
    "sourceLicense": "CC BY 4.0",
    "sourceParticipants": 27,
    "repetitionsPerLoad": len(rows),
    "measured": {
        "fiftyPercentOneRmLpt": describe("50%LPT"),
        "seventyFivePercentOneRmLpt": describe("75%LPT"),
    },
    "demo": {
        "referenceStatureCm": 175,
        "referenceHandVerticalStrokeM": stroke_m,
        "ascentFractionOfCycle": 0.5,
        "defaultCycleS": 2.8,
        "defaultMeanAscentVelocityMPerS": stroke_m / (2.8 * 0.5),
    },
    "limitations": [
        "Source rows are repetitions, not 135 independent participants.",
        "The source records only mean concentric velocity; it cannot validate frame-wise kinematics or muscle force.",
        "Load levels are percentages of self-reported 1RM, whereas demo load is not a calibrated percentage.",
        "The viewer path is artificial and assumes symmetric descent/ascent timing.",
    ],
}
OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Bench demo stroke: {stroke_m:.3f} m")
print(f"Default 2.8 s mean ascent: {result['demo']['defaultMeanAscentVelocityMPerS']:.3f} m/s")
for label, key in (("50% 1RM", "50%LPT"), ("75% 1RM", "75%LPT")):
    print(f"Measured {label} LPT median: {statistics.median(series[key]):.3f} m/s")
print(f"Wrote {OUTPUT}")
