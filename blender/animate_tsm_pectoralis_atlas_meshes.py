"""Build three bench- or press-pose atlas pectoralis research mesh tracks.

Four proxy landmarks register the start pose. Thorax/clavicle rigid motion plus
linear endpoint corrections follows TSM muscle-tendon paths. This is a visual
deformation experiment, not fiber strain, activation or muscle force.
"""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "public/models/z_anatomy_reference.glb"
FIT = ROOT / "docs/data/tsm_pectoralis_landmark_fit_screen.json"
AUDIT = ROOT / "docs/data/tsm_pectoralis_dynamic_registration_audit.json"
PAIRS = (
    ("Clavicular head of pectoralis major muscle.r", "PectoralisMajorClavicle_S", "clavicle"),
    ("Sternocostal head of pectoralis major muscle.r", "PectoralisMajorThorax_M", "thorax"),
    ("(Abdominal part of pectoralis major muscle).r", "PectoralisMajorThorax_I", "thorax"),
)


def to_blender(point):
    x, y, z = point
    return Vector((x, -z, y))


def body_matrix(frame, name):
    data = frame["blenderBodyFrames"][name]
    matrix = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            matrix[row][col] = data["rotationRows"][row][col]
    matrix.translation = Vector(data["translationM"])
    return matrix


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    exercise = args[0] if args else "press"
    if exercise not in ("bench", "press"):
        raise ValueError("Expected bench or press")
    blend_weight = .8 if exercise == "bench" else 1.0
    base = ROOT / f"assets/blender/opensim_tsm_{exercise}_pectoralis_path_proxies.blend"
    lookup = ROOT / f"public/data/{exercise}_tsm_reference.json"
    output = ROOT / f"assets/blender/opensim_tsm_{exercise}_pectoralis_atlas_probe.blend"
    preview = ROOT / f"assets/blender/opensim_tsm_{exercise}_pectoralis_atlas_probe.png"
    report = ROOT / f"docs/data/tsm_{exercise}_pectoralis_atlas_probe.json"
    frames = json.loads(lookup.read_text(encoding="utf-8"))["frames"]
    fit_report = json.loads(FIT.read_text(encoding="utf-8"))
    record = next(item for item in fit_report["records"]
                  if item["exercise"] == exercise and item["method"] ==
                  "medial_clavicle_plus_pectoral_origin_proxy")
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    case_audit = next(item for item in audit["cases"] if item["exercise"] == exercise)
    scenario = "endpoint_blend_80" if exercise == "bench" else "endpoint_blend"
    lower = "endpointBlend80MinimumEdgeLengthRatio" if exercise == "bench" else "endpointBlendMinimumEdgeLengthRatio"
    upper = "endpointBlend80MaximumEdgeLengthRatio" if exercise == "bench" else "endpointBlendMaximumEdgeLengthRatio"
    if len(frames) != 101 or len(case_audit["muscles"]) != 3:
        raise ValueError(f"{exercise} path or geometry audit is incomplete")
    for item in case_audit["muscles"]:
        if (item["scenarios"][scenario]["worst"]["maximumCm"] > 4.5 or
                item[lower] < .5 or item[upper] > 1.5):
            raise ValueError(f"Coarse {exercise} geometry screen failed: {item['modelMuscle']}")

    bpy.ops.wm.open_mainfile(filepath=str(base))
    scene = bpy.context.scene
    scene.frame_set(1)
    for model_name in (name for _, name, _ in PAIRS):
        proxy = bpy.data.objects.get(f"{model_name}_{exercise}_path_volume_proxy")
        if proxy:
            proxy.hide_render = True
            proxy.hide_viewport = True
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(ATLAS))
    imported = set(bpy.data.objects) - before
    atlas_objects = {obj.name: obj for obj in imported}
    fit = Matrix(record["atlasToModelBlenderRows"])
    group = bpy.data.collections.new("09_Atlas_Pectoralis_Research_Deformation_Not_Force")
    scene.collection.children.link(group)
    sample_indices = (0, 25, 50, 75, 100)
    colors = ((.82, .43, .53), (.93, .55, .60), (.74, .35, .52))
    results = []
    for color, (atlas_name, model_name, parent) in zip(colors, PAIRS):
        source = atlas_objects[atlas_name]
        base_vertices = [fit @ source.matrix_world @ vertex.co for vertex in source.data.vertices]
        faces = [tuple(poly.vertices) for poly in source.data.polygons]
        base_path = [to_blender(point) for point in frames[0]["muscles"]
                     [model_name]["viewerPathM"]]
        axis = base_path[-1] - base_path[0]
        axis_sq = axis.length_squared
        if axis_sq < .001:
            raise ValueError(f"Degenerate baseline path: {model_name}")
        fractions = [min(1, max(0, (vertex - base_path[0]).dot(axis) / axis_sq))
                     for vertex in base_vertices]
        base_body_inverse = body_matrix(frames[0], parent).inverted()
        mesh = bpy.data.meshes.new(f"{model_name}_atlas_research_mesh")
        mesh.from_pydata(base_vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(f"atlas_{model_name}_{exercise}_probe", mesh)
        group.objects.link(obj)
        mat = bpy.data.materials.new(f"{model_name} · anatomical candidate not force")
        mat.diffuse_color = (*color, 1)
        mat.use_nodes = True
        shader = next(node for node in mat.node_tree.nodes
                      if node.type == "BSDF_PRINCIPLED")
        shader.inputs["Base Color"].default_value = mat.diffuse_color
        shader.inputs["Roughness"].default_value = .66
        mesh.materials.append(mat)
        obj.shape_key_add(name="Four-proxy atlas fit at first pose", from_mix=False)
        sampled = {}
        for index, frame in enumerate(frames):
            delta = body_matrix(frame, parent) @ base_body_inverse
            path = [to_blender(point) for point in frame["muscles"][model_name]
                    ["viewerPathM"]]
            origin_delta = path[0] - delta @ base_path[0]
            insertion_delta = path[-1] - delta @ base_path[-1]
            key = obj.shape_key_add(name=f"TSM endpoint blend {index + 1:03d}",
                                    from_mix=False)
            for vertex_index, (vertex, fraction) in enumerate(zip(base_vertices, fractions)):
                key.data[vertex_index].co = (delta @ vertex +
                                             blend_weight * (origin_delta * (1 - fraction) +
                                                             insertion_delta * fraction))
            if index in sample_indices:
                sampled[index] = {str(v): list(key.data[v].co)
                                  for v in (0, len(base_vertices) // 2,
                                            len(base_vertices) - 1)}
            number = index + 1
            key.value = 0
            if number > 1:
                key.keyframe_insert(data_path="value", frame=number - 1)
            key.value = 1
            key.keyframe_insert(data_path="value", frame=number)
            key.value = 0
            if number < len(frames):
                key.keyframe_insert(data_path="value", frame=number + 1)
        obj["source"] = "Z-Anatomy / BodyParts3D, CC BY-SA 4.0"
        obj["model_path"] = model_name
        obj["status"] = "geometric research deformation; not attachment, strain or force"
        obj["fit_method"] = record["method"]
        obj["rigid_parent"] = parent
        results.append({"atlasMesh": atlas_name, "modelMuscle": model_name,
                        "rigidParent": parent, "vertexCount": len(base_vertices),
                        "shapeKeyCount": len(frames) + 1,
                        "sampledVerticesBlenderM": sampled})
    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    for name in ("01_TSM_Right_Arm_Bones_Reference",
                 "02_TSM_Muscle_Paths_Reference",
                 "05_TSM_Rigid_Body_Frames_Review",
                 "07_Biceps_Long_Head_Research_Deformation",
                 "08_Pectoralis_Path_Volume_Proxies"):
        collection = bpy.data.collections.get(name)
        if collection:
            collection.hide_render = True
            collection.hide_viewport = True
    scene["pectoralis_atlas_probe_status"] = "research geometry, not fiber strain or force"
    scene.frame_set(51)
    target = Vector((.34, -.02, .88 if exercise == "bench" else 1.59))
    camera = scene.camera
    camera.location = (.76, -1.25, 1.02 if exercise == "bench" else 1.73)
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = .85
    scene.render.filepath = str(preview)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    bpy.ops.render.render(write_still=True)
    report.write_text(json.dumps({
        "status": "research_pectoralis_mesh_motion_not_anatomical_or_force_validation",
        "sourceScene": str(base.relative_to(ROOT)),
        "scene": str(output.relative_to(ROOT)),
        "preview": str(preview.relative_to(ROOT)),
        "exercise": exercise,
        "endpointCorrectionWeight": blend_weight,
        "fit": record["method"],
        "method": "Rigid clavicle/thorax transport plus clamped initial-path endpoint-axis fraction times endpoint correction and exercise-specific correction weight, as screened across 101 frames in the linked audit",
        "sourceAudit": str(AUDIT.relative_to(ROOT)),
        "muscles": results,
        "limits": ["Synthetic press poses are not measured personal actions",
                   "Atlas-to-model proxy fit includes the middle muscle path origin",
                   "Visual mesh deformation does not identify anatomical attachments, fiber strain, activation or force"],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PECTORALIS_ATLAS_PROBE", output, preview)


if __name__ == "__main__":
    main()
