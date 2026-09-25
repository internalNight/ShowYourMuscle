"""Download one released SAME-Limb deep-squat trial per subject for external EMG evaluation.

The files remain in .cache and are never bundled with the app. Dataset: Tdongxu,
SAME-Limb v2.0.3 (CC BY 4.0), Hugging Face revision pinned below.
"""

import csv
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/research/same_limb"
REVISION = "233b0db6cfda8360338f92219e07fd3d3d1d7bdb"
BASE = "https://huggingface.co/datasets/Tdongxu/A_Synchronized_Lower_Limb_AMG_sEMG_and_Mocap/resolve/" + REVISION + "/"
METADATA = {
    "trials.csv": ("metadata/trials.csv", "aabaf8d8bdd753ca842a8c12115a1f1a84ef0513c54cd71263018638ad44b335"),
    "trial_file_manifest.csv": ("manifests/trial_file_manifest.csv", "059f85f812e7de9f8f0cddbaa4a88c7d44723993dcb436071a0cb07bb28717dd"),
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def get_metadata(name, remote, expected):
    path = CACHE / name
    if path.is_file() and sha256(path) == expected:
        return path
    temp = path.with_suffix(".partial")
    try:
        with urlopen(BASE + remote, timeout=90) as response, temp.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
        if sha256(temp) != expected:
            raise ValueError(f"Pinned SAME-Limb metadata digest mismatch: {remote}")
        temp.replace(path)
        return path
    finally:
        temp.unlink(missing_ok=True)


def get_trial(row, expected):
    subject = row["subject_id"]
    path = CACHE / (subject + "_deep_squat_A1.npz")
    if path.is_file() and sha256(path) == expected:
        return subject, path.stat().st_size, "cached"
    temp = path.with_suffix(".partial")
    try:
        with urlopen(BASE + row["relative_path"], timeout=90) as response, temp.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
        if sha256(temp) != expected:
            raise ValueError(f"Pinned SAME-Limb trial digest mismatch: {temp}")
        temp.replace(path)
        return subject, path.stat().st_size, "downloaded"
    finally:
        temp.unlink(missing_ok=True)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    metadata = {name: get_metadata(name, *source)
                for name, source in METADATA.items()}
    with metadata["trials.csv"].open(newline="", encoding="utf-8") as stream:
        rows = [row for row in csv.DictReader(stream)
                if row["condition_id"] == "deep_squat"
                and row["repetition"] == "A1"
                and row["release_status"] == "released"]
    if len(rows) != 30:
        raise ValueError(f"Expected 30 released deep-squat A1 trials, found {len(rows)}")
    with metadata["trial_file_manifest.csv"].open(newline="", encoding="utf-8") as stream:
        manifest = {row["relative_path"]: row["public_artifact_sha256"]
                    for row in csv.DictReader(stream)}
    if any(row["relative_path"] not in manifest for row in rows):
        raise ValueError("Missing file digests for one or more deep-squat trials")
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(get_trial, row, manifest[row["relative_path"]])
                                    for row in rows]):
            print(*future.result(), flush=True)


if __name__ == "__main__":
    main()
