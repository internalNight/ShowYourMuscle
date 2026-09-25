"""Run the OpenSim Moco squat-to-stand example as a solver feasibility check.

This solves an unweighted, single-leg reference movement. Its outputs must not
be presented as a user's loaded-barbell muscle forces.
"""

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
OUTPUT = ROOT / ".cache" / "moco-squat"
OUTPUT.mkdir(parents=True, exist_ok=True)
os.chdir(MODEL_DIR)


def add_actuator(model, coordinate_name, optimal_force):
    actuator = osim.CoordinateActuator()
    actuator.setName("tau_" + coordinate_name)
    actuator.setCoordinate(model.updCoordinateSet().get(coordinate_name))
    actuator.setOptimalForce(optimal_force)
    actuator.setMinControl(-1)
    actuator.setMaxControl(1)
    model.addComponent(actuator)


model = osim.Model("squatToStand_3dof9musc.osim")
model.updForceSet().clearAndDestroy()
model.initSystem()
add_actuator(model, "hip_flexion_r", 150)
add_actuator(model, "knee_angle_r", 300)
add_actuator(model, "ankle_angle_r", 150)

study = osim.MocoStudy()
problem = study.updProblem()
problem.setModel(model)
problem.setTimeBounds(0, 1)
problem.setStateInfo('/jointset/hip_r/hip_flexion_r/value', [-2, 0.5], -2, 0)
problem.setStateInfo('/jointset/knee_r/knee_angle_r/value', [-2, 0], -2, 0)
problem.setStateInfo('/jointset/ankle_r/ankle_angle_r/value', [-0.5, 0.7], -0.5, 0)
problem.setStateInfoPattern('/jointset/.*/speed', [], 0, 0)
problem.addGoal(osim.MocoControlGoal('effort'))
solver = study.initCasADiSolver()
solver.set_num_mesh_intervals(15)
solver.set_optim_convergence_tolerance(1e-4)
solver.set_optim_constraint_tolerance(1e-4)

solution = study.solve()
if solution.isSealed() or not solution.success():
    raise RuntimeError("Moco returned an unsuccessful solution")
os.chdir(OUTPUT)
solution.write('torque_driven_squat_to_stand.sto')

# Follow the OpenSim example's muscle-model preparation. These numerical
# adjustments make the example solvable; they are not a person calibration.
os.chdir(MODEL_DIR)
muscle_model = osim.Model('squatToStand_3dof9musc.osim')
muscle_model.finalizeConnections()
osim.DeGrooteFregly2016Muscle().replaceMuscles(muscle_model)
for index in range(muscle_model.getMuscles().getSize()):
    muscle = muscle_model.updMuscles().get(index)
    muscle.setMinControl(0.0)
    muscle.set_ignore_activation_dynamics(False)
    muscle.set_ignore_tendon_compliance(False)
    muscle.set_max_isometric_force(2.0 * muscle.get_max_isometric_force())
    smooth_muscle = osim.DeGrooteFregly2016Muscle.safeDownCast(muscle)
    smooth_muscle.set_active_force_width_scale(1.5)
    smooth_muscle.set_tendon_compliance_dynamics_mode('implicit')
    if muscle.getName() == 'soleus_r':
        smooth_muscle.set_ignore_passive_fiber_force(True)

os.chdir(OUTPUT)
kinematics = osim.TableProcessor('torque_driven_squat_to_stand.sto')
kinematics.append(osim.TabOpLowPassFilter(6))
inverse = osim.MocoInverse()
processor = osim.ModelProcessor(muscle_model)
processor.append(osim.ModOpAddReserves(2))
inverse.setModel(processor)
inverse.setKinematics(kinematics)
inverse.set_initial_time(0)
inverse.set_final_time(1)
inverse.set_mesh_interval(0.05)
inverse.set_convergence_tolerance(1e-4)
inverse.set_constraint_tolerance(1e-4)
inverse.set_kinematics_allow_extra_columns(True)
inverse.set_minimize_sum_squared_activations(True)
inverse.append_output_paths('.*normalized_fiber_length')
inverse.append_output_paths('.*active_fiber_force')
inverse_result = inverse.solve()
inverse_solution = inverse_result.getMocoSolution()
if inverse_solution.isSealed() or not inverse_solution.success():
    raise RuntimeError('MocoInverse returned an unsuccessful solution')
inverse_solution.write('muscle_driven_inverse.sto')
osim.STOFileAdapter().write(inverse_result.getOutputs(), 'muscle_outputs.sto')

summary = {
    "status": "research_solver_feasibility_only",
    "model": "squatToStand_3dof9musc.osim",
    "opensimVersion": osim.GetVersionAndDate(),
    "objective": solution.getObjective(),
    "frames": len(solution.getTimeMat()),
    "inverseObjective": inverse_solution.getObjective(),
    "inverseFrames": len(inverse_solution.getTimeMat()),
    "limitations": ["single-sided reference model", "no barbell or individual scaling",
                    "muscle parameters were strengthened and smoothed per OpenSim example",
                    "research solver result; not a personal force estimate"],
}
(OUTPUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print('MOCO_SOLVED', json.dumps(summary))
