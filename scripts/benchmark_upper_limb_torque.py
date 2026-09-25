"""Leave-one-person-out upper-limb torque feasibility screen.

This is a multi-joint tracking task, NOT a bench press or an app validation.
The 12-channel EMG condition is an optimistic measured-sensor comparison;
the mobile app does not request or measure EMG or joint angles.
"""

import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".cache/upper-limb-torque"
OUTPUT = ROOT / "docs/data/upper_limb_torque_holdout_probe.json"
SUBJECTS = tuple(f"S{n:02d}" for n in range(1, 18))
MUSCLES = ("DELTAnt", "DELTMed", "DELTPost", "PECT", "LATI", "TRILong",
           "TRILat", "TRIMed", "BICLong", "BICShort", "BRA", "BRD")
TARGETS = ("shoulder_elv", "elbow_flexion")
STRIDE = 5  # 20 Hz; reduce adjacent-sample redundancy.
RIDGE = 10.0  # fixed before inspecting held-out performance.


def load_subject(subject):
    base = DATA / subject / "MJ/T0"
    metadata = json.loads((DATA / subject / f"{subject}.json").read_text(encoding="utf-8"))
    files = [np.genfromtxt(base / f"{name}.csv", delimiter=",", names=True)
             for name in ("emgFilt", "humanPositions", "humanVelocities", "muscleTorque")]
    emg, positions, velocities, torques = files
    if len({len(item) for item in files}) != 1:
        raise ValueError(f"{subject}: sample count mismatch")
    times = [emg["TIME"], positions["TIME"], velocities["TIME"], torques["time"]]
    if max(float(np.max(np.abs(item - times[0]))) for item in times[1:]) > 1e-6:
        raise ValueError(f"{subject}: time alignment mismatch")
    dt = np.diff(times[0])
    if not np.all((dt > 0.0099) & (dt < 0.0101)):
        raise ValueError(f"{subject}: unexpected sample rate")
    sl = slice(0, None, STRIDE)
    body = np.array((metadata["height"] / 100, metadata["weight"],
                     metadata["measures"]["arm"], metadata["measures"]["forearm"]))
    body_features = np.repeat(body[None, :], len(emg[sl]), axis=0)
    shoulder, elbow = positions["shoulder_elv"][sl], positions["elbow_flexion"][sl]
    pose = np.column_stack((np.sin(shoulder), np.cos(shoulder), np.sin(elbow),
                            np.cos(elbow), velocities["shoulder_elv"][sl],
                            velocities["elbow_flexion"][sl]))
    sensor = np.column_stack([emg[name][sl] for name in MUSCLES])
    target = np.column_stack([torques[name][sl] for name in TARGETS])
    if not all(np.isfinite(array).all() for array in (body_features, pose, sensor, target)):
        raise ValueError(f"{subject}: nonfinite data")
    return {"body": body_features, "pose": pose, "emg": sensor, "target": target,
            "samples": len(target), "durationS": float(times[0][-1] - times[0][0]),
            "heightCm": metadata["height"], "weightKg": metadata["weight"],
            "anteriorDeltoidEmgP99MvcRatio": float(np.quantile(emg["DELTAnt"], .99))}


def design(rows, name):
    keys = {"body": ("body",), "pose": ("body", "pose"),
            "pose_emg": ("body", "pose", "emg")}[name]
    return np.concatenate([rows[key] for key in keys], axis=1)


def predict(train, test, name):
    y = np.concatenate([item["target"] for item in train])
    if name == "train_mean":
        return np.repeat(y.mean(axis=0)[None, :], len(test["target"]), axis=0)
    x = np.concatenate([design(item, name) for item in train])
    x_test = design(test, name)
    mean, std = x.mean(axis=0), x.std(axis=0)
    std = np.where(std < 1e-8, 1, std)
    x = (x - mean) / std
    x_test = (x_test - mean) / std
    target_mean = y.mean(axis=0)
    coefficient = np.linalg.solve(x.T @ x + RIDGE * np.eye(x.shape[1]),
                                  x.T @ (y - target_mean))
    return target_mean + x_test @ coefficient


def main():
    dataset = {subject: load_subject(subject) for subject in SUBJECTS}
    rows = []
    for subject, test in dataset.items():
        train = [value for key, value in dataset.items() if key != subject]
        methods = {}
        for name in ("train_mean", "body", "pose", "pose_emg"):
            estimated = predict(train, test, name)
            methods[name] = {}
            for index, target in enumerate(TARGETS):
                observed = test["target"][:, index]
                error = observed - estimated[:, index]
                denominator = np.sum((observed - observed.mean()) ** 2)
                methods[name][target] = {
                    "maeNm": round(float(np.mean(np.abs(error))), 3),
                    "r2": round(float(1 - np.sum(error ** 2) / denominator), 3)
                    if denominator > 0 else None,
                }
        rows.append({"subject": subject, "samples": test["samples"],
                     "durationS": round(test["durationS"], 2),
                     "heightCm": test["heightCm"], "weightKg": test["weightKg"],
                     "anteriorDeltoidEmgP99MvcRatio": round(
                         test["anteriorDeltoidEmgP99MvcRatio"], 3),
                     "methods": methods})
    summary = {}
    rng = np.random.default_rng(42)
    for target in TARGETS:
        summary[target] = {}
        for name in ("train_mean", "body", "pose", "pose_emg"):
            errors = np.array([row["methods"][name][target]["maeNm"] for row in rows])
            summary[target][name] = {
                "subjectMedianMaeNm": round(float(np.median(errors)), 3),
                "subjectRangeMaeNm": [round(float(errors.min()), 3), round(float(errors.max()), 3)],
                "positiveR2Subjects": sum(row["methods"][name][target]["r2"] > 0 for row in rows),
            }
        paired = np.array([row["methods"]["pose"][target]["maeNm"] -
                           row["methods"]["pose_emg"][target]["maeNm"] for row in rows])
        resamples = rng.integers(0, len(rows), size=(10000, len(rows)))
        interval = np.quantile(np.median(paired[resamples], axis=1), (0.025, 0.975))
        summary[target]["poseToPoseEmgPairedImprovementNm"] = {
            "median": round(float(np.median(paired)), 3),
            "bootstrap95": [round(float(value), 3) for value in interval],
            "improvedSubjects": int((paired > 0).sum()),
        }
    report = {
        "status": "external_research_screen_not_app_or_bench_force_validation",
        "source": "https://zenodo.org/records/11209324",
        "license": "CC BY-SA 4.0",
        "archiveMd5AsPublished": "ea2dd9d26ec61a5870b6455b8abe5918",
        "scope": "17 participants, one multi-joint shoulder/elbow tracking trial (MJ/T0) each",
        "method": "100 Hz processed signals sampled every fifth frame; exact timestamp check; leave one whole participant out; train-only standardization; fixed ridge=10; shoulder_elv and elbow_flexion torques in N.m",
        "inputs": {
            "body": "height, weight, arm and forearm length",
            "pose": "body plus shoulder and elbow angles and angular velocities",
            "pose_emg": "pose plus 12 MVC-normalized EMG channels; sensor data unavailable from app inputs",
        },
        "summary": summary,
        "subjects": rows,
        "limitations": [
            "Upper-limb exoskeleton tracking is not barbell bench press or overhead press.",
            "Joint torque labels are study processed values, not independent single-muscle force measurements.",
            "The app does not measure joint angles, velocities, EMG or MVC; body-only predictions cannot produce within-repetition variation.",
            "One trial per participant and a fixed linear ridge model are only a feasibility screen, not hyperparameter tuning or validation of a deployable model.",
            "Subject-level bootstrap intervals describe this sample and are not population performance guarantees.",
            "S14 anterior deltoid processed EMG reaches 3.694 times its supplied MVC normalization at the 99th percentile; this may reflect task/MVC differences or signal quality and is retained in the primary benchmark.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
