"""Screen three deltoid atlas surfaces after the humerus proxy registration.

Nearest-surface distances only rank candidate assets. They do not identify
fiber paths, attachment landmarks, activation, or force.
"""

import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
MAPPING = {
    "DeltoideusClavicle_A": "Clavicular part of deltoid muscle.r",
    "DeltoideusScapula_M": "Acromial part of deltoid muscle.r",
    "DeltoideusScapula_P": "Scapular spinal part of deltoid muscle.r",
}


def sampled_path(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


def to_blender(viewer_point):
    x, y, z = viewer_point
    return Vector((x, -z, y))


def body_matrix(data):
    rows = data["rotationRows"]
    position = data["translationM"]
    return Matrix(((rows[0][0], rows[0][1], rows[0][2], position[0]),
                   (rows[1][0], rows[1][1], rows[1][2], position[1]),
                   (rows[2][0], rows[2][1], rows[2][2], position[2]),
                   (0, 0, 0, 1)))


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
records = []
for exercise in ("bench", "press"):
    frames = json.loads((ROOT / "public/data" / f"{exercise}_tsm_reference.json")
                        .read_text(encoding="utf-8"))["frames"]
    registration = json.loads((ROOT / "docs/data" / f"tsm_{exercise}_upper_bone_registration.json")
                              .read_text(encoding="utf-8"))
    humerus = next(item for item in registration["bones"] if item["modelBody"] == "humerus")
    atlas_to_model = Matrix(humerus["atlasToModelBlenderRows"])
    starting_body = body_matrix(frames[0]["blenderBodyFrames"]["humerus"])
    for muscle, atlas_name in MAPPING.items():
        obj = bpy.data.objects.get(atlas_name)
        if obj is None:
            raise RuntimeError(f"Missing atlas mesh: {atlas_name}")
        standing_vertices = [atlas_to_model @ obj.matrix_world @ vertex.co
                             for vertex in obj.data.vertices]
        faces = [tuple(poly.vertices) for poly in obj.data.polygons]
        frame_rows = []
        for frame_index in (0, 25, 50, 75, 100):
            frame = frames[frame_index]
            delta = body_matrix(frame["blenderBodyFrames"]["humerus"]) @ starting_body.inverted()
            vertices = [delta @ vertex for vertex in standing_vertices]
            surface = BVHTree.FromPolygons(vertices, faces)
            path = [to_blender(point) for point in frame["muscles"][muscle]["viewerPathM"]]
            samples = []
            for index in range(21):
                point = sampled_path(path, index / 20)
                nearest, _, _, distance = surface.find_nearest(point)
                if nearest is None:
                    raise RuntimeError(f"No nearest surface for {atlas_name}")
                samples.append({"fraction": index / 20, "surfaceDistanceM": round(distance, 6)})
            distances = sorted(item["surfaceDistanceM"] for item in samples)
            frame_rows.append({"frameIndex": frame_index,
                               "medianUnsignedSurfaceDistanceM": distances[10],
                               "p95UnsignedSurfaceDistanceM": distances[19],
                               "maximumUnsignedSurfaceDistanceM": distances[20],
                               "samples": samples})
        row = {"exercise": exercise, "modelMuscle": muscle, "atlasMesh": atlas_name,
               "registeredVia": "humerus endpoint proxy transform",
               "vertexCount": len(standing_vertices), "pathPointCount": len(path),
               "frames": frame_rows,
               "maximumAcrossFramesM": max(item["maximumUnsignedSurfaceDistanceM"]
                                            for item in frame_rows)}
        records.append(row)
        print(exercise, muscle, "start median/p95/max; all-frame max cm",
              *(round(frame_rows[0][key] * 100, 2) for key in
                ("medianUnsignedSurfaceDistanceM", "p95UnsignedSurfaceDistanceM",
                 "maximumUnsignedSurfaceDistanceM")),
              round(row["maximumAcrossFramesM"] * 100, 2))

out = ROOT / "docs/data/tsm_deltoid_surface_screen.json"
out.write_text(json.dumps({"status": "research_candidate_screen_only",
                           "sampleCountPerMusclePerFrame": 21,
                           "checkedFrameIndices": [0, 25, 50, 75, 100],
                           "muscles": records,
                           "limits": ["Five synthetic exercise poses per action",
                                      "All three deltoid meshes use a humerus bone proxy transform despite origins on clavicle/acromion/scapular spine",
                                      "Unsigned surface distance is not a fiber path or attachment landmark",
                                      "No mesh deformation, EMG comparison, or muscle force validation"]},
                          indent=2) + "\n", encoding="utf-8")
