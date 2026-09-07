#!/usr/bin/env python3
"""Restricted QE 7.5 collected spinor wavefunction format reader.

This reads records, not QE numerical algorithms. Only scale-one, full-G,
non-LSDA PW spinors are supported. No normalization, conjugation, phase choice,
G completion, band sorting, or coefficient rotation is performed.
"""
import hashlib
import io
import itertools
import math
from pathlib import Path
import re
import struct

MAX_FILE_BYTES = 128_000_000
MAX_NGW = 1_000_000
MAX_IGWX = 100_000
MAX_BANDS = 256
CARTESIAN_TOLERANCE = 1e-12
FORMAT_SOURCE = 'https://github.com/QEF/q-e/blob/qe-7.5/Modules/io_base.f90#L103-L186'
PRODUCER_SOURCE = 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_restart_new.f90#L978-L1031'


class WavefunctionParseError(ValueError):
    def __init__(self, reason, status='FAIL', candidate_failures=None):
        super().__init__(reason)
        self.status = status
        self.candidate_failures = candidate_failures or []


def _require(condition, reason, status='FAIL'):
    if not condition:
        raise WavefunctionParseError(reason, status)


def _record_envelopes(stream, size, endian, marker_bytes):
    marker = struct.Struct(endian+('i' if marker_bytes == 4 else 'q'))
    stream.seek(0)
    records, prefix = [], []
    while stream.tell() < size:
        _require(len(records) < 4+MAX_BANDS, 'Extra trailing records')
        start = stream.tell()
        raw = stream.read(marker_bytes)
        _require(len(raw) == marker_bytes, 'Truncated leading record marker')
        length = marker.unpack(raw)[0]
        _require(0 < length <= MAX_FILE_BYTES, 'Invalid, oversized, or split record marker')
        end = start+marker_bytes+length
        _require(end+marker_bytes <= size, 'Truncated record payload or trailer')
        if len(records) < 3:
            _require(length <= 128, 'Wrong leading header record size')
            payload = stream.read(length)
            prefix.append(payload)
        else:
            # Header preflight deliberately does not read Miller or coefficient
            # payloads; it validates their envelopes and exact byte counts only.
            stream.seek(end)
        _require(stream.read(marker_bytes) == raw, 'Leading/trailing record markers disagree')
        records.append({'payload_offset': start+marker_bytes, 'payload_bytes': length})
    _require(stream.tell() == size and len(records) >= 5, 'Missing records or trailing bytes')
    return records, prefix


def _decode_header(records, prefix, endian, marker_bytes, integer_bytes, logical_bytes, size):
    integer = struct.Struct(endian+('i' if integer_bytes == 4 else 'q'))
    logical = struct.Struct(endian+('i' if logical_bytes == 4 else 'q'))
    real = struct.Struct(endian+'d')
    _require(len(prefix[0]) == 2*integer_bytes+logical_bytes+32,
             'Wfc header integer/logical widths disagree')
    _require(len(prefix[1]) == 4*integer_bytes and len(prefix[2]) == 72,
             'Wrong dimensions or reciprocal-vector record length')
    ik = integer.unpack_from(prefix[0], 0)[0]
    xk = [real.unpack_from(prefix[0], integer_bytes+8*i)[0] for i in range(3)]
    ispin = integer.unpack_from(prefix[0], integer_bytes+24)[0]
    gamma = logical.unpack_from(prefix[0], 2*integer_bytes+24)[0]
    scale = real.unpack_from(prefix[0], 2*integer_bytes+24+logical_bytes)[0]
    ngw, igwx, npol, nbnd = [integer.unpack_from(prefix[1], i*integer_bytes)[0] for i in range(4)]
    b = [[real.unpack_from(prefix[2], (3*column+row)*8)[0] for row in range(3)] for column in range(3)]
    _require(1 <= ik <= 1_000_000 and ispin in (1, 2) and gamma in (0, 1, -1), 'Invalid header index/spin/logical representation')
    _require(all(math.isfinite(x) for x in xk+[scale]+sum(b, [])), 'Nonfinite header Float64')
    _require(1 <= igwx <= MAX_IGWX and igwx <= ngw <= MAX_NGW,
             'Invalid NG dimensions/global-index ceiling')
    _require(1 <= npol <= 2 and 1 <= nbnd <= MAX_BANDS, 'Invalid spinor/band dimensions')
    _require(len(records) == 4+nbnd, 'Record count disagrees with band count')
    _require(records[3]['payload_bytes'] == 3*igwx*integer_bytes, 'Miller payload byte count disagrees with igwx')
    _require(all(r['payload_bytes'] == 16*npol*igwx for r in records[4:]),
             'Band payload byte count disagrees with npol*igwx ComplexF64')
    a, c, d = b
    determinant = (a[0]*(c[1]*d[2]-c[2]*d[1])-c[0]*(a[1]*d[2]-a[2]*d[1])
                   + d[0]*(a[1]*c[2]-a[2]*c[1]))
    _require(math.isfinite(determinant) and determinant != 0, 'Singular reciprocal lattice')
    return {'schema_version': 1, 'ik': ik, 'k_cart_bohr_inv': xk,
            'b_columns_bohr_inv': b, 'ispin': ispin, 'gamma_only': gamma != 0,
            'gamma_only_raw': gamma, 'scalef': scale, 'ngw': ngw, 'igwx': igwx,
            'npol': npol, 'nbnd': nbnd, 'file_bytes': size,
            'format': {'endian': 'little' if endian == '<' else 'big',
                       'record_marker_bytes': marker_bytes, 'integer_bytes': integer_bytes,
                       'logical_bytes': logical_bytes, 'real_bytes': 8, 'complex_bytes': 16},
            'records': records, 'record_payload_bytes': [r['payload_bytes'] for r in records],
            'header_payload_sha256': hashlib.sha256(b''.join(prefix)).hexdigest(),
            'format_source': FORMAT_SOURCE, 'producer_source': PRODUCER_SOURCE,
            'ngw_semantics': 'maximum original global G index; not selected plane-wave count',
            'igwx_semantics': 'dense collected k-supported count; must equal original XML npw',
            'coefficient_layout': 'one record per original band; up[NG] followed by down[NG]',
            'header_validation_status': 'HEADER_AND_RECORD_ENVELOPES_ONLY',
            'miller_values_status': 'NOT_READ', 'coefficient_values_status': 'NOT_READ'}


def _unique_candidate(candidates, failures):
    _require(bool(candidates), 'No supported unambiguous WFC record envelope: '+('; '.join(failures[:4])),
             'UNSUPPORTED_OR_MALFORMED_FORMAT')
    if len(candidates) != 1:
        raise WavefunctionParseError('More than one valid byte-format interpretation',
                                     'UNSUPPORTED_AMBIGUOUS_FORMAT', failures)
    candidates[0]['candidate_count'] = 1
    return candidates[0]


def _header(stream, size):
    _require(0 < size <= MAX_FILE_BYTES, 'Missing/oversized WFC file')
    stream.seek(0)
    _require(stream.read(8) != b'\x89HDF\r\n\x1a\n', 'HDF5 WFC is unsupported', 'UNSUPPORTED_HDF5')
    candidates, failures = [], []
    for endian, marker in itertools.product(('<', '>'), (4, 8)):
        try:
            records, prefix = _record_envelopes(stream, size, endian, marker)
        except WavefunctionParseError as error:
            failures.append('%s/M%d: %s' % (endian, marker, error))
            continue
        for integer, logical in itertools.product((4, 8), (4, 8)):
            try:
                candidates.append(_decode_header(records, prefix, endian, marker, integer, logical, size))
            except WavefunctionParseError as error:
                failures.append('%s/M%d/I%d/L%d: %s' % (endian, marker, integer, logical, error))
    return _unique_candidate(candidates, failures)


def read_header(path):
    """Read only three metadata payloads; seek all remaining record envelopes.

    A successful header check neither reads nor certifies Miller/coefficient
    values and does not authenticate this file as a historical G40 source.
    """
    path = Path(path)
    before = path.stat()
    with path.open('rb') as stream:
        result = _header(stream, before.st_size)
    after = path.stat()
    _require((before.st_size, before.st_mtime_ns, before.st_ino) ==
             (after.st_size, after.st_mtime_ns, after.st_ino), 'File changed during header read')
    return result


def _geometry(actual, expected, label):
    _require(isinstance(expected, list) and len(expected) == 3, 'Expected '+label+' must have three components')
    for a, e in zip(actual, expected):
        _require(type(e) in (int, float) and math.isfinite(e), 'Expected nonfinite/non-numeric '+label)
        _require(abs(a-e) <= CARTESIAN_TOLERANCE, 'Header '+label+' differs from bound XML geometry')


def _validate_expected(header, expected):
    keys = {'source_sha256', 'ik', 'k_cart_bohr_inv', 'b_columns_bohr_inv', 'npw', 'nbnd'}
    _require(isinstance(expected, dict) and keys <= set(expected) and set(expected) <= keys|{'ngw'},
             'Expected WFC binding requires SHA, ik, k_cart, B columns, npw and nbnd')
    _require(type(expected['ik']) is int and header['ik'] == expected['ik'], 'Native ik differs from bound original XML k point')
    _require(type(expected['nbnd']) is int and expected['nbnd'] == 24 and header['nbnd'] == 24,
             'Only all 24 original bands are supported', 'UNSUPPORTED_BAND_COUNT')
    _require(type(expected['npw']) is int and expected['npw'] == header['igwx'], 'Collected igwx differs from original XML npw')
    if 'ngw' in expected:
        _require(type(expected['ngw']) is int and expected['ngw'] == header['ngw'], 'ngw differs from bound native header')
    _require(header['npol'] == 2 and header['ispin'] == 1, 'Only non-LSDA two-component spinors are supported', 'UNSUPPORTED_SPIN_LAYOUT')
    _require(not header['gamma_only'], 'Gamma half-G wavefunctions are unsupported', 'UNSUPPORTED_GAMMA_ONLY')
    _require(header['scalef'] == 1.0, 'Only PW scalef=1 is supported; coefficients are never rescaled', 'UNSUPPORTED_SCALE_CONVENTION')
    _geometry(header['k_cart_bohr_inv'], expected['k_cart_bohr_inv'], 'k Cartesian (bohr^-1)')
    _require(isinstance(expected['b_columns_bohr_inv'], list) and len(expected['b_columns_bohr_inv']) == 3,
             'Expected reciprocal matrix requires three vector columns')
    for actual, wanted in zip(header['b_columns_bohr_inv'], expected['b_columns_bohr_inv']):
        _geometry(actual, wanted, 'reciprocal column (bohr^-1)')


def parse_wfc(path, expected):
    """Authenticate and read every original complex coefficient without edits.

    Result ``coefficients[component][native_G_position][original_band]`` has
    shape (2, igwx, 24). Conversion to NumPy complex128 is lossless; callers
    must independently bind occupations and prove their own Miller bijection.
    """
    _require(isinstance(expected, dict) and re.fullmatch('[0-9a-f]{64}', str(expected.get('source_sha256', ''))),
             'Missing exact source SHA-256 binding')
    path = Path(path)
    _require(0 < path.stat().st_size <= MAX_FILE_BYTES, 'Missing/oversized WFC file')
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    _require(sha == expected['source_sha256'], 'Original WFC source SHA-256 mismatch', 'BLOCKED_SOURCE_IDENTITY')
    header = _header(io.BytesIO(data), len(data))
    _validate_expected(header, expected)
    endian = '<' if header['format']['endian'] == 'little' else '>'
    integer_bytes = header['format']['integer_bytes']
    integer = struct.Struct(endian+('i' if integer_bytes == 4 else 'q'))
    r = header['records'][3]
    raw_miller = data[r['payload_offset']:r['payload_offset']+r['payload_bytes']]
    numbers = [x[0] for x in integer.iter_unpack(raw_miller)]
    miller = [numbers[i:i+3] for i in range(0, len(numbers), 3)]
    _require(len({tuple(m) for m in miller}) == header['igwx'], 'Duplicate native Miller indices')
    _require(all(abs(i) <= MAX_NGW for m in miller for i in m), 'Miller integer outside restricted index range')
    # Wavefunction support is k-dependent. Neither G=0 nor inversion closure
    # is a format requirement; density-file support rules do not apply here.
    ng, bands = header['igwx'], header['nbnd']
    coefficients = [[[0j for _ in range(bands)] for _ in range(ng)] for _ in range(2)]
    pair = struct.Struct(endian+'dd')
    payload_hash = hashlib.sha256()
    for band, record in enumerate(header['records'][4:]):
        raw = data[record['payload_offset']:record['payload_offset']+record['payload_bytes']]
        payload_hash.update(raw)
        restored = bytearray()
        for index, (real, imag) in enumerate(pair.iter_unpack(raw)):
            _require(math.isfinite(real) and math.isfinite(imag), 'Nonfinite coefficient real/imaginary component')
            component, g = divmod(index, ng)
            z = complex(real, imag)
            coefficients[component][g][band] = z
            restored.extend(pair.pack(z.real, z.imag))
        _require(bytes(restored) == raw, 'ComplexF64 coefficient bitwise round-trip failed')
    header.update(miller_values_status='PASS', coefficient_values_status='PASS',
                  coefficient_bitwise_roundtrip_status='PASS', source_sha256=sha)
    return {'schema_version': 1, 'qe_wfc_format_status': 'PASS', 'metadata': header,
            'miller': miller, 'coefficients': coefficients, 'shape': [2, ng, bands],
            'source_sha256': sha, 'miller_payload_sha256': hashlib.sha256(raw_miller).hexdigest(),
            'coefficient_payload_sha256': payload_hash.hexdigest(), 'coefficient_dtype': 'ComplexF64',
            'coefficient_layout': 'component,native_G_position,original_band',
            'coefficient_transformations': 'NONE; representation-only component/band indexing',
            'physical_validation_status': 'NOT_PERFORMED_BY_FORMAT_READER'}
