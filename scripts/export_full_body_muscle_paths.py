"""Export the 80 muscles of the selected OpenSim model as rendering-ready paths.

The default view draws 80 OpenSim paths; this is the data layer that drives them. For every
muscle in `RajagopalLaiUhlrich2023` it records the current path (the points a renderer can sweep a tube along, in
the ground frame at the model's default pose, the same pose the skeleton export uses) plus which wrapping
surfaces the path runs over, and a table of those surfaces with their type and radius.

Read-only with respect to the model: nothing is scaled, posed or simulated. The JSON is the deliverable.
"""

import json
import os
import sys
from pathlib import Path

import opensim as osim

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / ".cache/model-candidates/opensim-models/Models/Rajagopal/RajagopalLaiUhlrich2023.osim"
OUTPUT = ROOT / "docs/data/full_body_muscle_paths.json"


def wrap_names(geometry_path):
    """Wrap object names on a muscle's path, across the OpenSim API spellings."""
    for getter in ("getWrapObjectSet", "getWrapSet", "getPathWrapSet"):
        accessor = getattr(geometry_path, getter, None)
        if accessor is None:
            continue
        try:
            wrap_set = accessor()
        except Exception:
            continue
        names = []
        for index in range(wrap_set.getSize()):
            entry = wrap_set.get(index)
            for name_getter in ("getWrapObjectName", "getWrapObject"):
                value = getattr(entry, name_getter, None)
                if value is None:
                    continue
                try:
                    text = value()
                except Exception:
                    continue
                names.append(text if isinstance(text, str) else str(text))
                break
        return names
    return []


def wrap_object_table(model):
    """Every wrap object in the model: its body, type and radius where the type has one."""
    table = []
    for index in range(model.getBodySet().getSize()):
        body = model.getBodySet().get(index)
        accessor = getattr(body, "getWrapObjectSet", None)
        if accessor is None:
            continue
        try:
            wrap_set = accessor()
        except Exception:
            continue
        for wrap_index in range(wrap_set.getSize()):
            wrap = wrap_set.get(wrap_index)
            entry = {"body": body.getName(), "name": wrap.getName(), "type": wrap.getConcreteClassName()}
            for attribute in ("getRadius", "getXRadius", "getYRadius"):
                getter = getattr(wrap, attribute, None)
                if getter is None:
                    continue
                try:
                    entry[attribute[3:].lower()] = round(float(getter()), 6)
                except Exception:
                    pass
            table.append(entry)
    return table


def main():
    # OpenSim cannot open a path containing non-ASCII characters (the repository sits under a Chinese name), so
    # the model is loaded by bare file name from its own directory — the same route the skeleton export uses.
    os.chdir(MODEL.parent)
    model = osim.Model(MODEL.name)
    state = model.initSystem()
    muscles = []
    default_joints = {}
    for index in range(model.getJointSet().getSize()):
        joint = model.getJointSet().get(index)
        location = joint.getParentFrame().getPositionInGround(state)
        default_joints[joint.getName()] = [round(location.get(axis), 6) for axis in range(3)]
    total_points = 0
    with_wrap = 0
    wrap_use = {}
    for index in range(model.getMuscles().getSize()):
        muscle = model.getMuscles().get(index)
        geometry_path = muscle.getGeometryPath()
        path = geometry_path.getCurrentPath(state)
        points = []
        point_bodies = []
        for point_index in range(path.getSize()):
            point = path.get(point_index)
            location = None
            # A current-path entry is an AbstractPathPoint; its ground coordinates need the state.
            for getter in ("getLocationInGround", "getLocation"):
                accessor = getattr(point, getter, None)
                if accessor is None:
                    continue
                try:
                    location = accessor(state) if getter.endswith("InGround") else accessor()
                except Exception:
                    continue
                break
            if location is None:
                continue
            points.append([round(location.get(0), 6), round(location.get(1), 6), round(location.get(2), 6)])
            point_bodies.append(point.getParentFrame().getName())
        names = wrap_names(geometry_path)
        if names:
            with_wrap += 1
        for name in names:
            wrap_use[name] = wrap_use.get(name, 0) + 1
        total_points += len(points)
        muscles.append({
            "name": muscle.getName(),
            "type": muscle.getConcreteClassName(),
            "pathPoints": points,
            "pathBodies": point_bodies,
            "wrappingSurfaces": names,
        })
    table = wrap_object_table(model)
    report = {
        "status": "source_model_muscle_paths_only",
        "model": MODEL.name,
        "pose": "model default pose (initSystem), ground frame",
        "muscleCount": len(muscles),
        "totalPathPoints": total_points,
        "defaultJointsM": default_joints,
        "musclesWithWrapping": with_wrap,
        "wrappingSurfaceUse": dict(sorted(wrap_use.items())),
        "wrapObjects": table,
        "muscles": muscles,
        "limits": [
            "path points only: no pennation, no tendon length, no force",
            "no muscle mesh geometry: these are the polylines a renderer sweeps",
            "wrapping surfaces are recorded by name and radius, not as renderable tubes",
            "pathBodies attach current path points to source bodies for approximate rigid motion; wrapping is not recalculated after an arbitrary edit",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "muscles": len(muscles),
        "pathPoints": total_points,
        "withWrapping": with_wrap,
        "wrapObjects": len(table),
        "sample": muscles[0]["name"] if muscles else None,
        "samplePoints": len(muscles[0]["pathPoints"]) if muscles else 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
