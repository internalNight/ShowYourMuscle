"""Diagnose the research squat solution's soleus tendon lower-bound behavior.

Run after solve_viewer_squat.py --barbell-kg 0 --half-axial-mass. This does
not validate the solution or authorize displaying muscle force in the app.
"""

import json
import os
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "assets/opensim/squatToStand_3dof9musc.osim"
CASE = ROOT / ".cache/moco-viewer-squat/barbell-0kg-half-axial"
OUTPUTS = CASE / "viewer_squat_outputs.sto"
LOG = ROOT / ".cache/moco-viewer-squat/diagnose-soleus.log"
REPORT = ROOT / "docs/data/soleus_tendon_diagnostic.json"


def load_sto(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index("endheader")
    headers = lines[start + 1].split("\t")
    rows = [[float(value) for value in line.split("\t")]
            for line in lines[start + 2:] if line.strip()]
    if not rows or any(len(row) != len(headers) for row in rows):
        raise ValueError("Malformed STO output")
    return headers, rows


os.chdir(MODEL.parent)
model = osim.Model(MODEL.name)
soleus = model.getMuscles().get("soleus_r")
slack = soleus.get_tendon_slack_length()
headers, rows = load_sto(OUTPUTS)
index = headers.index("/forceset/soleus_r|tendon_length")
fiber_index = headers.index("/forceset/soleus_r|fiber_length_along_tendon")
tendon_lengths = [row[index] for row in rows]
near = [row for row in rows if abs(row[index] - slack) <= 1e-6]
example = min(near, key=lambda row: abs(row[0] - 0.825))
text = LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else ""
report = {
    "status": "research_solution_tendon_diagnostic_only",
    "case": CASE.name,
    "model": MODEL.name,
    "sampleCount": len(rows),
    "nearSlackToleranceM": 1e-6,
    "soleusTendonSlackM": slack,
    "soleusTendonLengthRangeM": [min(tendon_lengths), max(tendon_lengths)],
    "nearSlackSamples": len(near),
    "nearSlackFraction": len(near) / len(rows),
    "bucklingLogLines": sum("soleus_r' is buckling" in line for line in text.splitlines()),
    "exampleNearSlack": {
        "timeS": example[0],
        "tendonLengthM": example[index],
        "fiberLengthAlongTendonM": example[fiber_index],
    },
    "interpretation": "Tendon length is often at the slack-length lower bound. This is consistent with the buckling messages, but does not validate the anatomical force result.",
    "limits": ["one research configuration; no measured motion or ground reaction forces",
               "muscle parameters and single-leg mass split are unvalidated",
               "numerical convergence does not validate muscle recruitment"],
}
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("SOLEUS_TENDON_DIAGNOSTIC", len(near), "near-slack samples of", len(rows),
      "buckling log lines", report["bucklingLogLines"])
