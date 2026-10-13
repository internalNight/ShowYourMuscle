"""Register anatomical bone surfaces to the same OpenSim body transforms as muscles."""

import json
import re
from pathlib import Path

import numpy as np
import trimesh


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
SOURCE_BONES = ROOT / "public/models/unified_opensim_skeleton.glb"
SKIN = ROOT / "public/data/unified_muscle_skin.json"
REFERENCE = ROOT / "public/data/unified_opensim_reference.json"
AUDIT = ROOT / "docs/data/unified_opensim_geometry.json"
OUTPUT = ROOT / "public/models/unified_anatomy_bones.glb"
MAPPING = ROOT / "public/data/unified_anatomy_bones.json"

ORDINALS = {"First": 1, "Second": 2, "Third": 3, "Fourth": 4,
            "Fifth": 5, "Sixth": 6, "Seventh": 7, "Eighth": 8,
            "Ninth": 9, "Tenth": 10, "Eleventh": 11, "Twelfth": 12}


def body_for(name):
    side = name.rsplit(".", 1)[-1] if name.endswith((".r", ".l")) else None
    stem = name.rsplit(".", 1)[0] if side else name
    if stem in ("Body of sternum", "Manubrium of sternum"):
        return "sternum"
    if stem == "Sacrum":
        return "sacrum"
    if stem == "Hip bone":
        return "pelvis"
    if stem.startswith("Vertebra "):
        level = stem.split()[-1]
        return ("head_neck" if level.startswith("C") else
                f"thoracic{level[1:]}" if level.startswith("T") else
                f"lumbar{level[1:]}")
    rib = re.match(r"^(\w+) rib$", stem)
    if rib and side:
        return f"rib{ORDINALS[rib.group(1).capitalize()]}_{side.upper()}"
    cartilage = re.match(r"^Costal cartilage of (\w+) rib$", stem)
    if cartilage and side:
        return f"rib{ORDINALS[cartilage.group(1).capitalize()]}_{side.upper()}"
    return {"Femur": "femur", "Tibia": "tibia", "Fibula": "tibia",
            "Patella": "patella", "Calcaneus": "calcn",
            "Clavicle": "clavicle", "Scapula": "scapula",
            "Humerus": "humerus", "Radius": "radius", "Ulna": "ulna"}.get(stem, "") + (
                f"_{side.upper()}" if stem in ("Clavicle", "Scapula") and side else
                f"_{side}" if side else "")


def world_mesh(scene, node):
    transform, key = scene.graph[node]
    mesh = scene.geometry[key].copy()
    mesh.apply_transform(transform)
    return mesh


def main():
    atlas = trimesh.load(ATLAS, force="scene")
    source = trimesh.load(SOURCE_BONES, force="scene")
    skin = json.loads(SKIN.read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    body_index = {name: i for i, name in enumerate(reference["bodyNames"])}
    source_entries = {}
    for entry in audit["present"]:
        source_entries.setdefault(entry["body"], entry)
    scene = trimesh.Scene()
    records = []
    registration = np.asarray(skin["registration"])
    for name in sorted(atlas.graph.nodes_geometry):
        body = body_for(name)
        if body not in body_index:
            continue
        mesh = world_mesh(atlas, name)
        mesh.apply_transform(registration)
        if body in source_entries:
            entry = source_entries[body]
            source_mesh = world_mesh(source, entry["node"])
            pose = reference["neutral"]["bodies"][body_index[body]]
            transform = np.eye(4)
            transform[:3, :3] = np.asarray(pose["r"]).reshape(3, 3)
            transform[:3, 3] = pose["p"]
            source_mesh.apply_transform(transform)
            # Body-specific corrections remove most of the atlas/model size
            # mismatch without inventing an independent kinematic skeleton.
            mesh.apply_translation(source_mesh.centroid - mesh.centroid)
        if len(mesh.vertices) < 3 or len(mesh.faces) < 1:
            continue
        scene.add_geometry(mesh, node_name=name, geom_name=name)
        records.append({"name": name, "bodyIndex": body_index[body], "body": body})
    OUTPUT.write_bytes(scene.export(file_type="glb"))
    MAPPING.write_text(json.dumps({"schemaVersion": 1, "sourceModel": reference["model"],
                                   "bones": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(records)} anatomical bones ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
