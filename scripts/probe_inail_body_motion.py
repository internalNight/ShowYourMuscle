"""Probe whether measured body movement explains residual crate-lift support force.

Research-only: this is a coarse marker COM proxy, not a validated whole-body
center of mass or a phone input. It reuses only trials accepted by the fixed
INAIL known-load benchmark, so the comparison has the same participants/trials.
"""

import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.signal import butter, filtfilt, savgol_filter
from scipy.stats import binomtest

from benchmark_inail_lift_support import CACHE, G, LOAD_KG, OUTPUT as BASE_REPORT


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/data/inail_body_motion_probe.json"
FRACTIONS = json.loads((ROOT / "src/data/squat_mass_template.json").read_text(encoding="utf-8"))["fractions"]
MARKERS = ("Sacrum", "RAsis", "LAsis", "RShould", "LShould", "RKnee1", "RKnee2",
           "LKnee1", "LKnee2", "RMall", "LMall", "RMet", "LMet", "RHeel", "LHeel")


def vertical_acceleration(height, sample_rate=340):
    smooth = filtfilt(*butter(4, 6, fs=sample_rate), height)
    return savgol_filter(smooth, 101, 3, deriv=2, delta=1 / sample_rate)


def body_height_proxy(markers, torso_fraction=.70):
    y = {key: np.asarray(markers[key], dtype=float)[:, 1] for key in MARKERS}
    if not all(np.all(np.isfinite(value)) for value in y.values()):
        raise ValueError("Nonfinite body marker")
    pelvis = (y["Sacrum"] + y["RAsis"] + y["LAsis"]) / 3
    shoulder = (y["RShould"] + y["LShould"]) / 2
    torso = pelvis + torso_fraction * (shoulder - pelvis)
    total = FRACTIONS["torso"] * torso + FRACTIONS["pelvis"] * pelvis
    for side in "RL":
        hip = y[f"{side}Asis"]
        knee = (y[f"{side}Knee1"] + y[f"{side}Knee2"]) / 2
        ankle = y[f"{side}Mall"]
        foot = (y[f"{side}Met"] + y[f"{side}Heel"]) / 2
        thigh = hip + .47 * (knee - hip)
        shank = knee + .53 * (ankle - knee)
        total = total + FRACTIONS["thighEach"] * thigh
        total = total + FRACTIONS["shankEach"] * shank
        total = total + FRACTIONS["footEach"] * foot
    return total


def pelvis_height_proxy(markers):
    return sum(np.asarray(markers[name], dtype=float)[:, 1]
               for name in ("Sacrum", "RAsis", "LAsis")) / 3


def main():
    base = json.loads(BASE_REPORT.read_text(encoding="utf-8"))
    accepted = {(row["subject"], row["trial"]): row for row in base["trials"]}
    if len(accepted) != 84:
        raise ValueError("Expected 84 accepted benchmark trials")
    rows = []
    for path in sorted(CACHE.glob("S*_all_trials.mat")):
        subject = path.stem.split("_")[0]
        if subject not in {key[0] for key in accepted}:
            continue
        data = loadmat(path, simplify_cells=True)[path.stem]
        for motion, plate_trial in zip(data["Kinematic_data"], data["Ground_forces_and_moments"]):
            trial = motion["task"].removesuffix(".TDF")
            source = accepted.get((subject, trial))
            if source is None:
                continue
            start, stop = int(motion["events"]["start"]), int(motion["events"]["stop"])
            markers = motion["data_3D"]
            if float(motion["fs_3D"]) != 340 or float(plate_trial["fs_forces"]) != 680:
                raise ValueError("Unexpected sampling rate")
            body_heights = {
                "pelvisOnly": pelvis_height_proxy(markers),
                "torsoHalf": body_height_proxy(markers, .50),
                "bodyPrimary": body_height_proxy(markers, .70),
                "torsoHigh": body_height_proxy(markers, .90),
            }
            body_accels = {key: vertical_acceleration(height)
                           for key, height in body_heights.items()}
            body_accel = body_accels["bodyPrimary"]
            box_height = np.mean([np.asarray(markers[name])[:, 1] for name in
                                  ("load_RL1", "load_RL2", "load_LL1", "load_LL2")], axis=0)
            box_accel = vertical_acceleration(box_height)
            plates = plate_trial["platform_data"]
            force = np.asarray(plates["F_l"])[:, 1] + np.asarray(plates["F_r"])[:, 1]
            observed = np.interp(np.arange(len(body_accel)) / 340,
                                 np.arange(len(force)) / 680, force)[start:stop]
            norm = (source["subjectKg"] + source["boxKg"]) * G
            static = norm
            box_only = static + source["boxKg"] * box_accel[start:stop]
            body_and_box = box_only + source["subjectKg"] * body_accel[start:stop]
            controls = {key: box_only + source["subjectKg"] * accel[start:stop]
                        for key, accel in body_accels.items() if key != "bodyPrimary"}
            ratio = lambda predicted: round(float(np.mean(np.abs(observed - predicted)) / norm), 4)
            if abs(ratio(box_only) - source["ascentBoxAccelerationMaeRatio"]) > 0.00011:
                raise ValueError(f"Failed to reproduce fixed box benchmark: {subject} {trial}")
            rows.append({"subject": subject, "trial": trial,
                         "staticMaeRatio": ratio(static), "boxOnlyMaeRatio": ratio(box_only),
                         "bodyAndBoxMaeRatio": ratio(body_and_box),
                         "pelvisOnlyMaeRatio": ratio(controls["pelvisOnly"]),
                         "torsoHalfMaeRatio": ratio(controls["torsoHalf"]),
                         "torsoHighMaeRatio": ratio(controls["torsoHigh"]),
                         "bodyProxyVerticalTravelM": round(float(np.ptp(body_heights["bodyPrimary"][start:stop])), 3),
                         "bodyProxyAccelerationRmsMs2": round(float(np.sqrt(np.mean(body_accel[start:stop] ** 2))), 3)})
    if len(rows) != len(accepted):
        raise ValueError("Body marker proxy could not score the same 84 trials")
    people = []
    for subject in sorted({row["subject"] for row in rows}):
        group = [row for row in rows if row["subject"] == subject]
        item = {"subject": subject, "trials": len(group)}
        for key in ("staticMaeRatio", "boxOnlyMaeRatio", "bodyAndBoxMaeRatio",
                    "pelvisOnlyMaeRatio", "torsoHalfMaeRatio", "torsoHighMaeRatio"):
            item[f"median{key[0].upper()}{key[1:]}"] = round(float(np.median([row[key] for row in group])), 4)
        people.append(item)
    better = sum(person["medianBodyAndBoxMaeRatio"] < person["medianBoxOnlyMaeRatio"]
                 for person in people)
    controls = {}
    for key, field in (("pelvisOnly", "medianPelvisOnlyMaeRatio"),
                       ("torsoHalf", "medianTorsoHalfMaeRatio"),
                       ("torsoHigh", "medianTorsoHighMaeRatio")):
        controls[key] = {
            "participantMedianMaeRatio": round(float(np.median([p[field] for p in people])), 4),
            "participantsBeatingBoxOnly": sum(p[field] < p["medianBoxOnlyMaeRatio"]
                                               for p in people),
            "participantsBeatingBodyPrimary": sum(p[field] < p["medianBodyAndBoxMaeRatio"]
                                                  for p in people),
        }
    report = {
        "status": "exploratory_measured_marker_com_proxy_not_phone_prediction",
        "sourceBenchmark": str(BASE_REPORT.relative_to(ROOT)).replace("\\", "/"),
        "method": "Fixed mass fractions from the existing gait2354 squat template. Pelvis is the mean of sacrum and two ASIS marker heights; torso proxy is 70% of pelvis-to-mean-shoulder height. Each thigh/shank/foot proxy uses side ASIS, mean knee markers, malleolus, and mean heel/metatarsal markers. Controls use pelvis-only motion and torso proxy fractions of 50% and 90%; none fit plate force. Both body and crate heights receive the benchmark's 6 Hz lowpass and 101-sample second derivative. This is an exploratory body COM proxy, not validated segment COM reconstruction.",
        "summary": {
            "participants": len(people), "trials": len(rows),
            "participantMedianStaticMaeRatio": round(float(np.median([p["medianStaticMaeRatio"] for p in people])), 4),
            "participantMedianBoxOnlyMaeRatio": round(float(np.median([p["medianBoxOnlyMaeRatio"] for p in people])), 4),
            "participantMedianBodyAndBoxMaeRatio": round(float(np.median([p["medianBodyAndBoxMaeRatio"] for p in people])), 4),
            "participantsBodyAndBoxBeatsBoxOnly": better,
            "oneSidedSignTestP": round(float(binomtest(better, len(people), .5,
                                                        alternative="greater").pvalue), 5),
        },
        "bodyProxyControls": controls,
        "participants": people,
        "trials": rows,
        "limitations": [
            "Arm and head motion are lumped into a torso proxy; exact whole-body center of mass is not measured.",
            "This uses laboratory marker trajectories for each tested person; the phone's body fields and preset animation provide no equivalent observed body motion.",
            "Crate floor contact timing, hand support, and anatomical segment COM definitions remain unmodeled.",
            "This evaluates only net vertical plate force, not joint torque or any muscle force.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
