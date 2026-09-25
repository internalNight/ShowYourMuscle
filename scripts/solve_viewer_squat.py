"""Experimental muscle inverse solution for the viewer's squat.

Research output remains in .cache/. It must pass model and external-load
validation before any force display is enabled in the product.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

import opensim as osim

PLUGIN_DIR = Path(osim.__file__).parent
os.environ["CASADIPATH"] = str(PLUGIN_DIR)
os.environ["PATH"] = str(PLUGIN_DIR) + os.pathsep + os.environ["PATH"]
os.add_dll_directory(str(PLUGIN_DIR))

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "assets" / "opensim"
parser = argparse.ArgumentParser()
parser.add_argument("--barbell-kg", type=float, default=0.0)
parser.add_argument("--disable-passive", action="store_true",
                    help="Research sensitivity: remove all passive fiber forces")
parser.add_argument("--barbell-forward-m", type=float, default=0.0,
                    help="Research sensitivity: local torso x offset of the load application point")
parser.add_argument("--load-line-over-ankle", action="store_true",
                    help="Research sensitivity: fixed vertical load line through the model ankle")
parser.add_argument("--viewer-bar-path", action="store_true",
                    help="Research sensitivity: apply the exported illustrative bar path as a time-varying global load line")
parser.add_argument("--viewer-bar-offset-cm", type=float, default=0,
                    help="Research sensitivity: horizontal offset from the exported bar path in centimeters")
parser.add_argument("--half-axial-mass", action="store_true",
                    help="Research sensitivity: assign half torso/pelvis mass and inertia to the one-leg model")
parser.add_argument("--person-height-cm", type=float,
                    help="Research sensitivity: uniformly scale geometry relative to 175 cm")
parser.add_argument("--person-weight-kg", type=float,
                    help="Research sensitivity: target half of this person's body mass")
args = parser.parse_args()
if args.barbell_kg < 0 or args.barbell_kg > 200:
    raise ValueError("Research load must be between 0 and 200 kg")
if args.barbell_forward_m < -0.2 or args.barbell_forward_m > 0.3:
    raise ValueError("Research barbell offset must be between -0.2 and 0.3 m")
if args.load_line_over_ankle and (not args.barbell_kg or args.barbell_forward_m):
    raise ValueError("Ankle load-line experiment needs positive load and no local offset")
if args.viewer_bar_path and (not args.barbell_kg or args.barbell_forward_m or args.load_line_over_ankle):
    raise ValueError("Viewer bar path needs positive load and no alternative load-line option")
if args.viewer_bar_offset_cm not in (-6, 0, 6) or (args.viewer_bar_offset_cm and not args.viewer_bar_path):
    raise ValueError("Viewer bar offset must be -6, 0 or 6 cm and needs --viewer-bar-path")
if (args.person_height_cm is None) != (args.person_weight_kg is None):
    raise ValueError("Research person scaling needs both height and weight")
if args.person_height_cm is not None:
    if not 120 <= args.person_height_cm <= 220 or not 30 <= args.person_weight_kg <= 250:
        raise ValueError("Research height/weight are outside the app input ranges")
    if not args.half_axial_mass:
        raise ValueError("Person mass split experiment requires --half-axial-mass")
case_name = f"barbell-{args.barbell_kg:g}kg" + ("-no-passive" if args.disable_passive else "")
if args.barbell_forward_m:
    case_name += f"-loadx{args.barbell_forward_m:g}m"
if args.load_line_over_ankle:
    case_name += "-over-ankle"
if args.viewer_bar_path:
    case_name += "-viewer-bar-path"
    if args.viewer_bar_offset_cm:
        case_name += f"-offset{args.viewer_bar_offset_cm:+g}cm"
if args.half_axial_mass:
    case_name += "-half-axial"
if args.person_height_cm is not None:
    case_name += f"-h{args.person_height_cm:g}cm-w{args.person_weight_kg:g}kg"
kinematics_file = MODEL_DIR / "squat_coordinates.sto"
kinematics_sha256 = hashlib.sha256(kinematics_file.read_bytes()).hexdigest()
OUT = ROOT / ".cache" / "moco-viewer-squat" / f"kinematics-{kinematics_sha256[:12]}" / case_name
OUT.mkdir(parents=True, exist_ok=True)
os.chdir(MODEL_DIR)

model = osim.Model("squatToStand_3dof9musc.osim")
if args.half_axial_mass:
    # Symmetry experiment only: each modeled leg carries one half of the
    # shared axial segments. Keep limb masses unchanged.
    for name in ("pelvis", "torso"):
        body = model.updBodySet().get(name)
        body.setMass(body.getMass() / 2)
        inertia = body.get_inertia()
        halved = osim.Vec6(0)
        for axis in range(6):
            halved.set(axis, inertia.get(axis) / 2)
        body.set_inertia(halved)
if args.person_height_cm is not None:
    state = model.initSystem()
    factor = args.person_height_cm / 175
    scales = osim.ScaleSet()
    for index in range(model.getBodySet().getSize()):
        scale = osim.Scale()
        scale.setSegmentName(model.getBodySet().get(index).getName())
        scale.setScaleFactors(osim.Vec3(factor, factor, factor))
        scale.setApply(True)
        scales.cloneAndAppend(scale)
    if not model.scale(state, scales, False, args.person_weight_kg / 2):
        raise RuntimeError("OpenSim person geometry/mass scaling failed")
model_state = model.initSystem()
model_mass_kg = model.getTotalMass(model_state)
if args.barbell_kg:
    # The source model contains one leg. Apply half the barbell weight to its
    # torso as a fixed shoulder-height point load in the sagittal plane.
    load = osim.PrescribedForce()
    load.setName("half_barbell_weight")
    load.connectSocket_frame(model.getBodySet().get("torso"))
    load.setForceIsInGlobalFrame(True)
    load.setForceFunctions(osim.Constant(0), osim.Constant(-args.barbell_kg * 9.80665 / 2), osim.Constant(0))
    if args.viewer_bar_path:
        ankle = model.getJointSet().get("ankle_r").getChildFrame()
        ankle_x = ankle.getPositionInGround(model_state)[0]
        angles = json.loads((MODEL_DIR / "squat_angles.json").read_text(encoding="utf-8"))
        bar_path = osim.PiecewiseLinearFunction()
        for frame in angles["frames"]:
            bar_path.addPoint(2.8 * frame["phase"],
                              ankle_x + frame["barSagittalRelativeAnkleM"]
                              + args.viewer_bar_offset_cm / 100)
        load.setPointIsInGlobalFrame(True)
        load.setPointFunctions(bar_path, osim.Constant(1.2), osim.Constant(0))
    elif args.load_line_over_ankle:
        initial = model_state
        ankle = model.getJointSet().get("ankle_r").getChildFrame()
        ankle_x = ankle.getPositionInGround(initial)[0]
        load.setPointIsInGlobalFrame(True)
        # The vertical force is equivalent along this line for sagittal torque.
        # It is not a real barbell attachment to the torso.
        load.setPointFunctions(osim.Constant(ankle_x), osim.Constant(1.2), osim.Constant(0))
    else:
        load.setPointIsInGlobalFrame(False)
        length_scale = args.person_height_cm / 175 if args.person_height_cm is not None else 1
        load.setPointFunctions(osim.Constant(args.barbell_forward_m * length_scale),
                               osim.Constant(0.45 * length_scale), osim.Constant(0))
    model.addForce(load)
model.finalizeConnections()
osim.DeGrooteFregly2016Muscle().replaceMuscles(model)
for index in range(model.getMuscles().getSize()):
    muscle = model.updMuscles().get(index)
    muscle.setMinControl(0.0)
    muscle.set_ignore_activation_dynamics(False)
    muscle.set_ignore_tendon_compliance(False)
    muscle.set_max_isometric_force(2.0 * muscle.get_max_isometric_force())
    smooth = osim.DeGrooteFregly2016Muscle.safeDownCast(muscle)
    smooth.set_active_force_width_scale(1.5)
    smooth.set_tendon_compliance_dynamics_mode('implicit')
    if args.disable_passive or muscle.getName() == 'soleus_r':
        smooth.set_ignore_passive_fiber_force(True)

inverse = osim.MocoInverse()
processor = osim.ModelProcessor(model)
processor.append(osim.ModOpAddReserves(2))
inverse.setModel(processor)
inverse.setKinematics(osim.TableProcessor('squat_coordinates.sto'))
inverse.set_initial_time(0)
inverse.set_final_time(2.8)
inverse.set_mesh_interval(0.05)
inverse.set_convergence_tolerance(1e-4)
inverse.set_constraint_tolerance(1e-4)
inverse.set_minimize_sum_squared_activations(True)
inverse.append_output_paths('.*active_fiber_force')
inverse.append_output_paths('.*normalized_fiber_length')
inverse.append_output_paths('.*tendon_length')
inverse.append_output_paths('.*fiber_length_along_tendon')
inverse.append_output_paths('.*passive_force_multiplier')

result = inverse.solve()
solution = result.getMocoSolution()
if solution.isSealed() or not solution.success():
    raise RuntimeError('MocoInverse did not converge for the viewer squat')
os.chdir(OUT)
solution.write('viewer_squat_inverse.sto')
osim.STOFileAdapter().write(result.getOutputs(), 'viewer_squat_outputs.sto')
summary = {"status": "research_loaded_viewer_squat", "objective": solution.getObjective(),
           "frames": len(solution.getTimeMat()), "model": "squatToStand_3dof9musc.osim",
           "barbellKg": args.barbell_kg,
           "barbellLocalForwardM": args.barbell_forward_m,
           "loadLineOverAnkle": args.load_line_over_ankle,
           "viewerBarPath": args.viewer_bar_path,
           "viewerBarOffsetCm": args.viewer_bar_offset_cm,
           "kinematicsSha256": kinematics_sha256,
           "halfAxialMassAndInertia": args.half_axial_mass,
           "personHeightCm": args.person_height_cm,
           "personWeightKg": args.person_weight_kg,
           "modelMassKg": model_mass_kg,
           "passiveFiberForcesEnabled": not args.disable_passive,
           "limitations": ["single leg and half-barbell approximation",
                           "barbell load is a prescribed point force, not a barbell-body model",
                           "person scaling is uniform and unvalidated" if args.person_height_cm is not None
                           else "no individual scaling",
                           "muscle maximum forces doubled and curves widened"]}
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print('VIEWER_MOCO_SOLVED', json.dumps(summary))
