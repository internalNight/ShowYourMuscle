"""Search for a per-bone standing offset that keeps the atlas patella out of the femur.

The integrity audit found the patella mesh overlapping the femur mesh in 87 of 101 squat frames, and
the joint-clearance probe found that neither opening the tibial gap nor pushing the patella outwards
along a single direction fixes it. Every registered bone currently shares one standing bounding-box
translation, so the natural next question is whether a *per-bone* offset can do better.

This probe caches the deformed geometry once per frame and then evaluates candidate constants without
re-opening the scene: a candidate shifts the standing mesh by a world-frame vector before the body
motion, which is exactly the form both the Blender animator and the phone layer already use. The cost
is the summed femoral and tibial penetration plus a small penalty on the patella drifting away from
the femur, so the search cannot "fix" the overlap by flying off. No scene is modified.

Run as: blender --background assets/blender/opensim_eight_muscle_motion.blend \
            --python-exit-code 1 --python blender/optimise_patella_registration.py \
            [-- --report docs/data/patella_registration_optimisation.json]
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REPORT = ROOT / "docs/data/patella_registration_optimisation.json"
PATELLA = "atlas_Patella.r"
FEMUR = "atlas_Femur.r"
TIBIA = "atlas_Tibia.r"
BODY = "patella_r"
START_STEP_M = 0.006
MIN_STEP_M = 0.0005
BOUNDS_M = 0.035
DRIFT_WEIGHT = 0.02

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, default=REPORT)
args = parser.parse_args(argv)
report_path = args.report if args.report.is_absolute() else ROOT / args.report


def body_matrix(data):
    result = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            result[row][col] = data["rotationRows"][row][col]
    result.translation = Vector(data["translationM"])
    return result


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


def surface_distance(tree, vertices):
    """Smallest distance from the patella's vertices to the partner surface."""
    best = float("inf")
    for vertex in vertices:
        try:
            _, _, _, distance = tree.find_nearest(vertex)
        except RuntimeError:
            continue
        if distance is not None:
            best = min(best, distance)
    return best


def main():
    scene = bpy.context.scene
    if scene["status"] != "research_eight_muscle_deformations_only":
        raise AssertionError(f"unexpected scene status {scene['status']!r}")
    frames = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"]
    if len(frames) != scene.frame_end:
        raise AssertionError("lookup frame count differs from the scene")
    for name in (PATELLA, FEMUR, TIBIA):
        if name not in bpy.data.objects:
            raise AssertionError(f"the scene has no {name}")

    standing_body = body_matrix(frames[0]["blenderBodyFrames"][BODY])
    standing_inverse = standing_body.inverted()

    # Cache every frame once: the deformed patella vertices and the rotation that carries a
    # standing-frame offset into that frame, plus the two partner surfaces it must clear.
    cached = []
    for number in range(1, scene.frame_end + 1):
        scene.frame_set(number)
        frame = frames[number - 1]
        patella = evaluated_geometry(bpy.data.objects[PATELLA])
        femur = evaluated_geometry(bpy.data.objects[FEMUR])
        tibia = evaluated_geometry(bpy.data.objects[TIBIA])
        transform = body_matrix(frame["blenderBodyFrames"][BODY]) @ standing_inverse
        cached.append({
            "frame": number,
            "patella": patella,
            "femurTree": tree_from(*femur),
            "tibiaTree": tree_from(*tibia),
            "rotation": transform.to_3x3(),
        })

    femur_polygons = evaluated_geometry(bpy.data.objects[FEMUR])[1]
    patella_polygons = evaluated_geometry(bpy.data.objects[PATELLA])[1]

    def evaluate(offset):
        femur_frames = 0
        patella_frames_with_femur = 0
        tibia_frames = 0
        maximum_femur = 0.0
        maximum_tibia = 0.0
        distances = []
        depth_sum = 0.0
        for item in cached:
            moved = [vertex + item["rotation"] @ offset for vertex in item["patella"][0]]
            tree = tree_from(moved, patella_polygons)
            femur_overlap = item["femurTree"].overlap(tree)
            tibia_overlap = item["tibiaTree"].overlap(tree)
            if femur_overlap:
                femur_frames += 1
                depth = penetration(item["femurTree"], moved, patella_polygons,
                                    {pair[1] for pair in femur_overlap})
                depth_sum += depth
                maximum_femur = max(maximum_femur, depth)
            if tibia_overlap:
                tibia_frames += 1
                depth = penetration(item["tibiaTree"], moved, patella_polygons,
                                    {pair[1] for pair in tibia_overlap})
                depth_sum += depth
                maximum_tibia = max(maximum_tibia, depth)
            if not femur_overlap:
                distances.append(surface_distance(item["femurTree"], moved))
        distances.sort()
        median = distances[len(distances) // 2] if distances else 0.0
        cost = depth_sum + DRIFT_WEIGHT * sum(distances)
        return {
            "cost": cost,
            "femurPatellaFrames": femur_frames,
            "patellaTibiaFrames": tibia_frames,
            "maximumFemurDepthM": round(maximum_femur, 5),
            "maximumTibiaDepthM": round(maximum_tibia, 5),
            "medianFemurDistanceM": round(median, 5),
            "maximumFemurDistanceM": round(max(distances), 5) if distances else None,
            "offsetM": [round(value, 5) for value in offset],
            "offsetMagnitudeM": round(offset.length, 5),
        }

    baseline = evaluate(Vector((0.0, 0.0, 0.0)))
    best = baseline
    best_offset = Vector((0.0, 0.0, 0.0))
    step = START_STEP_M
    evaluations = 1
    trace = []
    axes = [Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))]
    while step >= MIN_STEP_M:
        improved = False
        for axis in axes:
            for direction in (1, -1):
                candidate = best_offset + axis * (direction * step)
                if candidate.length > BOUNDS_M:
                    continue
                result = evaluate(candidate)
                evaluations += 1
                if result["cost"] < best["cost"] - 1e-9:
                    best = result
                    best_offset = candidate
                    improved = True
                    trace.append({"stepM": step, "offsetM": result["offsetM"],
                                  "cost": round(result["cost"], 6)})
        if not improved:
            step /= 2.0

    report = {
        "status": "research_only_patella_registration_search",
        "scene": "assets/blender/opensim_eight_muscle_motion.blend",
        "source": "public/data/squat_opensim_reference.json",
        "framesChecked": scene.frame_end,
        "searchedObject": PATELLA,
        "searchedBody": BODY,
        "offsetFrame": "standing world frame, applied before the body motion, as the Blender "
                       "animator and the phone layer already apply the shared registration",
        "cost": "summed femoral and tibial penetration depth plus "
                f"{DRIFT_WEIGHT} x the summed patella-to-femur surface distance",
        "searchBoundsM": BOUNDS_M,
        "evaluations": evaluations,
        "trace": trace,
        "baseline": baseline,
        "optimised": best,
        "limitations": [
            "the offset is a single constant, so it cannot follow the patella through the movement",
            "it is a registration constant, not an attachment, landmark fit or joint model; the "
            "patella keeps the shared bounding-box registration for everything except this offset",
            "the cost balances penetration against drift with one arbitrary weight, and the reported "
            "per-part figures should be read instead of the cost alone",
            "only the patella was searched; the femur-to-tibia overlap is a hinge-and-cartilage "
            "problem that a rigid offset of one mesh does not describe",
            "vertices only: no surface fitting, no cartilage, no contact model, one subject, right "
            "side, standing registration",
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BLENDER_PATELLA_REGISTRATION_SEARCH_OK",
          json.dumps({"offsetM": best["offsetM"], "evaluations": evaluations,
                      "baseline": {key: baseline[key] for key in
                                   ("femurPatellaFrames", "maximumFemurDepthM",
                                    "patellaTibiaFrames", "medianFemurDistanceM")},
                      "optimised": {key: best[key] for key in
                                    ("femurPatellaFrames", "maximumFemurDepthM",
                                     "patellaTibiaFrames", "medianFemurDistanceM")}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
