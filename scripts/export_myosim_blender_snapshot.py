"""Export a compiled MyoSim neutral pose for a Blender structural review.

The output is a static research snapshot. Runtime wrapping tangent points
are included, but arcs on wrapping surfaces are displayed as chords.
"""

import json
import sys
from pathlib import Path

import numpy as np

from probe_myosim_fullbody import ROOT, SOURCE, model_import_path

OUTPUT = ROOT / ".cache/myosim_fullbody_neutral_snapshot.json"


def main():
    sys.path.insert(0, str(model_import_path()))
    import mujoco
    import myo_sim

    model, data = myo_sim.load("myofullbody")
    mujoco.mj_forward(model, data)
    # Region boundaries below are specific to the audited upstream assembly.
    boundaries = {0: "Ps_L1_VB_r", 209: "IO6_l", 210: "DELT1",
                  272: "UI_UB5", 273: "DELT1_l", 335: "UI_UB5_l",
                  336: "addbrev_r", 415: "vasmed_l"}
    for index, expected in boundaries.items():
        actual = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, index)
        if actual != expected:
            raise AssertionError(f"MyoSim actuator layout changed at {index}: {actual}")
    meshes = {}
    geoms = []
    for geom_id in range(model.ngeom):
        if model.geom_type[geom_id] != int(mujoco.mjtGeom.mjGEOM_MESH):
            continue
        mesh_id = int(model.geom_dataid[geom_id])
        if mesh_id < 0:
            raise AssertionError("Mesh geom without mesh data")
        if mesh_id not in meshes:
            vert_adr = int(model.mesh_vertadr[mesh_id])
            face_adr = int(model.mesh_faceadr[mesh_id])
            vertices = model.mesh_vert[vert_adr:vert_adr + model.mesh_vertnum[mesh_id]]
            faces = model.mesh_face[face_adr:face_adr + model.mesh_facenum[mesh_id]]
            if np.max(faces) >= len(vertices):
                raise AssertionError(f"Mesh {mesh_id} face index out of range")
            meshes[mesh_id] = {
                "vertices": vertices.round(6).tolist(),
                "faces": faces.tolist(),
            }
        body_id = int(model.geom_bodyid[geom_id])
        geoms.append({
            "id": geom_id,
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id),
            "body": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id),
            "meshId": mesh_id,
            "worldPositionM": data.geom_xpos[geom_id].round(8).tolist(),
            "worldRotation": data.geom_xmat[geom_id].reshape(3, 3).round(8).tolist(),
        })
    paths = []
    unwrapped_max_error = 0.0
    active_wrapped_count = 0
    declared_wrapped_count = 0
    active_wrapped_max_length_difference = 0.0
    runtime_points = data.wrap_xpos.reshape(-1, 3)
    runtime_objects = data.wrap_obj.reshape(-1)
    for actuator_id in range(model.nu):
        if model.actuator_trntype[actuator_id] != int(mujoco.mjtTrn.mjTRN_TENDON):
            raise AssertionError("Non-tendon actuator in full-body model")
        tendon_id = int(model.actuator_trnid[actuator_id, 0])
        first = int(model.tendon_adr[tendon_id])
        last = first + int(model.tendon_num[tendon_id])
        sites = []
        wrapping_count = 0
        for wrap_id in range(first, last):
            kind = int(model.wrap_type[wrap_id])
            if kind == int(mujoco.mjtWrap.mjWRAP_SITE):
                site_id = int(model.wrap_objid[wrap_id])
                sites.append(data.site_xpos[site_id].round(8).tolist())
            elif kind in (int(mujoco.mjtWrap.mjWRAP_SPHERE),
                          int(mujoco.mjtWrap.mjWRAP_CYLINDER)):
                wrapping_count += 1
        if len(sites) < 2:
            raise AssertionError(f"Actuator {actuator_id} has fewer than 2 path sites")
        path_start = int(data.ten_wrapadr[tendon_id])
        path_count = int(data.ten_wrapnum[tendon_id])
        display = runtime_points[path_start:path_start + path_count]
        active_wrapping = bool(np.any(runtime_objects[path_start:path_start +
                                                       path_count] >= 0))
        if len(display) < 2:
            raise AssertionError(f"Tendon {tendon_id} has no runtime path")
        polyline = sum(float(np.linalg.norm(b - a))
                       for a, b in zip(display, display[1:]))
        length = float(data.ten_length[tendon_id])
        if wrapping_count:
            declared_wrapped_count += 1
        if active_wrapping:
            active_wrapped_count += 1
            active_wrapped_max_length_difference = max(
                active_wrapped_max_length_difference, abs(polyline - length))
        else:
            unwrapped_max_error = max(unwrapped_max_error, abs(polyline - length))
        paths.append({
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR,
                                       actuator_id),
            "modelRegion": ("torso" if actuator_id < 210 else
                            "right_arm" if actuator_id < 273 else
                            "left_arm" if actuator_id < 336 else "legs"),
            "tendon": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_TENDON,
                                         tendon_id),
            "sitesWorldM": sites,
            "displayPathWorldM": display.round(8).tolist(),
            "modelTendonLengthM": round(length, 8),
            "displayPolylineLengthM": round(polyline, 8),
            "declaredWrappingObjectCount": wrapping_count,
            "activeWrapping": active_wrapping,
            "visualPathIncomplete": active_wrapping,
        })
    if not meshes or not geoms or len(paths) != 416:
        raise AssertionError("Incomplete full-body snapshot")
    if unwrapped_max_error > 1e-5:
        raise AssertionError(f"Unwrapped tendon length mismatch {unwrapped_max_error}")
    result = {
        "status": "neutral_static_structure_only_no_personalization_or_force",
        "source": "MyoHub/myo_sim; see docs/参考资料.md for provenance",
        "sourcePath": str(SOURCE.relative_to(ROOT)),
        "coordinateSystem": "MuJoCo XYZ in metres; Blender scene uses same Z-up axes",
        "meshCount": len(meshes),
        "compiledMeshAssets": int(model.nmesh),
        "meshGeometries": len(geoms),
        "muscleActuators": len(paths),
        "declaredWrappingPathCount": declared_wrapped_count,
        "wrappedVisualPathCount": active_wrapped_count,
        "unwrappedMaxLengthErrorM": unwrapped_max_error,
        "activeWrappedMaxChordLengthDifferenceM": active_wrapped_max_length_difference,
        "meshes": meshes,
        "geoms": geoms,
        "paths": paths,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, separators=(",", ":")) + "\n",
                      encoding="utf-8")
    print(json.dumps({"meshes": len(meshes), "geoms": len(geoms),
                      "muscles": len(paths),
                      "declaredWrappedPaths": declared_wrapped_count,
                      "activeWrappedPaths": active_wrapped_count,
                      "unwrappedMaxLengthErrorM": unwrapped_max_error,
                      "activeWrappedMaxChordLengthDifferenceM":
                          active_wrapped_max_length_difference,
                      "output": str(OUTPUT.relative_to(ROOT))}, indent=2))


if __name__ == "__main__":
    main()
