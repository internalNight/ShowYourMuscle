"""Inspect a small subset of the Zenodo upper-limb torque archive over HTTP Range.

The 1.4 GB CC BY-SA 4.0 archive is kept out of the application. This reader
requests only ZIP directory blocks and explicitly selected members.
"""

import argparse
import io
import json
import re
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path


URL = "https://zenodo.org/api/records/11209324/files/data.zip/content"
SIZE = 1407005034
BLOCK_SIZE = 1024 * 1024


class RangeFile(io.RawIOBase):
    def __init__(self):
        self.position = 0
        self.blocks = {}
        self.fetched_bytes = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        self.position = [offset, self.position + offset, SIZE + offset][whence]
        if self.position < 0:
            raise ValueError("negative ZIP offset")
        return self.position

    def _block(self, index):
        if index not in self.blocks:
            start = index * BLOCK_SIZE
            end = min(SIZE - 1, start + BLOCK_SIZE - 1)
            request = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(request, timeout=45) as response:
                content = response.read()
                expected = f"bytes {start}-{end}/{SIZE}"
                if response.status != 206 or response.headers.get("Content-Range") != expected:
                    raise RuntimeError("server did not honor ZIP byte range")
            if len(content) != end - start + 1:
                raise RuntimeError("short ZIP byte range")
            self.blocks[index] = content
            self.fetched_bytes += len(content)
        return self.blocks[index]

    def read(self, size=-1):
        if size < 0:
            raise ValueError("unbounded ZIP read is disabled")
        end = min(SIZE, self.position + size)
        chunks = []
        while self.position < end:
            index, offset = divmod(self.position, BLOCK_SIZE)
            chunk = self._block(index)[offset:offset + end - self.position]
            chunks.append(chunk)
            self.position += len(chunk)
        return b"".join(chunks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="S01")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--extract-trial", help="MJ/T0 or SJ/T0; filtered data only")
    parser.add_argument("--extract-models", action="store_true", help="extract scaled OpenSim models only")
    parser.add_argument("--all-subjects", action="store_true")
    args = parser.parse_args()
    archive_stream = RangeFile()
    with zipfile.ZipFile(archive_stream) as archive:
        entries = archive.infolist()
        print("entries", len(entries), "compressedBytes", sum(e.compress_size for e in entries))
        if args.list:
            print("rootNames", Counter(e.filename.split("/")[0] for e in entries))
            for entry in entries[:45]:
                print(entry.filename, entry.file_size, entry.compress_size)
        elif args.extract_models:
            subjects = [f"S{n:02d}" for n in range(1, 18)] if args.all_subjects else [args.subject]
            output = Path(__file__).resolve().parents[1] / ".cache/upper-limb-torque"
            for subject in subjects:
                name = f"{subject}/scaledModel.osim"
                target = output / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
                print("extractedModel", subject, target.stat().st_size)
        elif args.extract_trial:
            if not re.fullmatch(r"(MJ|SJ)/T\d+", args.extract_trial):
                parser.error("trial must be MJ/T0 or SJ/T0 style")
            subjects = [f"S{n:02d}" for n in range(1, 18)] if args.all_subjects else [args.subject]
            output = Path(__file__).resolve().parents[1] / ".cache/upper-limb-torque"
            files = ("emgFilt.csv", "humanPositions.csv", "humanVelocities.csv", "muscleTorque.csv")
            for subject in subjects:
                for name in (f"{subject}/{subject}.json", *(f"{subject}/{args.extract_trial}/{item}" for item in files)):
                    if name not in archive.namelist():
                        raise RuntimeError(f"missing expected member {name}")
                    target = output / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))  # ZIP CRC is checked by zipfile.
                print("extracted", subject, args.extract_trial)
            (output / "source.json").write_text(json.dumps({
                "record": "https://zenodo.org/records/11209324",
                "archiveMd5AsPublished": "ea2dd9d26ec61a5870b6455b8abe5918",
                "license": "CC BY-SA 4.0",
                "scope": "filtered EMG, kinematics, torque and metadata from selected trials",
                "warning": "different task from bench press; research data excluded from application"
            }, indent=2) + "\n", encoding="utf-8")
        else:
            matches = [e for e in entries if re.search(
                rf"(^|/){re.escape(args.subject)}(/|\.)", e.filename)]
            print("subjectMatches", len(matches))
            for entry in matches[:60]:
                print(entry.filename, entry.file_size, entry.compress_size)
            metadata = next((e for e in matches if e.filename.endswith(".json")), None)
            if metadata:
                print("metadata", json.loads(archive.read(metadata)))
    print("fetchedBytes", archive_stream.fetched_bytes)


if __name__ == "__main__":
    main()
