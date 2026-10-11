"""Search for a per-bone knee registration correction for the tibia (and its fibula).

Round 11 ruled out opening the joint gap, and round 12 fixed the patella with a constant standing
offset. The remaining defect is the big one: the femur mesh and the tibia mesh overlap in 97 of the 101
squat frames. Both are placed by rotating an OpenSim body frame, so the mesh sweeps about whichever
point that motion rotates about. This probe asks whether any *constant* per-bone correction can clear
that overlap, and reports the whole frontier instead of one fitted point:

  * translation only          - the patella recipe
  * pivot only                - rotate about a shifted centre, i.e. A(f) plus (I - R(f)) d
  * pivot + translation       - both knobs
  * pivot + translation + tilt

The cost counts penetration between the tibia group and the femur, the fibula and the femur, and the
tibia and the calcaneus, plus a weighted deviation of the knee-seat and ankle-seat distances from the
baseline, so a configuration cannot win by pressing the tibia into the femur, into the foot, or by
letting the ankle drift. Nothing is written back into the scene.

Run as: blender --background assets/blender/opensim_anatomy_bone_motion.blend \
            --python-exit-code 1 --python blender/optimise_knee_registration.py \
            [-- --report docs/data/knee_registration_optimisation.json]
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
REPORT = ROOT / "docs/data/knee_registration_optimisation.json"
SCENE = "assets/blender/opensim_anatomy_bone_motion.blend"
TIBIA = "atlas_Tibia.r"
FIBULA = "atlas_Fibula.r"
FEMUR = "atlas_Femur.r"
CALCN = "atlas_Calcaneus.r"
BODY = "tibia_r"
SEAT_VERTICES = 200
START_STEP_M = 0.005
MIN_STEP_M = 0.0004
BOUNDS_M = 0.03
START_STEP_RAD = 0.026
MIN_STEP_RAD = 0.003
BOUNDS_RAD = 0.14
PENALTY_WEIGHT = 5.0
CONFIGURATIONS = (
    {"label": "translation only", "stage": "offset", "boundsM": 0.025, "boundsRad": 0.0,
     "penaltyWeight": 5.0, "maxEvaluations": 600},
    {"label": "pivot only", "stage": "pivot", "boundsM": 0.06, "boundsRad": 0.0,
     "penaltyWeight": 5.0, "maxEvaluations": 900},
    {"label": "pivot plus translation", "stage": "pivot+offset", "boundsM": 0.06, "boundsRad": 0.0,
     "penaltyWeight": 5.0, "maxEvaluations": 1400},
    {"label": "pivot plus translation plus tilt", "stage": "pivot+offset+tilt", "boundsM": 0.06,
     "boundsRad": 0.2, "penaltyWeight": 5.0, "maxEvaluations": 2000},
)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, default=REPORT)
parser.add_argument("--stage", choices=("offset", "pivot", "pivot+offset", "pivot+offset+tilt"),
                    default="pivot+offset")
parser.add_argument("--single", action="store_true",
                    help="run only --stage instead of the four-configuration sweep")
parser.add_argument("--search-stride", type=int, default=3)
parser.add_argument("--max-evaluations", type=int, default=1400)
parser.add_argument("--bounds-m", type=float, default=BOUNDS_M)
parser.add_argument("--bounds-rad", type=float, default=BOUNDS_RAD)
parser.add_argument("--penalty-weight", type=float, default=PENALTY_WEIGHT)
parser.add_argument("--start-step-m", type=float, default=START_STEP_M)
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
    """Mean distance from a seat vertex subset to a partner surface."""
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


def region_centroid(vertices, indices):
    centre = Vector((0.0, 0.0, 0.0))
    for index in indices:
        centre += vertices[index]
    return centre / len(indices)


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


SUMMARY_KEYS = ("femurTibiaFrames", "femurFibulaFrames", "tibiaCalcaneusFrames",
                "maximumFemurTibiaDepthM", "maximumFemurFibulaDepthM", "maximumTibiaCalcaneusDepthM",
                "depthSumM", "meanKneeSeatDistanceM", "meanAnkleSeatDistanceM")


def summarise(result):
    return {key: result[key] for key in SUMMARY_KEYS}


def main():
    scene = bpy.context.scene
    if scene["status"] != "research_anatomy_bone_motion_only":
        raise AssertionError(f"unexpected scene status {scene['status']!r}")
    frames = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"]
    if len(frames) != scene.frame_end:
        raise AssertionError("lookup frame count differs from the scene")
    for name in (TIBIA, FIBULA, FEMUR, CALCN):
        if name not in bpy.data.objects:
            raise AssertionError(f"the scene has no {name}")

    standing_body = body_matrix(frames[0]["blenderBodyFrames"][BODY])

    scene.frame_set(1)
    tibia_vertices, tibia_polygons = evaluated_geometry(bpy.data.objects[TIBIA])
    fibula_vertices, fibula_polygons = evaluated_geometry(bpy.data.objects[FIBULA])
    femur_vertices, femur_polygons = evaluated_geometry(bpy.data.objects[FEMUR])
    calcn_vertices, calcn_polygons = evaluated_geometry(bpy.data.objects[CALCN])
    femur_tree = tree_from(femur_vertices, femur_polygons)
    calcn_tree = tree_from(calcn_vertices, calcn_polygons)
    knee_seat = nearest_indices(femur_tree, tibia_vertices, SEAT_VERTICES)
    ankle_seat = nearest_indices(calcn_tree, tibia_vertices, SEAT_VERTICES)
    tibia_standing = numpy.array([[vertex.x, vertex.y, vertex.z, 1.0] for vertex in tibia_vertices])
    fibula_standing = numpy.array([[vertex.x, vertex.y, vertex.z, 1.0] for vertex in fibula_vertices])
    pivot = region_centroid(tibia_vertices, knee_seat)

    cached = []
    for number in range(1, scene.frame_end + 1):
        scene.frame_set(number)
        frame = frames[number - 1]
        femur = evaluated_geometry(bpy.data.objects[FEMUR])
        calcn = evaluated_geometry(bpy.data.objects[CALCN])
        motion = body_matrix(frame["blenderBodyFrames"][BODY]) @ standing_body.inverted()
        cached.append({
            "frame": number,
            "femurTree": tree_from(*femur),
            "calcnTree": tree_from(*calcn),
            "motion": numpy_matrix(motion),
        })
    search_cache = cached[::max(1, args.search_stride)]

    def build_stage(stage, penalty_weight):
        # Every stage is a point in one nine-slot vector, so a configuration only searches the slots
        # it owns and the others stay at zero.
        active = {
            "offset": [3, 4, 5],
            "pivot": [0, 1, 2],
            "pivot+offset": [0, 1, 2, 3, 4, 5],
            "pivot+offset+tilt": [0, 1, 2, 3, 4, 5, 6, 7, 8],
        }[stage]
        offset_count = 1 if 3 in active else 0
        tilt_count = 1 if 6 in active else 0

        def unpack(values):
            pivot_shift = Vector(values[0:3])
            offset = Vector(values[3:6]) if offset_count else Vector((0.0, 0.0, 0.0))
            tilt = Vector(values[6:9]) if tilt_count else Vector((0.0, 0.0, 0.0))
            return pivot_shift, offset, tilt

        def shape(values):
            """Standing-frame transform of the tibia group, and the pivot shift in the same frame."""
            pivot_shift, offset, tilt = unpack(values)
            standing = Matrix.Identity(4)
            if tilt_count:
                rotation = (Matrix.Rotation(tilt.x, 4, "X") @ Matrix.Rotation(tilt.y, 4, "Y")
                            @ Matrix.Rotation(tilt.z, 4, "Z"))
                standing = Matrix.Translation(pivot) @ rotation @ Matrix.Translation(-pivot)
            if offset_count:
                standing = Matrix.Translation(offset) @ standing
            return numpy_matrix(standing), numpy.array([pivot_shift.x, pivot_shift.y, pivot_shift.z])

        def evaluate(values, subset, keep_frames, seats):
            standing, shift = shape(values)
            tibia_points = tibia_standing @ standing.T
            fibula_points = fibula_standing @ standing.T
            counters = {"femurTibia": 0, "femurFibula": 0, "tibiaCalcaneus": 0}
            maxima = {"femurTibia": 0.0, "femurFibula": 0.0, "tibiaCalcaneus": 0.0}
            depth_sum = 0.0
            knee_seat_sum = 0.0
            ankle_seat_sum = 0.0
            per_frame = []
            for item in subset:
                motion = item["motion"]
                rotation = motion[:3, :3]
                # Rotating about the registered pivot instead of the body origin adds (I - R(f)) d.
                effective = numpy.identity(4)
                effective[:3, :3] = rotation
                effective[:3, 3] = motion[:3, 3] + (shift - rotation @ shift)
                moved = tibia_points @ effective.T
                moved_fibula = fibula_points @ effective.T
                moved_vectors = [Vector(row[:3]) for row in moved]
                moved_fibula_vectors = [Vector(row[:3]) for row in moved_fibula]
                tree = tree_from(moved_vectors, tibia_polygons)
                fibula_tree = tree_from(moved_fibula_vectors, fibula_polygons)
                depths = {}
                for partner, partner_tree, vertices, polygons, counter, maximum in (
                        ("femurTibia", item["femurTree"], moved_vectors, tibia_polygons,
                         "femurTibia", "femurTibia"),
                        ("femurFibula", item["femurTree"], moved_fibula_vectors, fibula_polygons,
                         "femurFibula", "femurFibula"),
                        ("tibiaCalcaneus", item["calcnTree"], moved_vectors, tibia_polygons,
                         "tibiaCalcaneus", "tibiaCalcaneus")):
                    overlap = partner_tree.overlap(fibula_tree if partner == "femurFibula" else tree)
                    depth = 0.0
                    if overlap:
                        counters[counter] += 1
                        depth = penetration(partner_tree, vertices, polygons,
                                            {pair[1] for pair in overlap})
                        maxima[maximum] = max(maxima[maximum], depth)
                        depth_sum += depth
                    depths[partner] = depth
                knee_seat_sum += seat_distance(item["femurTree"], moved_vectors, knee_seat)
                ankle_seat_sum += seat_distance(item["calcnTree"], moved_vectors, ankle_seat)
                if keep_frames:
                    per_frame.append({"frame": item["frame"],
                                      "femurTibiaDepthM": round(depths["femurTibia"], 5),
                                      "femurFibulaDepthM": round(depths["femurFibula"], 5),
                                      "tibiaCalcaneusDepthM": round(depths["tibiaCalcaneus"], 5)})
            counted = len(subset)
            mean_knee = knee_seat_sum / counted
            mean_ankle = ankle_seat_sum / counted
            seat_penalty = abs(mean_knee - seats[0]) + abs(mean_ankle - seats[1])
            result = {
                "cost": depth_sum + penalty_weight * seat_penalty,
                "framesInCost": counted,
                "femurTibiaFrames": counters["femurTibia"],
                "femurFibulaFrames": counters["femurFibula"],
                "tibiaCalcaneusFrames": counters["tibiaCalcaneus"],
                "maximumFemurTibiaDepthM": round(maxima["femurTibia"], 5),
                "maximumFemurFibulaDepthM": round(maxima["femurFibula"], 5),
                "maximumTibiaCalcaneusDepthM": round(maxima["tibiaCalcaneus"], 5),
                "depthSumM": round(depth_sum, 5),
                "meanKneeSeatDistanceM": round(mean_knee, 5),
                "meanAnkleSeatDistanceM": round(mean_ankle, 5),
                "pivotShiftM": [round(value, 5) for value in values[0:3]],
                "offsetM": [round(value, 5) for value in values[3:6]] if offset_count else None,
                "tiltRad": [round(value, 5) for value in values[6:9]] if tilt_count else None,
            }
            if keep_frames:
                result["perFrame"] = per_frame
            return result

        return {"active": active, "evaluate": evaluate, "unpack": unpack}

    SLOTS = ["pivotX", "pivotY", "pivotZ", "offsetX", "offsetY", "offsetZ", "tiltX", "tiltY", "tiltZ"]

    started = time.time()
    zero = [0.0] * len(SLOTS)
    baseline_stage = build_stage("offset", PENALTY_WEIGHT)
    raw_baseline = baseline_stage["evaluate"](zero, cached, True, (0.0, 0.0))
    seats = (raw_baseline["meanKneeSeatDistanceM"], raw_baseline["meanAnkleSeatDistanceM"])
    baseline = baseline_stage["evaluate"](zero, cached, True, seats)
    baseline_cost_small = baseline_stage["evaluate"](zero, search_cache, False, seats)

    def run_configuration(configuration):
        stage = build_stage(configuration["stage"], configuration["penaltyWeight"])
        active = stage["active"]
        slope_m = [args.start_step_m if slot < 6 else START_STEP_RAD for slot in active]
        minimums = [MIN_STEP_M if slot < 6 else MIN_STEP_RAD for slot in active]
        bounds = [configuration["boundsM"] if slot < 6 else configuration["boundsRad"]
                  for slot in active]
        best_values = list(zero)
        best_small = stage["evaluate"](best_values, search_cache, False, seats)
        if configuration["stage"] == "offset":
            best_small = dict(best_small, cost=baseline_cost_small["cost"])
        evaluations = 1
        trace = []
        active_search = True
        while active_search and evaluations < configuration["maxEvaluations"]:
            improved = False
            for position, slot in enumerate(active):
                if evaluations >= configuration["maxEvaluations"]:
                    break
                for direction in (1, -1):
                    if evaluations >= configuration["maxEvaluations"]:
                        break
                    candidate = list(best_values)
                    candidate[slot] = candidate[slot] + direction * slope_m[position]
                    if abs(candidate[slot]) > bounds[position]:
                        continue
                    result = stage["evaluate"](candidate, search_cache, False, seats)
                    evaluations += 1
                    if result["cost"] < best_small["cost"] - 1e-9:
                        best_small = result
                        best_values = candidate
                        improved = True
                        trace.append({"parameter": SLOTS[slot],
                                      "value": round(candidate[slot], 5),
                                      "cost": round(result["cost"], 6),
                                      "femurTibiaFrames": result["femurTibiaFrames"]})
            if not improved:
                slope_m = [step / 2.0 for step in slope_m]
                if all(step < minimum for step, minimum in zip(slope_m, minimums)):
                    active_search = False
        full = stage["evaluate"](best_values, cached, True, seats)
        pivot_shift, offset, tilt = stage["unpack"](best_values)
        at_bound = [SLOTS[slot] for position, slot in enumerate(active)
                    if abs(abs(best_values[slot]) - bounds[position]) < 1e-6]
        return {
            "label": configuration["label"],
            "stage": configuration["stage"],
            "boundsM": configuration["boundsM"],
            "boundsRad": configuration["boundsRad"],
            "penaltyWeight": configuration["penaltyWeight"],
            "evaluations": evaluations,
            "parametersAtBound": at_bound,
            "pivotShiftM": [round(value, 5) for value in pivot_shift],
            "offsetM": [round(value, 5) for value in offset] if 3 in active else None,
            "tiltRad": [round(value, 5) for value in tilt] if 6 in active else None,
            "optimised": full,
            "trace": trace[-20:],
        }

    configurations = ([{"label": args.stage, "stage": args.stage, "boundsM": args.bounds_m,
                        "boundsRad": args.bounds_rad, "penaltyWeight": args.penalty_weight,
                        "maxEvaluations": args.max_evaluations}]
                      if args.single else [dict(item) for item in CONFIGURATIONS])
    results = [run_configuration(configuration) for configuration in configurations]
    elapsed = time.time() - started

    best = min(results, key=lambda item: (item["optimised"]["femurTibiaFrames"],
                                          item["optimised"]["depthSumM"]))

    # Why no constant can be right: the motion the animator applies per frame is a screw motion, not a
    # rotation about the knee. Solve its axis and compare that axis with the standing knee seat.
    centre_records = []
    for item in cached:
        motion = item["motion"]
        rotation = motion[:3, :3]
        translation = motion[:3, 3]
        cosine = max(-1.0, min(1.0, (float(numpy.trace(rotation)) - 1.0) / 2.0))
        angle = float(numpy.arccos(cosine))
        if angle < 0.05:
            continue
        axis = numpy.array([rotation[2, 1] - rotation[1, 2],
                            rotation[0, 2] - rotation[2, 0],
                            rotation[1, 0] - rotation[0, 1]]) / (2.0 * numpy.sin(angle))
        parallel = float(numpy.dot(axis, translation))
        perpendicular = translation - parallel * axis
        point = 0.5 * perpendicular + numpy.cross(axis, perpendicular) / (2.0 * numpy.tan(angle / 2.0))
        offset_from_axis = (numpy.array([pivot.x, pivot.y, pivot.z]) - point)
        axis_distance = float(numpy.linalg.norm(offset_from_axis
                                                - numpy.dot(offset_from_axis, axis) * axis))
        centre_records.append({
            "frame": item["frame"],
            "relativeRotationDeg": round(angle * 180.0 / 3.141592653589793, 2),
            "screwTranslationM": round(abs(parallel), 5),
            "axisDistanceToKneeSeatM": round(axis_distance, 5),
        })
    distances = sorted(record["axisDistanceToKneeSeatM"] for record in centre_records)
    slides = sorted(record["screwTranslationM"] for record in centre_records)
    significant = [record for record in centre_records if record["relativeRotationDeg"] > 10.0]
    significant_distances = sorted(record["axisDistanceToKneeSeatM"] for record in significant)
    significant_slides = sorted(record["screwTranslationM"] for record in significant)
    diagnostic = {
        "note": "each frame's body motion B(f) B(1)^-1 is a screw motion; this solves its axis and "
                "reports how far that axis sits from the standing knee-seat centroid, plus how far the "
                "motion slides along its own axis. A constant pivot shift moves every frame's centre by "
                "the same vector, so it cannot follow an axis that wanders or a real translation",
        "kneeSeatCentroidM": [round(value, 5) for value in pivot],
        "framesSolved": len(centre_records),
        "framesWithRotationOver10Deg": len(significant),
        "medianAxisDistanceToKneeSeatM": round(significant_distances[len(significant_distances) // 2], 5)
        if significant_distances else None,
        "minimumAxisDistanceToKneeSeatM": round(significant_distances[0], 5) if significant_distances else None,
        "maximumAxisDistanceToKneeSeatM": round(significant_distances[-1], 5)
        if significant_distances else None,
        "medianScrewTranslationM": round(significant_slides[len(significant_slides) // 2], 5)
        if significant_slides else None,
        "maximumScrewTranslationM": round(significant_slides[-1], 5) if significant_slides else None,
        "medianAxisDistanceAllFramesM": round(distances[len(distances) // 2], 5) if distances else None,
    }

    report = {
        "status": "research_only_knee_registration_search",
        "scene": SCENE,
        "source": "public/data/squat_opensim_reference.json",
        "framesChecked": len(cached),
        "searchedObjects": [TIBIA, FIBULA],
        "searchedBody": BODY,
        "pivotFrame": "standing world frame; the body origin motion is rotated about a registered "
                      "point shifted by d, which adds the angle-dependent translation (I - R(f)) d",
        "cost": "summed femur-to-tibia, femur-to-fibula and tibia-to-calcaneus penetration depth plus "
                "the penalty weight times the deviation of the mean knee-seat and ankle-seat distances "
                "from the baseline (seat vertices: the 200 tibia vertices nearest each partner)",
        "searchStride": max(1, args.search_stride),
        "baseline": baseline,
        "effectiveRotationCentre": diagnostic,
        "configurations": results,
        "optimised": {key: value for key, value in best.items() if key != "trace"},
        "bestConfiguration": best["label"],
        "elapsedSeconds": round(elapsed, 1),
        "limitations": [
            "every configuration returns constants: a pivot shift can follow the flexion angle, but "
            "nothing here fits a joint centre per frame, adds cartilage or models contact",
            "the fibula shares the tibia body frame, so it can only receive the same correction",
            "the search scores a strided subset of frames; the reported figures are recomputed on all "
            "101 frames",
            "the seat penalties use one arbitrary weight and 200 nearest vertices each; the reported "
            "per-part figures should be read instead of the cost alone",
            "penetration is measured between rigid vertex meshes with no cartilage, so a small "
            "residual contact may be anatomical rather than an error",
            "one subject, right side, standing bounding-box registration, 101 frames of one squat",
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BLENDER_KNEE_REGISTRATION_SEARCH_OK",
          json.dumps({"bestConfiguration": best["label"],
                      "elapsedSeconds": round(elapsed, 1),
                      "effectiveRotationCentre": diagnostic,
                      "baseline": summarise(baseline),
                      "configurations": [{"label": item["label"], "evaluations": item["evaluations"],
                                          "pivotShiftM": item["pivotShiftM"], "offsetM": item["offsetM"],
                                          "tiltRad": item["tiltRad"],
                                          "parametersAtBound": item["parametersAtBound"],
                                          "optimised": summarise(item["optimised"])}
                                         for item in results]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
