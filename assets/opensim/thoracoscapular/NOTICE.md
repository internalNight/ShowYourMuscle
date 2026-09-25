# Thoracoscapular shoulder model attribution

`TSM_subject_noWeight.osim` and the files in `Geometry/` were copied from the
[`OpenSim Models/for RMR solver` directory](https://github.com/ComputationalBiomechanicsLab/rmr-solver/tree/main/OpenSim%20Models/for%20RMR%20solver)
of ComputationalBiomechanicsLab's RMR solver repository. The repository's
[`LICENSE_data`](https://github.com/ComputationalBiomechanicsLab/rmr-solver/blob/main/LICENSE_data)
licenses its model and data under CC BY 4.0; the copy of that notice is here.

This subject-specific file is a modification of the original thoracoscapular
shoulder model by Seth, Dong, Matias and Delp (2019), *Muscle Contributions to
Upper-Extremity Movement and Work From a Musculoskeletal Model of the Human
Shoulder*, Frontiers in Neurorobotics 13:90,
[doi:10.3389/fnbot.2019.00090](https://doi.org/10.3389/fnbot.2019.00090).
The paper states that the model is available for commercial and research use.
See the [original SimTK project](https://simtk.org/projects/thoracoscapular).

`public/data/press_tsm_reference.json` is this project's derived 101-frame
synthetic angle sweep. It contains model muscle-tendon paths, lengths, moment
arms and skeletal positions, but no solved activation or force. The source
model was not designed or validated as an overhead-press or bench-press model.
No third-party endorsement is implied.

`public/data/bench_tsm_reference.json` is another project-derived dataset from
the same model. `scripts/fit_tsm_bench_trajectory.py` fits seven synthetic
joint-angle knots to an illustrative supine hand path; the exporter interpolates
these knots over 101 frames. The included `bench_trajectory_knots.json` is
project-generated. This is a geometric feasibility study, not observed bench
motion, a bilateral barbell model, or a muscle-force calculation.
