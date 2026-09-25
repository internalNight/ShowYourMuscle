"""Audit muscle-force allocation sensitivity against held-aside EMG trends.

Inputs are the research-only static-optimization outputs under seven solver
settings. Net joint moments were measured first, so matching an EMG direction
is not evidence of a forward personal force predictor.
"""

import json
from pathlib import Path

import numpy as np

from analyze_dynamic_squats import ROOT


SUBJECTS = ("AB01", "AB02", "AB03", "AB06", "AB08", "AB09", "AB11", "AB12", "AB13")
VARIANTS = ("baseline", "reg1", "reg20", "gmaxhalf", "gmaxdouble", "bfhalf", "bfdouble")
CHANNELS = {"glut_max": "RGMAX", "biceps_femoris": "RBF"}


def path_for(subject, variant):
    suffix = "" if variant == "baseline" else f"_{variant}"
    return ROOT / ".cache/lower-limb" / f"optimization_{subject}{suffix}.json"


def main():
    emg = json.loads((ROOT / "docs/data/dynamic_squat_emg_pilot.json").read_text(
        encoding="utf-8"))
    optimization = {}
    for subject in SUBJECTS:
        for variant in VARIANTS:
            path = path_for(subject, variant)
            if not path.exists():
                raise FileNotFoundError(f"Run the static-optimization sweep first: {path}")
            optimization[subject, variant] = json.loads(path.read_text(encoding="utf-8"))
    report = {
        "status": "research_only_measured_joint_moments_as_input_not_personal_force_validation",
        "scenarios": {
            "baseline": "regularization 5 N m; source model strengths",
            "reg1": "regularization 1 N m",
            "reg20": "regularization 20 N m",
            "gmaxhalf": "gluteus maximus max isometric forces x 0.5",
            "gmaxdouble": "gluteus maximus max isometric forces x 2",
            "bfhalf": "biceps femoris max isometric forces x 0.5",
            "bfdouble": "biceps femoris max isometric forces x 2",
        },
        "emg_gate": "Use original pilot's >=30 paired frames, >=20% coverage and both-condition active/inactive envelope >=1.5 channel gate; no MVC normalization",
        "torque_fit_gate": "Per phase/scenario, both trial conditions need median absolute residual <=5 Nm and maximum absolute residual <=50 Nm at hip, knee and ankle; thresholds are exploratory",
        "participants": {}, "summary": {},
    }
    for phase in ("descent", "ascent"):
        report["summary"][phase] = {}
        for group, channel in CHANNELS.items():
            eligible = emg["cross_subject_summary"][phase]["channel_ratios"][channel]["eligible_subjects"]
            rows = {}
            for subject in eligible:
                if subject not in SUBJECTS:
                    raise ValueError(f"Missing optimization sweep for {subject}")
                observed = emg["subjects"][subject][phase]["loaded_to_unloaded_rms_ratio"][channel]
                force_ratios = []
                loaded_forces = []
                acceptable_variants = []
                for variant in VARIANTS:
                    result = optimization[subject, variant]["phases"][phase]
                    ratio = result["loaded_to_unloaded_group_force_ratio"].get(group)
                    if ratio is None:
                        raise ValueError(f"Zero unloaded reference force: {subject} {phase} {group} {variant}")
                    force_ratios.append(ratio)
                    loaded_forces.append(result["25lbs"]["median_group_force_n"][group])
                    if all(max(result[load]["median_abs_residual_nm"].values()) <= 5
                           and max(result[load]["max_abs_residual_nm"].values()) <= 50
                           for load in ("0lbs", "25lbs")):
                        acceptable_variants.append(variant)
                acceptable_forces = [force for variant, force in zip(VARIANTS, loaded_forces)
                                     if variant in acceptable_variants]
                rows[subject] = {
                    "observed_emg_ratio": observed,
                    "baseline_force_ratio": force_ratios[0],
                    "all_scenario_force_ratio_range": [min(force_ratios), max(force_ratios)],
                    "all_scenario_loaded_force_n_range": [min(loaded_forces), max(loaded_forces)],
                    "loaded_force_max_to_min": round(max(loaded_forces) / min(loaded_forces), 3),
                    "torque_fit_scenarios": acceptable_variants,
                    "torque_fit_loaded_force_n_range": ([min(acceptable_forces), max(acceptable_forces)]
                                                       if acceptable_forces else None),
                    "torque_fit_loaded_force_max_to_min": (round(
                        max(acceptable_forces) / min(acceptable_forces), 3)
                        if len(acceptable_forces) >= 2 else None),
                    "baseline_direction_matches_emg": (force_ratios[0] > 1) == (observed > 1),
                    "all_scenarios_direction_match_emg": all((r > 1) == (observed > 1)
                                                              for r in force_ratios),
                }
            report["participants"][f"{phase}_{group}"] = rows
            report["summary"][phase][group] = {
                "eligible_subjects": eligible,
                "observed_emg_increase_count": sum(row["observed_emg_ratio"] > 1
                                                   for row in rows.values()),
                "baseline_direction_match_count": sum(row["baseline_direction_matches_emg"]
                                                      for row in rows.values()),
                "all_scenarios_direction_match_count": sum(
                    row["all_scenarios_direction_match_emg"] for row in rows.values()),
                "median_loaded_force_max_to_min": round(float(np.median([
                    row["loaded_force_max_to_min"] for row in rows.values()])), 3),
                "max_loaded_force_max_to_min": round(max(
                    row["loaded_force_max_to_min"] for row in rows.values()), 3),
                "subjects_with_at_least_three_torque_fit_scenarios": sum(
                    len(row["torque_fit_scenarios"]) >= 3 for row in rows.values()),
                "median_torque_fit_loaded_force_max_to_min": round(float(np.median([
                    row["torque_fit_loaded_force_max_to_min"] for row in rows.values()
                    if row["torque_fit_loaded_force_max_to_min"] is not None])), 3),
            }
    output = ROOT / "docs/data/dynamic_squat_force_sensitivity.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
