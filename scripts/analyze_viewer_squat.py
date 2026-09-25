"""Summarize research Moco runs without presenting them as user force advice."""

import argparse
import json
import os
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--runs-root", type=Path, default=ROOT / ".cache" / "moco-viewer-squat")
args = parser.parse_args()
RUNS = args.runs_root if args.runs_root.is_absolute() else ROOT / args.runs_root
RUNS = RUNS.resolve()
os.chdir(RUNS)  # OpenSim's Windows loader cannot reliably handle CJK paths.
CASES = ("barbell-0kg", "barbell-20kg", "barbell-60kg",
         "barbell-0kg-no-passive", "barbell-60kg-no-passive",
         "barbell-60kg-loadx0.12m", "barbell-60kg-over-ankle",
         "barbell-0kg-half-axial", "barbell-60kg-over-ankle-half-axial",
         "barbell-60kg-over-ankle-half-axial-h175cm-w72kg",
         "barbell-60kg-over-ankle-half-axial-h175cm-w90kg",
         "barbell-60kg-over-ankle-half-axial-h190cm-w72kg",
         "barbell-60kg-over-ankle-half-axial-h190cm-w90kg",
         "barbell-20kg-viewer-bar-path-half-axial",
         "barbell-60kg-viewer-bar-path-half-axial",
         "barbell-60kg-no-passive-viewer-bar-path-half-axial",
         "barbell-60kg-viewer-bar-path-offset+6cm-half-axial",
         "barbell-60kg-viewer-bar-path-offset-6cm-half-axial")
MUSCLES = ("glut_max2_r", "vas_int_r", "tib_ant_r")
JOINTS = ("hip_r_hip_flexion_r", "knee_r_knee_angle_r", "ankle_r_ankle_angle_r")


def read_column(table, name):
    labels = [str(label) for label in table.getColumnLabels()]
    if name not in labels:
        return None
    column = table.getDependentColumn(name)
    return [float(column[i]) for i in range(table.getNumRows())]


results = []
for case in CASES:
    folder = RUNS / case
    if not (folder / "summary.json").exists():
        continue
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    states = osim.TimeSeriesTable(f"{case}/viewer_squat_inverse.sto")
    outputs = osim.TimeSeriesTable(f"{case}/viewer_squat_outputs.sto")
    times = [float(states.getIndependentColumn()[i]) for i in range(states.getNumRows())]
    deepest = min(range(len(times)), key=lambda i: abs(times[i] - 1.4))
    if abs(times[deepest] - 1.4) > 0.001:
        raise ValueError(f"{case}: no solution row at deepest pose")
    muscle_values = {}
    for muscle in MUSCLES:
        stem = f"/forceset/{muscle}"
        values = {
            "activation": read_column(states, stem + "/activation")[deepest],
            "activeFiberForceN": read_column(outputs, stem + "|active_fiber_force")[deepest],
            "normalizedFiberLength": read_column(outputs, stem + "|normalized_fiber_length")[deepest],
        }
        passive = read_column(outputs, stem + "|passive_force_multiplier")
        if passive is not None:
            values["passiveForceMultiplier"] = passive[deepest]
        muscle_values[muscle] = values
    reserves = {}
    for joint in JOINTS:
        values = read_column(states, "/forceset/reserve_jointset_" + joint)
        # ModOpAddReserves(2) uses an optimal force of 2 Nm per control unit.
        reserves[joint] = {"deepestNm": values[deepest] * 2,
                           "peakAbsoluteNm": max(abs(value * 2) for value in values)}
    results.append({"case": case, "barbellKg": summary["barbellKg"],
                    "barbellLocalForwardM": summary.get("barbellLocalForwardM", 0),
                    "loadLineOverAnkle": summary.get("loadLineOverAnkle", False),
                    "halfAxialMassAndInertia": summary.get("halfAxialMassAndInertia", False),
                    "personHeightCm": summary.get("personHeightCm"),
                    "personWeightKg": summary.get("personWeightKg"),
                    "modelMassKg": summary.get("modelMassKg"),
                    "passiveFiberForcesEnabled": summary.get("passiveFiberForcesEnabled"),
                    "viewerBarPath": summary.get("viewerBarPath", False),
                    "viewerBarOffsetCm": summary.get("viewerBarOffsetCm", 0),
                    "kinematicsSha256": summary.get("kinematicsSha256"),
                    "deepestTimeS": times[deepest], "muscles": muscle_values,
                    "reserves": reserves})

if not results:
    raise RuntimeError("No completed viewer squat research runs found")
output = RUNS / "sensitivity_summary.json"
output.write_text(json.dumps({"status": "research_only", "runs": results}, indent=2) + "\n",
                  encoding="utf-8")
print("case                        glute activation  glute passive mult.  tib ant activation  peak ankle reserve Nm")
for result in results:
    glute = result["muscles"]["glut_max2_r"]
    tib = result["muscles"]["tib_ant_r"]
    ankle = result["reserves"]["ankle_r_ankle_angle_r"]
    print(f"{result['case']:<28} {glute['activation']:>16.3f} "
          f"{glute.get('passiveForceMultiplier', float('nan')):>19.3f} "
          f"{tib['activation']:>19.3f} {ankle['peakAbsoluteNm']:>22.3f}")
print(f"Saved {output}")
