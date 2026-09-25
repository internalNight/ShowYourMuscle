"""Check whether 17 subject-scaled upper-limb models personalize muscle strength."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".cache/upper-limb-torque"
OUTPUT = ROOT / "docs/data/upper_limb_model_parameter_audit.json"
SUBJECTS = tuple(f"S{number:02d}" for number in range(1, 18))
PARAMETERS = ("max_isometric_force", "optimal_fiber_length", "tendon_slack_length")


def main():
    models = {}
    for subject in SUBJECTS:
        root = ET.parse(DATA / subject / "scaledModel.osim").getroot()
        muscles = root.findall(".//Millard2012EquilibriumMuscle")
        if len(muscles) != 12:
            raise ValueError(f"{subject}: expected 12 muscles, got {len(muscles)}")
        values = {}
        for muscle in muscles:
            name = muscle.attrib["name"]
            values[name] = {field: float(muscle.findtext(field)) for field in PARAMETERS}
            if any(value <= 0 for value in values[name].values()):
                raise ValueError(f"{subject}: nonpositive muscle parameter {name}")
        models[subject] = values
    names = sorted(models[SUBJECTS[0]])
    if any(sorted(item) != names for item in models.values()):
        raise ValueError("muscle name sets differ across subjects")
    rows = []
    for name in names:
        fields = {}
        for field in PARAMETERS:
            values = [models[subject][name][field] for subject in SUBJECTS]
            fields[field] = {"min": min(values), "max": max(values),
                             "uniqueAt1eMinus8": len({round(value, 8) for value in values})}
        rows.append({"muscle": name, "parameters": fields})
    report = {
        "status": "scaled_geometry_not_personalized_maximum_muscle_force",
        "source": "https://zenodo.org/records/11209324",
        "license": "CC BY-SA 4.0",
        "models": len(SUBJECTS), "musclesPerModel": len(names),
        "unchangedMaxIsometricForceMuscles": sum(
            item["parameters"]["max_isometric_force"]["uniqueAt1eMinus8"] == 1 for item in rows),
        "changedOptimalFiberLengthMuscles": sum(
            item["parameters"]["optimal_fiber_length"]["uniqueAt1eMinus8"] > 1 for item in rows),
        "changedTendonSlackLengthMuscles": sum(
            item["parameters"]["tendon_slack_length"]["uniqueAt1eMinus8"] > 1 for item in rows),
        "muscles": rows,
        "limitations": [
            "This inspects serialized model parameters, not model performance or participants' measured strength.",
            "The tracking task is not bench press or overhead press.",
            "Identical maximum isometric forces cannot justify personal muscle-force estimates from height and weight alone.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "models", "musclesPerModel", "unchangedMaxIsometricForceMuscles",
        "changedOptimalFiberLengthMuscles", "changedTendonSlackLengthMuscles")}, indent=2))
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
