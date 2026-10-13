"""Register Z-Anatomy muscle surfaces to the neutral OpenSim skeleton.

The anatomy atlas is a visual surface. Motion and muscle-tendon lengths remain
defined by the single cyclistFullBodyMuscle OpenSim model. This export records
the rigid registration, source-to-model correspondence, and local belly anchors
so the same surfaces move in every viewer pose.
"""

import json
import math
import re
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
SKELETON = ROOT / "public/models/unified_opensim_skeleton.glb"
REFERENCE = ROOT / "public/data/unified_opensim_reference.json"
AUDIT = ROOT / "docs/data/unified_opensim_geometry.json"
OUT_MODEL = ROOT / "public/models/unified_muscle_surfaces.glb"
OUT_SKIN = ROOT / "public/data/unified_muscle_skin.json"
OUT_WEIGHTS = ROOT / "public/data/unified_muscle_weights.bin"


LANDMARKS = {
    "Hip bone.r": "r_pelvis.vtp", "Hip bone.l": "l_pelvis.vtp",
    "Femur.r": "r_femur.vtp", "Femur.l": "l_femur.vtp",
    "Tibia.r": "r_tibia.vtp", "Tibia.l": "l_tibia.vtp",
    "Fibula.r": "r_fibula.vtp", "Fibula.l": "l_fibula.vtp",
    "Humerus.r": "humerus_rv.vtp", "Humerus.l": "humerus_lv.vtp",
    "Ulna.r": "ulna_rv.vtp", "Ulna.l": "ulna_lv.vtp",
    "Radius.r": "radius_rv.vtp", "Radius.l": "radius_lv.vtp",
    "Sacrum": "sacrum.vtp",
}


def muscle_matches(name, source_names):
    stem, side = name.rsplit(".", 1)
    suffix = "_r" if side == "r" else "_l"
    upper_suffix = "" if side == "r" else "_L"
    names = []
    def use(*values):
        names.extend(value for value in values if value in source_names)
    if stem.startswith("Gluteus maximus"):
        use(*(f"glmax{i}{suffix}" for i in range(1, 4)))
    elif stem.startswith("Gluteus medius"):
        use(*(f"glmed{i}{suffix}" for i in range(1, 4)))
    elif stem.startswith("Long head of biceps femoris"):
        use(f"bflh140{suffix}")
    elif stem.startswith("Short head of biceps femoris"):
        use(f"bfsh140{suffix}")
    elif stem.startswith("Semimembranosus"):
        use(f"semimem{suffix}")
    elif stem.startswith("Semitendinosus"):
        use(f"semiten{suffix}")
    elif stem.startswith("Rectus femoris"):
        use(f"recfem{suffix}")
    elif stem.startswith("Vastus medialis"):
        use(f"vasmed{suffix}")
    elif stem.startswith("Vastus lateralis"):
        use(f"vaslat140{suffix}")
    elif stem.startswith("Vastus intermedius"):
        use(f"vasint{suffix}")
    elif stem.startswith("Lateral head of gastrocnemius"):
        use(f"gaslat140{suffix}")
    elif stem.startswith("Medial head of gastrocnemius"):
        use(f"gasmed{suffix}")
    elif stem.startswith("Soleus"):
        use(f"soleus{suffix}")
    elif stem.startswith("Tibialis anterior"):
        use(f"tibant{suffix}")
    elif stem.startswith("Rectus abdominis"):
        use(f"rect_abd{suffix}")
    elif stem.startswith("External abdominal oblique"):
        use(*(f"E0_R{i}{suffix}" for i in range(5, 13)))
    elif stem.startswith("Longissimus thoracis"):
        use(*(f"LTpT_T{i}{suffix}" for i in range(1, 13)))
    elif stem.startswith("Latissimus dorsi"):
        use(*(f"LD_L{i}{suffix}" for i in range(1, 6)))
    elif stem.startswith("Serratus anterior"):
        use(*(f"SerrAnt{i}_1_{side.upper()}" for i in range(1, 10)))
    elif stem.startswith("Rhomboid major"):
        use(*(f"TR{i}{suffix}" for i in range(1, 6)))
    elif stem.startswith("Descending part of trapezius"):
        use(f"trap_cl{upper_suffix}")
    elif stem.startswith("Transverse part of trapezius"):
        use(f"trap_acr_scap{upper_suffix}")
    elif stem.startswith("Ascending part of trapezius"):
        use(*(f"trap_inf_T{i}{upper_suffix}" for i in range(4, 13)))
    elif stem.startswith("Clavicular head of pectoralis"):
        use("PECM1" if side == "r" else "PECM1_l")
    elif stem.startswith("Sternocostal head of pectoralis"):
        use(*(("PECM2", "PECM3") if side == "r" else ("PECM2_l", "PECM3_l")))
    elif stem.startswith("(Abdominal part of pectoralis"):
        use("PECM3" if side == "r" else "PECM3_l")
    elif stem.startswith("Clavicular part of deltoid"):
        use("DELT1" if side == "r" else "DELT1_l")
    elif stem.startswith("Acromial part of deltoid"):
        use("DELT2" if side == "r" else "DELT2_l")
    elif stem.startswith("Scapular spinal part of deltoid"):
        use("DELT3" if side == "r" else "DELT3_l")
    elif stem.startswith("Long head of biceps brachii"):
        use(f"BIClong{suffix}")
    elif stem.startswith("Short head of biceps brachii"):
        use(f"BICshort{suffix}")
    elif stem.startswith("Brachialis"):
        use(f"BRA{suffix}")
    elif stem.startswith("Brachioradialis"):
        use(f"BRD{suffix}")
    elif stem.startswith("Long head of triceps brachii"):
        use(f"TRIlong{suffix}")
    elif stem.startswith("Lateral head of triceps brachii"):
        use(f"TRIlat{suffix}")
    elif stem.startswith("Medial head of triceps brachii"):
        use(f"TRImed{suffix}")
    return names


def main():
    atlas = trimesh.load(ATLAS, force="scene")
    bones = trimesh.load(SKELETON, force="scene")
    ref = json.loads(REFERENCE.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    source_names = set(ref["muscleNames"])
    entries = {entry["mesh"]: entry for entry in audit["present"]}
    bone_index = {name: index for index, name in enumerate(ref["bodyNames"])}

    def mesh_world(scene, node):
        transform, key = scene.graph[node]
        mesh = scene.geometry[key].copy()
        mesh.apply_transform(transform)
        return mesh

    def body_world(entry):
        mesh = mesh_world(bones, entry["node"])
        pose = ref["neutral"]["bodies"][bone_index[entry["body"]]]
        transform = np.eye(4)
        transform[:3, :3] = np.asarray(pose["r"]).reshape(3, 3)
        transform[:3, 3] = pose["p"]
        mesh.apply_transform(transform)
        return mesh

    pairs = []
    for atlas_name, source_file in LANDMARKS.items():
        if atlas_name in atlas.graph.nodes_geometry and source_file in entries:
            a = mesh_world(atlas, atlas_name)
            b = body_world(entries[source_file])
            pairs.append((atlas_name, a, b))
    if len(pairs) < 12:
        raise RuntimeError(f"Only {len(pairs)} matching bone landmarks")
    from_pts = np.asarray([a.centroid for _, a, _ in pairs])
    to_pts = np.asarray([b.centroid for _, _, b in pairs])
    a_mean, b_mean = from_pts.mean(0), to_pts.mean(0)
    u, singular, vt = np.linalg.svd((from_pts - a_mean).T @ (to_pts - b_mean))
    correction = np.eye(3)
    correction[-1, -1] = np.linalg.det(u @ vt)
    rotation = u @ correction @ vt
    scale = np.sum(singular * np.diag(correction)) / np.sum((from_pts - a_mean) ** 2)
    translation = b_mean - scale * (a_mean @ rotation)
    registration = np.eye(4)
    registration[:3, :3] = scale * rotation.T
    registration[:3, 3] = translation
    diagnostics = []
    bone_offsets = {}
    for name, a, b in pairs:
        a.apply_transform(registration)
        ctr_error = float(np.linalg.norm(a.centroid - b.centroid))
        bone_offsets[name] = b.centroid - a.centroid
        sample_a = a.vertices[::max(1, len(a.vertices) // 1000)]
        sample_b = b.vertices[::max(1, len(b.vertices) // 1000)]
        distance = cKDTree(sample_b).query(sample_a)[0]
        diagnostics.append({"atlas": name, "centroidErrorM": round(ctr_error, 4),
                            "medianSurfaceDistanceM": round(float(np.median(distance)), 4)})
    print("registration scale", scale, "landmark RMS", np.sqrt(np.mean([d["centroidErrorM"]**2 for d in diagnostics])))
    for diagnostic in diagnostics:
        print(diagnostic)

    scene = trimesh.Scene()
    records = []
    weights = bytearray()
    for name in sorted(atlas.graph.nodes_geometry):
        if "muscle" not in name and not any(s in name for s in ("gastrocnemius", "triceps brachii", "biceps brachii")):
            continue
        source_muscles = muscle_matches(name, source_names)
        if not source_muscles:
            print("UNMAPPED", name)
            continue
        mesh = mesh_world(atlas, name)
        mesh.apply_transform(registration)
        # The atlas has narrower shoulders/forearms than this OpenSim subject.
        # Keep torso and leg registration global; align limb bellies to their
        # corresponding source bones before deriving skin weights.
        side = name.rsplit(".", 1)[-1]
        if "deltoid muscle" in name:
            mesh.apply_translation(0.55 * bone_offsets[f"Humerus.{side}"])
        elif any(part in name for part in ("biceps brachii", "triceps brachii", "Brachialis muscle")):
            mesh.apply_translation(bone_offsets[f"Humerus.{side}"])
        elif "Brachioradialis muscle" in name:
            mesh.apply_translation(bone_offsets[f"Radius.{side}"])
        if len(mesh.vertices) < 3 or len(mesh.faces) < 1:
            continue
        # The body pair is derived from the corresponding OpenSim path. Its
        # first and last points are the model's origin/insertion at neutral.
        muscle_id = ref["muscleNames"].index(source_muscles[0])
        path = np.asarray(ref["neutral"]["paths"][muscle_id])
        start, end = path[0], path[-1]
        direction = end - start
        length_sq = float(direction @ direction)
        if length_sq < 1e-8:
            raise ValueError(f"degenerate OpenSim path: {source_muscles[0]}")
        projection = ((mesh.vertices - start) @ direction) / length_sq
        low, high = np.quantile(projection, [0.02, 0.98])
        u_values = np.clip((projection - low) / max(float(high - low), 1e-5), 0, 1)
        # Using muscle path closest point to each endpoint lets us read the
        # attachment bodies from a separate OpenSim export made below.
        records.append({"name": name, "modelMuscles": source_muscles,
                        "weightOffset": len(weights), "vertexCount": len(mesh.vertices),
                        "axis": (direction / math.sqrt(length_sq)).round(6).tolist(),
                        "center": mesh.centroid.round(6).tolist(),
                        "uMin": round(float(u_values.min()), 3),
                        "uMax": round(float(u_values.max()), 3)})
        weights.extend(np.rint(u_values * 255).astype(np.uint8).tobytes())
        scene.add_geometry(mesh, node_name=name, geom_name=name)

    # Read parent body names from the source OpenSim XML. Every muscle path
    # point has a socket_parent_frame reference; first/last identify anchors.
    import xml.etree.ElementTree as ET
    model_file = ROOT / ".cache/model-candidates/opensim-model-fullBodyMuscleActuated/cyclistFullBodyMuscle.osim"
    tree = ET.parse(model_file)
    attachment = {}
    for element in tree.iter():
        name = element.attrib.get("name")
        if name not in source_names:
            continue
        sockets = [node.text for node in element.iter("socket_parent_frame") if node.text]
        if len(sockets) >= 2:
            raw = [re.split(r"[/\\]", value.strip())[-1] for value in (sockets[0], sockets[-1])]
            if all(value in bone_index for value in raw):
                attachment[name] = [bone_index[value] for value in raw]
    for record in records:
        model_name = record["modelMuscles"][0]
        if model_name not in attachment:
            raise ValueError(f"No source attachment bodies for {model_name}")
        origin, insertion = attachment[model_name]
        name = record["name"]
        side = name.rsplit(".", 1)[-1]
        if any(part in name for part in ("femoris", "Vastus", "Semimembranosus", "Semitendinosus")):
            primary = f"femur_{side}"
        elif any(part in name for part in ("gastrocnemius", "Soleus", "Tibialis anterior")):
            primary = f"tibia_{side}"
        elif "Brachioradialis" in name:
            primary = f"radius_{side}"
        elif any(part in name for part in ("deltoid", "biceps brachii", "triceps brachii", "Brachialis")):
            primary = f"humerus_{side}"
        elif "Gluteus" in name:
            primary = "pelvis"
        elif "pectoralis" in name:
            primary = "sternum"
        elif "Rhomboid" in name:
            primary = f"scapula_{side.upper()}"
        elif "Serratus" in name:
            primary = f"scapula_{side.upper()}"
        elif "trapezius" in name:
            primary = "thoracic3"
        else:
            primary = "Abdomen"
        record["bodyIndices"] = [origin, bone_index[primary], insertion]

    OUT_MODEL.write_bytes(scene.export(file_type="glb"))
    OUT_WEIGHTS.write_bytes(weights)
    metadata = {"schemaVersion": 2, "sourceAtlas": "Z-Anatomy / BodyParts3D",
                "license": "CC BY-SA 4.0", "sourceModel": ref["model"],
                "registration": registration.round(7).tolist(),
                "boneLandmarks": diagnostics, "meshes": records}
    OUT_SKIN.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(records)} muscles, {len(weights)} vertices, {OUT_MODEL.stat().st_size} GLB bytes")


if __name__ == "__main__":
    main()
