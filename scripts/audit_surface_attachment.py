"""Audit how far displayed muscle surfaces drift from their OpenSim paths."""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import trimesh


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--live-extreme", action="store_true")
parser.add_argument("--anchor-strength", type=float)
args = parser.parse_args()
ref = json.loads((ROOT / "public/data/unified_opensim_reference.json").read_text())
skin = json.loads((ROOT / "public/data/unified_muscle_skin.json").read_text())
raw_weights = np.frombuffer((ROOT / "public/data/unified_muscle_weights.bin").read_bytes(), dtype=np.uint8)
atlas = trimesh.load(ROOT / "public/models/unified_muscle_surfaces.glb", force="scene")
name_to_index = {name: i for i, name in enumerate(ref["muscleNames"])}


def transforms(frame):
    result = []
    for body in frame["bodies"]:
        matrix = np.eye(4)
        matrix[:3, :3] = np.asarray(body["r"]).reshape(3, 3)
        matrix[:3, 3] = body["p"]
        result.append(matrix)
    return result


neutral = transforms(ref["neutral"])
frames = {"neutral": ref["neutral"],
          **{action: ref["actions"][action][50] for action in ("squat", "bench", "press")}}
if args.live_extreme:
    payload = json.dumps({"controls": {"pelvis_tilt": .5, "hip_flexion": 1.6,
                                       "knee_angle": 2.1, "ankle_angle": .3,
                                       "elv_angle": 1.2, "shoulder_elv": 2.4,
                                       "elbow_flex": 1.8}, "plantFeet": True}).encode()
    response = urlopen(Request("http://127.0.0.1:5173/api/pose", data=payload,
                               headers={"Content-Type": "application/json"}))
    frames["custom"] = json.load(response)["frame"]
results = []
for entry in skin["meshes"]:
    name = entry["name"]
    matrix, key = atlas.graph[name]
    mesh = atlas.geometry[key].copy()
    mesh.apply_transform(matrix)
    vertex = mesh.vertices
    take = np.arange(0, len(vertex), max(1, len(vertex) // 500))
    vertex = vertex[take]
    u = raw_weights[entry["weightOffset"] + take].astype(float) / 255

    def smooth(a, b, x):
        t = np.clip((x - a) / (b - a), 0, 1)
        return t * t * (3 - 2 * t)

    anchor_strength = (args.anchor_strength if args.anchor_strength is not None else
                       .55 if ("Short head of biceps brachii" in name or "gastrocnemius" in name)
                       else .82)
    origin = anchor_strength * (1 - smooth(.03, .38, u))
    insert = anchor_strength * smooth(.62, .97, u)
    weights = np.stack((origin, 1 - origin - insert, insert), axis=1)
    if weights.min() < -1e-5:
        raise ValueError(name)
    muscle_ids = [name_to_index[m] for m in entry["modelMuscles"]]
    distances = {}
    for label, current in frames.items():
        matrices = transforms(current)
        deformed = np.zeros_like(vertex)
        for slot, body_index in enumerate(entry["bodyIndices"]):
            transform = matrices[body_index] @ np.linalg.inv(neutral[body_index])
            moved = vertex @ transform[:3, :3].T + transform[:3, 3]
            deformed += moved * weights[:, slot, None]
        segments = [(a, b) for index in muscle_ids
                    for a, b in zip(current["paths"][index][:-1], current["paths"][index][1:])]
        point_distances = np.full(len(deformed), np.inf)
        for start, end in segments:
            start, end = np.asarray(start), np.asarray(end)
            axis = end - start
            u = np.clip(((deformed - start) @ axis) / max(axis @ axis, 1e-12), 0, 1)
            point_distances = np.minimum(point_distances,
                                         np.linalg.norm(deformed - start - u[:, None] * axis, axis=1))
        distances[label] = (float(np.median(point_distances)),
                            float(np.quantile(point_distances, .95)))
    results.append((max(distances[label][1] - distances["neutral"][1] for label in frames if label != "neutral"),
                    name, distances))

for increase, name, distances in sorted(results, reverse=True)[:25]:
    print(f"{name:52} p95 +{increase*100:.1f} cm  " +
          " ".join(f"{key}:{value[0]*100:.1f}/{value[1]*100:.1f}" for key, value in distances.items()))
