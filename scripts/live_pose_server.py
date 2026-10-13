"""Serve the built web app with on-demand OpenSim posture evaluation.

Run with an OpenSim 4.6 Python environment:
    python scripts/live_pose_server.py --port 5173
The browser and API share an origin. The model is kept in memory and every
manual change recomputes body transforms and all 520 muscle-tendon paths.
"""

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import threading

import opensim as osim
from scipy.optimize import least_squares

from export_unified_opensim import frame, plant_heels


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
MODEL_DIR = ROOT / "assets/opensim"
MODEL_FILE = MODEL_DIR / "cyclistFullBodyMuscle.osim"
CONTROLS = {
    "pelvis_tilt": (-1.5, 1.5),
    "hip_flexion": (-0.5, 2.0),
    "knee_angle": (0.0, 2.4),
    "ankle_angle": (-0.6, 0.5),
    "elv_angle": (-1.5, 1.5),
    "shoulder_elv": (0.0, 3.05),
    "elbow_flex": (0.0, 2.5),
}


def coordinate_values(controls):
    if not isinstance(controls, dict) or set(controls) - set(CONTROLS):
        raise ValueError("Unknown pose control")
    values = {}
    for name, raw in controls.items():
        if isinstance(raw, bool) or not isinstance(raw, (float, int)) or not math.isfinite(raw):
            raise ValueError(f"{name} must be a finite number")
        low, high = CONTROLS[name]
        if raw < low or raw > high:
            raise ValueError(f"{name} outside [{low}, {high}]")
        if name == "pelvis_tilt":
            values[name] = raw
        elif name in ("hip_flexion", "knee_angle", "ankle_angle", "elv_angle", "elbow_flex"):
            values[f"{name}_r"] = raw
            values[f"{name}_l"] = raw
        elif name == "shoulder_elv":
            values["shoulder_elv_r"] = raw
            values["shoulder_elv_l"] = -raw
    return values


def prepare_model():
    if not DIST.joinpath("index.html").is_file():
        raise FileNotFoundError("Build the web app first: npm run build")
    if not MODEL_FILE.is_file():
        raise FileNotFoundError(MODEL_FILE)
    os.chdir(MODEL_DIR)
    model = osim.Model(MODEL_FILE.name)
    coordinates = model.getCoordinateSet()
    coordinates.get("shoulder_elv_r").setRangeMax(3.1)
    coordinates.get("shoulder_elv_l").setRangeMin(-3.1)
    state = model.initSystem()
    bodies = [model.getBodySet().get(i).getName()
              for i in range(model.getBodySet().getSize())]
    muscles = [model.getMuscles().get(i)
               for i in range(model.getMuscles().getSize())]
    neutral = frame(model, state, bodies, muscles, {})
    reference = json.loads((ROOT / "public/data/unified_opensim_reference.json").read_text(encoding="utf-8"))
    if bodies != reference["bodyNames"] or [m.getName() for m in muscles] != reference["muscleNames"]:
        raise ValueError("Live OpenSim model does not match the exported viewer model")
    feet = [neutral["bodies"][bodies.index(f"calcn_{side}")]["p"] for side in ("r", "l")]
    ground = (sum(p[0] for p in feet) / 2, sum(p[1] for p in feet) / 2)
    return model, bodies, muscles, ground


def make_handler(model, bodies, muscles, ground):
    model_lock = threading.Lock()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(DIST), **kwargs)

        def json_reply(self, status, value):
            payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == "/api/health":
                self.json_reply(200, {"ready": True, "model": MODEL_FILE.name,
                                      "bodies": len(bodies), "muscles": len(muscles)})
                return
            return super().do_GET()

        def do_POST(self):
            if self.path not in ("/api/pose", "/api/ik"):
                self.json_reply(404, {"error": "Unknown API route"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 8192:
                    raise ValueError("Pose request must be 1–8192 bytes")
                request = json.loads(self.rfile.read(size))
                controls = request.get("controls")
                values = coordinate_values(controls)
                with model_lock:
                    state = model.initSystem()
                    if request.get("plantFeet", True):
                        values.update({"pelvis_tx": 0.0, "pelvis_ty": 0.93})
                        plant_heels(model, state, values, ground[1], ground[0])
                        state = model.initSystem()
                    if self.path == "/api/ik":
                        body = request.get("body")
                        target = request.get("target")
                        if body not in ("hand_r", "hand_l") or not isinstance(target, list) or len(target) != 3 or not all(
                                isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and abs(x) < 5
                                for x in target):
                            raise ValueError("IK target must be a hand body and finite 3D position")
                        side = body[-1]
                        side_sign = 1 if side == "r" else -1
                        old = [float(controls.get("elv_angle", 0)),
                               float(controls.get("shoulder_elv", 0)),
                               float(controls.get("elbow_flex", 0))]
                        coordinate_set = model.getCoordinateSet()
                        target_body = model.getBodySet().get(body)

                        def residual(parameters):
                            plane, elevation, elbow = parameters
                            coordinate_set.get(f"elv_angle_{side}").setValue(state, plane)
                            coordinate_set.get(f"shoulder_elv_{side}").setValue(state, side_sign * elevation)
                            coordinate_set.get(f"elbow_flex_{side}").setValue(state, elbow)
                            model.realizePosition(state)
                            point = target_body.getTransformInGround(state).p()
                            return [point.get(i) - target[i] for i in range(3)] + [
                                0.018 * (parameters[i] - old[i]) for i in range(3)]

                        def jacobian(parameters):
                            import numpy as np
                            baseline = np.asarray(residual(parameters))
                            columns = []
                            for index in range(3):
                                shifted = np.asarray(parameters).copy()
                                shifted[index] += 0.01 if shifted[index] < (1.5, 3.05, 2.5)[index] - 0.01 else -0.01
                                columns.append((np.asarray(residual(shifted)) - baseline) /
                                               (shifted[index] - parameters[index]))
                            return np.column_stack(columns)

                        # At the all-zero straight-arm pose the hand-height
                        # derivative is zero, so a local solver can remain on
                        # the joint bounds even for an easily reachable point.
                        seed = old if old[1] > 0.12 or old[2] > 0.12 else [0.0, 0.85, 1.0]
                        fitted = least_squares(residual, seed,
                                               bounds=([-1.5, 0, 0], [1.5, 3.05, 2.5]),
                                               jac=jacobian, max_nfev=40,
                                               ftol=1e-4, xtol=1e-4)
                        solved = dict(zip(("elv_angle", "shoulder_elv", "elbow_flex"), fitted.x.tolist()))
                        values.update(coordinate_values(solved))
                        state = model.initSystem()
                    else:
                        solved = None
                    result = frame(model, state, bodies, muscles, values)
                reply = {"frame": result}
                if solved is not None:
                    reply["solvedControls"] = solved
                    reply["targetErrorM"] = round(math.sqrt(sum((result["bodies"][bodies.index(body)]["p"][i] - target[i]) ** 2
                                                                   for i in range(3))), 4)
                self.json_reply(200, reply)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                self.json_reply(400, {"error": str(error)})
            except Exception as error:
                self.json_reply(500, {"error": str(error)})

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5173)
    args = parser.parse_args()
    model, bodies, muscles, ground = prepare_model()
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                 make_handler(model, bodies, muscles, ground))
    print(f"OpenSim live pose viewer: http://127.0.0.1:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
