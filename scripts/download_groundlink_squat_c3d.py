"""Fetch only squat C3D members from GroundLink subject ZIPs via HTTP ranges.

The source ZIPs are hundreds of MB each. This reads the central directory from
the last 1 MiB, then downloads three requested compressed members per subject.
All extracted data stay in .cache. No archive path is trusted for local output.
"""

import io
import struct
import urllib.request
import zipfile
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.cache/groundlink/c3d'
IDS = [f's{i:03d}' for i in range(1, 8)]
BASE = 'https://csr.bu.edu/groundlink/groundlink_data/c3d/'
TAIL_BYTES = 1 << 20


def ranged(url, begin, end):
    request = urllib.request.Request(url, headers={'Range': f'bytes={begin}-{end}'})
    with urllib.request.urlopen(request, timeout=90) as response:
        if response.status != 206:
            raise RuntimeError(f'Range request not honored: {response.status}')
        data = response.read()
        if len(data) != end - begin + 1:
            raise RuntimeError('Short or oversized range response')
        return data


def length(url):
    request = urllib.request.Request(url, method='HEAD')
    with urllib.request.urlopen(request, timeout=30) as response:
        return int(response.headers['Content-Length'])


def get_member(url, origin, info):
    header_at = origin + info.header_offset
    header = ranged(url, header_at, header_at + 29)
    signature, version, flags, method, modtime, moddate, crc, packed, unpacked, name_len, extra_len = struct.unpack('<IHHHHHIIIHH', header)
    if signature != 0x04034B50 or method != 8 or flags & 1:
        raise ValueError(f'Unsupported ZIP member: {info.filename}')
    data_at = header_at + 30 + name_len + extra_len
    packed_data = ranged(url, data_at, data_at + info.compress_size - 1)
    data = zlib.decompress(packed_data, -15)
    if len(data) != info.file_size or zlib.crc32(data) != info.CRC:
        raise ValueError(f'ZIP integrity mismatch: {info.filename}')
    return data


for subject in IDS:
    url = BASE + f'{subject}_c3d.zip'
    archive_length = length(url)
    tail_size = min(TAIL_BYTES, archive_length)
    tail = ranged(url, archive_length - tail_size, archive_length - 1)
    with zipfile.ZipFile(io.BytesIO(tail)) as archive:
        members = [info for info in archive.infolist()
                   if info.filename.lower().endswith('.c3d')
                   and '_squat_' in info.filename.lower()]
    if len(members) != 3:
        raise ValueError(f'Expected three squat C3Ds for {subject}; found {len(members)}')
    for info in members:
        target = OUT / subject / Path(info.filename).name
        if target.exists() and target.stat().st_size == info.file_size:
            print(f'Cached {target.name}')
            continue
        data = get_member(url, archive_length - tail_size, info)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print(f'{subject} {target.name} {len(data)} bytes')
