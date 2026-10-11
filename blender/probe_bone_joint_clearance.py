"""How much joint clearance it would take to remove the registered meshes' interpenetration.

The integrity audit (blender/audit_registered_mesh_integrity.py) found that the registered bone
meshes interpenetrate from early in the squat, and that seven muscle pairs gain intersections during
it. Its conclusion was that clearing that needs "a joint cartilage gap or per-muscle attachment
registration", without saying how large a gap. This probe measures it:

1. where the overlap sits, as the distance from the deepest overlapping point to the model's knee
   joint centre and its projection on the femur and tibia axes (joint line versus segment shafts);
2. how much a hypothetical clearance buys, by displacing every tibia-side object (the tibia and
   fibula meshes and the three tibia-driven muscle meshes) distally along the tibial axis in steps
   and recounting intersections on every frame.

The clearance is a measuring device, not a proposed edit: it says how large a cartilage-like gap
would have to be, and whether the remaining overlap is joint-line related at all. No scene is
modified, and none of this is anatomy, attachment or force.

Run as: blender --background assets/blender/opensim_eight_muscle_motion.blend \
            --python-exit-code 1 --python blender/probe_bone_joint_clearance.py \
            [-- --report docs/data/bone_joint_clearance_probe.json]
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REPORT = ROOT / "docs/data/bone_joint_clearance_probe.json"
REFERENCE_FRAME = 1
CLEARANCE_STEPS_MM = (0, 2, 4, 6, 8, 10)
TIBIA_SIDE_BODY = "tibia_r"
PATELLA = "atlas_Patella.r"
BODY_NAMES = {"femur": "femur_r", "tibia": "tibia_r", "pelvis": "pelvis"}

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--report", type=Path, default=REPORT)
args = parser.parse_args(argv)
report_path = args.report if args.report.is_absolute() else ROOT / args.report


def to_blender(point):
    """The scene's coordinate mapping, identical to the one the mesh-motion checks use."""
    x, y, z = point
    return Vector((0.09 - x, -z, y))


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
    return BVHTree.FromPolygons([tuple(vertex) for vertex in vertices], polygons,
                                all_triangles=False)


def face_centroid(vertices, polygon):
    centroid = Vector((0.0, 0.0, 0.0))
    for vertex in polygon:
        centroid += vertices[vertex]
    return centroid / len(polygon)


def nearest_depth(tree, point):
    try:
        location, normal, _, distance = tree.find_nearest(point)
    except RuntimeError:
        return 0.0
    if location is None or (point - location).dot(normal) >= 0:
        return 0.0
    return distance


def deepest_point(tree_partner, vertices, polygons, indices):
    depth = 0.0
    point = None
    for index in indices:
        centroid = face_centroid(vertices, polygons[index])
        value = nearest_depth(tree_partner, centroid)
        if value > depth:
            depth = value
            point = centroid
    return depth, point


def main():
    scene = bpy.context.scene
    if scene["status"] != "research_eight_muscle_deformations_only":
        raise AssertionError(f"unexpected scene status {scene['status']!r}")
    lookup = json.loads(LOOKUP.read_text(encoding="utf-8"))
    frames = lookup["frames"]
    if len(frames) != scene.frame_end:
        raise AssertionError("lookup frame count differs from the scene")

    bone_objects = {}
    bone_bodies = {}
    for obj in bpy.data.objects:
        if obj.type == "MESH" and "opensim_body" in obj.keys():
            bone_objects[obj.name] = obj
            bone_bodies[obj.name] = obj["opensim_body"]
    muscle_objects = {}
    muscle_bodies = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or "path_source" not in obj.keys():
            continue
        muscle = obj["path_source"].removeprefix("OpenSim reference ")
        muscle_objects[muscle] = obj
        muscle_bodies[muscle] = BODY_NAMES[obj["method"][len("rigid "):obj["method"].index(" motion")]]

    body_of = {**bone_bodies, **muscle_bodies}
    tibia_side = sorted(name for name, body in body_of.items() if body == TIBIA_SIDE_BODY)
    if tibia_side != sorted(["atlas_Tibia.r", "atlas_Fibula.r", "soleus_r", "tib_ant_r", "med_gas_r"]):
        raise AssertionError(f"unexpected tibia-side objects: {tibia_side}")
    if PATELLA not in bone_objects:
        raise AssertionError(f"the scene has no {PATELLA} bone mesh")

    names = list(muscle_objects) + list(bone_objects)
    pair_names = [(first, second) for index, first in enumerate(names)
                  for second in names[index + 1:]]

    reference = frames[REFERENCE_FRAME - 1]
    joints = {key: to_blender(value) for key, value in reference["viewerJointsM"].items()}
    knee_offset = (Vector(reference["blenderBodyFrames"][TIBIA_SIDE_BODY]["translationM"]) -
                   joints["knee"]).length

    scene.frame_set(REFERENCE_FRAME)
    reference_trees = {}
    for name, obj in {**muscle_objects, **bone_objects}.items():
        reference_trees[name] = tree_from(*evaluated_geometry(obj))
    reference_pairs = {pair for pair in pair_names
                       if reference_trees[pair[0]].overlap(reference_trees[pair[1]])}

    report = {
        "status": "research_only_bone_joint_clearance_probe",
        "scene": "assets/blender/opensim_eight_muscle_motion.blend",
        "source": "public/data/squat_opensim_reference.json",
        "framesChecked": scene.frame_end,
        "referenceFrame": REFERENCE_FRAME,
        "clearanceStepsMm": list(CLEARANCE_STEPS_MM),
        "clearanceDirection": "distal along the knee-to-ankle axis, applied to every tibia-side mesh",
        "patellaClearanceDirection": "outward from the nearest femoral surface through the patella "
                                     "centre, applied to the patella mesh alone",
        "tibiaSideObjects": tibia_side,
        "jointCentreCheckM": {
            "tibiaBodyOriginToKneeCentre": round(knee_offset, 5),
        },
        "referenceIntersectingPairs": sorted("+".join(pair) for pair in reference_pairs),
        "pairs": {},
        "summary": {},
        "limitations": [
            "the clearance is a hypothetical rigid translation used to measure how large a gap the "
            "overlap needs; no scene is modified and no anatomy is changed",
            "displacing tibia-side muscle meshes with the tibia assumes they follow that segment, "
            "which is how the research layer already drives them",
            "penetration depth and the deepest point come from intersecting face centroids, so they "
            "are estimates rather than measured overlap volumes",
            "the deepest point is characterised by its distance to the model's knee joint centre and "
            "by projections on the two segment axes; that centre is a model joint, not a fitted "
            "anatomical landmark",
            "no published cartilage or meniscus thickness was checked in this round, so the measured "
            "clearance is reported as geometry only, not as a physiological requirement",
            "one standing registration, one subject's squat, right side only",
        ],
    }

    for frame_number in range(REFERENCE_FRAME, scene.frame_end + 1):
        scene.frame_set(frame_number)
        frame = frames[frame_number - 1]
        geometries = {}
        trees = {}
        for name, obj in {**muscle_objects, **bone_objects}.items():
            geometries[name] = evaluated_geometry(obj)
            trees[name] = tree_from(*geometries[name])
        joints = {key: to_blender(value) for key, value in frame["viewerJointsM"].items()}
        femur_axis = (joints["knee"] - joints["hip"]).normalized()
        tibia_axis = (joints["ankle"] - joints["knee"]).normalized()

        intersecting = []
        for first, second in pair_names:
            if (first, second) in reference_pairs:
                continue
            overlap = trees[first].overlap(trees[second])
            if overlap:
                intersecting.append((first, second, overlap))
        if not intersecting:
            continue

        displaced_trees = {}
        for step in CLEARANCE_STEPS_MM:
            if step:
                offset = tibia_axis * (step / 1000.0)
                displaced_trees[step] = {**trees, **{
                    name: tree_from([vertex + offset for vertex in geometries[name][0]],
                                    geometries[name][1]) for name in tibia_side}}
            else:
                displaced_trees[step] = trees

        # A distal clearance cannot touch the patella, which rides its own body, so the
        # patellofemoral gap is swept separately along the patella's own outward direction: the
        # direction from the nearest femoral surface to the patella's centre.
        patella_vertices, patella_polygons = geometries[PATELLA]
        patella_centre = sum(patella_vertices, Vector()) / len(patella_vertices)
        try:
            contact, normal, _, _ = trees["atlas_Femur.r"].find_nearest(patella_centre)
        except RuntimeError:
            contact = None
        if contact is not None and (patella_centre - contact).length > 1e-6:
            patella_axis = (patella_centre - contact).normalized()
        else:
            patella_axis = None
        displaced_patella = {}
        for step in CLEARANCE_STEPS_MM:
            if step and patella_axis is not None:
                offset = patella_axis * (step / 1000.0)
                displaced_patella[step] = {**trees, PATELLA: tree_from(
                    [vertex + offset for vertex in patella_vertices], patella_polygons)}
            else:
                displaced_patella[step] = trees

        for first, second, overlap in intersecting:
            key = f"{first}+{second}"
            record = report["pairs"].setdefault(key, {
                "frames": [],
                "maximumDepthM": 0.0,
                "deepestFrame": None,
                "deepestPoint": None,
                "clearanceSweepFramesIntersecting": {str(step): 0 for step in CLEARANCE_STEPS_MM},
                "patellaSweepFramesIntersecting": {str(step): 0 for step in CLEARANCE_STEPS_MM},
                "tibiaSide": [name for name in (first, second) if name in tibia_side],
                "movesWithClearance": any(name in tibia_side for name in (first, second)),
            })
            record["frames"].append(frame_number)
            depth, point = deepest_point(trees[second], geometries[first][0], geometries[first][1],
                                         {pair[0] for pair in overlap})
            if depth > record["maximumDepthM"]:
                record["maximumDepthM"] = round(depth, 5)
                record["deepestFrame"] = frame_number
                record["deepestPoint"] = {
                    "distanceToKneeCentreM": round((point - joints["knee"]).length, 5),
                    "alongFemurAxisFromHipM": round((point - joints["hip"]).dot(femur_axis), 5),
                    "alongTibiaAxisFromKneeM": round((point - joints["knee"]).dot(tibia_axis), 5),
                }
            for step in CLEARANCE_STEPS_MM:
                if displaced_trees[step][first].overlap(displaced_trees[step][second]):
                    record["clearanceSweepFramesIntersecting"][str(step)] += 1
                if PATELLA in (first, second) and \
                        displaced_patella[step][first].overlap(displaced_patella[step][second]):
                    record["patellaSweepFramesIntersecting"][str(step)] += 1

    bone_pairs = {key: value for key, value in report["pairs"].items()
                  if all(part in bone_objects for part in key.split("+"))}
    muscle_pairs = {key: value for key, value in report["pairs"].items() if key not in bone_pairs}

    def first_clearing(pairs, field="clearanceSweepFramesIntersecting"):
        for step in CLEARANCE_STEPS_MM:
            if all(value[field][str(step)] == 0 for value in pairs.values()):
                return step
        return None

    patella_pairs = {key: value for key, value in report["pairs"].items() if PATELLA in key}
    worst_bone = (max(bone_pairs.items(), key=lambda item: item[1]["maximumDepthM"])
                  if bone_pairs else None)
    report["summary"] = {
        "addedPairCount": len(report["pairs"]),
        "bonePairCount": len(bone_pairs),
        "musclePairCount": len(muscle_pairs),
        "tibiaClearanceClearingAllBonePairOverlapMm": first_clearing(bone_pairs),
        "tibiaClearanceClearingAllMusclePairOverlapMm": first_clearing(muscle_pairs),
        "tibiaClearancePerPairMm": {key: first_clearing({key: value})
                                    for key, value in report["pairs"].items()},
        "patellaClearancePerPatellaPairMm": {key: first_clearing({key: value},
                                                                 "patellaSweepFramesIntersecting")
                                             for key, value in patella_pairs.items()},
        "worstBonePair": worst_bone[0] if worst_bone else None,
        "worstBonePairDepthM": worst_bone[1]["maximumDepthM"] if worst_bone else None,
        "worstBonePairDeepestPoint": worst_bone[1]["deepestPoint"] if worst_bone else None,
        "bonePairFramesAtZeroClearance": {key: len(value["frames"]) for key, value in bone_pairs.items()},
        "musclePairFramesAtZeroClearance": {key: len(value["frames"])
                                            for key, value in muscle_pairs.items()},
        "pairsUnaffectedByTibiaClearance": sorted(key for key, value in report["pairs"].items()
                                                  if not value["movesWithClearance"]),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BLENDER_BONE_JOINT_CLEARANCE_PROBE_OK",
          json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
