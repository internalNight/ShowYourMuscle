"""Read the two numeric storages in GroundLink force NPYs without unpickling."""

import pickletools
import struct

import numpy as np


def _ops(blob):
    return list(pickletools.genops(blob))


def _float_storage(blob):
    cursor = 0
    for _ in range(5):
        operations = _ops(blob[cursor:])
        if operations[-1][0].name != 'STOP' or any(
            arg != 'torch FloatStorage' for op, arg, _ in operations
            if op.name == 'GLOBAL'
        ):
            raise ValueError('Unexpected embedded storage pickle')
        cursor += operations[-1][2] + 1
    remaining = blob[cursor:]
    if len(remaining) < 8:
        raise ValueError('Missing storage length')
    count = struct.unpack('<Q', remaining[:8])[0]
    if count < 6 or count > 10_000_000 or len(remaining) != 8 + count * 4 or count % 6:
        raise ValueError('Unexpected storage count or length')
    return np.frombuffer(remaining[8:], dtype='<f4').reshape(2, count // 6, 3).transpose(1, 0, 2)


def read_groundlink_npy(data):
    if data[:6] != b'\x93NUMPY' or data[6:8] != b'\x01\x00':
        raise ValueError('Unexpected NumPy header')
    header_len = struct.unpack('<H', data[8:10])[0]
    header = data[10:10 + header_len]
    if b"'descr': '|O'" not in header or b"'shape': ()" not in header:
        raise ValueError('Unexpected NumPy dtype/shape')
    operations = _ops(data[10 + header_len:])
    globals_seen = {arg for op, arg, _ in operations if op.name == 'GLOBAL'}
    allowed = {'numpy.core.multiarray _reconstruct', 'numpy ndarray', 'numpy dtype',
               'torch._utils _rebuild_tensor_v2', 'torch.storage _load_from_bytes',
               'collections OrderedDict'}
    if globals_seen != allowed:
        raise ValueError(f'Unexpected pickle references: {globals_seen}')
    keys = [arg for op, arg, _ in operations if op.name == 'BINUNICODE'
            and arg in ('CoP', 'GRF')]
    storage_blobs = [arg for op, arg, _ in operations if op.name == 'BINBYTES']
    if keys != ['CoP', 'GRF'] or len(storage_blobs) != 2:
        raise ValueError('Unexpected force payload layout')
    parsed = {key: _float_storage(blob)
              for key, blob in zip(keys, storage_blobs)}
    if parsed['CoP'].shape != parsed['GRF'].shape or not all(
        np.isfinite(arr).all() for arr in parsed.values()
    ):
        raise ValueError('Invalid force/CoP sample dimensions')
    return parsed
