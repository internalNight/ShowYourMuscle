"""Package only geometry actually referenced and present in the unified OpenSim model.

Each glTF node is named body:<OpenSim body>:<source mesh>. Vertices stay in
that body's local frame; the browser applies OpenSim's world transform for
every preset frame. Missing upstream VTP files are recorded, never fabricated.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache/model-candidates/opensim-model-fullBodyMuscleActuated"
SUPPLEMENT = ROOT / ".cache/model-candidates/pose2sim/Pose2Sim/OpenSim_Setup/Geometry"
MODEL = SOURCE / "cyclistFullBodyMuscle.osim"
OUTPUT = ROOT / "public/models/unified_opensim_skeleton.glb"
REPORT = ROOT / "docs/data/unified_opensim_geometry.json"


def parse_vtp(path):
    piece = ET.parse(path).getroot().find(".//Piece")
    points = connectivity = offsets = None
    for section in piece:
        for array in section:
            if array.tag != "DataArray":
                continue
            values = (array.text or "").split()
            if section.tag == "Points":
                points = np.asarray(values, dtype=np.float32).reshape(-1, 3)
            elif section.tag == "Polys" and array.get("Name") == "connectivity":
                connectivity = [int(value) for value in values]
            elif section.tag == "Polys" and array.get("Name") == "offsets":
                offsets = [int(value) for value in values]
    if points is None or connectivity is None or offsets is None:
        raise ValueError(f"cannot read {path}")
    faces = []
    start = 0
    for end in offsets:
        polygon = connectivity[start:end]
        for index in range(1, len(polygon) - 1):
            faces.append((polygon[0], polygon[index], polygon[index + 1]))
        start = end
    return points, np.asarray(faces, dtype=np.int32)


def main():
    if not MODEL.is_file():
        raise FileNotFoundError(f"clone source model first: {SOURCE}")
    document = ET.parse(MODEL).getroot()
    bodies = document.find(".//BodySet/objects")
    scene = trimesh.Scene()
    present = []
    missing = []
    excluded = []
    for body in bodies:
        name = body.attrib["name"]
        for mesh in body.iter("Mesh"):
            filename = mesh.findtext("mesh_file")
            if not filename:
                continue
            path = SOURCE / "Geometry" / filename
            origin = "model repository"
            if not path.is_file() and (SUPPLEMENT / filename).is_file():
                path = SUPPLEMENT / filename
                origin = "Pose2Sim matching geometry"
            entry = {"body": name, "mesh": filename, "origin": origin}
            if not path.is_file():
                missing.append(entry)
                continue
            if name.startswith("thoracic") and origin == "Pose2Sim matching geometry":
                excluded.append({**entry, "reason": "source model positions upper vertebrae above the skull"})
                continue
            vertices, faces = parse_vtp(path)
            scale = np.fromstring(mesh.findtext("scale_factors", "1 1 1"), sep=" ")
            vertices *= scale
            geometry = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
            node = f"body:{name}:{mesh.attrib.get('name', filename)}"
            scene.add_geometry(geometry, node_name=node, geom_name=node)
            present.append({**entry, "node": node, "triangles": len(faces)})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(scene.export(file_type="glb"))
    REPORT.write_text(json.dumps({
        "model": MODEL.name,
        "source": "https://github.com/ross-wilkinson/opensim-model-fullBodyMuscleActuated",
        "license": "MIT; Copyright (c) 2021 ross-wilkinson; BSD-3-Clause; Copyright (c) 2022 perfanalytics",
        "supplement": "https://github.com/perfanalytics/pose2sim/tree/main/Pose2Sim/OpenSim_Setup/Geometry",
        "present": present,
        "missing": missing,
        "excluded": excluded,
        "limits": "Only exact mesh filenames referenced by this one .osim model are used. Missing meshes are not synthesized. Twelve thoracic meshes are excluded because this model places them visibly above the skull. Supplement geometry shares 64 byte-identical filenames with the model source; the other added meshes have not been individually registration-validated.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(present)} source meshes, {len(missing)} missing, {len(excluded)} excluded, "
          f"{sum(item['triangles'] for item in present)} triangles, "
          f"{OUTPUT.stat().st_size} GLB bytes")


if __name__ == "__main__":
    main()
