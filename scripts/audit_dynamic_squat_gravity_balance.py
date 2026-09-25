"""Compare measured squat vertical GRF with scaled-model COM acceleration.

This is a research audit of two public bodyweight squat intervals. It uses
experimental IK and force-plate data, so it cannot validate the phone's preset
pose or infer muscle force. It checks how much the acceleration term matters
before extending the phone's static gravity-line display to dynamics.
"""

import json
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
import opensim as osim
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from scipy.signal import savgol_filter

from analyze_dynamic_squats import ROOT, load_trial

CASES = (("AB01", 50, 52), ("AB02", 23, 25))
G = 9.80665


def read_motion(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines.index("endheader")
    names = lines[header + 1].split()
    values = np.array([[float(v) for v in line.split()]
                       for line in lines[header + 2:] if line.strip()])
    if values.shape[1] != len(names):
        raise ValueError(f"Unexpected motion columns: {path}")
    return names, values


def inspect(subject, start, end):
    model_path = (ROOT / ".cache/lower-limb-raw" / subject / "Models" /
                  f"{subject}-Scaled1.osim")
    motion_path = ROOT / ".cache/lower-limb" / f"{subject}_ik_{start:g}_{end:g}.mot"
    trial = load_trial(subject, "0lbs")
    names, motion = read_motion(motion_path)
    times = motion[:, 0]
    dt = float(np.median(np.diff(times)))
    if not np.isclose(dt, 0.005, atol=1e-5):
        raise ValueError(f"Unexpected IK sample interval for {subject}: {dt}")

    # Keep the filename ASCII for OpenSim's Windows model loader.
    with tempfile.NamedTemporaryFile(prefix=f"muscle_atlas_{subject}_", suffix=".osim",
                                     delete=False) as handle:
        temporary = Path(handle.name)
    shutil.copyfile(model_path, temporary)
    try:
        model = osim.Model(str(temporary))
        state = model.initSystem()
        coordinates = model.getCoordinateSet()
        setters = []
        for column, name in enumerate(names[1:], 1):
            coordinate = coordinates.get(name)
            angular = not name.endswith(("_tx", "_ty", "_tz"))
            setters.append((column, coordinate, angular))
        centers = np.zeros((len(times), 3))
        for row_index, row in enumerate(motion):
            for column, coordinate, angular in setters:
                value = math.radians(row[column]) if angular else row[column]
                coordinate.setValue(state, value, False)
            model.realizePosition(state)
            center = model.calcMassCenterPosition(state)
            centers[row_index] = [center.get(axis) for axis in range(3)]
        mass = model.getTotalMass(state)
    finally:
        temporary.unlink(missing_ok=True)

    # Local cubic fits permit stable second derivatives. They are not the
    # authors' inverse-dynamics filter; report three windows for sensitivity.
    windows = (21, 41, 61)
    smoothed_y = savgol_filter(centers[:, 1], 41, 3)
    grf = trial["grf"]
    measured_vertical = np.interp(times, trial["time"],
                                  grf["RForceY_Vertical"] + grf["LForceY_Vertical"])
    static_vertical = np.full(len(times), mass * G)
    # Exclude Savitzky-Golay edge estimates, then focus on actual squat motion.
    moving = np.interp(times, trial["time"], trial["task_active"].astype(float)) > 0.5
    edge = np.arange(len(times))
    use = moving & (edge >= 30) & (edge < len(times) - 30)
    if use.sum() < 30:
        raise RuntimeError(f"Too few usable frames for {subject}")
    measured = measured_vertical[use]
    static = static_vertical[use]

    def error(predicted):
        residual = predicted - measured
        return {"maeN": float(np.mean(np.abs(residual))),
                "maeFractionBodyWeight": float(np.mean(np.abs(residual)) / (mass * G)),
                "biasN": float(np.mean(residual)),
                "p90AbsoluteErrorN": float(np.percentile(np.abs(residual), 90)),
                "r2": float(1 - np.sum(residual ** 2) /
                            np.sum((measured - measured.mean()) ** 2))}

    dynamic_results = {}
    for window in windows:
        acceleration_y = savgol_filter(centers[:, 1], window, 3,
                                       deriv=2, delta=dt)
        dynamic_results[str(window)] = {
            "windowMs": round(window * dt * 1000, 1),
            "modelComVerticalAccelerationRangeMs2": [float(acceleration_y[use].min()),
                                                        float(acceleration_y[use].max())],
            **error((mass * (G + acceleration_y))[use]),
        }
    horizontal_results = {}
    for axis, force_name in ((0, "ForceX"), (2, "ForceZ")):
        measured_axis = np.interp(times, trial["time"],
                                  grf["R" + force_name] + grf["L" + force_name])[use]
        acceleration_axis = savgol_filter(centers[:, axis], 41, 3,
                                          deriv=2, delta=dt)[use]
        residual = mass * acceleration_axis - measured_axis
        horizontal_results[force_name] = {
            "measuredMeanN": float(measured_axis.mean()),
            "maeN": float(np.mean(np.abs(residual))),
            "biasN": float(np.mean(residual)),
        }

    report = {
        "subject": subject, "intervalS": [start, end],
        "bodyMassModelKg": mass, "usableFrames": int(use.sum()),
        "verticalGrfN": {"mean": float(measured.mean()),
                         "min": float(measured.min()), "max": float(measured.max())},
        "modelComVerticalRangeCm": float((smoothed_y[use].max() - smoothed_y[use].min()) * 100),
        "staticBodyWeightOnly": error(static),
        "bodyWeightPlusComAccelerationBySmoothingWindow": dynamic_results,
        "horizontalForceConsistency205ms": horizontal_results,
    }
    acceleration_y = savgol_filter(centers[:, 1], 41, 3, deriv=2, delta=dt)
    series = {"timeS": times[use] - start, "measuredN": measured,
              "staticN": static,
              "dynamicN": (mass * (G + acceleration_y))[use]}
    return report, series


def main():
    audits = [inspect(*case) for case in CASES]
    rows = [report for report, _ in audits]
    report = {
        "status": "research_physics_audit_not_phone_or_muscle_force_validation",
        "source": "Scherpereel et al. 2023, doi:10.1038/s41597-023-02840-6",
        "method": "Public scaled subject models + replayed experimental IK; compare m(g+a_COM) with two measured force plates during 0-lb squats. No barbell or individual muscle forces in this audit.",
        "cases": rows,
    }
    output = ROOT / "docs/data/dynamic_squat_gravity_balance.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=False)
    for axis, (row, series) in zip(axes, audits):
        axis.plot(series["timeS"], series["measuredN"], color="#2b6cb0",
                  label="Measured force plates", linewidth=1.8)
        axis.plot(series["timeS"], series["dynamicN"], color="#dd6b20",
                  label="Scaled model: m(g + COM acceleration)", linewidth=1.5)
        axis.plot(series["timeS"], series["staticN"], color="#718096",
                  label="Static body weight: mg", linestyle="--", linewidth=1.2)
        axis.set_title(f'{row["subject"]}: bodyweight squat, {row["usableFrames"]} active frames')
        axis.set_ylabel("Vertical ground force (N)")
        axis.grid(alpha=0.2)
    axes[-1].set_xlabel("Time from interval start (s)")
    axes[0].legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    figure = ROOT / "docs/figures/dynamic_squat_gravity_balance.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure, dpi=170)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
