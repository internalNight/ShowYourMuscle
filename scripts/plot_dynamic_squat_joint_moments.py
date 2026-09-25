"""Render the per-subject matched squat contrasts as a static research figure."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "docs/data/dynamic_squat_angle_match.json").read_text(
    encoding="utf-8"))
subjects = data["cross_subject_summary"]["descent"]["accepted_subjects"]
fig, axes = plt.subplots(2, 1, figsize=(10.2, 6.4), sharex=True,
                         layout="constrained")
fig.suptitle("Added 25 lb vs bodyweight squat at matched poses", fontsize=15)
colors = {"descent": "#2b6695", "ascent": "#c25c34"}

for axis, (joint, label) in zip(axes, (("hip", "Right hip flexion moment"),
                                       ("knee", "Right knee moment"))):
    for phase, offset in (("descent", -0.09), ("ascent", 0.09)):
        chosen = set(data["cross_subject_summary"][phase]["accepted_subjects"])
        for index, subject in enumerate(subjects):
            if subject not in chosen:
                continue
            value = data["subjects"][subject][phase][
                f"r_{joint}_moment_loaded_minus_unloaded"]["median"]
            axis.scatter(index + offset, value, s=48, color=colors[phase],
                         marker="o" if phase == "descent" else "s", zorder=3)
        axis.scatter([], [], s=48, color=colors[phase],
                     marker="o" if phase == "descent" else "s", label=phase.capitalize())
    axis.axhline(0, color="#444", lw=1)
    axis.set_ylabel("Difference (N m/kg)")
    axis.set_title(label, loc="left", fontsize=11)
    axis.grid(axis="y", alpha=0.22)
    axis.legend(frameon=False, ncol=2, loc="lower left" if joint == "hip" else "upper left")

axes[1].set_xticks(np.arange(len(subjects)), subjects)
axes[1].set_xlabel("Participant (AB05 omitted: insufficient matched coverage)")
output = ROOT / "docs/figures/dynamic_squat_joint_moments.png"
output.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(output, dpi=180, facecolor="white")
print(output)
