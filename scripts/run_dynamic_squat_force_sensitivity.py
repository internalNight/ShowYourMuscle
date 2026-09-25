"""Reproduce the research-only squat static-allocation sensitivity sweep.

Requires the extracted source trials and individual OpenSim models in .cache.
Each output is kept outside the mobile bundle. Run the analysis script after
this sweep to regenerate the compact report under docs/data.
"""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from analyze_dynamic_squat_force_sensitivity import SUBJECTS, VARIANTS, path_for


SCRIPT = Path(__file__).with_name("probe_dynamic_squat_static_optimization.py")
OPTIONS = {
    "baseline": (),
    "reg1": ("--regularization-nm", "1"),
    "reg20": ("--regularization-nm", "20"),
    "gmaxhalf": ("--glut-max-strength-scale", "0.5"),
    "gmaxdouble": ("--glut-max-strength-scale", "2"),
    "bfhalf": ("--biceps-femoris-strength-scale", "0.5"),
    "bfdouble": ("--biceps-femoris-strength-scale", "2"),
}


def run_case(subject, variant):
    output = path_for(subject, variant)
    command = [sys.executable, str(SCRIPT), "--subject", subject,
               "--output", str(output), *OPTIONS[variant]]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{subject} {variant}: {result.stderr[-1500:]}")
    return f"{subject} {variant}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--force", action="store_true",
                        help="Recompute outputs even when they already exist")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    cases = [(subject, variant) for subject in SUBJECTS for variant in VARIANTS
             if args.force or not path_for(subject, variant).exists()]
    print(f"Computing {len(cases)} of {len(SUBJECTS) * len(VARIANTS)} cases")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_case, *case): case for case in cases}
        for future in as_completed(futures):
            print(future.result(), flush=True)
    print("Sweep complete. Run scripts/analyze_dynamic_squat_force_sensitivity.py")


if __name__ == "__main__":
    main()
