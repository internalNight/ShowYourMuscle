"""Attach a physical barbell body to a bilateral public squat model.

This is a model-assembly probe. It checks mass accounting, COM, connectivity,
and muscle preservation. The torso attachment is a research assumption; no
barbell trajectory, foot contact, muscle activation or personal force is solved.
"""

import argparse
import json
import math
import shutil
import tempfile
from pathlib import Path

import opensim as osim
import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache/lower-limb-raw"
SUBJECTS = ("AB01", "AB02", "AB03", "AB05", "AB06", "AB07", "AB08",
            "AB09", "AB10", "AB11", "AB12", "AB13")
IK_INTERVALS = {"AB01": (50, 52), "AB02": (23, 25)}
BAR_LENGTH_M = 2.2
BAR_RADIUS_M = 0.014
BAR_CENTER_LOCAL_TORSO_M = (-0.03, 0.53, 0.0)


def xyz(vector):
    return [float(vector.get(axis)) for axis in range(3)]


def deepest_record(subject):
    if subject not in IK_INTERVALS:
        return None
    start, end = IK_INTERVALS[subject]
    path = ROOT / ".cache/lower-limb" / f"{subject}_ik_{start:g}_{end:g}.mot"
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines.index("endheader")
    names = lines[header + 1].split()
    rows = [[float(value) for value in line.split()]
            for line in lines[header + 2:] if line.strip()]
    knee_column = names.index("knee_angle_r")
    values = min(rows, key=lambda row: row[knee_column])
    return {"timeS": values[0], "rightKneeAngleDeg": values[knee_column],
            "coordinates": dict(zip(names[1:], values[1:]))}


def apply_record(model, state, record):
    if record is None:
        return
    coordinates = model.getCoordinateSet()
    for name, value in record["coordinates"].items():
        angular = not name.endswith(("_tx", "_ty", "_tz"))
        coordinates.get(name).setValue(state, math.radians(value) if angular else value,
                                       False)
    state.setTime(record["timeS"])
    model.realizePosition(state)


def reference_bar_rotation(model, state):
    """Orient a torso-welded shaft laterally in the reference ground pose."""
    torso = model.getBodySet().get("torso")
    transform = torso.getRotationInGround(state)
    ground_from_torso = np.array([[transform.get(row, column)
                                   for column in range(3)] for row in range(3)])
    # WeldJoint's Vec3 orientation matches intrinsic XYZ Euler angles here.
    angles = Rotation.from_matrix(ground_from_torso.T).as_euler("XYZ")
    return osim.Vec3(*map(float, angles))


def add_barbell(model, mass_kg, forward_offset_m, parent_rotation):
    radius, length = BAR_RADIUS_M, BAR_LENGTH_M
    transverse_inertia = mass_kg * (3 * radius ** 2 + length ** 2) / 12
    axial_inertia = mass_kg * radius ** 2 / 2
    bar = osim.Body("barbell_shaft", mass_kg, osim.Vec3(0),
                    osim.Inertia(transverse_inertia, transverse_inertia, axial_inertia))
    torso = model.updBodySet().get("torso")
    local_position = osim.Vec3(BAR_CENTER_LOCAL_TORSO_M[0] + forward_offset_m,
                               BAR_CENTER_LOCAL_TORSO_M[1], BAR_CENTER_LOCAL_TORSO_M[2])
    # In the reference pose the shaft's long local z axis is global lateral z.
    weld = osim.WeldJoint("barbell_to_torso", torso, local_position, parent_rotation,
                          bar, osim.Vec3(0), osim.Vec3(0))
    model.addBody(bar)
    model.addJoint(weld)
    return bar


def inspect(subject, bar_kg):
    source = SOURCE / subject / "Models" / f"{subject}-Scaled1.osim"
    with tempfile.NamedTemporaryFile(prefix=f"muscle_atlas_{subject}_", suffix=".osim",
                                     delete=False) as handle:
        temporary = Path(handle.name)
    shutil.copyfile(source, temporary)
    try:
        record = deepest_record(subject)
        base = osim.Model(str(temporary))
        base_state = base.initSystem()
        apply_record(base, base_state, record)
        base_mass = float(base.getTotalMass(base_state))
        base_com = xyz(base.calcMassCenterPosition(base_state))
        base_muscles = base.getMuscles().getSize()
        bar_rotation = reference_bar_rotation(base, base_state)
        rows = []
        for offset_cm in (-6, 0, 6):
            model = osim.Model(str(temporary))
            bar = add_barbell(model, bar_kg, offset_cm / 100, bar_rotation)
            state = model.initSystem()
            apply_record(model, state, record)
            bar_com = xyz(bar.findStationLocationInGround(state, osim.Vec3(0)))
            bar_end_a = xyz(bar.findStationLocationInGround(state, osim.Vec3(0, 0, -BAR_LENGTH_M / 2)))
            bar_end_b = xyz(bar.findStationLocationInGround(state, osim.Vec3(0, 0, BAR_LENGTH_M / 2)))
            bar_axis = [(bar_end_b[axis] - bar_end_a[axis]) / BAR_LENGTH_M
                        for axis in range(3)]
            if max(abs(bar_axis[0]), abs(bar_axis[1]), abs(bar_axis[2] - 1)) > 1e-6:
                raise RuntimeError(f"Barbell is not lateral in {subject} reference pose")
            total_mass = float(model.getTotalMass(state))
            loaded_com = xyz(model.calcMassCenterPosition(state))
            expected = [(base_mass * base_com[axis] + bar_kg * bar_com[axis]) /
                        (base_mass + bar_kg) for axis in range(3)]
            error = max(abs(loaded_com[axis] - expected[axis]) for axis in range(3))
            if abs(total_mass - base_mass - bar_kg) > 1e-7 or error > 1e-7:
                raise RuntimeError(f"Mass or COM accounting failed for {subject} {offset_cm}")
            if model.getMuscles().getSize() != base_muscles or base_muscles != 54:
                raise RuntimeError(f"Muscle set changed for {subject}")
            roundtrip = None
            if offset_cm == 0:
                with tempfile.NamedTemporaryFile(prefix=f"muscle_atlas_loaded_{subject}_",
                                                 suffix=".osim", delete=False) as handle:
                    serialized = Path(handle.name)
                try:
                    model.printToXML(str(serialized))
                    reloaded = osim.Model(str(serialized))
                    reloaded_state = reloaded.initSystem()
                    apply_record(reloaded, reloaded_state, record)
                    reloaded_mass = float(reloaded.getTotalMass(reloaded_state))
                    reloaded_com = xyz(reloaded.calcMassCenterPosition(reloaded_state))
                    reload_com_error = max(abs(reloaded_com[axis] - loaded_com[axis])
                                           for axis in range(3))
                    if (abs(reloaded_mass - total_mass) > 1e-7 or
                            reload_com_error > 1e-7 or
                            reloaded.getBodySet().getSize() != 13 or
                            reloaded.getJointSet().getSize() != 13 or
                            reloaded.getMuscles().getSize() != 54):
                        raise RuntimeError(f"Serialized model changed for {subject}")
                    roundtrip = {"passed": True, "comErrorM": reload_com_error,
                                 "bodyCount": reloaded.getBodySet().getSize(),
                                 "jointCount": reloaded.getJointSet().getSize(),
                                 "muscleCount": reloaded.getMuscles().getSize()}
                finally:
                    serialized.unlink(missing_ok=True)
            rows.append({"barOffsetCm": offset_cm, "barComGroundM": bar_com,
                         "barAxisGroundUnit": bar_axis,
                         "loadedComGroundM": loaded_com,
                         "totalMassKg": total_mass,
                         "comMassWeightedErrorM": error,
                         "serializedRoundtrip": roundtrip,
                         "bodyCount": model.getBodySet().getSize(),
                         "jointCount": model.getJointSet().getSize(),
                         "muscleCount": model.getMuscles().getSize()})
        return {"subject": subject,
                "poseContext": "deepest_available_experimental_IK" if record else "source_model_default_not_a_standing_pose",
                "ikTimeS": record["timeS"] if record else None,
                "ikRightKneeAngleDeg": record["rightKneeAngleDeg"] if record else None,
                "baseMassKg": base_mass,
                "baseComGroundM": base_com, "baseMuscleCount": base_muscles,
                "barbellTorsoRotationRad": xyz(bar_rotation),
                "barbellScenarios": rows}
    finally:
        temporary.unlink(missing_ok=True)


def main():
    osim.Logger.setLevelString("Error")
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects", nargs="+", default=list(SUBJECTS))
    parser.add_argument("--bar-kg", type=float, default=20.0)
    args = parser.parse_args()
    if args.bar_kg <= 0 or not math.isfinite(args.bar_kg):
        parser.error("bar-kg must be finite and positive")
    rows = [inspect(subject, args.bar_kg) for subject in args.subjects]
    result = {
        "status": "bilateral_barbell_assembly_probe_not_validated_personal_dynamics",
        "source": "Scherpereel et al. 2023 public scaled gait2354 OpenSim models",
        "barbellMassKg": args.bar_kg,
        "barbellLengthM": BAR_LENGTH_M,
        "barbellLocalTorsoM": list(BAR_CENTER_LOCAL_TORSO_M),
        "connection": "one WeldJoint from torso to a cylindrical barbell body",
        "limitations": ["torso attachment point is assumed, not a measured high-bar position",
                        "model has no upper limbs or barbell grip constraints",
                        "no measured bar path, foot contact, net joint moments or muscle forces",
                        "54 maximum isometric force parameters remain unpersonalized"],
        "subjects": rows,
    }
    output = ROOT / "docs/data/bilateral_barbell_model_probe.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"subjects": len(rows), "first": rows[0],
                      "maxComErrorM": max(s["comMassWeightedErrorM"] for row in rows
                                          for s in row["barbellScenarios"])}, indent=2))


if __name__ == "__main__":
    main()
