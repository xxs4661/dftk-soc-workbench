#!/usr/bin/env python3
"""Bounded independent readers for the fixed public Phase 7F evidence.

This module does not import production parsers. Original bytes are exact inputs;
the numerical module separately assesses derived floating point quantities.
Only the published LE/M4/I4/L4 spinor WFC and P2 formats are supported.
"""
from __future__ import annotations

import ast
import csv
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zipfile

import numpy as np


class InputIdentityError(ValueError):
    """A public input violates the exact identity or supported-format contract."""


def require(condition, message):
    if not condition:
        raise InputIdentityError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_path(root, relative):
    p = Path(relative)
    require(not p.is_absolute() and '..' not in p.parts, 'non-public source path')
    require(not any(x.startswith('.') for x in p.parts), 'hidden source path')
    root = Path(root).resolve()
    resolved = (root / p).resolve()
    require(resolved.is_relative_to(root), 'source escapes public root')
    require(resolved.is_file(), f'missing public input: {relative}')
    return resolved


def verify_sources(root, manifest):
    """Hash the explicit plan whitelist before any data parser sees its bytes."""
    require(isinstance(manifest, dict) and bool(manifest), 'empty input manifest')
    receipt = {}
    for relative, expected in sorted(manifest.items()):
        require(re.fullmatch(r'[0-9a-f]{64}', expected) is not None, 'invalid source SHA')
        path = source_path(root, relative)
        h = hashlib.sha256()
        with path.open('rb') as stream:
            first = stream.read(4096)
            require(not first.startswith(b'version https://git-lfs.github.com/spec/v1'),
                    f'unmaterialized LFS pointer: {relative}')
            h.update(first)
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
        require(h.hexdigest() == expected, f'source SHA mismatch: {relative}')
        receipt[relative] = {'sha256': expected, 'bytes': path.stat().st_size}
    return receipt


def load_canonical_npz(path, declaration, max_expanded_bytes=64 * 1024 * 1024):
    """Validate ZIP/NPY before NumPy allocation; no pickle, implicit extra keys,
    object arrays or unconstrained expanded payloads. Hash the NPY container and
    declared-order array bytes separately, even for Fortran-stored NPY members.
    """
    require(declaration.get('container', 'numpy.npz') == 'numpy.npz' and
            declaration.get('allow_pickle', False) is False, 'unsupported package declaration')
    raw = Path(path).read_bytes()
    require(len(raw) == declaration['bytes'], 'NPZ compressed size mismatch')
    require(digest(raw) == declaration['sha256'], 'NPZ compressed SHA mismatch')
    arrays, receipt = {}, {}
    expected = declaration['arrays']
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [x.filename for x in infos]
            require(len(names) == len(set(names)), 'duplicate NPZ member')
            require(set(names) == {x + '.npy' for x in expected}, 'undeclared or missing NPZ member')
            require(sum(x.file_size for x in infos) <= max_expanded_bytes, 'NPZ expansion limit')
            for info in infos:
                require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        'unsupported ZIP compression')
                name = info.filename[:-4]
                spec = expected[name]
                require(spec['dtype'] in ('<f8', '<c16', '<i8'), 'unsupported declared dtype')
                require(spec['order'] in ('C', 'F'), 'invalid expanded-byte order')
                shape = spec['shape']
                require(isinstance(shape, list) and 0 < len(shape) <= 4 and
                        all(type(n) is int and 0 < n <= 1_000_000 for n in shape),
                        'invalid declared shape')
                size = math.prod(shape) * np.dtype(spec['dtype']).itemsize
                require(size == spec['bytes'] and size <= max_expanded_bytes, 'declared byte limit')
                require(size <= info.file_size <= size + 65536, 'NPY container size mismatch')
                payload = archive.read(info)
                require(payload[:6] == b'\x93NUMPY', 'invalid NPY magic')
                version = payload[6:8]
                require(version in (b'\x01\x00', b'\x02\x00'), 'unsupported NPY version')
                offset = 10 if version == b'\x01\x00' else 12
                nheader = struct.unpack('<H' if offset == 10 else '<I', payload[8:offset])[0]
                require(nheader <= 65524 and offset + nheader <= len(payload), 'truncated NPY header')
                header = ast.literal_eval(payload[offset:offset + nheader].decode('latin1'))
                require(set(header) == {'descr', 'fortran_order', 'shape'}, 'unknown NPY header field')
                require(header['descr'] == spec['dtype'], 'NPY dtype identity mismatch')
                require(header['shape'] == tuple(shape), 'NPY shape identity mismatch')
                require(type(header['fortran_order']) is bool, 'invalid NPY storage order')
                require(len(payload) == offset + nheader + size, 'truncated or trailing NPY bytes')
                arr = np.load(io.BytesIO(payload), allow_pickle=False, max_header_size=65536)
                require(not arr.dtype.hasobject and np.isfinite(arr).all(), 'object or nonfinite array')
                expanded = arr.tobytes(order=spec['order'])
                require(digest(expanded) == spec['sha256'], 'expanded array SHA mismatch: ' + name)
                arr.flags.writeable = False
                arrays[name] = arr
                receipt[name] = {'dtype': arr.dtype.str, 'shape': list(arr.shape),
                                 'expanded_order': spec['order'], 'expanded_sha256': digest(expanded),
                                 'npy_storage_order': 'F' if header['fortran_order'] else 'C',
                                 'npy_container_sha256': digest(payload), 'bytes': size}
    except (zipfile.BadZipFile, EOFError, KeyError, SyntaxError, UnicodeError, struct.error) as exc:
        raise InputIdentityError('invalid or truncated NPZ: ' + str(exc)) from exc
    return arrays, receipt


def verify_array_immutability(arrays, receipt):
    """Recheck original in-memory bytes after the independent numerical path."""
    require(set(arrays) == set(receipt), 'original array key set changed')
    for name, arr in arrays.items():
        spec = receipt[name]
        require(arr.dtype.str == spec['dtype'] and list(arr.shape) == spec['shape'],
                'original array dimensions or dtype changed: ' + name)
        require(digest(arr.tobytes(order=spec['expanded_order'])) == spec['expanded_sha256'],
                'original array bytes changed: ' + name)
    return {'status': 'EXACT_MATCH', 'array_count': len(arrays)}


def reconstruct_wfc(kpoint, original):
    """Reassemble every native WFC record in memory without a native file copy."""
    meta = original['metadata']
    require(meta['format'] == {'endian': 'little', 'record_marker_bytes': 4,
                              'integer_bytes': 4, 'logical_bytes': 4,
                              'real_bytes': 8, 'complex_bytes': 16}, 'unsupported native WFC format')
    c = kpoint['coefficients']
    g = kpoint['millers']
    require(c.shape == (2, meta['igwx'], meta['nbnd']) and g.shape == (meta['igwx'], 3),
            'native WFC dimensions')
    require(meta['npol'] == 2 and meta['ispin'] == 1 and meta['gamma_only_raw'] == 0
            and meta['gamma_only'] is False and meta['scalef'] == 1.0, 'unsupported native spinor flags')
    require(np.array_equal(np.array(meta['k_cart_bohr_inv']), kpoint['k_cart']), 'native k mismatch')
    require(np.issubdtype(g.dtype, np.integer) and (g >= -(2**31)).all() and
            (g < 2**31).all(), 'native Miller int32 range')
    header = [struct.pack('<i3diid', meta['ik'], *meta['k_cart_bohr_inv'],
                          meta['ispin'], meta['gamma_only_raw'], meta['scalef']),
              struct.pack('<4i', meta['ngw'], meta['igwx'], meta['npol'], meta['nbnd']),
              # Metadata stores a list of column vectors (outer index = column).
              # This differs from state['reciprocal_columns'], a matrix.
              np.asarray(meta['b_columns_bohr_inv'], dtype='<f8').tobytes(order='C')]
    miller = np.asarray(g, dtype='<i4').tobytes(order='C')
    bands = [np.asarray(c[:, :, band], dtype='<c16').tobytes(order='C')
             for band in range(c.shape[2])]
    require(digest(b''.join(header)) == meta['header_payload_sha256'], 'native header SHA mismatch')
    require(digest(miller) == original['miller_payload_sha256'], 'native Miller SHA mismatch')
    require(digest(b''.join(bands)) == original['coefficient_payload_sha256'], 'native coefficient SHA mismatch')
    payloads = header + [miller] + bands
    require([len(x) for x in payloads] == meta['record_payload_bytes'], 'native record sizes')
    native = bytearray()
    for payload, envelope in zip(payloads, meta['records'], strict=True):
        require(envelope == {'payload_offset': len(native) + 4, 'payload_bytes': len(payload)},
                'native record offset')
        marker = struct.pack('<i', len(payload))
        native.extend(marker + payload + marker)
    require(len(native) == meta['file_bytes'], 'native file length')
    require(digest(native) == original['source_sha256'] == meta['source_sha256'], 'native whole-file SHA mismatch')
    return {'sha256': digest(native), 'bytes': len(native), 'records': len(payloads),
            'bands': c.shape[2], 'status': 'EXACT_MATCH', 'native_file_written': False}


def decimal_token(token):
    """Return a native decimal and half its last printed place (before units)."""
    require(re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?', token) is not None,
            'invalid decimal token')
    try:
        d = Decimal(token.replace('D', 'E').replace('d', 'e'))
        return d, Decimal(5).scaleb(d.as_tuple().exponent - 1)
    except InvalidOperation as exc:
        raise InputIdentityError('invalid decimal token') from exc


def _gzip_text(path, limit=16 * 1024 * 1024):
    try:
        with gzip.open(path, 'rb') as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit, 'gzip expansion limit')
        return raw.decode('ascii')
    except (OSError, EOFError, UnicodeError) as exc:
        raise InputIdentityError('invalid or truncated gzip') from exc


def read_filplot(path, lattice_columns, grid=(40, 40, 40)):
    """Fixed ibrav=0, one-species/one-atom plot_num=2 native formatted output.

    Header cell printing is checked but never used to refit the physical volume.
    No padding is present in this authenticated package; unexpected padding fails.
    """
    lines = _gzip_text(path).splitlines()
    require(len(lines) >= 10, 'truncated filplot header')
    dims = [int(x) for x in lines[1].split()]
    require(dims == [*grid, *grid, 1, 1], 'filplot grid/padding/species/atoms')
    cell = lines[2].split()
    require(len(cell) == 7 and int(cell[0]) == 0, 'filplot ibrav/celldm format')
    alat, alat_u = decimal_token(cell[1])
    require(alat > 0 and all(Decimal(x) == 0 for x in cell[2:]), 'filplot unsupported celldm')
    printed = [line.split() for line in lines[3:6]]
    require(all(len(row) == 3 for row in printed), 'filplot lattice header')
    physical = np.asarray(lattice_columns)
    require(physical.shape == (3, 3), 'physical lattice dimensions')
    for j, row in enumerate(printed):
        for i, token in enumerate(row):
            factor, factor_u = decimal_token(token)
            center = alat * factor
            radius = abs(factor) * alat_u + abs(alat) * factor_u + alat_u * factor_u
            require(abs(float(center) - physical[i, j]) <= float(radius) + 1e-13,
                    'filplot header differs from source-certified physical lattice')
    info = lines[6].split()
    require(len(info) == 4 and int(info[3]) == 2, 'filplot plot_num is not 2')
    species = lines[7].split()
    require(len(species) == 3 and species[:2] == ['1', 'Mg'], 'filplot species header')
    atom = lines[8].split()
    require(len(atom) == 5 and atom[0] == '1' and atom[-1] == '1', 'filplot atom header')
    require(all(decimal_token(t)[0].is_finite() for t in info[:3] + species[2:] + atom[1:4]),
            'filplot nonfinite header')
    tokens = tuple(' '.join(lines[9:]).split())
    require(len(tokens) == math.prod(grid), 'filplot values count')
    values, widths = [], []
    for token in tokens:
        d, half = decimal_token(token)
        values.append(float(d / 2))
        widths.append(float(half / 2))
    values = np.array(values, dtype='<f8').reshape(grid, order='F')
    widths = np.array(widths, dtype='<f8').reshape(grid, order='F')
    require(np.isfinite(values).all() and np.isfinite(widths).all(), 'nonfinite filplot values')
    values.flags.writeable = widths.flags.writeable = False
    return {'values_ha': values, 'halfwidth_ha': widths, 'tokens': tokens,
            'token_sha256': digest('\n'.join(tokens).encode('ascii')), 'grid': list(grid),
            'lattice_columns': physical, 'plot_num': 2, 'padding': [0, 0, 0],
            'source_units': 'Ry', 'units': 'Ha', 'unit_divisions_by_two': 1,
            'ordering': 'first index fastest', 'header_lattice_used_for_volume': False}


def read_density_csv(path, expected_count=22119):
    reader = csv.reader(io.StringIO(_gzip_text(path)))
    require(next(reader, None) == ['m1', 'm2', 'm3', 'QE_real', 'QE_imag'], 'density CSV header')
    millers, values = [], []
    for row in reader:
        require(len(row) == 5, 'density CSV columns')
        require(all(re.fullmatch(r'-?\d+', x) for x in row[:3]), 'noninteger density Miller')
        millers.append(tuple(int(x) for x in row[:3]))
        values.append(complex(float(row[3]), float(row[4])))
    require(len(values) == expected_count, 'density CSV count')
    require(len(set(millers)) == len(millers), 'duplicate density Miller')
    g, c = np.array(millers, dtype='<i8'), np.array(values, dtype='<c16')
    require(np.isfinite(c).all(), 'nonfinite density coefficient')
    g.flags.writeable = c.flags.writeable = False
    return {'millers': g, 'coefficients': c}


def verify_xml(path, state, qmeta):
    """Bind unaltered original occupations (already wg/wk) and energies to XML."""
    raw = Path(path).read_bytes()
    require(digest(raw) == qmeta['xml']['source_xml_sha256'], 'original XML SHA')
    root = ET.fromstring(raw)
    for node in root.iter():
        node.tag = node.tag.split('}')[-1]
    out = root.find('output')
    require(out is not None, 'XML output missing')
    atomic = out.find('atomic_structure')
    band = out.find('band_structure')
    require(atomic is not None and band is not None, 'XML structures missing')
    require(band.findtext('lsda') == 'false' and band.findtext('noncolin') == 'true'
            and band.findtext('spinorbit') == 'true', 'XML spinor state')
    require(int(band.findtext('nbnd')) == 24 and int(band.findtext('nks')) == 3,
            'original Q 3k/24 states')
    require(qmeta['occupation_capacity'] == qmeta['xml']['capacity'] == 1,
            'original occupation capacity')
    lattice = np.array([[float(x) for x in atomic.findtext('cell/a' + str(i)).split()]
                        for i in range(1, 4)], dtype='<f8').T
    require(np.array_equal(lattice, state['lattice_columns']), 'XML lattice exact identity')
    alat = float(atomic.attrib['alat'])
    native = qmeta['xml']['native_tokens']
    rows = band.findall('ks_energies')
    require(len(rows) == len(state['kpoints']) == len(native) == 3, 'XML k count')
    for row, k, tokens in zip(rows, state['kpoints'], native, strict=True):
        point = row.find('k_point')
        ktokens = point.text.split()
        ftokens = row.findtext('occupations').split()
        etokens = row.findtext('eigenvalues').split()
        require(ktokens == tokens['k'] and ftokens == tokens['occupations'] and
                etokens == tokens['eigenvalues_ha'] and point.attrib['weight'] == tokens['weight'],
                'XML native token identity')
        f, e = np.array(ftokens, dtype='<f8'), np.array(etokens, dtype='<f8')
        require(f.shape == e.shape == (24,) and np.isfinite(f).all() and
                (f >= 0).all() and (f <= 1).all(), 'XML physical occupations')
        require(np.array_equal(f, k['occupations']) and np.array_equal(e, k['eigenvalues']),
                'XML original f/e exact identity')
        require(float(point.attrib['weight']) == k['weight'] and k['weight'] > 0,
                'XML original spatial weight')
        require(np.array_equal(np.array(ktokens, dtype='<f8') * (2 * np.pi / alat), k['k_cart']),
                'XML original cartesian k identity')
        require(int(row.findtext('npw')) == len(k['millers']), 'XML plane-wave count')
    return {'status': 'EXACT_MATCH', 'k_count': 3, 'bands_per_k': 24, 'occupation_capacity': 1,
            'occupation_convention': 'XML f = original wg/wk; original spatial w applied once',
            'eigenvalue_units': 'Ha in XML, no conversion', 'electrons': float(band.findtext('nelec'))}


def read_inputs(source_root, plan):
    """Read only plan-listed public inputs; caller runs synthetic tests first.

    Historical tables are returned as data, never substituted for new numerics.
    This function is intended for the single formal Linux execution.
    """
    manifest = plan['input_sha256']
    identities = verify_sources(source_root, manifest)
    def path(relative):
        require(relative in manifest, 'unknown source outside explicit manifest: ' + relative)
        return source_path(source_root, relative)
    def js(relative):
        return json.loads(path(relative).read_text())
    base = 'results/mg-soc-wavefunction-energy/'
    evidence = js(base + 'evidence.json')
    q, qreceipt = load_canonical_npz(path(base + 'qe-orbitals.npz'), evidence['packages']['qe-orbitals'])
    op, opreceipt = load_canonical_npz(path(base + 'nonlocal-operator.npz'), evidence['packages']['nonlocal-operator'])
    state = {key: q[key] for key in ('lattice_columns', 'reciprocal_columns')}
    state['kpoints'] = [{**{key: q[f'k{i}_{key}'] for key in
                           ('millers', 'coefficients', 'occupations', 'eigenvalues', 'k_cart')},
                         'weight': float(q[f'k{i}_weight'][0])} for i in range(1, 4)]
    operator = {'D': op['D'], 'kpoints': [{'P': op[f'k{i}_P'], 'millers': op[f'k{i}_millers']}
                                        for i in range(1, 4)]}
    operator['P'] = [x['P'] for x in operator['kpoints']]
    operator['millers'] = [x['millers'] for x in operator['kpoints']]
    qmeta = evidence['Q_source_metadata']
    xml = verify_xml(path('results/mg-soc-qe-diagnostics/G40/qe.xml'), state, qmeta)
    require(qmeta['n_bands'] == 24 and qmeta['fft_size'] == [40, 40, 40], 'Q public shape contract')
    wfc = []
    for index, (k, orig) in enumerate(zip(state['kpoints'], qmeta['original_wfc'], strict=True), 1):
        require(orig['metadata']['ik'] == index, 'original WFC k index')
        require(np.array_equal(np.array(orig['metadata']['b_columns_bohr_inv']).T,
                               state['reciprocal_columns']), 'native reciprocal identity')
        wfc.append(reconstruct_wfc(k, orig))
    saved = read_density_csv(path('results/mg-soc-density-hartree/qe-rho.csv.gz'))
    potential = read_filplot(path('results/mg-soc-qe-local-potential/P2/local-ionic.pp.gz'),
                            state['lattice_columns'])
    tables = js(base + 'state-checks.json')
    nonlocal_tables = js(base + 'nonlocal-checks.json')
    ab = {}
    for label in ('A', 'B'):
        kpoints = []
        for i in range(1, 4):
            original_rows = nonlocal_tables['states'][label]['kpoints'][i - 1]['rows']
            states = tables[label]['per_k'][i - 1]['states']
            require(len(original_rows) == len(states) == 24, 'A/B full state-table count')
            occupations = np.array([r['occupation'] for r in original_rows], dtype='<f8')
            weight = float(original_rows[0]['weight_spatial'])
            require(all(r['weight_spatial'] == weight for r in original_rows), 'A/B row weights')
            require(np.array_equal(occupations, [r['occupation'] for r in states]), 'A/B table f identity')
            occupations.flags.writeable = False
            kpoints.append({'up': op[f'{label}_k{i}_up'], 'down': op[f'{label}_k{i}_down'],
                            'occupations': occupations, 'weight': weight,
                            'rows': original_rows, 'states': states})
        ab[label] = {'kpoints': kpoints}
    return {'state': state, 'operator': operator, 'ab': ab, 'saved_density': saved,
            'potential': potential, 'package_arrays': {'Q': q, 'operator': op},
            'identity': {'files': identities, 'packages': {'Q': qreceipt, 'operator': opreceipt},
                         'xml': xml, 'native_wfc': wfc},
            'historical': {'state_checks': tables, 'nonlocal_checks': nonlocal_tables,
                           'comparison': js(base + 'comparison.json')},
            'metadata': qmeta}
