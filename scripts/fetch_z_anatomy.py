"""Fetch the CC BY-SA 4.0 Z-Anatomy Blender source into the ignored cache."""

from pathlib import Path
from urllib.request import urlretrieve
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
ARCHIVE = CACHE / "z-anatomy.zip"
BLEND = CACHE / "z-anatomy" / "Startup.blend"
SOURCE = "https://raw.githubusercontent.com/Z-Anatomy/Models-of-human-anatomy/master/Z-Anatomy.zip"
EXPECTED_BYTES = 86_734_957

CACHE.mkdir(exist_ok=True)
if not ARCHIVE.exists() or ARCHIVE.stat().st_size != EXPECTED_BYTES:
    urlretrieve(SOURCE, ARCHIVE)
    if ARCHIVE.stat().st_size != EXPECTED_BYTES:
        raise RuntimeError("Downloaded Z-Anatomy archive has an unexpected size")
if not BLEND.exists():
    BLEND.parent.mkdir(exist_ok=True)
    with ZipFile(ARCHIVE) as source, source.open("Z-Anatomy/Startup.blend") as original, BLEND.open("wb") as target:
        import shutil

        shutil.copyfileobj(original, target)
print(f"Z-Anatomy source: {BLEND} ({BLEND.stat().st_size:,} bytes)")
