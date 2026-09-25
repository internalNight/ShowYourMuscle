"""Download the seven GroundLink force archives to ignored local research cache."""

import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.cache/groundlink'
BASE = 'https://csr.bu.edu/groundlink/groundlink_data/force/'
OUT.mkdir(parents=True, exist_ok=True)

for number in range(1, 8):
    subject = f's{number:03d}'
    target = OUT / f'{subject}_force.zip'
    if not target.exists():
        with urllib.request.urlopen(BASE + target.name, timeout=120) as response:
            target.write_bytes(response.read())
    with zipfile.ZipFile(target) as zipped:
        bad = zipped.testzip()
        squats = [name for name in zipped.namelist() if '_squat_' in name.lower()]
    if bad or len(squats) != 3:
        raise ValueError(f'Archive integrity or trial-count mismatch: {target}, {bad}, {len(squats)}')
    print(f'{subject}: {target.stat().st_size} bytes, {len(squats)} squat trials')
