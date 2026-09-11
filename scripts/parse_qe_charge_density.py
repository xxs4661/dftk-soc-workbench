#!/usr/bin/env python3
"""Read the restricted QE 7.5 non-HDF5 charge-density record format.

This is a binary format reader, not a QE algorithm. It preserves native Miller
order and ComplexF64 values. It never scales, conjugates, completes half-G data,
or establishes historical provenance from a newly computed hash alone.
"""
import hashlib
import itertools
import math
from pathlib import Path
import struct

FORMAT_SOURCES = {
    'records': 'https://github.com/QEF/q-e/blob/qe-7.5/Modules/io_base.f90#L402-L594',
    'charge_only_and_reciprocal_columns': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/io_rho_xml.f90#L23-L62',
}
MAX_NGM = 1_000_000


class ChargeDensityParseError(ValueError):
    def __init__(self, reason, status='FAIL', candidate_failures=None):
        super().__init__(reason)
        self.status = status
        self.candidate_failures = candidate_failures or []


def _records(data, endian, marker_bytes, max_ngm):
    marker = struct.Struct(endian + ('i' if marker_bytes == 4 else 'q'))
    records = []
    offset = 0
    while offset < len(data):
        if len(records) >= 7:
            raise ValueError('Extra trailing records')
        if len(data) - offset < 2*marker_bytes:
            raise ValueError('Truncated record marker')
        size = marker.unpack_from(data, offset)[0]
        if size <= 0:
            raise ValueError('Zero/negative or split Fortran record marker is unsupported')
        if size > max(72, 24*max_ngm):
            raise ValueError('Record exceeds declared size ceiling')
        end = offset + marker_bytes + size
        if end + marker_bytes > len(data):
            raise ValueError('Truncated record payload')
        if marker.unpack_from(data, end)[0] != size:
            raise ValueError('Leading/trailing record markers disagree')
        records.append(memoryview(data)[offset+marker_bytes:end])
        offset = end + marker_bytes
    if offset != len(data) or len(records) < 4:
        raise ValueError('Missing records or unread trailing bytes')
    return records


def _decode(records, endian, integer_bytes, logical_bytes, max_ngm):
    if len(records[0]) != logical_bytes + 2*integer_bytes:
        raise ValueError('Header size differs from logical/integer candidate')
    integer = struct.Struct(endian + ('i' if integer_bytes == 4 else 'q'))
    logical = struct.Struct(endian + ('i' if logical_bytes == 4 else 'q'))
    gamma_raw = logical.unpack_from(records[0])[0]
    if gamma_raw not in (0, 1, -1):
        raise ValueError('Unsupported LOGICAL representation')
    ngm = integer.unpack_from(records[0], logical_bytes)[0]
    nspin = integer.unpack_from(records[0], logical_bytes + integer_bytes)[0]
    if not 1 <= ngm <= max_ngm:
        raise ValueError('ngm is outside the declared positive size ceiling')
    if not 1 <= nspin <= 4:
        raise ValueError('nspin is outside the supported header size ceiling')
    if len(records) != 3+nspin:
        raise ValueError('Record count disagrees with saved nspin')
    if len(records[1]) != 9*8 or len(records[2]) != 3*ngm*integer_bytes:
        raise ValueError('Reciprocal lattice or Miller payload length mismatch')
    if any(len(record) != 16*ngm for record in records[3:]):
        raise ValueError('ComplexF64 coefficient payload length mismatch')
    real = struct.Struct(endian + 'd')
    numbers = [real.unpack_from(records[1], i*8)[0] for i in range(9)]
    if not all(math.isfinite(value) for value in numbers):
        raise ValueError('Nonfinite reciprocal lattice component')
    columns = [numbers[i:i+3] for i in (0, 3, 6)]
    a, b, c = columns
    determinant = (a[0]*(b[1]*c[2]-b[2]*c[1])
                   - b[0]*(a[1]*c[2]-a[2]*c[1])
                   + c[0]*(a[1]*b[2]-a[2]*b[1]))
    if not math.isfinite(determinant) or determinant == 0:
        raise ValueError('Singular/nonfinite reciprocal lattice determinant')
    # Fortran mill(3,ngm): the three coordinates of each G are contiguous.
    miller = [tuple(integer.unpack_from(records[2], (3*i+j)*integer_bytes)[0]
                    for j in range(3)) for i in range(ngm)]
    if len(set(miller)) != ngm:
        raise ValueError('Duplicate Miller indices, including possible duplicate G=0')
    if miller.count((0, 0, 0)) != 1:
        raise ValueError('Missing unique G=0 Miller index')
    pair = struct.Struct(endian + 'dd')
    components = []
    for record in records[3:]:
        values = [complex(*pair.unpack_from(record, 16*i)) for i in range(ngm)]
        if not all(math.isfinite(z.real) and math.isfinite(z.imag) for z in values):
            raise ValueError('Nonfinite charge coefficient real/imaginary component')
        components.append(values)
    return {'gamma_only': gamma_raw != 0, 'gamma_only_raw': gamma_raw,
            'ngm': ngm, 'nspin': nspin, 'b_columns_bohr_inv': columns,
            'miller': miller, 'rho_components': components,
            'g_zero_index': miller.index((0, 0, 0)),
            'record_lengths': [len(record) for record in records]}


def _select_unique(candidates):
    """No numerical closeness or DFTK comparison may resolve an ambiguity."""
    if len(candidates) != 1:
        raise ChargeDensityParseError('Ambiguous binary encoding: multiple fully validated candidates', 'UNSUPPORTED')
    return candidates[0]


def _check_limits(expected_ngm, max_ngm):
    if type(max_ngm) is not int or not 1 <= max_ngm <= MAX_NGM:
        raise ChargeDensityParseError('max_ngm must be a positive integer no larger than 1000000')
    if expected_ngm is not None and (type(expected_ngm) is not int or not 1 <= expected_ngm <= max_ngm):
        raise ChargeDensityParseError('Invalid independently expected ngm')


def parse_charge_density_bytes(data, *, expected_ngm=None, max_ngm=MAX_NGM):
    """Parse complete bytes; used also by independent synthetic writer tests."""
    if not isinstance(data, bytes):
        raise ChargeDensityParseError('Input must be immutable raw bytes')
    _check_limits(expected_ngm, max_ngm)
    if len(data) > 88*max_ngm + 1024:
        raise ChargeDensityParseError('File exceeds bounded record-format size ceiling')
    if data.startswith(b'\x89HDF\r\n\x1a\n'):
        raise ChargeDensityParseError('HDF5 charge density is explicitly unsupported; no conversion performed', 'UNSUPPORTED')
    candidates = []
    failures = []
    for endian, marker_bytes in itertools.product(('<', '>'), (4, 8)):
        try:
            records = _records(data, endian, marker_bytes, max_ngm)
        except (ValueError, struct.error) as error:
            failures.append({'endian': endian, 'record_marker_bytes': marker_bytes, 'reason': str(error)})
            continue
        for integer_bytes, logical_bytes in itertools.product((4, 8), repeat=2):
            encoding = {'endian': 'little' if endian == '<' else 'big',
                        'record_marker_bytes': marker_bytes,
                        'integer_bytes': integer_bytes, 'logical_bytes': logical_bytes,
                        'real_bytes': 8, 'complex_bytes': 16}
            try:
                decoded = _decode(records, endian, integer_bytes, logical_bytes, max_ngm)
                decoded['encoding'] = encoding
                candidates.append(decoded)
            except (ValueError, struct.error, ArithmeticError) as error:
                failures.append(dict(encoding, reason=str(error)))
    if not candidates:
        raise ChargeDensityParseError('No binary encoding satisfies every record/header/payload/finite/G constraint',
                                      candidate_failures=failures)
    result = _select_unique(candidates)
    if result['gamma_only'] or result['nspin'] != 1:
        raise ChargeDensityParseError('Only gamma_only=false and one saved total-charge component are supported', 'UNSUPPORTED')
    if expected_ngm is not None and result['ngm'] != expected_ngm:
        raise ChargeDensityParseError('Actual density ngm differs from independently expected XML ngm')
    result['rho_g'] = result.pop('rho_components')[0]
    result.update(schema_version=1, binary_parse_status='PASS',
                  format='QE 7.5 non-HDF5 sequential Fortran charge-density records',
                  sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
                  candidate_count=len(candidates), format_sources=FORMAT_SOURCES,
                  coefficient_convention='Native rho%of_g; no scaling or conjugation applied',
                  source_binding_status='REQUIRES_HISTORICAL_RECEIPT')
    return result


def parse_qe_charge_density(path, *, expected_ngm=None, max_ngm=MAX_NGM):
    """Read one file without writing; caller must first bind its historical hash."""
    _check_limits(expected_ngm, max_ngm)
    source = Path(path)
    try:
        if source.stat().st_size > 88*max_ngm + 1024:
            raise ChargeDensityParseError('File exceeds bounded record-format size ceiling')
        return parse_charge_density_bytes(source.read_bytes(), expected_ngm=expected_ngm, max_ngm=max_ngm)
    except OSError as error:
        raise ChargeDensityParseError('Charge-density source is unavailable: ' + type(error).__name__, 'BLOCKED') from error
