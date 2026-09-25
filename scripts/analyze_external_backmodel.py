"""Summarize public box-lifting IK/ID trials as a trend reference.

This is not a validation of our barbell squat model. The trials include hand
forces, different kinematics and a different lumbar musculoskeletal model.
"""

import json
import statistics
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "backmodel"
OUTPUT = ROOT / "docs" / "data" / "backmodel_box_lift_summary.json"
SOURCE = "https://github.com/CEINMS-RT/BackModel"
REVISION = "ca4cbcb9736dbcfc05e9b75ed17a2c3a4c9f0562"
RAW = f"https://raw.githubusercontent.com/CEINMS-RT/BackModel/{REVISION}/Sample%20data"
FIELDS = ("L5_S1_Flex_Ext", "L4_L5_Flex_Ext", "L3_L4_Flex_Ext")


def load(mass: int, kind: str):
    path = CACHE / f"squat{mass}kg-{kind}.sto"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            f"{RAW}/squat{mass}kg/{kind}.sto",
            headers={"User-Agent": "muscle-atlas-research"},
        )
        with urllib.request.urlopen(request, timeout=40) as response:
            path.write_bytes(response.read())
    lines = path.read_text().splitlines()
    header_end = next(i for i, line in enumerate(lines) if line.strip().lower() == "endheader")
    labels = [label.strip() for label in lines[header_end + 1].split("\t") if label.strip()]
    rows = [[float(value) for value in line.split()] for line in lines[header_end + 2:] if line.strip()]
    if not rows or any(len(row) != len(labels) for row in rows):
        raise ValueError(f"Malformed storage data: {path}")
    return labels, rows


summary = {"source": SOURCE, "revision": REVISION,
           "movement": "squat-style box lifting, not barbell squat", "trials": {}}
for mass in (5, 15):
    id_labels, id_rows = load(mass, "id")
    ik_labels, ik_rows = load(mass, "ik")
    trial = {
        "loadKg": mass,
        "idRows": len(id_rows),
        "ikRows": len(ik_rows),
        "durationSeconds": round(id_rows[-1][0] - id_rows[0][0], 3),
        "lumbarFlexionMoment": {},
        "ikPelvisTiltRangeRad": [round(min(row[ik_labels.index("pelvis_tilt")] for row in ik_rows), 3),
                                 round(max(row[ik_labels.index("pelvis_tilt")] for row in ik_rows), 3)],
    }
    for field in FIELDS:
        values = [row[id_labels.index(field)] for row in id_rows]
        trial["lumbarFlexionMoment"][field] = {
            "median": round(statistics.median(values), 2),
            "maximum": round(max(values), 2),
        }
    summary["trials"][f"{mass}kg"] = trial

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for label, trial in summary["trials"].items():
    print(label, trial["durationSeconds"], "s", trial["lumbarFlexionMoment"]["L5_S1_Flex_Ext"])
print("Descriptive comparison only; no posture or speed matching and no model validation.")
