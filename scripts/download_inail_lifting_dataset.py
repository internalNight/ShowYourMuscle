"""Range-extract INAIL Lifting Dataset 1 research MAT files from the public ZIP.

Original source: https://humandatacorpus.org/lifting-and-carrying-iso-11228/
The source publishes kinematics, force plates, and sEMG for 17 people lifting a
crate. Raw files stay under ignored .cache/ and are not redistributed in the app.
"""

import argparse
import io
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/research/inail"
URL = ("https://www.dropbox.com/scl/fi/kh59g74qpuh4teiy1ccur/Dataset1.zip"
       "?dl=1&rlkey=e6np47hnb1zrse6siagrm6mt9")


class RangeReader(io.RawIOBase):
    def __init__(self):
        with urlopen(Request(URL, method="HEAD"), timeout=40) as response:
            self.size = int(response.headers["Content-Length"])
        self.position = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = (offset if whence == 0 else
                         self.position + offset if whence == 1 else self.size + offset)
        return self.position

    def read(self, count=-1):
        if count < 0:
            count = self.size - self.position
        if count <= 0:
            return b""
        end = min(self.size - 1, self.position + count - 1)
        with urlopen(Request(URL, headers={"Range": f"bytes={self.position}-{end}"}),
                     timeout=120) as response:
            if response.status != 206:
                raise ValueError(f"Dataset server ignored HTTP Range: {response.status}")
            data = response.read()
        self.position += len(data)
        return data


def extract_one(archive_name, output_name):
    target = CACHE / output_name
    with ZipFile(RangeReader()) as archive:
        info = archive.getinfo(archive_name)
        if target.is_file() and target.stat().st_size == info.file_size:
            checksum = 0
            with target.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    checksum = zlib.crc32(block, checksum)
            if checksum == info.CRC:
                return output_name, info.file_size, "cached"
        data = archive.read(info)  # ZipFile checks the source CRC.
    temp = target.with_suffix(target.suffix + ".partial")
    try:
        temp.write_bytes(data)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return output_name, len(data), "downloaded"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Fetch all 17 subject MAT files")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    with ZipFile(RangeReader()) as archive:
        names = [item.filename for item in archive.infolist()
                 if item.filename.endswith("_all_trials.mat")
                 and "/Exported/mat_format/" in item.filename
                 and not item.filename.startswith("__MACOSX/")]
        metadata = [item.filename for item in archive.infolist()
                    if item.filename.endswith(("Dataset1_Lifting_and_carrying.docx",
                                               "Subjects_info.xlsx"))
                    and not item.filename.startswith("__MACOSX/")]
    if len(names) != 17:
        raise ValueError(f"Expected 17 subject files, found {len(names)}")
    if len(metadata) != 2:
        raise ValueError(f"Expected source protocol and participant spreadsheet, found {len(metadata)}")
    if not args.all:
        names = [name for name in names if name.endswith("S01_all_trials.mat")]
    names += metadata
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(extract_one, name, Path(name).name) for name in names]
        for future in as_completed(jobs):
            print(*future.result(), flush=True)


if __name__ == "__main__":
    main()
