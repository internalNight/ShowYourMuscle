"""Measure how every right-leg atlas muscle mesh sits relative to its model path.

The repository has two standing screens for these meshes, and they disagree for the muscles that
were hardest to judge: `right_leg_muscle_path_screen.json` reports the distance from a horizontal
z-slice centroid to the path, while `right_leg_muscle_surface_path_screen.json` reports the distance
from path samples to the nearest mesh surface. A centroid of a wrapping, tilted cross-section is not
a muscle axis, and a maximum surface distance can be produced by a long tendon that simply leaves the
belly mesh behind. This probe separates those cases instead of picking one number:

* limb-axis geometry, using exactly the origin/axis rule the phone applies for each body;
* the radial band of mesh vertices around that axis, compared with the path's own radial distance;
* surface distances split into samples inside the mesh height and samples beyond it, together with
  how much of each outside distance is explained by distal (-z) extension rather than lateral offset.
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "assets/blender/opensim_seven_muscle_motion.blend"
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
LOOKUP = ROOT / "public/data/squat_opensim_reference.json"
REGISTRATION = ROOT / "docs/data/standing_registration_probe.json"
CENTRE_SCREEN = ROOT / "docs/data/right_leg_muscle_path_screen.json"
SURFACE_SCREEN = ROOT / "docs/data/right_leg_muscle_surface_path_screen.json"
REPORT = ROOT / "docs/data/right_leg_mesh_alignment_probe.json"
PAIRS = [
    ("glut_max2_r", "Gluteus maximus muscle.r", "pelvis"),
    ("rect_fem_r", "Rectus femoris muscle.r", "femur_r"),
    ("bifemsh_r", "Short head of biceps femoris.r", "femur_r"),
    ("semimem_r", "Semimembranosus muscle.r", "femur_r"),
    ("vas_int_r", "Vastus intermedius muscle.r", "femur_r"),
    ("tib_ant_r", "Tibialis anterior muscle.r", "tibia_r"),
    ("soleus_r", "Soleus muscle.r", "tibia_r"),
    ("med_gas_r", "Medial head of gastrocnemius.r", "tibia_r"),
]
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--pair", action="append", default=[],
                    help="restrict to muscle=atlasMesh pairs, for example med_gas_r=Medial head of gastrocnemius.r")
parser.add_argument("--report", type=Path, default=REPORT)
args = parser.parse_args(argv)
report_path = args.report if args.report.is_absolute() else ROOT / args.report
selected = PAIRS
if args.pair:
    wanted = {item.split("=", 1)[0]: item.split("=", 1)[1] for item in args.pair}
    selected = [pair for pair in PAIRS if pair[0] in wanted]
    missing = set(wanted) - {pair[0] for pair in selected}
    if missing:
        parser.error(f"unknown muscles: {sorted(missing)}")


def to_blender(point):
    x, y, z = point
    return Vector((0.09 - x, -z, y))


def bounds(points):
    return {"minimumM": [round(min(point[i] for point in points), 5) for i in range(3)],
            "maximumM": [round(max(point[i] for point in points), 5) for i in range(3)]}


def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def at_fraction(points, fraction):
    lengths = [(b - a).length for a, b in zip(points, points[1:])]
    remaining = fraction * sum(lengths)
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if remaining <= length and length > 0:
            return a.lerp(b, remaining / length)
        remaining -= length
    return points[-1].copy()


def limb_axis(standing, body):
    """Mirror the phone rule: femur meshes use hip→knee, pelvis and tibia meshes use knee→ankle."""
    first, second = ("hip", "knee") if body == "femur_r" else ("knee", "ankle")
    origin = to_blender(standing["viewerJointsM"][first])
    return origin, (to_blender(standing["viewerJointsM"][second]) - origin).normalized()


bpy.ops.wm.open_mainfile(filepath=str(SCENE))
scene = bpy.context.scene
scene.frame_set(1)
existing = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(ATLAS))
imported = {obj.name: obj for obj in set(bpy.data.objects) - existing}
shift = Vector(json.loads(REGISTRATION.read_text(encoding="utf-8"))["translationM"])
standing = json.loads(LOOKUP.read_text(encoding="utf-8"))["frames"][0]
centre_screen = {item["opensimMuscle"]: item
                 for item in json.loads(CENTRE_SCREEN.read_text(encoding="utf-8"))["muscles"]}
surface_screen = {item["opensimMuscle"]: item
                  for item in json.loads(SURFACE_SCREEN.read_text(encoding="utf-8"))["muscles"]}

report = {"status": "research_only_standing_leg_alignment_probe",
          "scene": str(SCENE.relative_to(ROOT)),
          "atlas": str(ATLAS.relative_to(ROOT)),
          "axisRule": "femur_r meshes use hip to knee; pelvis and tibia_r meshes use knee to ankle",
          "surfaceWindowM": 0.01,
          "muscles": {}}
for muscle_id, atlas_name, body in selected:
    source = imported[atlas_name]
    points = [source.matrix_world @ vertex.co + shift for vertex in source.data.vertices]
    origin, axis = limb_axis(standing, body)
    offset = [point - origin for point in points]
    along = [value.dot(axis) for value in offset]
    radial = [value.length for value in
              (value - axis * value.dot(axis) for value in offset)]
    path = [to_blender(point) for point in standing["muscles"][muscle_id]["viewerPathM"]]
    path_offset = [point - origin for point in path]
    path_radial = [value.length for value in
                   (value - axis * value.dot(axis) for value in path_offset)]
    slices = []
    for fraction in (0.05, 0.25, 0.5, 0.75, 0.95):
        path_point = at_fraction(path, fraction)
        height = (path_point - origin).dot(axis)
        window = sorted(value for value, position in zip(radial, along)
                        if abs(position - height) < 0.01)
        slices.append({
            "fractionFromPathStart": fraction,
            "sliceVertexCount": len(window),
            "sliceMinimumRadiusM": round(window[0], 5) if window else None,
            "sliceMaximumRadiusM": round(window[-1], 5) if window else None,
            "pathRadiusM": round((path_point - origin
                                  - axis * (path_point - origin).dot(axis)).length, 5)})
    # Split the published surface screen: samples inside the mesh height describe the belly, and
    # samples beyond it are dominated by the model path continuing past the mesh.
    surface = surface_screen[muscle_id]
    inside = [item for item in surface["samples"] if item["withinMeshHeight"]]
    outside = [item for item in surface["samples"] if not item["withinMeshHeight"]]
    distal = [abs(item["pathBlenderM"][2] - item["nearestMeshM"][2]) / item["distanceM"]
              for item in outside if item["distanceM"] > 1e-9]
    report["muscles"][muscle_id] = {
        "atlasMesh": atlas_name, "body": body,
        "vertexCount": len(points),
        "meshBounds": bounds(points), "pathBounds": bounds(path),
        "meshHeightM": round(max(point.z for point in points) - min(point.z for point in points), 5),
        "pathLengthM": round(sum((b - a).length for a, b in zip(path, path[1:])), 5),
        "meshRadialDistanceFromLimbAxisM": {
            "minimum": round(min(radial), 5), "median": round(median(radial), 5),
            "maximum": round(max(radial), 5)},
        "pathRadialDistanceFromLimbAxisM": {
            "minimum": round(min(path_radial), 5), "maximum": round(max(path_radial), 5)},
        "sliceRadiusAtPathHeight": slices,
        "surfaceScreenInsideMeshHeight": {
            "sampleCount": len(inside),
            "medianDistanceM": round(median([item["distanceM"] for item in inside]), 5) if inside else None,
            "maximumDistanceM": round(max(item["distanceM"] for item in inside), 5) if inside else None},
        "surfaceScreenBeyondMeshHeight": {
            "sampleCount": len(outside),
            "maximumDistanceM": round(max(item["distanceM"] for item in outside), 5) if outside else None,
            "medianDistalShareOfDistance": round(median(distal), 4) if distal else None},
        "publishedCentreDistanceM": round(centre_screen[muscle_id]["maximumCenterDistanceM"], 5),
        "publishedSurfaceDistanceM": {
            "median": round(surface["medianSurfaceDistanceM"], 5),
            "p95": round(surface["p95SurfaceDistanceM"], 5),
            "maximum": round(surface["maximumSurfaceDistanceM"], 5)}}
report["limitations"] = [
    "standing pose only, right side only, shared bone bounding-box registration",
    "the limb axis is the phone's scaling axis, not an anatomical muscle line of action",
    "slice radii use a 1 cm window around the path height and are not attachments",
    "distal share = |z difference| / surface distance; near 1 means the model path runs past the "
    "mesh rather than sitting to one side of it",
    "nearest surface is not a fiber path or an attachment, and no deformation is simulated here"]
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for muscle_id, item in report["muscles"].items():
    inside = item["surfaceScreenInsideMeshHeight"]
    outside = item["surfaceScreenBeyondMeshHeight"]
    print(f"{muscle_id:11s} inside n={inside['sampleCount']:2d} med={inside['medianDistanceM']} "
          f"max={inside['maximumDistanceM']} | beyond n={outside['sampleCount']:2d} "
          f"max={outside['maximumDistanceM']} distalShare={outside['medianDistalShareOfDistance']} "
          f"| meshH={item['meshHeightM']} pathL={item['pathLengthM']}")
print("SAVED_LEG_ALIGNMENT_PROBE", report_path)
