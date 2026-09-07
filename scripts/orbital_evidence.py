"""Small Phase 7F array transport and final-result publication helpers.

Only fixed little-endian numeric arrays are accepted. File representation may
change C/F order; values, component order, occupations and phases do not change.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import uuid
import zipfile

import numpy as np

DTYPES = {'<f8', '<c16', '<i8'}
MAX_ELEMENTS = 10_000_000
MAX_BYTES = 512_000_000
LAYOUT = 'component,G,state; interleaved components; F order'


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _shape(shape):
    _need(isinstance(shape, list) and len(shape) <= 4 and
          all(type(n) is int and 0 < n <= MAX_ELEMENTS for n in shape), 'Invalid array shape')
    count = math.prod(shape)
    _need(count <= MAX_ELEMENTS, 'Array element limit exceeded')
    return count


def _array(value):
    _need(isinstance(value, np.ndarray) and value.dtype.str in DTYPES, 'Unsupported array dtype; require little-endian f8/c16/i8')
    _shape(list(value.shape))
    _need(np.all(np.isfinite(value)), 'Nonfinite numeric array')
    return value


def _descriptor(array, order):
    array = _array(array)
    data = array.tobytes(order=order)
    return {'dtype': array.dtype.str, 'shape': list(array.shape), 'order': order,
            'bytes': len(data), 'sha256': sha256(data)}


def _check_descriptor(descriptor, *, order):
    _need(isinstance(descriptor, dict) and descriptor.get('dtype') in DTYPES, 'Invalid descriptor dtype')
    _need(descriptor.get('order') == order, 'Wrong array storage order')
    count = _shape(descriptor.get('shape'))
    _need(type(descriptor.get('bytes')) is int and descriptor['bytes'] == count*np.dtype(descriptor['dtype']).itemsize,
          'Descriptor byte count disagrees with dtype/shape')
    _need(re.fullmatch('[0-9a-f]{64}', str(descriptor.get('sha256', ''))) is not None, 'Invalid array hash')


def _json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False)+'\n').encode()


def _atomic_bytes(path, data):
    temp = path.parent/(path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        with temp.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def load_package(path, manifest):
    path = Path(path)
    _need(isinstance(manifest, dict) and manifest.get('schema_version') == 1 and
          manifest.get('container') == 'numpy.npz' and manifest.get('allow_pickle') is False,
          'Unsupported NPZ manifest')
    _need(type(manifest.get('bytes')) is int and 0 < manifest['bytes'] <= MAX_BYTES,
          'Invalid NPZ byte count')
    _need(path.is_file() and not path.is_symlink() and path.stat().st_size == manifest['bytes'], 'NPZ missing, linked or wrong size')
    data = path.read_bytes()
    _need(sha256(data) == manifest['sha256'], 'NPZ file hash mismatch')
    descriptors = manifest.get('arrays')
    _need(isinstance(descriptors, dict) and 0 < len(descriptors) <= 256, 'Missing/invalid array manifest')
    for key, descriptor in descriptors.items():
        _need(re.fullmatch('[A-Za-z][A-Za-z0-9_-]*', key) is not None, 'Unsafe NPZ key')
        _check_descriptor(descriptor, order='C')
    _need(sum(d['bytes'] for d in descriptors.values()) <= MAX_BYTES, 'Expanded NPZ size limit exceeded')
    with zipfile.ZipFile(path) as archive:
        items = archive.infolist()
        names = [item.filename for item in items]
        _need(len(names) == len(set(names)) and set(names) == {k+'.npy' for k in descriptors},
              'Missing, extra, duplicated or unsafe NPZ members')
        _need(all(i.file_size <= descriptors[i.filename[:-4]]['bytes']+4096 for i in items),
              'NPY member exceeds declared data/header size')
    arrays = {}
    with np.load(path, allow_pickle=False) as archive:
        for key, expected in descriptors.items():
            array = _array(archive[key])
            _need(array.flags.c_contiguous, 'Canonical NPZ member is not C-order')
            actual = _descriptor(array, 'C')
            _need(actual == expected, 'NPZ expanded array identity mismatch: '+key)
            arrays[key] = np.array(array, copy=True, order='C')
            _need(arrays[key].tobytes() == array.tobytes(), 'NPZ decoding changed numeric bytes')
    _need(sha256(path.read_bytes()) == manifest['sha256'], 'NPZ changed during load')
    return arrays


def save_package(path, arrays):
    path = Path(path)
    _need(not path.exists() and not path.is_symlink(), 'Existing package refused')
    _need(isinstance(arrays, dict) and 0 < len(arrays) <= 256, 'Expected named numeric arrays')
    canonical = {}
    for key, value in arrays.items():
        _need(isinstance(key, str) and re.fullmatch('[A-Za-z][A-Za-z0-9_-]*', key), 'Invalid array key')
        canonical[key] = np.array(_array(value), copy=True, order='C')
    descriptors = {k: _descriptor(v, 'C') for k, v in canonical.items()}
    _need(sum(d['bytes'] for d in descriptors.values()) <= MAX_BYTES, 'Expanded package too large')
    temp = path.parent/(path.name+'.tmp-'+uuid.uuid4().hex)
    reserved = False
    try:
        with temp.open('xb') as stream:
            np.savez_compressed(stream, **canonical)
            stream.flush(); os.fsync(stream.fileno())
        data = temp.read_bytes()
        manifest = {'schema_version': 1, 'container': 'numpy.npz', 'allow_pickle': False,
                    'sha256': sha256(data), 'bytes': len(data), 'arrays': descriptors}
        decoded = load_package(temp, manifest)
        _need(all(decoded[k].tobytes() == canonical[k].tobytes() for k in canonical), 'NPZ bitwise round-trip failed')
        # Exclusive reservation prevents replacing a previous evidence package.
        with path.open('xb'):
            reserved = True
        os.replace(temp, path)
        return manifest
    except Exception:
        if reserved and path.exists():
            path.unlink()
        raise
    finally:
        if temp.exists():
            temp.unlink()


def read_primitive(directory, descriptor):
    _check_descriptor(descriptor, order='F')
    name = descriptor.get('path')
    _need(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_-]+\.bin', name), 'Unsafe primitive path')
    _need(1 <= len(descriptor['shape']) <= 3, 'Unsupported primitive rank')
    path = Path(directory)/name
    _need(path.is_file() and not path.is_symlink() and path.stat().st_size == descriptor['bytes'], 'Primitive file missing, linked or wrong size')
    data = path.read_bytes()
    _need(sha256(data) == descriptor['sha256'], 'Primitive hash mismatch')
    array = np.frombuffer(data, dtype=descriptor['dtype']).reshape(descriptor['shape'], order='F').copy(order='F')
    _array(array)
    _need(array.tobytes(order='F') == data, 'Primitive bitwise round-trip failed')
    return array


def _write_primitive(directory, name, value):
    descriptor = _descriptor(value, 'F')
    _need(1 <= value.ndim <= 3, 'Unsupported primitive rank')
    path = directory/(name+'.bin')
    with path.open('xb') as stream:
        stream.write(value.tobytes(order='F')); stream.flush(); os.fsync(stream.fileno())
    descriptor.update(path=path.name, bitwise_roundtrip_status='PASS')
    _need(read_primitive(directory, descriptor).tobytes(order='F') == value.tobytes(order='F'),
          'Primitive persisted round-trip failed')
    return descriptor


def _metadata(metadata):
    _need(isinstance(metadata, dict) and metadata.get('schema_version') == 1 and
          metadata.get('phase') == '7F' and metadata.get('execution_status') == 'PASS', 'State metadata is not Phase7F PASS')
    _need(metadata.get('label') in ('A', 'B', 'Q') and isinstance(metadata.get('source_run_id'), str)
          and bool(metadata['source_run_id']), 'Missing state label/source run')
    _need(re.fullmatch('[0-9a-f]{64}', str(metadata.get('plan_sha256', ''))), 'Missing state plan binding')
    _need(type(metadata.get('n_bands')) is int and metadata['n_bands'] == 24 and
          type(metadata.get('occupation_capacity')) is int and metadata['occupation_capacity'] == 1,
          'Only original 24 capacity-one spinor states are supported')
    _need(metadata.get('normalization_applied') is False and metadata.get('orbital_rotation_applied') is False,
          'Altered mathematical orbitals are not supported')
    _need(metadata.get('source_binding_status') == 'PASS' and metadata.get('data_roundtrip_status') == 'PASS',
          'State source/transport binding is not PASS')
    _json_bytes(metadata)


def _validate_state(state):
    _need(isinstance(state, dict), 'State envelope must be an object')
    _metadata(state['raw_metadata'])
    _need(state['label'] == state['raw_metadata']['label'], 'State label and provenance disagree')
    for name in ('lattice_columns', 'reciprocal_columns'):
        array = _array(state[name])
        _need(array.dtype.str == '<f8' and array.shape == (3, 3), 'Invalid geometry matrix '+name)
    grid = state['fft_size']
    _need(isinstance(grid, list) and len(grid) == 3 and all(type(n) is int and n > 0 for n in grid), 'Invalid physical FFT size')
    _need(isinstance(state['kpoints'], list) and 0 < len(state['kpoints']) <= 8, 'Invalid kpoint list')
    for k in state['kpoints']:
        g, c = _array(k['millers']), _array(k['coefficients'])
        _need(g.dtype.str == '<i8' and g.ndim == 2 and g.shape[1] == 3 and
              c.dtype.str == '<c16' and c.shape == (2, g.shape[0], 24), 'Miller/spinor shape or dtype mismatch')
        _need(len(set(map(tuple, g.tolist()))) == len(g), 'Duplicate Miller vectors')
        for name in ('occupations', 'eigenvalues', 'k_cart'):
            array = _array(k[name]); size = 3 if name == 'k_cart' else 24
            _need(array.dtype.str == '<f8' and array.shape == (size,), 'Invalid kpoint vector '+name)
        _need(np.all((k['occupations'] >= 0) & (k['occupations'] <= 1)), 'Occupations exceed spinor capacity')
        frac = k['coordinate_fractional']
        _need(len(frac) == 3 and all(type(x) in (int, float, np.float64) and math.isfinite(x) for x in frac), 'Invalid fractional k coordinate')
        _need(type(k['weight']) in (int, float, np.float64) and math.isfinite(k['weight']) and 0 <= k['weight'] <= 1, 'Invalid spatial weight')
    if 'n_out' in state:
        n = _array(state['n_out'])
        _need(n.dtype.str == '<f8' and n.shape == tuple(grid), 'Invalid original density shape')


def load_state_metadata(meta_path, *, expected_sha256=None):
    path = Path(meta_path)
    _need(path.is_file() and not path.is_symlink(), 'State metadata missing or linked')
    data = path.read_bytes(); digest = sha256(data)
    if expected_sha256 is not None:
        _need(digest == expected_sha256, 'State metadata hash mismatch')
    metadata = json.loads(data)
    _metadata(metadata)
    _need(metadata.get('coefficient_layout') == LAYOUT, 'Wrong primitive spinor layout')
    arr = lambda descriptor: read_primitive(path.parent, descriptor)
    ks = []
    for k in metadata['kpoints']:
        ks.append({'millers': np.ascontiguousarray(arr(k['millers']).T),
                   'coefficients': arr(k['coefficients']), 'occupations': arr(k['occupations']),
                   'eigenvalues': arr(k['eigenvalues']), 'k_cart': arr(k['k_cart']),
                   'coordinate_fractional': k['coordinate_fractional'], 'weight': k['weight'],
                   'source_k_index': k.get('source_k_index')})
    state = {'label': metadata['label'], 'lattice_columns': arr(metadata['lattice_columns']),
             'reciprocal_columns': arr(metadata['reciprocal_columns']), 'fft_size': metadata['fft_size'],
             'kpoints': ks, 'raw_metadata': metadata, 'metadata_sha256': digest}
    if 'n_out' in metadata:
        state['n_out'] = arr(metadata['n_out'])
    _validate_state(state)
    _need(path.read_bytes() == data, 'State metadata changed during read')
    return state


def write_state_metadata(state, newdir):
    _validate_state(state)
    directory = Path(newdir)
    directory.mkdir(parents=True, exist_ok=False)
    metadata = copy.deepcopy(state['raw_metadata'])
    metadata.update(coefficient_layout=LAYOUT, fft_size=state['fft_size'],
        lattice_columns=_write_primitive(directory, 'lattice-columns', state['lattice_columns']),
        reciprocal_columns=_write_primitive(directory, 'reciprocal-columns', state['reciprocal_columns']))
    ks = []
    for index, k in enumerate(state['kpoints'], 1):
        row = {'source_k_index': k.get('source_k_index', index),
               'coordinate_fractional': list(map(float, k['coordinate_fractional'])), 'weight': float(k['weight'])}
        for name in ('millers', 'coefficients', 'occupations', 'eigenvalues', 'k_cart'):
            value = k[name].T if name == 'millers' else k[name]
            row[name] = _write_primitive(directory, 'k%d-%s' % (index, name), value)
        ks.append(row)
    metadata['kpoints'] = ks
    if 'n_out' in state:
        metadata['n_out'] = _write_primitive(directory, 'n-out', state['n_out'])
    else:
        metadata.pop('n_out', None)
    path = directory/'metadata.json'
    encoded = _json_bytes(metadata)
    # Validate complete staged metadata/arrays before publishing its PASS file.
    staged = directory/'metadata.pending.json'
    _atomic_bytes(staged, encoded)
    restored = load_state_metadata(staged, expected_sha256=sha256(encoded))
    for original, decoded in zip(state['kpoints'], restored['kpoints']):
        for key in ('millers', 'coefficients', 'occupations', 'eigenvalues', 'k_cart'):
            _need(original[key].tobytes(order='C') == decoded[key].tobytes(order='C'), 'State export changed '+key)
    os.replace(staged, path)
    return path


def recorded_run(directory, work, *, run_id, initial=None):
    """A unique directory, one callback, and a final result published last.

    ``work(directory)`` returns a complete JSON object with execution_status
    PASS/FAIL/BLOCKED and matching integer exit_code. It may include a textual
    summary; all other numerical gates belong to that bounded callback.
    """
    directory = Path(directory)
    failure = lambda reason: {'schema_version': 1, 'run_id': str(run_id), 'execution_status': 'FAIL', 'exit_code': 9, 'reason': reason}
    if directory.exists() or directory.is_symlink():
        record = failure('Existing output directory refused; prior results preserved')
        record['exit_code'] = 2
        print(json.dumps(record)); return 2
    try:
        _need(isinstance(run_id, str) and re.fullmatch('[A-Za-z0-9_-]+', run_id), 'Invalid run ID')
        _need(initial is None or isinstance(initial, dict), 'Initial record must be an object')
        directory.mkdir(parents=True, exist_ok=False)
        started = dict(initial or {}, schema_version=1, run_id=run_id, execution_status='RUNNING', exit_code=9)
        _atomic_bytes(directory/'result.json', _json_bytes(started))
        result = work(directory)
        _need(isinstance(result, dict), 'Work result must be an object')
        _need(result.get('execution_status') in ('PASS', 'FAIL', 'BLOCKED') and type(result.get('exit_code')) is int,
              'Work result lacks a valid status/exit protocol')
        _need((result['execution_status'] == 'PASS') == (result['exit_code'] == 0), 'Contradictory status and exit code')
        _need(result.get('run_id', run_id) == run_id and result.get('schema_version', 1) == 1, 'Wrong result run/schema identity')
        summary = result.get('summary', 'Run %s: %s\n' % (run_id, result['execution_status']))
        _need(isinstance(summary, str), 'Result summary must be text')
        summary_bytes = summary.encode()
        result = dict(result, schema_version=1, run_id=run_id, summary_sha256=sha256(summary_bytes))
        encoded = _json_bytes(result)
        _atomic_bytes(directory/'summary.txt', summary_bytes)
        _atomic_bytes(directory/'result.json', encoded)
    except (Exception, KeyboardInterrupt) as error:
        result = failure(type(error).__name__+': '+str(error))
        if isinstance(error, FileNotFoundError):
            result.update(execution_status='BLOCKED', exit_code=10)
        encoded = _json_bytes(result)
        try:
            _atomic_bytes(directory/'result.json', encoded)
        except Exception as persistence_error:
            try:
                with (directory/'result.json').open('wb') as stream:
                    stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            except Exception:
                result['persistence_status'] = 'FAIL'
                print('Result persistence failed; this run is not PASS: '+str(persistence_error), file=sys.stderr)
    print(json.dumps(result, allow_nan=False))
    return result['exit_code']
