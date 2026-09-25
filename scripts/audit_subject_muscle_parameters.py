"""Check what personalization exists in 12 public scaled gait2354 models.

The experiment's subject models can inform geometry, but their muscle strength
parameters should not be assumed to measure each subject's real capacity.
"""

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / ".cache/lower-limb-raw"
SUBJECTS = ("AB01", "AB02", "AB03", "AB05", "AB06", "AB07", "AB08",
            "AB09", "AB10", "AB11", "AB12", "AB13")
PROPERTIES = ("max_isometric_force", "optimal_fiber_length", "tendon_slack_length")


def read_model(subject):
    root = ET.parse(RAW / subject / "Models" / f"{subject}-Scaled1.osim").getroot()
    muscles = root.findall(".//Thelen2003Muscle")
    if not muscles:
        raise RuntimeError(f"No Thelen2003Muscle elements for {subject}")
    return {muscle.attrib["name"]: {
        property_name: float(muscle.findtext(property_name))
        for property_name in PROPERTIES
    } for muscle in muscles}


def main():
    with (RAW / "Subject_masses.csv").open(newline="", encoding="utf-8-sig") as handle:
        masses = {row["Subject"]: float(row["Mass"]) for row in csv.DictReader(handle)}
    models = {subject: read_model(subject) for subject in SUBJECTS}
    names = sorted(models[SUBJECTS[0]])
    for subject in SUBJECTS:
        if sorted(models[subject]) != names:
            raise ValueError(f"Muscle set differs for {subject}")
    summary = {}
    for property_name in PROPERTIES:
        ratios = []
        exactly_unchanged = 0
        for name in names:
            values = [models[subject][name][property_name] for subject in SUBJECTS]
            if max(values) == min(values):
                exactly_unchanged += 1
            ratios.append(max(values) / min(values))
        summary[property_name] = {
            "exactlyUnchangedMuscles": exactly_unchanged,
            "largestAcrossSubjectMaxMinRatio": max(ratios),
            "medianAcrossSubjectMaxMinRatio": sorted(ratios)[len(ratios) // 2],
        }
    examples = {}
    for name in ("glut_max1_r", "glut_max2_r", "vas_int_r", "bifemlh_r"):
        if name in names:
            examples[name] = {subject: models[subject][name]
                              for subject in SUBJECTS}
    report = {
        "status": "public_scaled_model_parameter_audit_not_individual_strength_validation",
        "source": "Scherpereel et al. 2023, doi:10.1038/s41597-023-02840-6",
        "modelCount": len(SUBJECTS),
        "muscleCountEach": len(names),
        "subjects": [{"id": subject, "massKg": masses[subject]}
                     for subject in SUBJECTS],
        "summary": summary,
        "examples": examples,
        "interpretation": "Scaling changes geometry and total body mass, but muscle maximum isometric force must be checked independently before treating outputs as personalized force predictions.",
    }
    output = ROOT / "docs/data/subject_muscle_parameter_audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"modelCount": report["modelCount"],
                      "muscleCountEach": report["muscleCountEach"],
                      "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
