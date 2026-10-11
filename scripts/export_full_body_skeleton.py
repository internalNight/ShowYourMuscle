"""Export a full-body OpenSim skeleton to glTF for the app.

The model is `RajagopalLaiUhlrich2023` (22 bodies, 22 joints, 80 muscles). Its own visualization meshes are
incomplete (the hand bones reference `*_lvs.vtp` files that are not in the package), so each body is paired
with the best mesh that exists locally, by name; the left upper limb is mirrored from the right because no
left-side humerus, ulna, radius or hand mesh exists in any of the local sets. The pairing table below is the
whole substitution, and `docs/data/full_body_skeleton_export.json` records what was used.

The exported glTF keeps the model's **body tree**: one node per body, translated and rotated to that body's
frame relative to its parent as it stands in the model's default pose. That is what makes runtime scaling
possible — scaling a parent node scales everything below it, which is how OpenSim's own `ScaleSet` behaves.
Mesh vertices are baked in each body's own frame, so a node's scale is the only thing a runtime has to set.

The file is written to `public/models/full_body_skeleton.glb` because the app ships it; the numbers are
recorded in `docs/data/full_body_skeleton_export.json`, where the shipped check reads them.
"""

import json
import math
import os
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / ".cache/model-candidates/opensim-models/Models/Rajagopal/RajagopalLaiUhlrich2023.osim"
OUTPUT_GLB = ROOT / "public/models/full_body_skeleton.glb"
OUTPUT_JSON = ROOT / "docs/data/full_body_skeleton_export.json"
REFERENCE_HEIGHT_CM = 175.0

# body -> [(mesh file name, mirror about x?), ...]  Every mesh below exists somewhere under .cache; the
# search path is fixed so the export is reproducible on this machine and fails loudly anywhere else.
MESH_DIRS = [
    ROOT / ".cache/model-candidates/opensim-models/Models/Rajagopal/Geometry",
    ROOT / ".cache/model-candidates/rmr-solver-py/Input/knee_model/geometry",
    ROOT / ".cache/model-candidates/rmr-solver-py/Input/shoulder_model/Geometry",
    ROOT / "assets/opensim/thoracoscapular/Geometry",
]
PAIRING = {
    "pelvis": [("sacrum.vtp", False), ("r_pelvis.vtp", False), ("l_pelvis.vtp", False)],
    "torso": [("hat_spine.vtp", False), ("hat_ribs_scap.vtp", False), ("hat_skull.vtp", False)],
    "femur_r": [("r_femur.vtp", False)],
    "femur_l": [("l_femur.vtp", False)],
    "tibia_r": [("r_tibia.vtp", False), ("r_fibula.vtp", False)],
    "tibia_l": [("l_tibia.vtp", False), ("l_fibula.vtp", False)],
    "patella_r": [("r_patella.vtp", False)],
    "patella_l": [("l_patella.vtp", False)],
    "talus_r": [("r_talus.vtp", False)],
    "talus_l": [("l_talus.vtp", False)],
    "calcn_r": [("r_foot.vtp", False)],
    "calcn_l": [("l_foot.vtp", False)],
    "toes_r": [("r_bofoot.vtp", False)],
    "toes_l": [("l_bofoot.vtp", False)],
    "humerus_r": [("humerus.vtp", False)],
    "humerus_l": [("humerus.vtp", True)],
    "ulna_r": [("ulna.vtp", False)],
    "ulna_l": [("ulna.vtp", True)],
    "radius_r": [("radius.vtp", False)],
    "radius_l": [("radius.vtp", True)],
    "hand_r": [("r_hand.vtp", False)],
    "hand_l": [("r_hand.vtp", True)],
}
# Which bodies a circumference input may widen, and in which axes. Lengths never take a girth factor.
SEGMENT_GIRTH_BODIES = {
    "chest": ["torso"],
    "waist": ["pelvis", "torso"],
    "thigh": ["femur_r", "femur_l"],
    "calf": ["tibia_r", "tibia_l"],
    "arm": ["humerus_r", "humerus_l"],
}


def find_mesh(name):
    for directory in MESH_DIRS:
        candidate = directory / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no local copy of {name} in: " + ", ".join(str(d) for d in MESH_DIRS))


def read_vtp(path):
    """Read an ASCII VTK PolyData file into vertices, triangles, polygon count and per-vertex normals.

    These files are written in the VTK 9 layout: `Polys` carries a flat `connectivity` index list plus
    cumulative `offsets`, and faces may have any number of vertices, so each face is fan-triangulated —
    the same thing VTK's own polydata mapper does when it renders. The files also carry their own
    `Normals`, which are used in preference to recomputed ones so the exported shading matches the source.
    """
    piece = ET.parse(path).getroot().find(".//Piece")
    points = connectivity = offsets = normals = None
    for section in piece:
        for array in section:
            if array.tag != "DataArray":
                continue
            name = array.get("Name")
            text = (array.text or "").split()
            if section.tag == "Points":
                points = [float(value) for value in text]
            elif section.tag == "Polys" and name == "connectivity":
                connectivity = [int(value) for value in text]
            elif section.tag == "Polys" and name == "offsets":
                offsets = [int(value) for value in text]
            elif section.tag == "PointData" and name == "Normals":
                normals = [float(value) for value in text]
    if not points or not connectivity or not offsets:
        raise ValueError(f"{path.name} is not an ASCII points/connectivity/offsets PolyData file")
    vertices = [(points[i], points[i + 1], points[i + 2]) for i in range(0, len(points), 3)]
    triangles = []
    start = 0
    for end in offsets:
        face = connectivity[start:end]
        start = end
        if len(face) < 3:
            raise ValueError(f"{path.name} has a {len(face)}-vertex face")
        for corner in range(1, len(face) - 1):
            triangles.append((face[0], face[corner], face[corner + 1]))
    source_normals = ([(normals[i], normals[i + 1], normals[i + 2]) for i in range(0, len(normals), 3)]
                      if normals else None)
    if source_normals is not None and len(source_normals) != len(vertices):
        source_normals = None
    return vertices, triangles, len(offsets), source_normals


def mirrored(vertices, triangles, normals):
    """Mirror a right-side mesh onto the left side about the left-right axis (z: x is forward, y is up).

    An independent render measured the previous version, which negated x, and found the left arm 20-42 mm
    out of symmetry while the natively paired leg meshes agreed to under 1 mm — negating x mirrors front to
    back instead of left to right.
    """
    flipped = [(x, y, -z) for (x, y, z) in vertices]
    flipped_normals = ([(nx, ny, -nz) for (nx, ny, nz) in normals] if normals else None)
    return flipped, [(a, c, b) for (a, b, c) in triangles], flipped_normals


def vertex_normals(vertices, triangles):
    normals = [[0.0, 0.0, 0.0] for _ in vertices]
    for (a, b, c) in triangles:
        first, second, third = vertices[a], vertices[b], vertices[c]
        edge1 = [second[i] - first[i] for i in range(3)]
        edge2 = [third[i] - first[i] for i in range(3)]
        face = [edge1[1] * edge2[2] - edge1[2] * edge2[1],
                edge1[2] * edge2[0] - edge1[0] * edge2[2],
                edge1[0] * edge2[1] - edge1[1] * edge2[0]]
        for index in (a, b, c):
            for axis in range(3):
                normals[index][axis] += face[axis]
    for normal in normals:
        length = math.sqrt(sum(component * component for component in normal)) or 1.0
        for axis in range(3):
            normal[axis] /= length
    return normals


os.chdir(MODEL.parent)
model = osim.Model(MODEL.name)
state = model.initSystem()
bodies = [model.getBodySet().get(i).getName() for i in range(model.getBodySet().getSize())]

ground = {}
for name in bodies:
    transform = model.getBodySet().get(name).getTransformInGround(state)
    rotation = transform.R()
    translation = transform.p()
    ground[name] = (
        [[rotation.get(row, column) for column in range(3)] for row in range(3)],
        [translation.get(i) for i in range(3)],
    )

# A joint connects PhysicalOffsetFrames, not bodies, and those frames expose no parent-frame accessor in the
# Python API. Every physical frame does carry the mobilized-body index it belongs to, which is how a frame is
# mapped back to its body here.
owning = {}
for name in bodies:
    owning[model.getBodySet().get(name).getMobilizedBodyIndex()] = name


def owning_body_name(frame):
    return owning.get(frame.getMobilizedBodyIndex())


parent_of = {name: None for name in bodies}
for index in range(model.getJointSet().getSize()):
    joint = model.getJointSet().get(index)
    child = owning_body_name(joint.getChildFrame())
    parent = owning_body_name(joint.getParentFrame())
    if child is None or child not in parent_of:
        continue
    parent_of[child] = parent if parent != child else None


def frame_translation(frame, fallback_body):
    """Where a joint's offset frame sits, expressed in the body frame it is attached to.

    The runtime needs each bone's proximal and distal joint in that bone's own frame to fit the mesh onto the
    app's own skeleton segments, so the numbers are recorded here rather than guessed at the other end.
    """
    offset = osim.PhysicalOffsetFrame.safeDownCast(frame)
    if offset is None:
        return None
    parent_frame = offset.getParentFrame()
    if parent_frame is None or parent_frame.getName() != fallback_body:
        return None
    translation = offset.get_translation()
    return [translation.get(0), translation.get(1), translation.get(2)]


joint_frames = []
for index in range(model.getJointSet().getSize()):
    joint = model.getJointSet().get(index)
    child_body = owning_body_name(joint.getChildFrame())
    parent_body = owning_body_name(joint.getParentFrame())
    joint_frames.append({
        "joint": joint.getName(),
        "childBody": child_body,
        "parentBody": parent_body,
        "locationInChildBodyM": frame_translation(joint.getChildFrame(), child_body),
        "locationInParentBodyM": frame_translation(joint.getParentFrame(), parent_body),
    })


def relative_transform(child):
    parent = parent_of[child]
    if parent is None:
        return [0.0, 0.0, 0.0], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    parent_rotation, parent_translation = ground[parent]
    child_rotation, child_translation = ground[child]
    # R_rel = R_parent^T · R_child, t_rel = R_parent^T · (p_child − p_parent)
    relative_rotation = [[sum(parent_rotation[k][row] * child_rotation[k][column] for k in range(3))
                          for column in range(3)] for row in range(3)]
    delta = [child_translation[i] - parent_translation[i] for i in range(3)]
    relative_translation = [sum(parent_rotation[k][row] * delta[k] for k in range(3)) for row in range(3)]
    return relative_translation, relative_rotation


def quaternion(rotation):
    trace = rotation[0][0] + rotation[1][1] + rotation[2][2]
    if trace > 0:
        scale = math.sqrt(trace + 1.0) * 2
        return [(rotation[2][1] - rotation[1][2]) / scale, (rotation[0][2] - rotation[2][0]) / scale,
                (rotation[1][0] - rotation[0][1]) / scale, 0.25 * scale]
    if rotation[0][0] > rotation[1][1] and rotation[0][0] > rotation[2][2]:
        scale = math.sqrt(1.0 + rotation[0][0] - rotation[1][1] - rotation[2][2]) * 2
        return [0.25 * scale, (rotation[0][1] + rotation[1][0]) / scale, (rotation[0][2] + rotation[2][0]) / scale,
                (rotation[2][1] - rotation[1][2]) / scale]
    if rotation[1][1] > rotation[2][2]:
        scale = math.sqrt(1.0 + rotation[1][1] - rotation[0][0] - rotation[2][2]) * 2
        return [(rotation[0][1] + rotation[1][0]) / scale, 0.25 * scale, (rotation[1][2] + rotation[2][1]) / scale,
                (rotation[0][2] - rotation[2][0]) / scale]
    scale = math.sqrt(1.0 + rotation[2][2] - rotation[0][0] - rotation[1][1]) * 2
    return [(rotation[0][2] + rotation[2][0]) / scale, (rotation[1][2] + rotation[2][1]) / scale, 0.25 * scale,
            (rotation[1][0] - rotation[0][1]) / scale]


binary = bytearray()
buffer_views = []
accessors = []
meshes = []
nodes = []
node_index = {}
records = []


def add_accessor(payload, component_type, type_name, count, target=None):
    while len(binary) % 4:
        binary.append(0)
    offset = len(binary)
    binary.extend(payload)
    view = {"buffer": 0, "byteOffset": offset, "byteLength": len(payload)}
    if target is not None:
        view["target"] = target
    buffer_views.append(view)
    accessors.append({"bufferView": len(buffer_views) - 1, "componentType": component_type,
                      "count": count, "type": type_name})
    return len(accessors) - 1


SPLIT_PARTS = {
    "pelvis": [("pelvis_sacrum", ["sacrum.vtp"]), ("pelvis_r", ["r_pelvis.vtp"]), ("pelvis_l", ["l_pelvis.vtp"])],
    "torso": [("torso_spine", ["hat_spine.vtp"]), ("torso_ribs", ["hat_ribs_scap.vtp"]),
              ("torso_skull", ["hat_skull.vtp"])],
    "tibia_r": [("tibia_r_shaft", ["r_tibia.vtp"]), ("tibia_r_fibula", ["r_fibula.vtp"])],
    "tibia_l": [("tibia_l_shaft", ["l_tibia.vtp"]), ("tibia_l_fibula", ["l_fibula.vtp"])],
}

# Split the merged meshes before anything is built: each part becomes its own node under the body it belongs
# to, so the node tree, the joint frames and the OpenSim body count all stay as they were.
OPEN_SIM_BODIES = len(bodies)
for _body_name, _parts in SPLIT_PARTS.items():
    if _body_name not in bodies:
        continue
    PAIRING[_body_name] = []
    # The base index is taken once: recomputing it per part moved it as the earlier parts were inserted, which
    # pushed the later ones after their own parent and left the parent's union box holding only the first part.
    _base = bodies.index(_body_name)
    for _offset, (_part_name, _meshes) in enumerate(_parts):
        PAIRING[_part_name] = [(_mesh, False) for _mesh in _meshes]
        parent_of[_part_name] = _body_name
        ground[_part_name] = ground[_body_name]
        bodies.insert(_base + _offset, _part_name)

for body in bodies:
    node_index[body] = len(nodes)
    translation, rotation = relative_transform(body)
    node = {"name": body, "translation": [round(value, 9) for value in translation],
            "rotation": [round(value, 9) for value in quaternion(rotation)], "scale": [1, 1, 1],
            "children": []}
    nodes.append(node)

    vertices = []
    triangles = []
    normals = []
    used = []
    for mesh_name, mirror in PAIRING.get(body, []):
        path = find_mesh(mesh_name)
        mesh_vertices, mesh_triangles, mesh_polygons, mesh_normals = read_vtp(path)
        if mirror:
            mesh_vertices, mesh_triangles, mesh_normals = mirrored(mesh_vertices, mesh_triangles, mesh_normals)
        if body.startswith('hand') and mesh_vertices:
            # The model ships no hand mesh at all, so a substitute from another local model is used, and that
            # mesh is expressed in that model's own frame: it landed 0.23 m behind and 0.29 m below the wrist,
            # which the independent render reported as a 212.5 mm gap at the wrist and hands floating behind
            # the thighs. It is centred on this body's origin instead — the same convention every other bone
            # already follows — so the substitute hangs off the wrist together with the forearm.
            low = [min(vertex[axis] for vertex in mesh_vertices) for axis in range(3)]
            high = [max(vertex[axis] for vertex in mesh_vertices) for axis in range(3)]
            centre = [(low[axis] + high[axis]) / 2 for axis in range(3)]
            mesh_vertices = [(vertex[0] - centre[0], vertex[1] - centre[1], vertex[2] - centre[2])
                             for vertex in mesh_vertices]
        base = len(vertices)
        vertices.extend(mesh_vertices)
        triangles.extend((a + base, b + base, c + base) for (a, b, c) in mesh_triangles)
        if mesh_normals is None:
            # A mesh without its own normals gets the rest of the body's normals recomputed as a whole, so
            # the mixed case stays consistent instead of averaging file normals with computed ones.
            normals = None
        elif normals is not None:
            normals.extend(mesh_normals)
        used.append({"mesh": mesh_name, "mirroredAboutZ": mirror, "points": len(mesh_vertices),
                     "polygons": mesh_polygons, "triangles": len(mesh_triangles),
                     "hadOwnNormals": mesh_normals is not None,
                     "source": str(path.relative_to(ROOT)).replace("\\", "/")})
    if not triangles:
        # No mesh property at all: glTF wants an integer index, and `"mesh": null` made three.js refuse the
        # whole file once the split started routing bodies down this path. The record still has to say where the
        # body is, so it takes the union of the parts that were just built inside it.
        node.pop("mesh", None)
        parts = [entry for entry in records if entry.get("parent") == body and entry.get("boundsInBodyFrame")]
        if parts:
            low = [min(entry["boundsInBodyFrame"]["min"][axis] for entry in parts) for axis in range(3)]
            high = [max(entry["boundsInBodyFrame"]["max"][axis] for entry in parts) for axis in range(3)]
        else:
            low = high = [0.0, 0.0, 0.0]
        records.append({"body": body, "parent": parent_of[body], "translation": translation,
                        "rotation": nodes[-1]["rotation"], "meshes": [], "points": 0, "triangles": 0,
                        # The GLB tree cannot tell a part from a child body — both hang off the same parent — so
                        # the distinction lives here, and the render cross-check reads it.
                        "parts": [name for name, _meshes in SPLIT_PARTS.get(body, [])],
                        "boundsInBodyFrame": {"min": low, "max": high}})
        continue

    if normals is None or len(normals) != len(vertices):
        normals = vertex_normals(vertices, triangles)
    flat_positions = [component for vertex in vertices for component in vertex]
    flat_normals = [component for normal in normals for component in normal]
    flat_indices = [index for triangle in triangles for index in triangle]
    position_accessor = add_accessor(struct.pack(f"<{len(flat_positions)}f", *flat_positions), 5126, "VEC3",
                                    len(vertices), target=34962)
    normal_accessor = add_accessor(struct.pack(f"<{len(flat_normals)}f", *flat_normals), 5126, "VEC3",
                                  len(normals), target=34962)
    index_accessor = add_accessor(struct.pack(f"<{len(flat_indices)}I", *flat_indices), 5125, "SCALAR",
                                 len(flat_indices), target=34963)
    accessor_min = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
    accessor_max = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
    accessors[position_accessor]["min"] = [round(value, 9) for value in accessor_min]
    accessors[position_accessor]["max"] = [round(value, 9) for value in accessor_max]
    meshes.append({"name": f"{body}_mesh", "primitives": [
        {"attributes": {"POSITION": position_accessor, "NORMAL": normal_accessor},
         "indices": index_accessor, "mode": 4}]})
    node["mesh"] = len(meshes) - 1
    records.append({"body": body, "parent": parent_of[body], "translation": translation,
                    "rotation": nodes[-1]["rotation"], "meshes": used, "points": len(vertices),
                    "triangles": len(triangles),
                    "boundsInBodyFrame": {"min": accessor_min, "max": accessor_max}})

roots = [name for name in bodies if parent_of[name] is None]
for body in bodies:
    parent = parent_of[body]
    if parent is not None:
        nodes[node_index[parent]]["children"].append(node_index[body])

# Every one of the model's 22 bodies is assigned, so the default view can render all of them: 9 teaching
# segments carry 22 bone meshes. A segment may hold several bodies — the forearm has held ulna and radius since
# the first export — and each body keeps its true place through its own baked offset.
# Bodies the model ships as one merged mesh, split into the structures they actually hold. Each part is a
# child node of its body and carries the source mesh in the body's own frame, so the assembled skeleton is
# unchanged while the app can finally name and address spine, ribs, skull, sacrum and both hip bones.
SEGMENT_BODIES = {
    "pelvis->chest": ["pelvis_sacrum", "pelvis_r", "pelvis_l", "torso_spine", "torso_ribs", "torso_skull"],
    "kneeL->patellaL": ["patella_l"],
    "kneeR->patellaR": ["patella_r"],
    "wristL->handL": ["hand_l"],
    "wristR->handR": ["hand_r"],
    "ankleL->footL": ["talus_l", "calcn_l", "toes_l"],
    "ankleR->footR": ["talus_r", "calcn_r", "toes_r"],
    "hipL->kneeL": ["femur_l"],
    "hipR->kneeR": ["femur_r"],
    "kneeL->ankleL": ["tibia_l_shaft", "tibia_l_fibula", "patella_l", "talus_l", "calcn_l", "toes_l"],
    "kneeR->ankleR": ["tibia_r_shaft", "tibia_r_fibula", "patella_r", "talus_r", "calcn_r", "toes_r"],
    "shoulderL->elbowL": ["humerus_l"],
    "shoulderR->elbowR": ["humerus_r"],
    "elbowL->wristL": ["ulna_l", "radius_l", "hand_l"],
    "elbowR->wristR": ["ulna_r", "radius_r", "hand_r"],
}


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def normalize(value):
    length = math.sqrt(sum(component * component for component in value)) or 1.0
    return [component / length for component in value]


def segment_offset(record, proximal):
    """The 4x4 (column-major, glTF order) matrix taking this body frame into the app's segment frame."""
    low = record["boundsInBodyFrame"]["min"]
    high = record["boundsInBodyFrame"]["max"]
    axis = max(range(3), key=lambda index: high[index] - low[index])
    distal = list(proximal)
    distal[axis] = low[axis] if abs(proximal[axis] - low[axis]) > abs(proximal[axis] - high[axis]) else high[axis]
    along = normalize([distal[index] - proximal[index] for index in range(3)])
    reference = [1.0, 0.0, 0.0] if abs(along[0]) < 0.9 else [0.0, 0.0, 1.0]
    side = normalize(cross(reference, along))
    up = cross(along, side)
    half = math.sqrt(sum((distal[index] - proximal[index]) ** 2 for index in range(3))) / 2 or 1.0
    middle = [(proximal[index] + distal[index]) / 2 for index in range(3)]
    # local = D * A * (point - middle): A has the segment's basis as rows (so A = R^T) and D scales the
    # along-axis (row 1) to unit half-length while leaving the cross-section untouched, so the bone keeps its
    # true thickness and the app's own scales do the rest.
    rows = [[rows_axis[i] * (1.0 / half if i == 1 else 1.0) for i in range(3)] + [0.0]
            for rows_axis in (side, along, up)]
    rows.append([0.0, 0.0, 0.0, 1.0])
    for index in range(3):
        rows[index][3] = -sum(rows[index][column] * middle[column] for column in range(3))
    return [rows[row][column] for column in range(4) for row in range(4)]


proximal_of = {frame["childBody"]: frame["locationInChildBodyM"] for frame in joint_frames
               if frame["locationInChildBodyM"] is not None}

# A split part has no joint of its own; it sits in its body's frame, so the point that places its teaching
# segment is the one that places its body.
for _body_name, _parts in SPLIT_PARTS.items():
    for _part_name, _meshes in _parts:
        if _body_name in proximal_of:
            proximal_of[_part_name] = proximal_of[_body_name]

segments = []
for segment, body_names in SEGMENT_BODIES.items():
    for body_name in body_names:
        record = next((entry for entry in records if entry["body"] == body_name), None)
        if record is None or not record["points"]:
            continue
        # The root body has no joint frame pointing at it; its frame origin is the only meaningful proximal
        # point, and segment_offset only needs a point on the segment axis.
        proximal = proximal_of.get(body_name, [0.0, 0.0, 0.0])
        segments.append({"segment": segment, "body": body_name,
                         "offset": [round(value, 9) for value in segment_offset(record, proximal)]})


def world_box(record):
    """A body's local bounding box taken into the model frame, rotation included.

    Adding the translation alone (as an earlier version of this script did) under-reports the assembled
    height by about 12 cm, because a body's local box is rotated by its ground transform: the value has to
    come from the eight transformed corners, not from the two local corners.
    """
    rotation, translation = ground[record["body"]]
    low = record["boundsInBodyFrame"]["min"]
    high = record["boundsInBodyFrame"]["max"]
    corners = [[low[axis] if (mask >> axis) & 1 else high[axis] for axis in range(3)] for mask in range(8)]
    return [[sum(rotation[row][column] * corner[column] for column in range(3)) + translation[row]
             for corner in corners] for row in range(3)]


boxes = [world_box(record) for record in records if record["points"]]
# The GLB is authored with the root body at the origin, so the reported bounds are shifted by the root's own
# ground position — that makes them directly comparable with what a viewer loading the GLB measures.
root_shift = ground[roots[0]][1]
all_min = [min(min(box[axis]) for box in boxes) - root_shift[axis] for axis in range(3)]
all_max = [max(max(box[axis]) for box in boxes) - root_shift[axis] for axis in range(3)]

gltf = {
    "asset": {"version": "2.0", "generator": "ShowYourMuscle full-body skeleton export",
              "extras": {"sourceModel": MODEL.name,
                         "sourceSha256": __import__("hashlib").sha256(MODEL.read_bytes()).hexdigest().upper(),
                         "referenceHeightCm": REFERENCE_HEIGHT_CM,
                         "referenceHeightCmNote":
                             "身高缩放的基准；缩放因子的定义与 OpenSim ScaleSet 一致：身高因子作用于全部体段，"
                             "围度因子只作用于对应体段的横向两轴",
                         "segmentGirthBodies": SEGMENT_GIRTH_BODIES,
                         "segments": segments,
                         "substitutedMeshes": True,
                         "substitutionNote":
                             "模型自带的 *_lvs.vtp 手骨网格不在任何本地数据集中，因此按名字改用本地存在的网格；"
                             "左臂没有左侧网格，由右侧网格镜像得到（同时翻转三角形绕向）"}},
    "scene": 0,
    "scenes": [{"nodes": [node_index[name] for name in roots], "name": "full body skeleton"}],
    "nodes": nodes,
    "meshes": meshes,
    "accessors": accessors,
    "bufferViews": buffer_views,
    "buffers": [{"byteLength": len(binary)}],
    "materials": [{"name": "bone", "pbrMetallicRoughness": {"baseColorFactor": [0.86, 0.84, 0.78, 1.0],
                                                            "metallicFactor": 0.0, "roughnessFactor": 0.65}}],
}

json_chunk = json.dumps(gltf, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
binary_chunk = bytes(binary) + b"\x00" * ((4 - len(binary) % 4) % 4)
glb = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(json_chunk) + 8 + len(binary_chunk))
glb += struct.pack("<II", len(json_chunk), 0x4E4F534A) + json_chunk
glb += struct.pack("<II", len(binary_chunk), 0x004E4942) + binary_chunk
OUTPUT_GLB.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_GLB.write_bytes(glb)

report = {
    "status": "full_body_skeleton_export_geometry_only",
    "model": {"path": str(MODEL.relative_to(ROOT)).replace("\\", "/"),
              "sha256": gltf["asset"]["extras"]["sourceSha256"], "bodies": OPEN_SIM_BODIES},
    "output": {"path": str(OUTPUT_GLB.relative_to(ROOT)).replace("\\", "/"), "bytes": len(glb),
               "nodes": len(nodes), "meshes": len(meshes),
               "triangles": sum(record["triangles"] for record in records)},
    "referenceHeightCm": REFERENCE_HEIGHT_CM,
    "pairing": PAIRING,
    "segmentGirthBodies": SEGMENT_GIRTH_BODIES,
    "segments": segments,
    "roots": roots,
    "jointFrames": joint_frames,
    "boundsInExportM": {"min": all_min, "max": all_max,
                        "heightM": all_max[1] - all_min[1], "widthM": all_max[0] - all_min[0]},
    "bodies": records,
    "limitations": [
        "这是 OpenSim 模型的骨骼几何，不是用户本人的解剖测量；缩放模型只是几何近似",
        "手骨网格由本地存在的替代网格代替，左臂由右侧镜像，因此手指细节不是模型自带的那一份",
        "模型自带的躯干只有 thorax/脊柱/肋骨/颅骨四块网格，没有单独的颈部与面部细节",
        "导出的是模型默认姿态下的刚体骨架；本文件不包含肌肉路径、肌肉网格或任何力的结果",
    ],
}
OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps({
    "glb": str(OUTPUT_GLB), "bytes": len(glb), "nodes": len(nodes), "meshes": len(meshes),
    "triangles": report["output"]["triangles"],
    "heightM": round(report["boundsInExportM"]["heightM"], 4),
    "widthM": round(report["boundsInExportM"]["widthM"], 4),
    "boundsMin": [round(value, 3) for value in all_min], "roots": roots,
}, ensure_ascii=False, indent=2))
