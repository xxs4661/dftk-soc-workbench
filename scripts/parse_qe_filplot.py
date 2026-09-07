#!/usr/bin/env python3
"""Restricted QE 7.5 filplot reader; no interpolation or numerical QE code.

Only ibrav=0 and plot_num 0/2 are supported. Returned physical values retain
the native origin and first-index-fastest order. Decimal bounds describe the
printed token, not the error of the reconstructed potential/density.
"""
from decimal import Decimal, localcontext
import gzip
import hashlib
import math
from pathlib import Path
import re


FORMAT_SOURCE = 'https://github.com/QEF/q-e/blob/qe-7.5/Modules/plot_io.f90#L55-L68'
MAX_POINTS = 2_000_000
MAX_BYTES = 64_000_000
_NUMBER = re.compile(r'[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[EeDd][+-]?[0-9]+)?\Z')
_INTEGER = re.compile(r'[+-]?[0-9]+\Z')


class FilplotParseError(ValueError):
    def __init__(self, reason, status='FAIL'):
        super().__init__(reason)
        self.status = status


def decimal_token(token):
    """Return exact decimal value and nearest-rounding half last printed place."""
    if not isinstance(token, str) or not _NUMBER.fullmatch(token):
        raise FilplotParseError('Malformed or nonfinite decimal token: ' + repr(token))
    mantissa, *exponent = re.split('[EeDd]', token)
    digits = len(mantissa.split('.', 1)[1]) if '.' in mantissa else 0
    power = int(exponent[0]) if exponent else 0
    if abs(power) > 300 or digits > 100:
        raise FilplotParseError('Decimal exponent/precision outside supported finite range')
    value = Decimal(token.replace('d', 'e').replace('D', 'E'))
    halfwidth = Decimal(5).scaleb(power-digits-1)
    if not math.isfinite(float(value)) or not math.isfinite(float(halfwidth)):
        raise FilplotParseError('Nonfinite decimal value or print interval')
    return value, halfwidth


def _integer(token, label):
    if not _INTEGER.fullmatch(token):
        raise FilplotParseError('Invalid integer in ' + label)
    return int(token)


def _det(columns):
    a, b, c = columns
    return (a[0]*(b[1]*c[2]-b[2]*c[1]) - b[0]*(a[1]*c[2]-a[2]*c[1])
            + c[0]*(a[1]*b[2]-a[2]*b[1]))


def _contains(value, interval, label):
    if isinstance(value, bool):
        raise FilplotParseError('Invalid expected numeric value: ' + label)
    try:
        target = Decimal(str(value))
    except Exception as exc:
        raise FilplotParseError('Invalid expected numeric value: ' + label) from exc
    if not target.is_finite():
        raise FilplotParseError('Nonfinite expected numeric value: ' + label)
    # XML-to-Float64 products can incur a few arithmetic ulps. This does not
    # enlarge the native token's reported decimal quantization interval.
    slack = Decimal(str(8*math.ulp(float(target))))
    if not interval[0]-slack <= target <= interval[1]+slack:
        raise FilplotParseError('Expected ' + label + ' is outside native print interval')


def _interval(token):
    value, width = decimal_token(token)
    return value-width, value+width


def _product_interval(left, right):
    values = [a*b for a in left for b in right]
    return min(values), max(values)


def validate_expected(parsed, expected):
    """Check explicitly supplied source-bound geometry; do not fit registration."""
    if not isinstance(expected, dict):
        raise FilplotParseError('Expected geometry must be an object')
    supported = {'grid', 'lattice_columns_bohr', 'positions_cartesian_bohr',
                 'species', 'atom_species_indices', 'cutoffs', 'unit'}
    if set(expected)-supported:
        raise FilplotParseError('Unknown expected filplot fields: ' + str(sorted(set(expected)-supported)))
    header = parsed['header']
    if 'grid' in expected and expected['grid'] != parsed['grid']:
        raise FilplotParseError('Physical grid differs from requested grid')
    if 'unit' in expected and expected['unit'] != parsed['unit']:
        raise FilplotParseError('Requested unit disagrees with source-backed plot_num unit')
    if 'species' in expected:
        species = expected['species']
        if not isinstance(species, list) or len(species) != len(header['species']):
            raise FilplotParseError('Species count differs from requested species')
        for requested, actual in zip(species, header['species']):
            if not isinstance(requested, dict) or set(requested) != {'symbol', 'z_valence'}:
                raise FilplotParseError('Expected species requires symbol and z_valence')
            if requested['symbol'] != actual['symbol']:
                raise FilplotParseError('Species symbol differs from requested species')
            _contains(requested['z_valence'], _interval(actual['z_valence_token']), 'z_valence')
    if 'atom_species_indices' in expected:
        if expected['atom_species_indices'] != [a['species_index'] for a in header['atoms']]:
            raise FilplotParseError('Atom species association differs from requested geometry')
    with localcontext() as context:
        context.prec = 60
        alat = _interval(header['celldm_tokens'][0])
        for key, actual in [('lattice_columns_bohr', header['at_columns_tokens']),
                            ('positions_cartesian_bohr', [a['tau_tokens'] for a in header['atoms']])]:
            if key not in expected:
                continue
            requested = expected[key]
            if not isinstance(requested, list) or len(requested) != len(actual):
                raise FilplotParseError('Expected geometry dimensions differ: ' + key)
            for i, (want, tokens) in enumerate(zip(requested, actual)):
                if not isinstance(want, list) or len(want) != 3:
                    raise FilplotParseError('Expected vector must have three components: ' + key)
                for j in range(3):
                    _contains(want[j], _product_interval(alat, _interval(tokens[j])),
                              '%s[%d][%d]' % (key, i, j))
    if 'cutoffs' in expected:
        cutoffs = expected['cutoffs']
        if not isinstance(cutoffs, dict) or set(cutoffs) != {'gcutm', 'dual', 'ecut_ry'}:
            raise FilplotParseError('Expected cutoffs require gcutm, dual, ecut_ry')
        for key, token in zip(('gcutm', 'dual', 'ecut_ry'), header['cutoff_tokens']):
            _contains(cutoffs[key], _interval(token), key)
    return 'PASS'


def parse_qe_filplot(path, *, expected_plot_num, expected=None):
    """Read native bytes or their gzip container; errors never return a PASS.

    ``expected`` accepts explicit source-bound grid, lattice vector columns in
    bohr, atom Cartesian positions in bohr, indexed species, and cutoffs.
    A format-only parse does not establish input provenance or registration.
    """
    if type(expected_plot_num) is not int or expected_plot_num not in (0, 2):
        raise FilplotParseError('Only requested plot_num 0 or 2 is supported', 'UNSUPPORTED')
    stored = Path(path).read_bytes()
    if len(stored) > MAX_BYTES:
        raise FilplotParseError('Stored filplot exceeds supported byte ceiling')
    if stored.startswith(b'\x1f\x8b'):
        try:
            with gzip.open(path, 'rb') as stream:
                data = stream.read(MAX_BYTES+1)
        except (OSError, EOFError) as exc:
            raise FilplotParseError('Invalid gzip filplot container') from exc
    else:
        data = stored
    if len(data) > MAX_BYTES:
        raise FilplotParseError('Native filplot exceeds supported byte ceiling')
    try:
        lines = data.decode('ascii').splitlines()
    except UnicodeDecodeError as exc:
        raise FilplotParseError('Non-ASCII filplot is unsupported') from exc
    if not lines or len(lines[0]) > 75:
        raise FilplotParseError('Missing or overlong native title line')
    cursor = 1
    raw_header = [lines[0]]

    def line_tokens(count, label):
        nonlocal cursor
        if cursor >= len(lines):
            raise FilplotParseError('Missing header line: ' + label)
        line = lines[cursor]
        cursor += 1
        raw_header.append(line)
        tokens = line.split()
        if len(tokens) != count:
            raise FilplotParseError('Wrong header field count: ' + label)
        return tokens

    dimensions = [_integer(t, 'dimensions') for t in line_tokens(8, 'dimensions')]
    nr1x, nr2x, nr3x, nr1, nr2, nr3, nat, ntyp = dimensions
    if min(dimensions) <= 0 or any(a < n for a, n in zip(dimensions[:3], dimensions[3:6])):
        raise FilplotParseError('Invalid physical/allocation dimensions')
    payload_count = nr1x*nr2x*nr3
    if payload_count > MAX_POINTS or nat > 10000 or ntyp > nat:
        raise FilplotParseError('Dimensions exceed restricted size/species limits')
    cell_tokens = line_tokens(7, 'ibrav/celldm')
    ibrav = _integer(cell_tokens[0], 'ibrav')
    if ibrav != 0:
        raise FilplotParseError('Only explicit ibrav=0 lattice columns are supported', 'UNSUPPORTED')
    celldm = [float(decimal_token(t)[0]) for t in cell_tokens[1:]]
    if celldm[0] <= 0:
        raise FilplotParseError('Nonpositive alat/celldm(1)')
    at_tokens = [line_tokens(3, 'at column') for _ in range(3)]
    at = [[float(decimal_token(t)[0]) for t in column] for column in at_tokens]
    lattice = [[celldm[0]*v for v in column] for column in at]
    volume = _det(lattice)
    if not math.isfinite(volume) or volume <= 0:
        raise FilplotParseError('Singular or nonpositive-orientation cell')
    cut_tokens = line_tokens(4, 'cutoffs/plot_num')
    cuts = [float(decimal_token(t)[0]) for t in cut_tokens[:3]]
    if min(cuts) <= 0:
        raise FilplotParseError('Nonpositive native cutoff/dual')
    plot_num = _integer(cut_tokens[3], 'plot_num')
    if plot_num != expected_plot_num:
        raise FilplotParseError('Native plot_num disagrees with requested action')
    species = []
    for i in range(ntyp):
        tokens = line_tokens(3, 'species')
        if _integer(tokens[0], 'species index') != i+1:
            raise FilplotParseError('Species index missing, repeated, or reordered')
        z = float(decimal_token(tokens[2])[0])
        if not re.fullmatch('[A-Z][a-z]?', tokens[1]) or z <= 0:
            raise FilplotParseError('Invalid species label or z_valence')
        species.append({'index': i+1, 'symbol': tokens[1], 'z_valence': z,
                        'z_valence_token': tokens[2]})
    if len({s['symbol'] for s in species}) != ntyp:
        raise FilplotParseError('Duplicate species labels are unsupported', 'UNSUPPORTED')
    atoms = []
    for i in range(nat):
        tokens = line_tokens(5, 'atom')
        species_index = _integer(tokens[4], 'atom species index')
        if _integer(tokens[0], 'atom index') != i+1 or not 1 <= species_index <= ntyp:
            raise FilplotParseError('Invalid/repeated atom index or atom species association')
        tau = [float(decimal_token(t)[0]) for t in tokens[1:4]]
        atoms.append({'index': i+1, 'species_index': species_index, 'tau_alat': tau,
                      'tau_tokens': tokens[1:4], 'position_cartesian_bohr': [celldm[0]*v for v in tau]})
    payload_tokens = []
    payload_lines = lines[cursor:]
    if len(payload_lines) != (payload_count+4)//5:
        raise FilplotParseError('Missing or extra payload line, including possible repeated header')
    for i, line in enumerate(payload_lines):
        want = min(5, payload_count-5*i)
        tokens = line.split()
        if len(tokens) != want:
            # Extreme adjacent signed fields can occupy the entire field width.
            # Fixed-width fallback is allowed only for the exact native layout.
            tokens = [line[j:j+17].strip() for j in range(0, len(line), 17)] if len(line) == 17*want else []
        if len(tokens) != want:
            raise FilplotParseError('Missing or extra payload token')
        for token in tokens:
            decimal_token(token)
        payload_tokens.extend(tokens)
    indices = [i+nr1x*(j+nr2x*k) for k in range(nr3) for j in range(nr2) for i in range(nr1)]
    physical_tokens = [payload_tokens[i] for i in indices]
    scale = Decimal('0.5') if plot_num == 2 else Decimal(1)
    pairs = [decimal_token(token) for token in physical_tokens]
    values = [float(value*scale) for value, _ in pairs]
    halfwidths = [float(width*scale) for _, width in pairs]
    unit = 'Ha' if plot_num == 2 else 'electron/bohr^3'
    result = {
        'schema_version': 1, 'parse_status': 'PASS', 'plot_num': plot_num,
        'grid': [nr1, nr2, nr3], 'allocated_grid': [nr1x, nr2x, nr3x],
        'payload_count': payload_count, 'physical_count': len(values),
        'padding_count_excluded': payload_count-len(values),
        'ordering': 'first_index_fastest; zero_origin; physical_periodic_nodes_without_endpoint',
        'unit': unit, 'native_unit': 'Ry' if plot_num == 2 else unit, 'unit_scale': float(scale),
        'values': values, 'halfwidths': halfwidths, 'raw_tokens': physical_tokens,
        'payload_tokens': payload_tokens, 'physical_payload_indices': indices,
        'source_sha256': hashlib.sha256(data).hexdigest(),
        'stored_sha256': hashlib.sha256(stored).hexdigest(),
        'print_interval_scope': 'nearest_decimal_rounding_only; excludes reconstruction and numerical errors',
        'format_source': FORMAT_SOURCE,
        'header': {'title': lines[0], 'raw_lines': raw_header, 'ibrav': ibrav,
                   'celldm': celldm, 'celldm_tokens': cell_tokens[1:], 'alat_bohr': celldm[0],
                   'at_columns_alat': at, 'at_columns_tokens': at_tokens,
                   'lattice_columns_bohr': lattice, 'printed_geometry_volume_bohr3': volume,
                   'cutoff_tokens': cut_tokens[:3], 'gcutm': cuts[0], 'dual': cuts[1],
                   'ecut_ry': cuts[2], 'species': species, 'atoms': atoms},
        'expected_validation_status': 'NOT_REQUESTED',
    }
    if expected is not None:
        result['expected_validation_status'] = validate_expected(result, expected)
    return result
