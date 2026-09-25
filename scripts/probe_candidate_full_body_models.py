"""Audit a third-party exercise-model generator before considering reuse.

The checkout is kept under .cache and is not bundled with the app. This probe
checks what the generated XML actually contains, then asks OpenSim 4.6 to load
and initialize it. Passing XML checks alone does not validate biomechanics.
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / ".cache/model-candidates/OpenSim_Models"
sys.path.insert(0, str(CANDIDATE / "src"))

from opensim_models.exercises.bench_press.bench_press_model import build_bench_press_model
from opensim_models.exercises.clean_and_jerk.clean_and_jerk_model import build_clean_and_jerk_model
from opensim_models.exercises.squat.squat_model import build_squat_model


def audit(name, builder):
    xml = builder(body_mass=72, height=1.75, plate_mass_per_side=0)
    root = ET.fromstring(xml)
    bodies = root.findall(".//BodySet/objects/Body")
    joints = root.findall(".//JointSet/objects/*")
    forces = root.findall(".//ForceSet/objects/*")
    if not bodies:
        bodies = root.findall(".//BodySet/Body")
    if not joints:
        joints = root.findall(".//JointSet/*")
    if not forces:
        forces = root.findall(".//ForceSet/*")
    with tempfile.NamedTemporaryFile(prefix=f"muscle_atlas_{name}_", suffix=".osim",
                                     delete=False) as handle:
        path = Path(handle.name)
    with tempfile.NamedTemporaryFile(prefix=f"muscle_atlas_{name}_wrapped_", suffix=".osim",
                                     delete=False) as handle:
        wrapped_path = Path(handle.name)
    path.write_text(xml, encoding="utf-8")
    result = {
        "exercise": name,
        "xmlSha256": hashlib.sha256(xml.encode("utf-8")).hexdigest(),
        "xmlBodies": len(bodies),
        "xmlJoints": len(joints),
        "xmlForces": len(forces),
        "xmlMuscleElements": len([element for element in root.iter()
                                  if "Muscle" in element.tag]),
        "barbellAttachmentJointNames": [joint.get("name") for joint in joints
                                         if "barbell_to" in joint.get("name", "")],
    }
    try:
        model = osim.Model(str(path))
        state = model.initSystem()
        result.update({"opensimLoadAndInit": "passed_but_check_counts",
                       "opensimBodies": model.getBodySet().getSize(),
                       "opensimJoints": model.getJointSet().getSize(),
                       "opensimMuscles": model.getMuscles().getSize(),
                       "opensimTotalMassKg": model.getTotalMass(state)})
    except Exception as exc:
        result.update({"opensimLoadAndInit": "failed",
                       "opensimError": str(exc)[:2000]})
    # Diagnostic only: OpenSim's Set serialization normally requires an
    # <objects> wrapper. Check whether this alone makes the generated model
    # usable, without modifying or adopting the third-party source.
    for tag in ("BodySet", "JointSet", "ForceSet", "ContactGeometrySet"):
        container = root.find(f".//Model/{tag}")
        if container is None or container.find("objects") is not None:
            continue
        objects = ET.Element("objects")
        for child in list(container):
            container.remove(child)
            objects.append(child)
        container.append(objects)
    wrapped_path.write_text(ET.tostring(root, encoding="unicode", xml_declaration=True),
                            encoding="utf-8")
    try:
        model = osim.Model(str(wrapped_path))
        state = model.initSystem()
        result.update({"wrappedSetDiagnostic": "passed_but_check_counts",
                       "wrappedBodies": model.getBodySet().getSize(),
                       "wrappedJoints": model.getJointSet().getSize(),
                       "wrappedMuscles": model.getMuscles().getSize(),
                       "wrappedTotalMassKg": model.getTotalMass(state)})
    except Exception as exc:
        result.update({"wrappedSetDiagnostic": "failed",
                       "wrappedSetError": str(exc)[:2000]})
    path.unlink(missing_ok=True)
    wrapped_path.unlink(missing_ok=True)
    return result


def main():
    commit = subprocess.check_output(
        ["git", "-C", str(CANDIDATE), "rev-parse", "HEAD"], text=True).strip()
    rows = [audit("squat", build_squat_model),
            audit("bench_press", build_bench_press_model),
            audit("clean_and_jerk", build_clean_and_jerk_model)]
    report = {
        "status": "third_party_model_candidate_audit_not_product_validation",
        "source": "https://github.com/D-sorganization/OpenSim_Models",
        "sourceCommit": commit,
        "license": "MIT per repository LICENSE; confirm attribution if integrated",
        "input": "72 kg body, 1.75 m height, 20 kg empty barbell",
        "runs": rows,
    }
    output = ROOT / "docs/data/third_party_exercise_model_audit.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
