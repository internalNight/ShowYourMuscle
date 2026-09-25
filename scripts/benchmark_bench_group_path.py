"""Screen the illustrative bench hand path against published group events.

Larsen et al. 2022 Table 1 reports group-mean bar displacement relative to
the shoulder at two ascent events. This checks direction and centimetre-scale
geometry only. It does not validate any individual's movement or muscle force.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "public/data/bench_tsm_reference.json"
OUTPUT = ROOT / "src/data/bench_group_path_benchmark.json"
SOURCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC9658160/"
REFERENCE_STATURE_CM = 175.0
COHORT_MEAN_STATURE_CM = 183.8
SCALE = REFERENCE_STATURE_CM / COHORT_MEAN_STATURE_CM

# Larsen et al. 2022 Table 1: vertical bar height since lowest position,
# and fore-aft horizontal distance from the shoulder origin, in metres.
EVENTS = {
    "1RM": {"firstVelocityPeak": (.028, .176), "secondVelocityPeak": (.285, .090)},
    "3RM": {"firstVelocityPeak": (.032, .160), "secondVelocityPeak": (.294, .070)},
    "6RM": {"firstVelocityPeak": (.032, .169), "secondVelocityPeak": (.283, .086)},
    "10RM": {"firstVelocityPeak": (.040, .167), "secondVelocityPeak": (.294, .090)},
}

lookup = json.loads(LOOKUP.read_text(encoding="utf-8"))
frames = lookup["frames"]
if len(frames) != 101 or lookup["status"] != "bench_research_kinematics_only":
    raise ValueError("Expected the 101-frame illustrative bench path")
ascent = [frame["viewerJointsM"]["hand"] for frame in frames[50:]]
bottom_height = ascent[0][1]
rises = [hand[1] - bottom_height for hand in ascent]
if any(right < left - 1e-8 for left, right in zip(rises, rises[1:])):
    raise ValueError("Hand height should rise throughout the synthetic ascent")


def model_bench_axis_at_rise(rise):
    if not 0 <= rise <= rises[-1]:
        raise ValueError(f"Study event rise outside model stroke: {rise:.3f} m")
    for index in range(1, len(rises)):
        if rise <= rises[index]:
            fraction = (rise - rises[index - 1]) / (rises[index] - rises[index - 1])
            return ascent[index - 1][2] * (1 - fraction) + ascent[index][2] * fraction
    return ascent[-1][2]


comparisons = {}
errors = []
for load, pair in EVENTS.items():
    result = {}
    for event_name, (height, horizontal) in pair.items():
        scaled_height = height * SCALE
        scaled_horizontal = horizontal * SCALE
        modeled = model_bench_axis_at_rise(scaled_height)
        error = modeled - scaled_horizontal
        errors.append(abs(error))
        result[event_name] = {
            "publishedGroupMeanHeightM": height,
            "publishedGroupMeanShoulderDistanceM": horizontal,
            "statureScaledHeightM": scaled_height,
            "statureScaledShoulderDistanceM": scaled_horizontal,
            "demoBenchAxisDistanceM": modeled,
            "demoMinusScaledGroupMeanM": error,
        }
    if result["firstVelocityPeak"]["demoBenchAxisDistanceM"] <= result["secondVelocityPeak"]["demoBenchAxisDistanceM"]:
        raise ValueError(f"Demo bar travels away from the shoulder for {load}")
    comparisons[load] = result

mean_absolute_error = sum(errors) / len(errors)
# This is an engineering regression threshold for a rough group path, not an
# experimental confidence interval or a claim of personal biomechanics.
if mean_absolute_error > .03:
    raise ValueError(f"Group event geometry differs by {mean_absolute_error:.3f} m")

output = {
    "status": "group_event_kinematic_screen_only",
    "source": SOURCE,
    "sourceTable": "Table 1, v_max1 and v_max2",
    "cohortParticipants": 12,
    "cohortMeanStatureCm": COHORT_MEAN_STATURE_CM,
    "referenceStatureCm": REFERENCE_STATURE_CM,
    "statureScale": SCALE,
    "demoAscentStrokeM": rises[-1],
    "demoBottomBenchAxisDistanceM": ascent[0][2],
    "demoTopBenchAxisDistanceM": ascent[-1][2],
    "comparison": comparisons,
    "meanAbsoluteGroupEventDifferenceM": mean_absolute_error,
    "maximumAbsoluteGroupEventDifferenceM": max(errors),
    "limitations": [
        "The source gives cohort means and SDs, not person-level synchronized trajectories.",
        "All four RM conditions use one illustrative path; the fit cannot predict load-specific kinematics.",
        "The reported horizontal distance and model bench-axis coordinate have different subject origins and are only approximately aligned.",
        "Uniform stature scaling is a rough group comparison and does not validate anatomy, forces, contact, or muscle activation.",
    ],
}
OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"8 group ascent events: MAE {mean_absolute_error * 100:.2f} cm, "
      f"max {max(errors) * 100:.2f} cm")
print(f"Demo bench-axis hand distance: bottom {ascent[0][2]:.3f} m, "
      f"top {ascent[-1][2]:.3f} m")
