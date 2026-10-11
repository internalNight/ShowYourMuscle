"""Integrity audit of the squat research layer's deformed meshes, on every frame.

Stage 1 of the roadmap asks that muscle paths stay synchronised with the bones during motion
"without interpenetration or wrong flips", but the existing mesh-motion checks only sample five
frames and only compare local edge lengths. This audit covers all 101 frames of the eight-muscle
scene and measures the three things that criterion needs:

1. edge distortion, as the ratio of every deformed edge to its standing length;
2. face flips, as the angle between each face normal and the same face's normal carried by the
   rigid body motion of that muscle's bone (a flip is a reversal relative to the bone, not to the
   world, because the whole limb legitimately rotates);
3. interpenetration, as triangle-pair intersections between the deformed muscle meshes themselves
   and between each muscle mesh and the registered bone meshes. Pairs that already intersect in the
   scene's first frame are treated as the reference state, so what is reported is the penetration
   the deformation *adds*, which is what a coarse bounding-box registration can plausibly get wrong.

Research only: this measures geometry of a heuristic deformation, not anatomy, attachment sites or
force.

Run as: blender --background assets/blender/opensim_eight_muscle_motion.blend \
            --python-exit-code 1 --python blender/audit_registered_mesh_integrity.py \
            [-- --report docs/data/registered_mesh_integrity_audit.json]
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
REPORT = ROOT / "docs/data/registered_mesh_integrity_audit.json"
REFERENCE_FRAME = 1
EDGE_GATE = (0.5, 1.5)
BODY_NAMES = {"femur": "femur_r", "tibia": "tibia_r", "pelvis": "pelvis"}
DEGENERATE_AREA = 1e-10

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, default=REPORT)
args = parser.parse_args(argv)
report_path = args.report if args.report.is_absolute() else ROOT / args.report


def body_matrix(data):
    matrix = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            matrix[row][col] = data["rotationRows"][row][col]
    matrix.translation = Vector(data["translationM"])
    return matrix


def rigid_delta(frame, reference, body):
    return (body_matrix(frame["blenderBodyFrames"][body]) @
            body_matrix(reference["blenderBodyFrames"][body]).inverted())


def evaluated_geometry(obj):
    """World-space vertices and polygon index tuples of an object's evaluated mesh."""
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
    return BVHTree.FromPolygons([tuple(vertex) for vertex in vertices], polygons,
                                all_triangles=False)


def face_normal(vertices, polygon):
    return (vertices[polygon[1]] - vertices[polygon[0]]).cross(
        vertices[polygon[2]] - vertices[polygon[0]])


def shared_vertex_members(polygons):
    return [set(polygon) for polygon in polygons]


def self_intersections(tree, members):
    """Face pairs of one mesh that intersect each other but share no vertex."""
    pairs = set()
    for first, second in tree.overlap(tree):
        if first >= second or (members[first] & members[second]):
            continue
        pairs.add((first, second))
    return pairs


def penetration_depth(tree, point):
    try:
        location, normal, _, distance = tree.find_nearest(point)
    except RuntimeError:
        return 0.0
    if location is None or (point - location).dot(normal) >= 0:
        return 0.0
    return distance


def main():
    scene = bpy.context.scene
    if scene["status"] != "research_eight_muscle_deformations_only":
        raise AssertionError(f"unexpected scene status {scene['status']!r}")
    if (scene.frame_start, scene.frame_end) != (REFERENCE_FRAME, 101):
        raise AssertionError(f"unexpected frame range {scene.frame_start}-{scene.frame_end}")

    lookup = json.loads(LOOKUP.read_text(encoding="utf-8"))
    frames = lookup["frames"]
    reference = frames[REFERENCE_FRAME - 1]

    bone_objects = {}
    bone_bodies = {}
    for obj in bpy.data.objects:
        if obj.type == "MESH" and "opensim_body" in obj.keys():
            # Two bone meshes share one OpenSim body (the fibula follows the tibia), so the object
            # name is the key and the body is recorded next to it.
            bone_objects[obj.name] = obj
            bone_bodies[obj.name] = obj["opensim_body"]
    muscle_objects = {}
    muscle_bodies = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or "path_source" not in obj.keys():
            continue
        muscle = obj["path_source"].removeprefix("OpenSim reference ")
        method = obj["method"]
        if not method.startswith("rigid ") or " motion" not in method:
            raise AssertionError(f"{obj.name}: cannot read the driving body from {method!r}")
        word = method[len("rigid "):method.index(" motion")]
        if word not in BODY_NAMES:
            raise AssertionError(f"{obj.name}: unknown driving body {word!r}")
        muscle_objects[muscle] = obj
        muscle_bodies[muscle] = BODY_NAMES[word]
    if len(muscle_objects) != 8:
        raise AssertionError(f"expected eight research muscle meshes, found {len(muscle_objects)}")
    if len(bone_objects) != 6:
        raise AssertionError(f"expected six registered bone meshes, found {len(bone_objects)}")

    # The bones must actually move, or this screen would be measuring a static pose.
    scene.frame_set(REFERENCE_FRAME)
    standing_femur = bone_objects["atlas_Femur.r"].matrix_world.copy()
    scene.frame_set(51)
    moved_femur = bone_objects["atlas_Femur.r"].matrix_world.copy()
    motion = max(abs(standing_femur[row][col] - moved_femur[row][col])
                 for row in range(4) for col in range(4))
    if motion < 0.05:
        raise AssertionError("the registered bones do not move across the squat")

    base_vertices = {}
    reference_normals = {}
    edge_pairs = {}
    polygons_by_muscle = {}
    for muscle, obj in muscle_objects.items():
        keys = obj.data.shape_keys
        if keys is None or len(keys.key_blocks) != 102:
            raise AssertionError(f"{obj.name}: expected 102 shape keys")
        base = [vertex.co.copy() for vertex in keys.key_blocks[0].data]
        polygons = [tuple(polygon.vertices) for polygon in obj.data.polygons]
        if any(len(polygon) < 3 for polygon in polygons):
            raise AssertionError(f"{obj.name}: polygon with fewer than three vertices")
        base_vertices[muscle] = base
        polygons_by_muscle[muscle] = polygons
        reference_normals[muscle] = [face_normal(base, polygon) for polygon in polygons]
        edge_pairs[muscle] = [(edge.vertices[0], edge.vertices[1]) for edge in obj.data.edges]

    def mesh_pairs():
        keys = []
        for first in sorted(muscle_objects):
            keys.append((first, first))
            for second in sorted(muscle_objects):
                if first < second:
                    keys.append((first, second))
            for bone in sorted(bone_objects):
                keys.append((first, bone))
        # Bone-to-bone pairs are the control: near the flexed knee the two bone meshes themselves
        # come together, so some muscle-to-bone overlap is inherited rather than created by the
        # muscle deformation.
        for first in sorted(bone_objects):
            for second in sorted(bone_objects):
                if first < second:
                    keys.append((first, second))
        return keys

    # Reference state: which mesh pairs already intersect in the first frame.
    scene.frame_set(REFERENCE_FRAME)
    reference_trees = {}
    for name, obj in {**muscle_objects, **bone_objects}.items():
        reference_trees[name] = tree_from(*evaluated_geometry(obj))
    baseline_pairs = set()
    baseline_self = {}
    for first, second in mesh_pairs():
        if first == second:
            baseline_self[first] = len(self_intersections(
                reference_trees[first], shared_vertex_members(polygons_by_muscle[first])))
        elif reference_trees[first].overlap(reference_trees[second]):
            baseline_pairs.add((first, second))

    report = {
        "status": "research_only_mesh_integrity_audit",
        "scene": "assets/blender/opensim_eight_muscle_motion.blend",
        "sceneStatus": scene["status"],
        "source": "public/data/squat_opensim_reference.json",
        "sourceModel": scene.get("source_model", ""),
        "framesChecked": scene.frame_end,
        "referenceFrame": REFERENCE_FRAME,
        "edgeRatioGate": list(EDGE_GATE),
        "boneMeshes": {name: body for name, body in sorted(bone_bodies.items())},
        "musclesChecked": {},
        "bonePairIntersections": {},
        "summary": {},
        "limitations": [
            "the deformation is a heuristic rigid-body-plus-endpoint correction, so this screen "
            "tests its geometry, not anatomy, attachment or force",
            "intersections are triangle-pair overlaps of closed surface meshes; they say nothing "
            "about which structure lies outside which",
            "pairs that already intersect in the first frame are taken as the reference state, so "
            "the screen reports added penetration rather than absolute overlap",
            "penetration depth is measured from intersecting face centroids to the other surface "
            "and is therefore an estimate, not a measured overlap volume",
            "flips are judged against each muscle's own rigid body motion; a face that reverses "
            "relative to its neighbours without reversing against the bone is not counted",
            "one standing registration with shared bounding-box centres and one subject's squat, "
            "right side only",
        ],
    }

    added = {}
    for frame_number in range(REFERENCE_FRAME, scene.frame_end + 1):
        scene.frame_set(frame_number)
        frame = frames[frame_number - 1]
        geometries = {}
        trees = {}
        for name, obj in {**muscle_objects, **bone_objects}.items():
            geometries[name] = evaluated_geometry(obj)
            trees[name] = tree_from(*geometries[name])

        for muscle, obj in muscle_objects.items():
            entry = report["musclesChecked"].setdefault(muscle, {
                "object": obj.name,
                "body": muscle_bodies[muscle],
                "vertexCount": len(base_vertices[muscle]),
                "polygonCount": len(polygons_by_muscle[muscle]),
                "edgeRatio": {"minimum": None, "maximum": None, "minimumFrame": None,
                              "edgesBelowGate": 0, "edgesAboveGate": 0},
                "flippedFaces": {"maximumFaces": 0, "frames": []},
                "degenerateFaces": {"maximumFaces": 0, "frames": []},
                "selfIntersections": {"referenceFacePairs": baseline_self[muscle],
                                      "maximumFacePairs": 0, "worstFrame": None,
                                      "framesAboveReference": []},
                "addedIntersections": {},
            })
            polygons = polygons_by_muscle[muscle]
            inverse = obj.matrix_world.inverted()
            local = [inverse @ vertex for vertex in geometries[muscle][0]]
            rotation = rigid_delta(frame, reference, muscle_bodies[muscle]).to_3x3()

            flipped = 0
            degenerate = 0
            for index, polygon in enumerate(polygons):
                normal = face_normal(local, polygon)
                if normal.length < DEGENERATE_AREA:
                    degenerate += 1
                    continue
                carried = rotation @ reference_normals[muscle][index]
                if carried.length < DEGENERATE_AREA:
                    continue
                if normal.normalized().dot(carried.normalized()) < 0:
                    flipped += 1
            if flipped:
                entry["flippedFaces"]["maximumFaces"] = max(
                    entry["flippedFaces"]["maximumFaces"], flipped)
                entry["flippedFaces"]["frames"].append({"frame": frame_number, "faces": flipped})
            if degenerate:
                entry["degenerateFaces"]["maximumFaces"] = max(
                    entry["degenerateFaces"]["maximumFaces"], degenerate)
                entry["degenerateFaces"]["frames"].append(
                    {"frame": frame_number, "faces": degenerate})

            ratios = []
            below = above = 0
            for first, second in edge_pairs[muscle]:
                standing = (base_vertices[muscle][first] - base_vertices[muscle][second]).length
                if standing < 1e-8:
                    continue
                ratio = (local[first] - local[second]).length / standing
                ratios.append(ratio)
                below += ratio < EDGE_GATE[0]
                above += ratio > EDGE_GATE[1]
            if ratios:
                low, high = min(ratios), max(ratios)
                if entry["edgeRatio"]["minimum"] is None or low < entry["edgeRatio"]["minimum"]:
                    entry["edgeRatio"]["minimum"] = round(low, 4)
                    entry["edgeRatio"]["minimumFrame"] = frame_number
                entry["edgeRatio"]["maximum"] = round(
                    max(entry["edgeRatio"]["maximum"] or 0.0, high), 4)
                entry["edgeRatio"]["edgesBelowGate"] += below
                entry["edgeRatio"]["edgesAboveGate"] += above

            pairs = self_intersections(trees[muscle], shared_vertex_members(polygons))
            if len(pairs) > entry["selfIntersections"]["maximumFacePairs"]:
                entry["selfIntersections"]["maximumFacePairs"] = len(pairs)
                entry["selfIntersections"]["worstFrame"] = frame_number
            if len(pairs) > baseline_self[muscle]:
                entry["selfIntersections"]["framesAboveReference"].append(
                    {"frame": frame_number, "facePairs": len(pairs)})

            for partner in list(muscle_objects) + list(bone_objects):
                if partner == muscle or (muscle, partner) in baseline_pairs:
                    continue
                if partner in muscle_objects and muscle >= partner:
                    continue
                overlap = trees[muscle].overlap(trees[partner])
                if not overlap:
                    continue
                depth = 0.0
                for index, _ in set(overlap):
                    polygon = polygons[index]
                    centroid = Vector((0.0, 0.0, 0.0))
                    for vertex in polygon:
                        centroid += geometries[muscle][0][vertex]
                    centroid /= len(polygon)
                    depth = max(depth, penetration_depth(trees[partner], centroid))
                record = entry["addedIntersections"].setdefault(partner, {
                    "frames": [], "maximumFacePairs": 0, "maximumDepthM": 0.0})
                record["maximumFacePairs"] = max(record["maximumFacePairs"], len(set(overlap)))
                record["maximumDepthM"] = max(record["maximumDepthM"], round(depth, 5))
                record["frames"].append({"frame": frame_number, "facePairs": len(set(overlap)),
                                         "depthM": round(depth, 5)})
                added.setdefault((muscle, partner), []).append(frame_number)

        for first in sorted(bone_objects):
            for second in sorted(bone_objects):
                if first >= second or (first, second) in baseline_pairs:
                    continue
                overlap = trees[first].overlap(trees[second])
                if not overlap:
                    continue
                depth = 0.0
                for index, _ in set(overlap):
                    polygon = geometries[first][1][index]
                    centroid = Vector((0.0, 0.0, 0.0))
                    for vertex in polygon:
                        centroid += geometries[first][0][vertex]
                    centroid /= len(polygon)
                    depth = max(depth, penetration_depth(trees[second], centroid))
                record = report["bonePairIntersections"].setdefault(f"{first}+{second}", {
                    "frames": [], "maximumFacePairs": 0, "maximumDepthM": 0.0})
                record["maximumFacePairs"] = max(record["maximumFacePairs"], len(set(overlap)))
                record["maximumDepthM"] = max(record["maximumDepthM"], round(depth, 5))
                record["frames"].append({"frame": frame_number, "facePairs": len(set(overlap)),
                                         "depthM": round(depth, 5)})
                added.setdefault((first, second), []).append(frame_number)

    frames_with_flips = sorted({item["frame"] for entry in report["musclesChecked"].values()
                                for item in entry["flippedFaces"]["frames"]})
    frames_with_degenerate = sorted({item["frame"] for entry in report["musclesChecked"].values()
                                     for item in entry["degenerateFaces"]["frames"]})
    report["summary"] = {
        "boneMotionAcrossSquat": round(motion, 5),
        "referenceIntersectingMeshPairs": sorted("+".join(pair) for pair in baseline_pairs),
        "referenceSelfIntersectingMuscles": {muscle: count
                                             for muscle, count in baseline_self.items() if count},
        "meshesWithEdgeRatioOutsideGate": sorted(
            muscle for muscle, entry in report["musclesChecked"].items()
            if entry["edgeRatio"]["edgesBelowGate"] or entry["edgeRatio"]["edgesAboveGate"]),
        "worstEdgeRatioMinimum": round(min(
            entry["edgeRatio"]["minimum"] for entry in report["musclesChecked"].values()), 4),
        "worstEdgeRatioMaximum": round(max(
            entry["edgeRatio"]["maximum"] for entry in report["musclesChecked"].values()), 4),
        "framesWithFlippedFaces": frames_with_flips,
        "framesWithDegenerateFaces": frames_with_degenerate,
        "addedIntersectingMeshPairs": {"+".join(key): frames for key, frames in sorted(added.items())
                                       if not (key[0] in bone_objects and key[1] in bone_objects)},
        "addedIntersectingBonePairs": {"+".join(key): frames for key, frames in sorted(added.items())
                                       if key[0] in bone_objects and key[1] in bone_objects},
        "addedIntersectionFrameCount": len({frame for values in added.values() for frame in values}),
        "maximumAddedDepthM": round(max(
            [record["maximumDepthM"] for entry in report["musclesChecked"].values()
             for record in entry["addedIntersections"].values()] +
            [record["maximumDepthM"] for record in report["bonePairIntersections"].values()],
            default=0.0), 5),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print("BLENDER_REGISTERED_MESH_INTEGRITY_AUDIT_OK",
          json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
