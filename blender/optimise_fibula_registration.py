"""Search for a constant standing registration correction for the fibula.

The knee sweep showed that no constant correction of the tibia group clears the femur-to-tibia
overlap, but it also showed that the femur-to-fibula pair (71 of 101 frames at baseline) can be
cleared. The fibula shares the tibia body frame in OpenSim, so the animator applies one transform to
both; this probe asks what a correction of the fibula *alone* can do, which is the patella recipe
applied to the second small bone.

Cost: femur-to-fibula plus tibia-to-fibula penetration depth, plus a weighted deviation of the mean
fibula-to-femur and fibula-to-tibia seat distances from the baseline, so the search cannot win by
pulling the fibula away from the skeleton or by pressing it into the tibia. The fibula-to-tibia pair
already intersects at standing, so its reference state is reported next to the result.

Run as: blender --background assets/blender/opensim_anatomy_bone_motion.blend \
            --python-exit-code 1 --python blender/optimise_fibula_registration.py \
            [-- --report docs/data/fibula_registration_optimisation.json]
"""

import argparse
import json
import sys
import time
from pathlib import Path

import bpy
import numpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REPORT = ROOT / "docs/data/fibula_registration_optimisation.json"
SCENE = "assets/blender/opensim_anatomy_bone_motion.blend"
FIBULA = "atlas_Fibula.r"
TIBIA = "atlas_Tibia.r"
FEMUR = "atlas_Femur.r"
BODY = "tibia_r"
SEAT_VERTICES = 150
START_STEP_M = 0.004
MIN_STEP_M = 0.0004
BOUNDS_M = 0.03
PENALTY_WEIGHT = 5.0

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, default=REPORT)
parser.add_argument("--search-stride", type=int, default=3)
parser.add_argument("--max-evaluations", type=int, default=800)
parser.add_argument("--bounds-m", type=float, default=BOUNDS_M)
parser.add_argument("--penalty-weight", type=float, default=PENALTY_WEIGHT)
args = parser.parse_args(argv)
report_path = args.report if args.report.is_absolute() else ROOT / args.report


def body_matrix(data):
    result = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            result[row][col] = data["rotationRows"][row][col]
    result.translation = Vector(data["translationM"])
    return result


def numpy_matrix(matrix):
    return numpy.array([list(row) for row in matrix])


def evaluated_geometry(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        matrix = obj.matrix_world
        vertices = [matrix @ vertex.co for vertex in mesh.vertices]
        polygons = [tuple(polygon.vertices) for polygon in mesh.polygons]
    finally:
        evaluated.to_mesh_clear()
    return vertices, polygons


def tree_from(vertices, polygons):
    return BVHTree.FromPolygons([tuple(vertex) for vertex in vertices], polygons, all_triangles=False)


def face_centroid(vertices, polygon):
    centroid = Vector((0.0, 0.0, 0.0))
    for vertex in polygon:
        centroid += vertices[vertex]
    return centroid / len(polygon)


def penetration(tree, vertices, polygons, indices):
    depth = 0.0
    for index in indices:
        centroid = face_centroid(vertices, polygons[index])
        try:
            location, normal, _, distance = tree.find_nearest(centroid)
        except RuntimeError:
            continue
        if location is not None and (centroid - location).dot(normal) < 0:
            depth = max(depth, distance)
    return depth


def seat_distance(tree, vertices, indices):
    total = 0.0
    counted = 0
    for index in indices:
        try:
            _, _, _, distance = tree.find_nearest(vertices[index])
        except RuntimeError:
            continue
        if distance is not None:
            total += distance
            counted += 1
    return total / counted if counted else 0.0


def nearest_indices(tree, vertices, count):
    scored = []
    for index, vertex in enumerate(vertices):
        try:
            _, _, _, distance = tree.find_nearest(vertex)
        except RuntimeError:
            continue
        if distance is not None:
            scored.append((distance, index))
    scored.sort()
    return [index for _, index in scored[:count]]


def main():
    scene = bpy.context.scene
    if scene["status"] != "research_anatomy_bone_motion_only":
        raise AssertionError(f"unexpected scene status {scene['status']!r}")
    frames = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"]
    if len(frames) != scene.frame_end:
        raise AssertionError("lookup frame count differs from the scene")
    for name in (FIBULA, TIBIA, FEMUR):
        if name not in bpy.data.objects:
            raise AssertionError(f"the scene has no {name}")

    standing_body = body_matrix(frames[0]["blenderBodyFrames"][BODY])

    scene.frame_set(1)
    fibula_vertices, fibula_polygons = evaluated_geometry(bpy.data.objects[FIBULA])
    tibia_vertices, tibia_polygons = evaluated_geometry(bpy.data.objects[TIBIA])
    femur_vertices, femur_polygons = evaluated_geometry(bpy.data.objects[FEMUR])
    tibia_tree = tree_from(tibia_vertices, tibia_polygons)
    femur_tree = tree_from(femur_vertices, femur_polygons)
    femur_seat = nearest_indices(femur_tree, fibula_vertices, SEAT_VERTICES)
    tibia_seat = nearest_indices(tibia_tree, fibula_vertices, SEAT_VERTICES)
    fibula_standing = numpy.array([[vertex.x, vertex.y, vertex.z, 1.0] for vertex in fibula_vertices])

    cached = []
    for number in range(1, scene.frame_end + 1):
        scene.frame_set(number)
        frame = frames[number - 1]
        femur = evaluated_geometry(bpy.data.objects[FEMUR])
        tibia = evaluated_geometry(bpy.data.objects[TIBIA])
        motion = body_matrix(frame["blenderBodyFrames"][BODY]) @ standing_body.inverted()
        cached.append({
            "frame": number,
            "femurTree": tree_from(*femur),
            "tibiaTree": tree_from(*tibia),
            "motion": numpy_matrix(motion),
        })
    search_cache = cached[::max(1, args.search_stride)]

    def evaluate(offset, subset, keep_frames, seats):
        points = fibula_standing @ numpy_matrix(Matrix.Translation(offset)).T
        femur_frames = 0
        tibia_frames = 0
        maximum_femur = 0.0
        maximum_tibia = 0.0
        depth_sum = 0.0
        femur_seat_sum = 0.0
        tibia_seat_sum = 0.0
        per_frame = []
        for item in subset:
            effective = item["motion"]
            moved = points @ effective.T
            moved_vectors = [Vector(row[:3]) for row in moved]
            tree = tree_from(moved_vectors, fibula_polygons)
            femur_depth = 0.0
            tibia_depth = 0.0
            femur_overlap = item["femurTree"].overlap(tree)
            if femur_overlap:
                femur_frames += 1
                femur_depth = penetration(item["femurTree"], moved_vectors, fibula_polygons,
                                          {pair[1] for pair in femur_overlap})
                maximum_femur = max(maximum_femur, femur_depth)
                depth_sum += femur_depth
            tibia_overlap = item["tibiaTree"].overlap(tree)
            if tibia_overlap:
                tibia_frames += 1
                tibia_depth = penetration(item["tibiaTree"], moved_vectors, fibula_polygons,
                                          {pair[1] for pair in tibia_overlap})
                maximum_tibia = max(maximum_tibia, tibia_depth)
                depth_sum += tibia_depth
            femur_seat_sum += seat_distance(item["femurTree"], moved_vectors, femur_seat)
            tibia_seat_sum += seat_distance(item["tibiaTree"], moved_vectors, tibia_seat)
            if keep_frames:
                per_frame.append({"frame": item["frame"], "femurFibulaDepthM": round(femur_depth, 5),
                                  "tibiaFibulaDepthM": round(tibia_depth, 5)})
        counted = len(subset)
        mean_femur_seat = femur_seat_sum / counted
        mean_tibia_seat = tibia_seat_sum / counted
        seat_penalty = abs(mean_femur_seat - seats[0]) + abs(mean_tibia_seat - seats[1])
        result = {
            "cost": depth_sum + args.penalty_weight * seat_penalty,
            "framesInCost": counted,
            "femurFibulaFrames": femur_frames,
            "tibiaFibulaFrames": tibia_frames,
            "maximumFemurFibulaDepthM": round(maximum_femur, 5),
            "maximumTibiaFibulaDepthM": round(maximum_tibia, 5),
            "depthSumM": round(depth_sum, 5),
            "meanFemurSeatDistanceM": round(mean_femur_seat, 5),
            "meanTibiaSeatDistanceM": round(mean_tibia_seat, 5),
            "offsetM": [round(value, 5) for value in offset],
            "offsetMagnitudeM": round(offset.length, 5),
        }
        if keep_frames:
            result["perFrame"] = per_frame
        return result

    started = time.time()
    raw_baseline = evaluate(Vector((0.0, 0.0, 0.0)), cached, True, (0.0, 0.0))
    seats = (raw_baseline["meanFemurSeatDistanceM"], raw_baseline["meanTibiaSeatDistanceM"])
    baseline = evaluate(Vector((0.0, 0.0, 0.0)), cached, True, seats)
    best = evaluate(Vector((0.0, 0.0, 0.0)), search_cache, False, seats)
    best_offset = Vector((0.0, 0.0, 0.0))
    step = START_STEP_M
    evaluations = 2
    trace = []
    axes = [Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))]
    while step >= MIN_STEP_M and evaluations < args.max_evaluations:
        improved = False
        for axis in axes:
            for direction in (1, -1):
                if evaluations >= args.max_evaluations:
                    break
                candidate = best_offset + axis * (direction * step)
                if candidate.length > args.bounds_m:
                    continue
                result = evaluate(candidate, search_cache, False, seats)
                evaluations += 1
                if result["cost"] < best["cost"] - 1e-9:
                    best = result
                    best_offset = candidate
                    improved = True
                    trace.append({"stepM": step, "offsetM": result["offsetM"],
                                  "cost": round(result["cost"], 6),
                                  "femurFibulaFrames": result["femurFibulaFrames"]})
        if not improved:
            step /= 2.0
    optimised = evaluate(best_offset, cached, True, seats)
    elapsed = time.time() - started

    report = {
        "status": "research_only_fibula_registration_search",
        "scene": SCENE,
        "source": "public/data/squat_opensim_reference.json",
        "framesChecked": len(cached),
        "searchedObject": FIBULA,
        "searchedBody": BODY,
        "offsetFrame": "standing world frame, applied before the body motion, as the Blender animator "
                       "and the phone layer already apply the shared registration",
        "cost": "summed femur-to-fibula and tibia-to-fibula penetration depth plus "
                f"{args.penalty_weight} x the deviation of the mean fibula-to-femur and "
                "fibula-to-tibia seat distances from the baseline",
        "searchBoundsM": args.bounds_m,
        "evaluations": evaluations,
        "elapsedSeconds": round(elapsed, 1),
        "trace": trace[-30:],
        "baseline": baseline,
        "optimised": optimised,
        "limitations": [
            "the offset is a single constant, so the fibula cannot follow the ankle through the movement",
            "it is a registration constant, not an attachment, landmark fit or joint model; the fibula "
            "keeps the shared bounding-box registration for everything except this offset",
            "the search scores a strided subset of frames; the reported figures are recomputed on all "
            "101 frames",
            "the seat penalties use one arbitrary weight and the 150 nearest vertices each; the "
            "reported per-part figures should be read instead of the cost alone",
            "penetration is measured between rigid vertex meshes with no cartilage, and the "
            "fibula-to-tibia pair already intersects at standing, so a residual contact there may be "
            "anatomical rather than an error",
            "one subject, right side, standing bounding-box registration, 101 frames of one squat",
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BLENDER_FIBULA_REGISTRATION_SEARCH_OK",
          json.dumps({"offsetM": optimised["offsetM"],
                      "offsetMagnitudeM": optimised["offsetMagnitudeM"],
                      "evaluations": evaluations, "elapsedSeconds": round(elapsed, 1),
                      "baseline": {key: baseline[key] for key in
                                   ("femurFibulaFrames", "tibiaFibulaFrames",
                                    "maximumFemurFibulaDepthM", "maximumTibiaFibulaDepthM",
                                    "meanFemurSeatDistanceM", "meanTibiaSeatDistanceM")},
                      "optimised": {key: optimised[key] for key in
                                    ("femurFibulaFrames", "tibiaFibulaFrames",
                                     "maximumFemurFibulaDepthM", "maximumTibiaFibulaDepthM",
                                     "meanFemurSeatDistanceM", "meanTibiaSeatDistanceM")}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
