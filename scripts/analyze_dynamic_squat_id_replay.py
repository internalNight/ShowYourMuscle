"""Compare a source-subject OpenSim IK/ID replay to released CSV labels."""

import argparse
import json
from pathlib import Path

import numpy as np

from analyze_dynamic_squats import ROOT, load_trial, read_csv


def read_storage(path):
    with path.open(encoding="utf-8") as handle:
        lines = handle.readlines()
    header = next(i for i, line in enumerate(lines) if line.strip() == "endheader") + 1
    names = lines[header].split()
    values = np.loadtxt(path, skiprows=header + 1)
    return dict(zip(names, values.T))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="AB01")
    parser.add_argument("--start", type=float, default=50)
    parser.add_argument("--end", type=float, default=52)
    parser.add_argument("--condition", choices=("0lbs", "25lbs"), required=True)
    parser.add_argument("--omit-free-moment", action="store_true",
                        help="Read the sensitivity replay without force-plate torque vectors")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    labelled = load_trial(args.subject, args.condition)
    if args.start < labelled["time"][0] or args.end > labelled["time"][-1]:
        parser.error("The requested interval falls outside the labelled load condition")
    ik = read_storage(ROOT / ".cache/lower-limb" /
                      f"{args.subject}_ik_{args.start:g}_{args.end:g}.mot")
    suffix = "_no_free_moment" if args.omit_free_moment else ""
    replay = read_storage(ROOT / ".cache/lower-limb/id-reproduction" /
                          f"{args.subject}_id_{args.start:g}_{args.end:g}{suffix}.sto")
    source = ROOT / ".cache/lower-limb-raw" / args.subject / "CSV_Data/squats_1"
    source_angle = read_csv(source / "Joint_Angle.csv")
    source_moment = read_csv(source / "Joint_Moments.csv")
    if not np.allclose(ik["time"], replay["time"], atol=1e-6):
        raise ValueError("IK and ID output grids differ")
    indices = np.rint(ik["time"] / 0.005).astype(int)
    if not np.allclose(source_angle["time"][indices], ik["time"], atol=1e-6):
        raise ValueError("Source CSV and replay time grids differ")
    report = {"subject": args.subject, "condition": args.condition,
              "interval_s": [args.start, args.end],
              "source": "Scherpereel et al. 2023 original marker TRC, scaled OpenSim model, original force-plate MOT and raw Joint_Moments.csv",
              "method": "OpenSim 4.6; all 35 model markers equally weighted; source external loads applied to each calcaneus; 6 Hz low-pass coordinate filter; muscle forces excluded; errors evaluated 0.4 s from interval edges",
              "forcePlateFreeMomentIncluded": not args.omit_free_moment,
              "samples": len(indices), "coordinates": {}, "moments": {}}
    labelled_indices = np.searchsorted(labelled["time"], ik["time"])
    if not np.allclose(labelled["time"][labelled_indices], ik["time"], atol=1e-6):
        raise ValueError("Processed trial and raw replay time grids differ")
    for name in ("hip_flexion_r", "knee_angle_r", "ankle_angle_r",
                 "hip_flexion_l", "knee_angle_l", "ankle_angle_l"):
        diff = ik[name] - source_angle[name][indices]
        report["coordinates"][name] = {
            "mae_deg": round(float(np.mean(np.abs(diff))), 3),
            "p90_abs_deg": round(float(np.percentile(np.abs(diff), 90)), 3),
        }
    mass = 78.9
    with (ROOT / ".cache/lower-limb-raw/Subject_masses.csv").open() as handle:
        import csv
        mass = float(next(row["Mass"] for row in csv.DictReader(handle)
                          if row["Subject"] == args.subject))
    report["mass_kg"] = mass
    for name in ("hip_flexion_r_moment", "knee_angle_r_moment",
                 "ankle_angle_r_moment"):
        actual = source_moment[name][indices]
        processed = labelled["moment"][name][labelled_indices]
        predicted = replay[name]
        middle = (ik["time"] >= args.start + 0.4) & (ik["time"] <= args.end - 0.4)
        values = {"released_raw_csv_median_abs": round(float(np.median(np.abs(actual[middle]))), 3),
                  "processed_filtered_vs_raw_mae": round(float(np.mean(np.abs(processed[middle] - actual[middle]))), 4),
                  "replay_id_median_abs_nm": round(float(np.median(np.abs(predicted[middle]))), 2),
                  "csv_times_mass_median_abs_nm": round(float(np.median(np.abs(actual[middle] * mass))), 2),
                  "mae_if_csv_is_nm": round(float(np.mean(np.abs(predicted[middle] - actual[middle]))), 2),
                  "mae_if_csv_is_nm_per_kg": round(float(np.mean(np.abs(predicted[middle] - actual[middle] * mass))), 2)}
        report["moments"][name] = values
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
