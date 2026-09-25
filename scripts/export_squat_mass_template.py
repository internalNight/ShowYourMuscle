"""Extract preserved segment-mass fractions from the public scaled gait2354 models.

These fractions describe one OpenSim template, not measured participant-specific
segment masses. The source dataset preserved its generic mass distribution.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
models = sorted((ROOT / ".cache/lower-limb-raw").glob("AB*/Models/*-Scaled1.osim"))
if len(models) != 12:
    raise RuntimeError(f"Expected 12 extracted scaled models, found {len(models)}")

groups = {
    "torso": ["torso"],
    "pelvis": ["pelvis"],
    "thighEach": ["femur_r"],
    "shankEach": ["tibia_r"],
    "footEach": ["talus_r", "calcn_r", "toes_r"],
}
rows = []
for path in models:
    root = ET.parse(path).getroot()
    bodies = {body.get("name"): float(body.findtext("mass"))
              for body in root.findall(".//BodySet/objects/Body")}
    if not bodies:
        raise RuntimeError(f"No body masses in {path}")
    total = sum(bodies.values())
    result = {key: sum(bodies[name] for name in names) / total
              for key, names in groups.items()}
    for key in ("thighEach", "shankEach", "footEach"):
        side = key.replace("Each", "")
        left_names = [name.replace("_r", "_l") for name in groups[key]]
        left_fraction = sum(bodies[name] for name in left_names) / total
        if abs(left_fraction - result[key]) > 1e-7:
            raise RuntimeError(f"Asymmetric {side} mass distribution in {path}")
    if abs(result["torso"] + result["pelvis"] + 2 * sum(
            result[key] for key in ("thighEach", "shankEach", "footEach")) - 1) > 1e-7:
        raise RuntimeError(f"Unaccounted body mass in {path}")
    rows.append(result)

first = rows[0]
deviation = max(abs(row[key] - first[key]) for row in rows for key in first)
if deviation > 1e-6:
    raise RuntimeError(f"Scaled models do not share one mass template: {deviation}")

output = {
    "status": "generic_gait2354_mass_fraction_template_not_personal_measurement",
    "source": "Scherpereel et al. 2023 public OpenSim scaled models",
    "sourceUrl": "https://www.nature.com/articles/s41597-023-02840-6",
    "modelCount": len(models),
    "maxFractionDeviation": deviation,
    "fractions": {key: round(value, 10) for key, value in first.items()},
    "note": "The paper says segment mass distribution was preserved during scaling; the 12 models are not 12 independent mass-fraction measurements.",
}
target = ROOT / "src/data/squat_mass_template.json"
target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {target}: {len(models)} models, maximum fraction deviation {deviation:.2e}")
