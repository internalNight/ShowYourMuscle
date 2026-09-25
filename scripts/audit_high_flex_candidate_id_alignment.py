"""Compare source and high-flex candidate ID on the same measured squat."""

import json
import os

import numpy as np
import opensim as osim

from analyze_dynamic_squat_id_replay import read_storage
from audit_full_bilateral_static_optimization import read_sto
from audit_high_flex_candidate import CANDIDATE, ROOT, SUBJECTS, read_ik, set_pose
from audit_high_flex_hip_knee_ankle_capacity import COORDINATES, mapped_targets
from probe_high_flex_scaled_capacity import ratios_from_dimensions, scale_model
from probe_high_flex_segment_scaling import dimensions

OUTPUT = ROOT / "docs/data/high_flex_candidate_id_alignment.json"
SUBJECT = "AB02"
WINDOWS = {"shallow": (23.0, 23.1), "deep": (23.6, 23.7)}
SO_DIR = ROOT / ".cache/lower-limb/high-flex-static-optimization"


def summary(difference, source_values, candidate_values, unit="Nm"):
    return {
        f"sourceMappedMedian{unit}": round(float(np.median(source_values)), 3),
        f"candidateMedian{unit}": round(float(np.median(candidate_values)), 3),
        f"candidateMinusMappedSourceMedian{unit}": round(float(np.median(difference)), 3),
        f"candidateMinusMappedSourceMae{unit}": round(float(np.mean(np.abs(difference))), 3),
        f"candidateMinusMappedSourceMaxAbs{unit}": round(float(np.max(np.abs(difference))), 3),
    }


def main():
    os.chdir(ROOT)
    osim.Logger.setLevelString("Error")
    config = SUBJECTS[SUBJECT]
    source = osim.Model(str(config["source"].relative_to(ROOT)))
    source_state = source.initSystem()
    candidate = osim.Model(str(CANDIDATE.relative_to(ROOT)))
    candidate_state = candidate.initSystem()
    reference = read_ik(config["ik"], config["intervalS"])[0]
    set_pose(source, source_state, reference)
    set_pose(candidate, candidate_state, reference, flip_knee=True)
    factors = ratios_from_dimensions(dimensions(source, source_state, "knee"),
                                     dimensions(candidate, candidate_state,
                                                "walker_knee"))
    scale_model(candidate, candidate_state, factors,
                float(source.getTotalMass(source_state)))
    source_id = read_storage(ROOT / ".cache/lower-limb/id-reproduction"
                             / "AB02_id_23_25_no_free_moment.sto")
    candidate_id = read_storage(ROOT / ".cache/lower-limb/high-flex-candidate-id"
                                / "AB02/candidate_id.sto")
    if not np.allclose(source_id["time"], candidate_id["time"], atol=1e-6):
        raise AssertionError("Source and candidate ID grids differ")
    rows = read_ik(config["ik"], (23, 25))
    if len(rows) != 401:
        raise AssertionError("Expected 401 measured IK frames")
    so_audit = json.loads((ROOT / "docs/data/high_flex_static_optimization_audit.json")
                          .read_text(encoding="utf-8"))
    report = {
        "status": "research_only_source_vs_candidate_inverse_dynamics",
        "source": "AB02 subject-scaled gait2354 model, measured IK and force plates",
        "candidate": "RajagopalLaiUhlrich2023, joint-center segment and total-mass scaled",
        "comparison": "source ten-axis ID mapped to candidate joint axes, then compared with separately recomputed candidate ID on the same measured inputs",
        "freeForcePlateMomentIncluded": False,
        "windows": {},
        "limitations": [
            "matching total mass and selected joint-center distances does not match body inertias, centers of mass or ground-contact frames",
            "candidate subtalar and MTP motion was locked rather than reproduced",
            "neither ID calculation identifies individual muscle force or predicts phone-user dynamics",
        ],
    }
    for label, (start, end) in WINDOWS.items():
        selected = [row for row in rows if start - 1e-7 <= row["time"] <=
                    end + 1e-7]
        mapped = []
        actual = []
        indices = []
        for row in selected:
            set_pose(source, source_state, row)
            set_pose(candidate, candidate_state, row, flip_knee=True)
            index = int(round((row["time"] - source_id["time"][0]) / 0.005))
            if abs(source_id["time"][index] - row["time"]) > 1e-6:
                raise AssertionError("IK/ID frame mismatch")
            source_torque = {name: float(source_id[name + "_moment"][index])
                             for name in COORDINATES}
            projection, _ = mapped_targets(source, source_state, candidate,
                                           candidate_state, source_torque)
            mapped.append(projection)
            actual.append([candidate_id[name + "_moment"][index]
                           for name in COORDINATES])
            indices.append(index)
        mapped = np.array(mapped)
        actual = np.array(actual)
        indices = np.array(indices)
        if len(indices) != 21:
            raise AssertionError("Expected 21 frames per window")
        coordinate_comparison = {
            name: summary(actual[:, i] - mapped[:, i], mapped[:, i],
                          actual[:, i]) for i, name in enumerate(COORDINATES)}
        pelvis = {}
        for name in ("pelvis_tx_force", "pelvis_ty_force", "pelvis_tz_force",
                     "pelvis_tilt_moment", "pelvis_list_moment",
                     "pelvis_rotation_moment"):
            source_values = source_id[name][indices]
            candidate_values = candidate_id[name][indices]
            pelvis[name] = summary(candidate_values - source_values,
                                   source_values, candidate_values,
                                   "N" if name.endswith("_force") else "Nm")
        so_dir = (SO_DIR / "AB02_23_23.1_strength4.2_physiology" if
                  label == "shallow" else SO_DIR /
                  "AB02_23.6_23.7_strength4.2_physiology")
        so_names, so_forces = read_sto(next(so_dir.glob("*force.sto")))
        if not np.allclose(so_forces[:, 0], candidate_id["time"][indices],
                           atol=1e-6):
            raise AssertionError("Candidate ID and SO times differ")
        pelvis_so_crosscheck = {}
        matching_audit = next(run for run in so_audit["runs"] if
                              run["run"] == so_dir.name)
        failed = matching_audit["failedFrameTimesS"]
        if failed is None:
            raise AssertionError("SO convergence warnings were not audited")
        valid = np.array([not any(abs(time - bad) < 1e-4 for bad in failed)
                          for time in so_forces[:, 0]], dtype=bool)
        for axis in ("tx", "ty", "tz"):
            id_values = candidate_id[f"pelvis_{axis}_force"][indices][valid]
            so_values = so_forces[valid, so_names.index(f"reserve_pelvis_{axis}")]
            pelvis_so_crosscheck[axis] = {
                "convergedFrameCount": int(np.sum(valid)),
                "meanAbsoluteDifferenceN": round(float(np.mean(
                    np.abs(so_values - id_values))), 3),
                "maximumAbsoluteDifferenceN": round(float(np.max(
                    np.abs(so_values - id_values))), 3),
            }
        report["windows"][label] = {
            "intervalS": [start, end],
            "frameCount": len(indices),
            "tenJointAxes": coordinate_comparison,
            "pelvis": pelvis,
            "soPelvisReserveVsCandidateId": pelvis_so_crosscheck,
        }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({label: {
        "hipRotationR": window["tenJointAxes"]["hip_rotation_r"],
        "hipRotationL": window["tenJointAxes"]["hip_rotation_l"],
        "pelvisTy": window["pelvis"]["pelvis_ty_force"],
        "soPelvisReserveVsCandidateId": window["soPelvisReserveVsCandidateId"],
    } for label, window in report["windows"].items()},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
