"""Re-run a short AB01 squat inverse-kinematics interval from original markers.

This research utility keeps output in ignored .cache/ and is a prerequisite
for independent inverse-dynamics/unit verification. It does not alter the app.
"""

import argparse
import os
from pathlib import Path

import opensim as osim

from analyze_dynamic_squats import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="AB01")
    parser.add_argument("--start", type=float, default=50)
    parser.add_argument("--end", type=float, default=52)
    args = parser.parse_args()
    if args.end <= args.start or args.end - args.start > 2:
        parser.error("Use a positive interval of at most 2 seconds")
    base = ROOT / ".cache/lower-limb-raw" / args.subject
    model_file = base / "Models" / f"{args.subject}-Scaled1.osim"
    marker_file = base / "MarkerData/squats_1.trc"
    if not model_file.exists() or not marker_file.exists():
        parser.error("Source model and original marker TRC must be extracted first")
    output = ROOT / ".cache/lower-limb" / f"{args.subject}_ik_{args.start:g}_{args.end:g}.mot"
    output.parent.mkdir(parents=True, exist_ok=True)
    # OpenSim's Windows file loader does not accept this workspace's Chinese
    # absolute path; relative ASCII paths work from the project cwd.
    model = osim.Model(os.path.relpath(model_file))
    marker_names = {model.getMarkerSet().get(i).getName()
                    for i in range(model.getMarkerSet().getSize())}
    with marker_file.open(encoding="utf-8") as handle:
        for _ in range(3):
            next(handle)
        observed = set(next(handle).rstrip("\n\t").split("\t")[2:])
    matched = sorted(marker_names & observed)
    if len(matched) < 20:
        raise ValueError(f"Only {len(matched)} source markers match the model")
    tool = osim.InverseKinematicsTool()
    tool.setModel(model)
    tool.setMarkerDataFileName(os.path.relpath(marker_file))
    tool.setStartTime(args.start)
    tool.setEndTime(args.end)
    tool.setOutputMotionFileName(os.path.relpath(output))
    tool.setResultsDir(os.path.relpath(output.parent))
    tasks = tool.upd_IKTaskSet()
    for name in matched:
        task = osim.IKMarkerTask()
        task.setName(name)
        task.setWeight(1)
        task.setApply(True)
        tasks.cloneAndAppend(task)
    success = tool.run()
    print(f"IK success={success}; markers={len(matched)}; output={output}")
    if not success or not output.exists():
        raise RuntimeError("OpenSim inverse kinematics did not produce coordinates")


if __name__ == "__main__":
    main()
