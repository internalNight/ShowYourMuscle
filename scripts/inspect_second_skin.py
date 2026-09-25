"""List or selectively extract Georgia Tech biomechanics ZIP members.

Uses HTTP byte ranges to inspect either large archive without downloading all
of it. The source data remain under ignored .cache/ and never enter the phone app.
Sources: Georgia Tech repository items 1853/78043 and 1853/70296, CC BY 4.0.
"""

import argparse
import re
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    "second-skin": ("https://repository.gatech.edu/server/api/core/bitstreams/"
                    "d56cbae7-5621-401d-9d93-0f9f6fb93045/content"),
    "lower-limb": ("https://repository.gatech.edu/server/api/core/bitstreams/"
                   "03f9679f-28ce-4d8b-b195-4b3b1aa4adc9/content"),
    "lower-limb-raw": ("https://repository.gatech.edu/server/api/core/bitstreams/"
                       "0c050d51-54f0-4ccf-9bcd-65521c0e20c3/content"),
    "lower-limb-code": ("https://repository.gatech.edu/server/api/core/bitstreams/"
                        "7bcb697f-bc16-493e-a255-d944e5cfa794/content"),
    "lower-limb-segmentation": ("https://repository.gatech.edu/server/api/core/bitstreams/"
                                "cc0f5ba9-5163-4bb1-a871-e3bcc1e49d46/content"),
}
CHUNK = 256 * 1024


class RangeReader:
    def __init__(self, url):
        self.url = url
        self.position = 0
        self.cache_start = -1
        self.cache = b""
        _, total = self._fetch(0, 0)
        self.size = total

    def _fetch(self, start, end):
        request = urllib.request.Request(self.url, headers={
            "Range": f"bytes={start}-{end}", "User-Agent": "MuscleAtlasResearch/0.1"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.status != 206:
                        raise RuntimeError(f"Server did not honor byte range: {response.status}")
                    content_range = response.headers.get("Content-Range", "")
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                    if not match or int(match.group(1)) != start or int(match.group(2)) != end:
                        raise RuntimeError(f"Unexpected Content-Range: {content_range}")
                    data = response.read()
                    if len(data) != end - start + 1:
                        raise RuntimeError("Incomplete byte range")
                    return data, int(match.group(3))
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == 4:
                    raise
                time.sleep(0.5 * (2 ** attempt))

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = (offset if whence == 0 else self.position + offset
                         if whence == 1 else self.size + offset)
        if not 0 <= self.position <= self.size:
            raise ValueError("Seek outside remote ZIP")
        return self.position

    def read(self, count=-1):
        count = min(self.size - self.position,
                    self.size - self.position if count < 0 else count)
        if count <= 0:
            return b""
        if count > 64 * 1024 * 1024:
            raise ValueError("Refusing a byte-range request larger than 64 MiB")
        if count <= CHUNK:
            start = (self.position // CHUNK) * CHUNK
            if start != self.cache_start:
                end = min(self.size - 1, start + CHUNK - 1)
                self.cache, _ = self._fetch(start, end)
                self.cache_start = start
            begin = self.position - start
            data = self.cache[begin:begin + count]
            if len(data) < count:
                rest, _ = self._fetch(self.position + len(data), self.position + count - 1)
                data += rest
        else:
            data, _ = self._fetch(self.position, self.position + count - 1)
        self.position += len(data)
        return data

    def seekable(self):
        return True


parser = argparse.ArgumentParser()
parser.add_argument("--archive", choices=ARCHIVES, default="second-skin")
parser.add_argument("--pattern", default="pseudo_static_sym_squat")
parser.add_argument("--member", action="append", default=[],
                    help="Exact ZIP member name to extract under .cache/<archive>; repeatable")
parser.add_argument("--dynamic-squats", action="store_true",
                    help="Select the published 0/25 lb squat validation files for chosen subjects")
parser.add_argument("--static-squats", action="store_true",
                    help="Select Second Skin 0/25-lb static squat EMG and ML files")
parser.add_argument("--subjects", nargs="+", default=None)
parser.add_argument("--include-emg", action="store_true",
                    help="Also extract 2000 Hz raw EMG with --dynamic-squats")
parser.add_argument("--force", action="store_true",
                    help="Re-extract members even if the local file has matching size and CRC")
parser.add_argument("--list-limit", type=int, default=40)
parser.add_argument("--list-subjects", action="store_true",
                    help="Print distinct AB subject directories among pattern matches")
args = parser.parse_args()
OUTPUT = ROOT / ".cache" / args.archive

members = list(args.member)
if args.dynamic_squats and args.static_squats:
    parser.error("choose only one squat selection mode")
if args.dynamic_squats:
    subjects = args.subjects or [
        "AB01", "AB02", "AB03", "AB05", "AB06", "AB07", "AB08", "AB09",
        "AB10", "AB11", "AB12", "AB13"]
    if args.archive == "lower-limb":
        for subject in subjects:
            for load in ("0lbs", "25lbs"):
                trial = "squats_2_0lbs" if subject == "AB05" and load == "0lbs" else f"squats_1_{load}"
                for kind in ("activity_flag", "angle", "moment_filt", "grf") + (
                        ("emg",) if args.include_emg else ()):
                    members.append(f"{subject}/{trial}/{subject}_{trial}_{kind}.csv")
    elif args.archive == "lower-limb-raw":
        members.append("Subject_masses.csv")
        members.extend(f"{subject}/Models/{subject}-Scaled1.osim"
                       for subject in subjects)
    else:
        parser.error("--dynamic-squats requires --archive lower-limb or lower-limb-raw")
if args.static_squats:
    if args.archive != "second-skin":
        parser.error("--static-squats requires --archive second-skin")
    for subject in (args.subjects or ["AB01", "AB02", "AB03", "AB04", "AB05",
                                     "AB06", "AB08", "AB09", "AB10", "AB11"]):
        for condition in ("unweighted", "vest_25lb"):
            trial = f"pseudo_static_sym_squat_{condition}"
            for kind, extension in (("EMG", "mat"), ("MachineLearning", "csv")):
                suffix = "_EMG" if kind == "EMG" else ""
                members.append(f"OpenSource_Dataset/Data/{subject}/{kind}/{trial}/"
                               f"{trial}_01{suffix}.{extension}")

with zipfile.ZipFile(RangeReader(ARCHIVES[args.archive])) as archive:
    matches = [entry for entry in archive.infolist()
               if args.pattern.lower() in entry.filename.lower() and not entry.is_dir()]
    print(f"ZIP entries={len(archive.infolist())}; matching={len(matches)}")
    if args.list_subjects:
        print("Subjects:", " ".join(sorted({part for entry in matches
                                           for part in PurePosixPath(entry.filename).parts
                                           if re.fullmatch(r"AB\d{2}", part)})))
    for entry in matches[:args.list_limit]:
        print(f"{entry.file_size:>10} raw / {entry.compress_size:>10} zip bytes  {entry.filename}")
    for member in dict.fromkeys(members):
        entry = archive.getinfo(member)
        relative = PurePosixPath(entry.filename)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe ZIP path")
        destination = (OUTPUT / Path(*relative.parts)).resolve()
        if not destination.is_relative_to(OUTPUT.resolve()):
            raise ValueError("ZIP path escapes cache")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not args.force and destination.stat().st_size == entry.file_size:
            checksum = 0
            with destination.open("rb") as existing:
                while chunk := existing.read(1024 * 1024):
                    checksum = zlib.crc32(chunk, checksum)
            if checksum == entry.CRC:
                print(f"CACHED {destination} ({entry.file_size} bytes; CRC verified)")
                continue
        temporary = destination.with_name(destination.name + ".part")
        with archive.open(entry) as source, temporary.open("wb") as target:
            while data := source.read(1024 * 1024):
                target.write(data)
        temporary.replace(destination)
        print(f"EXTRACTED {destination} ({destination.stat().st_size} bytes)")
