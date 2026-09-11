#!/usr/bin/env python3
"""QE 7.5 QEXSD adapter for the prescribed Mg charge-only SOC SCF.

No calculation or QE algorithm is implemented here. Generic XML/number helpers
are reused without changing the frozen scalar parser or its acceptance rules.
A verified input-file receipt is mandatory: XML cannot establish a UPF SHA-256.
"""
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from parse_qe_baseline import require, text, finite, vector, boolean, positive_int, dot

QE_HARTREE_EV = 4.3597447222071e-18 / 1.602176634e-19
HARTREE_EV = 27.211386245981  # CODATA 2022 presentation, not a fitted conversion.
FORMAT_SOURCES = {
    'xml_units': 'https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd.f90#L128-L136',
    'xml_energy_fermi_smearing': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_restart_new.f90#L637-L727',
    'xml_eigenvalues_occupations': 'https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd_init.f90#L1216-L1250',
    'zero_starting_magnetization_omission': 'https://github.com/QEF/q-e/blob/qe-7.5/Modules/qexsd_init.f90#L132-L154',
    'pbesol_indices': 'https://github.com/QEF/q-e/blob/qe-7.5/XClib/qe_dft_list.f90#L116-L118',
    'bands_fixed_mu_occupations': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/non_scf.f90#L89-L102',
    'fd_xml_label': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/set_occupations.f90#L135-L157',
    'noncollinear_weights': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/setup.f90#L647-L675',
    'xml_input_control_units': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_init_qexsd_input.f90#L440-L486',
    'native_spectrum_printer': 'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/print_ks_energies.f90#L122-L210',
    'native_eV_constant': 'https://github.com/QEF/q-e/blob/qe-7.5/Modules/constants.f90#L34-L55',
    'input_semantics': 'https://gitlab.com/QEF/q-e/-/raw/qe-7.5/PW/Doc/INPUT_PW.def',
    'fermi_dirac_free_energy': 'https://lists.quantum-espresso.org/pipermail/users/2005-October/003180.html',
    'energy_presentation': 'https://physics.nist.gov/cuu/pdf/wall_2022.pdf',
}


class QeSocParseError(ValueError):
    def __init__(self, reason, status='FAIL'):
        super().__init__(reason)
        self.status = status


def energy_to_ha(value, unit):
    number = finite(str(value))
    if unit not in ('Ha', 'Ry', 'eV'):
        raise QeSocParseError('Unsupported energy unit: ' + str(unit), 'BLOCKED')
    return number / {'Ha': 1, 'Ry': 2, 'eV': HARTREE_EV}[unit]


def same_point(a, b, tolerance):
    return len(a) == len(b) == 3 and all(abs(x-y-round(x-y)) <= tolerance for x, y in zip(a, b))


def match_points(requested, actual, tolerance):
    for points in (requested, actual):
        if any(same_point(p, q, tolerance) for i, p in enumerate(points) for q in points[:i]):
            raise QeSocParseError('Duplicate or ambiguous reciprocal k points')
    if len(requested) != len(actual):
        raise QeSocParseError('Missing or extra requested reciprocal k points')
    indices = []
    for point in requested:
        matches = [i for i, candidate in enumerate(actual) if same_point(point, candidate, tolerance)]
        if len(matches) != 1 or matches[0] in indices:
            raise QeSocParseError('Missing or ambiguous requested reciprocal k point')
        indices.append(matches[0])
    return indices


def rounded_value(token, unit):
    value = finite(token)
    token = token.replace('D', 'E').replace('d', 'e')
    half_digit = float(Decimal(10) ** Decimal(token).as_tuple().exponent) / 2
    return {'token': token, 'value': value, 'unit': unit, 'half_last_digit': half_digit,
            'displayed_zero_is_exact_zero_claim': False}


def text_consistency(native_ha, token, unit, slack_ha):
    raw = rounded_value(token, unit)
    factor = {'Ha': 1, 'Ry': 2, 'eV': QE_HARTREE_EV}[unit]
    delta = native_ha - raw['value'] / factor
    bound = raw['half_last_digit'] / factor + slack_ha
    if abs(delta) > bound:
        raise QeSocParseError('XML and stdout ' + unit + ' field disagree beyond native printed precision')
    return dict(raw, xml_minus_stdout_ha=delta, consistency_bound_ha=bound)


_NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?|[+-]?(?:NaN|Inf(?:inity)?)'


def _numeric_lines(value):
    tokens=[]
    for line in value.splitlines():
        if not line.strip():
            if tokens:break
            continue
        found=re.findall(_NUMBER,line,re.I)
        if not found or re.sub(_NUMBER,'',line,flags=re.I).strip():break
        tokens.extend(found)
    return tokens


def stdout_spectrum_check(final_stdout,points,lattice,alat,calculation,gates):
    """Corroborate all native XML levels using coordinate-matched printed eV."""
    headers=list(re.finditer(r'k\s*=\s*([^\n]+?)\(\s*(\d+)\s+PWs\)\s+bands\s+\(ev\):',final_stdout,re.I))
    if len(headers)!=len(points):
        raise QeSocParseError('Missing final stdout 24-state k-point spectrum','BLOCKED')
    used=[];errors=[];bounds=[];occupation_fields=0
    for i,header in enumerate(headers):
        coordinate_tokens=re.findall(_NUMBER,header.group(1),re.I)
        if len(coordinate_tokens)!=3:
            raise QeSocParseError('Malformed native stdout k coordinate','BLOCKED')
        raw=[finite(x) for x in coordinate_tokens]
        half=[rounded_value(x,'tpiba')['half_last_digit'] for x in coordinate_tokens]
        frac=[dot(a,raw)/alat for a in lattice]
        coordinate_bound=max(sum(abs(a[j])*half[j] for j in range(3))/alat for a in lattice)+gates['coordinate_abs']
        matches=[j for j,p in enumerate(points) if same_point(frac,p['coordinate_fractional'],coordinate_bound)]
        if len(matches)!=1 or matches[0] in used:
            raise QeSocParseError('Missing/duplicate/ambiguous stdout k coordinates')
        index=matches[0];used.append(index);point=points[index]
        if int(header.group(2))!=point['npw']:
            raise QeSocParseError('XML/stdout spatial plane-wave count mismatch')
        end=headers[i+1].start() if i+1<len(headers) else len(final_stdout)
        body=final_stdout[header.end():end]
        values=_numeric_lines(body)
        if len(values)!=len(point['eigenvalues_ha']):
            raise QeSocParseError('Missing native stdout eigenvalues or band count mismatch')
        for value,native in zip(values,point['eigenvalues_ha']):
            check=text_consistency(native,value,'eV',gates['stdout_conversion_abs_ha'])
            errors.append(abs(check['xml_minus_stdout_ha'])*QE_HARTREE_EV)
            bounds.append(check['consistency_bound_ha']*QE_HARTREE_EV)
        occupation_parts=re.split(r'occupation numbers',body,flags=re.I)
        if calculation=='scf' and len(occupation_parts)!=2:
            raise QeSocParseError('Missing native final SCF occupation numbers','BLOCKED')
        if len(occupation_parts)==2:
            tokens=_numeric_lines(occupation_parts[1]);occupation_fields+=len(tokens)
            if point['occupations'] is None or len(tokens)!=len(point['occupations']):
                raise QeSocParseError('Native occupation array sizes disagree')
            for token,native in zip(tokens,point['occupations']):
                raw=rounded_value(token,'dimensionless')
                if abs(native-raw['value'])>raw['half_last_digit']+gates['magnetization_abs']:
                    raise QeSocParseError('Native XML/stdout occupations disagree')
    return {'status':'PASS','matched_eigenvalues':len(errors),'stdout_to_xml_kpoint_indices':used,
            'max_abs_xml_minus_stdout_ev':max(errors),'maximum_printed_rounding_bound_ev':max(bounds),
            'occupation_fields_checked':occupation_fields,'native_ev_per_ha':QE_HARTREE_EV,
            'scope':'Native stdout rounding crosscheck, not an eigenvector residual estimate'}


def _case_contract(case):
    e, pseudo = case['electrons'], case['pseudo']
    if (e['n_electrons'] != 10 or e['n_bands'] != 24 or e['occupation_capacity'] != 1
            or e['temperature_ha'] != .001 or pseudo['element'] != 'Mg'
            or pseudo['z_valence'] != 10 or pseudo['nlcc'] is not False
            or len(case['kpoints']) != 3):
        raise QeSocParseError('Requested input is outside the prescribed Mg/10-electron/capacity-one SOC case')
    if case.get('verified_pseudo_sha256') != pseudo['sha256']:
        raise QeSocParseError('Missing or wrong verified pseudopotential SHA-256 receipt')
    if pseudo['sha256'] != '19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256':
        raise QeSocParseError('Wrong Mg pseudopotential SHA-256')
    p = case['parsing']
    return {'coordinate_abs':p['coordinate_tolerance'], 'weight_abs':p['weight_tolerance'],
            'electron_abs':p['electron_tolerance'], 'geometry_abs':p['geometry_tolerance'],
            'magnetization_abs':p['occupation_tolerance'],
            'parameter_abs':p['energy_arithmetic_tolerance_ha'],
            'eigenvalue_order_abs_ha':p['energy_arithmetic_tolerance_ha'],
            'native_energy_abs_ha':p['energy_arithmetic_tolerance_ha'],
            'stdout_conversion_abs_ha':p['energy_arithmetic_tolerance_ha']}


def parse_qe_soc(xml_path, stdout_path, case, process_exit_code=0, calculation='scf'):
    """Return a finite normalized SCF record or an explicit FAIL/BLOCKED error.

    `case.verified_pseudo_sha256` is an execution receipt supplied after checking
    actual copied/loaded UPF bytes. It is never derived from the filename or XML.
    The separately requested bands mode exposes spectra only. Its occupations
    are recomputed at the inherited SCF chemical potential; its E/F is ignored.
    """
    try:
        return _parse(xml_path, stdout_path, case, process_exit_code, calculation)
    except QeSocParseError:
        raise
    except (ET.ParseError, OSError) as error:
        raise QeSocParseError('Missing or truncated QE native output: ' + type(error).__name__, 'BLOCKED') from error
    except (KeyError, TypeError, IndexError, ArithmeticError) as error:
        raise QeSocParseError('Malformed required SOC parser field: ' + str(error), 'BLOCKED') from error
    except ValueError as error:
        status = 'BLOCKED' if str(error).startswith('QE XML missing') else 'FAIL'
        raise QeSocParseError(str(error), status) from error


def _parse(xml_path, stdout_path, case, process_exit_code, calculation):
    gates = _case_contract(case)
    if calculation not in ('scf','bands'):
        raise QeSocParseError('Only SCF or explicit spectra-only bands schema is supported', 'BLOCKED')
    if type(process_exit_code) is not int or process_exit_code != 0:
        raise QeSocParseError('QE process did not exit normally with code zero')
    stdout = Path(stdout_path).read_text()
    if 'JOB DONE.' not in stdout:
        raise QeSocParseError('Incomplete stdout: missing JOB DONE', 'BLOCKED')
    versions = re.findall(r'Program\s+PWSCF\s+v\.([^\s]+)', stdout)
    if versions != ['7.5']:
        raise QeSocParseError('Unsupported or ambiguous actual QE version', 'BLOCKED')
    convergences = re.findall(r'convergence\s+(has been achieved|NOT achieved)', stdout, re.I)
    if calculation == 'scf' and (not convergences or convergences[-1].lower() != 'has been achieved'):
        raise QeSocParseError('Final stdout SCF convergence not established')
    boundary = 'End of self-consistent calculation' if calculation=='scf' else 'End of band structure calculation'
    if boundary not in stdout:
        raise QeSocParseError('Missing final '+calculation+' spectrum boundary', 'BLOCKED')
    final_stdout = stdout.rsplit(boundary, 1)[1]
    root = ET.parse(xml_path).getroot()
    if root.tag != '{http://www.quantum-espresso.org/ns/qes/qes-1.0}espresso' or root.get('Units') != 'Hartree atomic units':
        raise QeSocParseError('Unsupported XML namespace or units', 'BLOCKED')
    for element in root.iter():
        element.tag = element.tag.split('}')[-1]
    fmt = require(root, 'general_info/xml_format')
    creator = require(root, 'general_info/creator')
    if ((fmt.get('NAME'), fmt.get('VERSION')) != ('QEXSD', '25.05.21')
            or (creator.get('NAME'), creator.get('VERSION')) != ('PWSCF', '7.5')):
        raise QeSocParseError('Unsupported XML format or creator version', 'BLOCKED')
    if text(root, 'exit_status') != '0':
        raise QeSocParseError('XML reports failed exit_status')
    require(root, 'closed')
    outputs = root.findall('output')
    if not outputs:
        raise QeSocParseError('Missing final XML output', 'BLOCKED')
    output = outputs[-1]  # Never select a convenient successful intermediate step.
    inp = require(root, 'input')
    if text(inp, 'control_variables/calculation') != calculation:
        raise QeSocParseError('SCF and bands/NSCF calculation mismatch')
    if text(inp, 'control_variables/restart_mode') != 'from_scratch':
        raise QeSocParseError('SCF did not request a fresh run')
    bands = require(output, 'band_structure')
    flags = {'lsda': False, 'noncolin': True, 'spinorbit': True}
    for parent, prefix in ((inp, 'spin/'), (bands, ''), (output, 'magnetization/')):
        if {key: boolean(parent, prefix + key) for key in flags} != flags:
            raise QeSocParseError('SOC/noncolin must actually be enabled, without LSDA')
    if boolean(output, 'magnetization/do_magnetization'):
        raise QeSocParseError('Charge-only calculation requires actual do_magnetization=false')
    if abs(finite(text(output, 'magnetization/absolute'))) > gates['magnetization_abs']:
        raise QeSocParseError('Actual magnetization conflicts with charge-only target')
    for name in ('nosym', 'noinv', 'no_t_rev'):
        if not boolean(inp, 'symmetry_flags/' + name):
            raise QeSocParseError('Requested explicit k-point reduction controls are not active')
    if not boolean(inp, 'electron_control/diago_full_acc'):
        raise QeSocParseError('Empty-state full diagonalization accuracy is not enabled')
    # QE7.5 serializes diago_thr_init unchanged (Ry), while conv_thr is /2 (Ha).
    controls = {'diago_thr_init':case['qe']['diago_thr_init_ry'],
                'conv_thr':case['qe']['conv_thr_ry']/2,
                'mixing_beta':case['qe']['mixing_beta']}
    for field, expected in controls.items():
        if not math.isclose(finite(text(inp,'electron_control/'+field)), expected, rel_tol=1e-12, abs_tol=0):
            raise QeSocParseError('Wrong actual electron_control '+field+' or unit')
    if positive_int(text(inp,'electron_control/max_nstep')) != case['qe']['electron_maxstep']:
        raise QeSocParseError('Wrong actual electron_maxstep')
    if text(inp, 'bands/occupations') != 'smearing' or text(bands, 'occupations_kind') != 'smearing':
        raise QeSocParseError('Fermi-Dirac smearing is not active')
    for parent in (require(inp, 'bands'), bands):
        smear = require(parent, 'smearing')
        if (smear.text or '').strip() != 'fd':
            raise QeSocParseError('Actual smearing is not Fermi-Dirac')
        if abs(finite(smear.attrib['degauss']) - case['electrons']['temperature_ha']) > gates['parameter_abs']:
            raise QeSocParseError('Wrong XML temperature/tau (Hartree)')
    if finite(text(inp, 'bands/tot_charge')) != 0:
        raise QeSocParseError('Unexpected charge changes electron count')
    ne = finite(text(bands, 'nelec'))
    nb = positive_int(text(bands, 'nbnd'))
    nk = positive_int(text(bands, 'nks'))
    if abs(ne-case['electrons']['n_electrons']) > gates['electron_abs'] or nb != 24 or nk != 3:
        raise QeSocParseError('Wrong electron, band or k-point count')
    structure = require(output, 'atomic_structure')
    alat = finite(structure.attrib['alat'])
    if alat <= 0 or positive_int(structure.attrib['nat']) != 1:
        raise QeSocParseError('Wrong lattice scale or atom count')
    lattice = [vector(require(structure, 'cell/a'+str(i)), 3) for i in (1, 2, 3)]
    reciprocal = [vector(require(output, 'basis_set/reciprocal_lattice/b'+str(i)), 3) for i in (1, 2, 3)]
    expected_lattice = case['geometry']['lattice_vectors_bohr']
    for i, a in enumerate(lattice):
        if any(abs(v-w) > gates['geometry_abs'] for v, w in zip(a, expected_lattice[i])):
            raise QeSocParseError('Actual cell differs from requested cell')
        for j, b in enumerate(reciprocal):
            if abs(dot(a,b)/alat-(i == j)) > gates['coordinate_abs']:
                raise QeSocParseError('Actual direct/reciprocal lattice duality failed')
    atoms = require(structure, 'atomic_positions').findall('atom')
    if len(atoms) != 1 or atoms[0].get('name') != 'Mg':
        raise QeSocParseError('Wrong actual element/position count')
    cartesian = vector(atoms[0], 3)
    position = [dot(cartesian,b)/alat for b in reciprocal]
    if not same_point(position,case['geometry']['positions_fractional'][0],gates['coordinate_abs']):
        raise QeSocParseError('Actual atomic position differs from request')
    for parent, path in ((inp,'basis'),(output,'basis_set')):
        for field,expected in (('ecutwfc',case['cutoffs']['qe_ecutwfc_ry']/2),('ecutrho',case['cutoffs']['qe_ecutrho_ry']/2)):
            if abs(finite(text(parent,path+'/'+field))-expected) > gates['parameter_abs']:
                raise QeSocParseError('Actual XML cutoff (Hartree) differs from request')
    points = []
    for block in bands.findall('ks_energies'):
        point = require(block,'k_point')
        raw = vector(point,3)
        weight = finite(point.attrib['weight'])
        values = vector(require(block,'eigenvalues'),nb)
        occ_node=block.find('occupations')
        occ = (None if calculation=='bands' and occ_node is None else vector(require(block,'occupations'),nb))
        if occ is not None and any(f < 0 or f > 1 for f in occ):
            raise QeSocParseError('Raw spinor occupation exceeds capacity one')
        if any(a > b + gates['eigenvalue_order_abs_ha'] for a,b in zip(values,values[1:])):
            raise QeSocParseError('Native bands are not energy ordered')
        points.append({'coordinate_fractional':[dot(a,raw)/alat for a in lattice],
                       'coordinate_raw':raw,'weight_raw':weight,'weight_spatial':weight,
                       'eigenvalues_ha':values,'occupations_raw':occ,'occupations':None if occ is None else list(occ),
                       'npw':positive_int(text(block,'npw'))})
    order = match_points([p['coordinate_fractional'] for p in case['kpoints']],
                         [p['coordinate_fractional'] for p in points],gates['coordinate_abs'])
    for expected,index in zip(case['kpoints'],order):
        if abs(points[index]['weight_raw']-expected['weight_spatial']) > gates['weight_abs']:
            raise QeSocParseError('Raw SOC k-point weight differs from spatial requested weight; no factor two allowed')
    if abs(sum(p['weight_raw'] for p in points)-1) > gates['weight_abs']:
        raise QeSocParseError('Raw SOC weights must sum to one')
    have_occupations=all(p['occupations'] is not None for p in points)
    if not have_occupations and any(p['occupations'] is not None for p in points):
        raise QeSocParseError('Partial occupation blocks are ambiguous','BLOCKED')
    electron_sum = sum(p['weight_spatial']*sum(p['occupations']) for p in points) if have_occupations else None
    if calculation=='scf' and abs(electron_sum-ne) > gates['electron_abs']:
        raise QeSocParseError('Capacity-one weighted occupations miscount electrons')
    species = require(output,'atomic_species').findall('species')
    if len(species)!=1 or species[0].get('name')!='Mg' or text(species[0],'pseudo_file') != case['pseudo']['filename']:
        raise QeSocParseError('Wrong XML pseudopotential species or filename')
    input_species = require(inp,'atomic_species').findall('species')
    if len(input_species)!=1:
        raise QeSocParseError('Ambiguous input species for charge-only SOC')
    initial_magnetization=input_species[0].find('starting_magnetization')
    # QE7.5 omits this optional species field when all starting values are zero.
    # Absence is accepted only alongside independently checked actual domag=false.
    if initial_magnetization is not None and finite(initial_magnetization.text or '') != 0:
        raise QeSocParseError('Zero starting magnetization is required for charge-only SOC')
    starting_magnetization_evidence = ('explicit XML zero' if initial_magnetization is not None else
                                      'QE7.5 all-zero field omission plus actual do_magnetization=false')
    reads = re.findall(r'PseudoPot\.\s*#\s*\d+\s+for\s+(\w+)\s+read from file:\s*(\S+)',stdout)
    summaries = re.findall(r'Pseudo is\s+([^\n,]+),\s*Zval\s*=\s*(\S+)',stdout)
    if len(reads)!=1 or reads[0][0]!='Mg' or Path(reads[0][1]).name!=case['pseudo']['filename'] or len(summaries)!=1:
        raise QeSocParseError('Ambiguous or wrong native pseudopotential read')
    description,zval=summaries[0]
    if ' '.join(description.split()) != 'Norm-conserving' or abs(finite(zval)-10)>gates['electron_abs']:
        raise QeSocParseError('Native pseudopotential must be NC, no NLCC, valence10')
    declarations=re.findall(r'Exchange-correlation\s*=\s*([^\n]+)\s*\(([\d\s]+)\)',stdout)
    if len(declarations)!=1:
        raise QeSocParseError('Missing or ambiguous actual XC declaration','BLOCKED')
    xc_name,indices=declarations[0];indices=[int(x) for x in indices.split()]
    if indices[:4] != case['xc']['qe_indices'] or any(indices[4:]) or text(output,'dft/functional').upper()!='PBESOL':
        raise QeSocParseError('Actual XC differs from PBEsol exchange and correlation')
    if calculation=='scf':
        scf=require(output,'convergence_info/scf_conv')
        if not boolean(scf,'convergence_achieved'):
            raise QeSocParseError('Final XML SCF not converged')
        steps=positive_int(text(scf,'n_scf_steps'));error=finite(text(scf,'scf_error'))
        if error<0:
            raise QeSocParseError('Negative SCF error estimate')
        energy_xml=require(output,'total_energy')
        native={child.tag:finite(child.text or '') for child in energy_xml}
        free=finite(text(energy_xml,'etot'));demet=finite(text(energy_xml,'demet'))
        if demet>gates['native_energy_abs_ha']:
            raise QeSocParseError('Positive demet contradicts FD entropy-energy sign')
        etokens=re.findall(r'!\s+total energy\s*=\s*(\S+)\s+Ry',final_stdout)
        stokens=re.findall(r'smearing contrib\.\s*\(-TS\)\s*=\s*(\S+)\s+Ry',final_stdout)
        if not etokens or not stokens:
            raise QeSocParseError('Missing final native total/free energy or -TS contribution','BLOCKED')
        native_stdout={'free_energy':text_consistency(free,etokens[-1],'Ry',gates['native_energy_abs_ha']),
                       'entropy_energy':text_consistency(demet,stokens[-1],'Ry',gates['native_energy_abs_ha'])}
        mu=finite(text(bands,'fermi_energy'))
        ftokens=re.findall(r'the Fermi energy is\s*(\S+)\s*ev',final_stdout,re.I)
        if not ftokens:
            raise QeSocParseError('Missing final Fermi energy in native stdout','BLOCKED')
        native_stdout['fermi_energy']=text_consistency(mu,ftokens[-1],'eV',gates['stdout_conversion_abs_ha'])
        internal_tokens=re.findall(r'internal energy E=F\+TS\s*=\s*(\S+)\s+Ry',final_stdout)
        if not internal_tokens:
            raise QeSocParseError('Missing native internal energy E=F+TS','BLOCKED')
        native_stdout['internal_energy']=text_consistency(free-demet,internal_tokens[-1],'Ry',gates['native_energy_abs_ha'])
        components=('eband','ehart','vtxc','etxc','ewald')
        native_sum_error=None
        if all(name in native for name in components):
            native_sum_error=free-(native['eband']-native['ehart']-native['vtxc']+native['etxc']+native['ewald']+demet)
            # These native fields need not share one density/SCF correction.
            # Preserve this partial combination as a diagnostic, never a gate
            # or a replacement for the explicitly printed SCF E/F.
    else:
        # The bands XML may contain stale SCF energy/convergence fields. They are
        # deliberately not read as a new energy or an SCF convergence result.
        native_stdout={}
        fermi_node=bands.find('fermi_energy')
        mu=None if fermi_node is None else finite(fermi_node.text or '')
    spectrum_check=stdout_spectrum_check(final_stdout,points,lattice,alat,calculation,gates)
    ethrs=[finite(token) for token in re.findall(r'ethr\s*=\s*([^\s,]+)',stdout)]
    if not ethrs or any(x<=0 for x in ethrs):
        raise QeSocParseError('Missing positive native diagonalization threshold evidence','BLOCKED')
    warnings=[{'line':i+1,'text':line.strip()} for i,line in enumerate(stdout.splitlines())
              if re.search(r'warning|not converged|too large|negative (?:rho|charge)|convergence NOT',line,re.I)]
    entropy=(-sum(p['weight_spatial']*sum(f*math.log(f)+(1-f)*math.log1p(-f)
                    for f in p['occupations'] if 0<f<1) for p in points) if have_occupations else None)
    tau=case['electrons']['temperature_ha']
    result={'schema_version':1,'code':'QE','calculation':calculation,'execution_status':'PASS',
            'input_comparability_status':'PASS','energy_semantics_status':'PASS' if calculation=='scf' else 'NOT_APPLICABLE_SPECTRUM_ONLY',
            'version':'7.5','exit_code':process_exit_code,'electrons':ne,'n_bands':nb,
            'occupation_capacity':1,'tau_ha':tau,'smearing':'Fermi-Dirac',
            'energy':None if calculation=='bands' else {'internal_ha':free-demet,'free_ha':free,'entropy_ha':demet,
                      'native_etot_ha':free,'native_demet_ha':demet,'native_components_ha':native,
                      'native_band_energy_partial_reconstruction_difference_ha':native_sum_error,
                      'native_component_reconstruction_status':'NOT_COMPLETE_ENERGY_DECOMPOSITION',
                      'native_component_note':'F minus (eband-ehart-vtxc+etxc+ewald+demet); no complete same-density/correction identity is assumed',
                      'sources':{'free_ha':'final XML output/total_energy/etot',
                                 'entropy_ha':'final XML output/total_energy/demet',
                                 'internal_ha':'E = F - demet, no zero-temperature extrapolation or correction'}},
            'fermi_energy_ha':mu,'fermi_energy_definition':'Native FD chemical potential; no cross-code equality gate',
            'occupations_source':'RECOMPUTED_BY_SCF' if calculation=='scf' else 'RECOMPUTED_AT_INHERITED_SCF_CHEMICAL_POTENTIAL',
            'chemical_potential_source':'SCF_GLOBAL_FERMI_LEVEL' if calculation=='scf' else 'INHERITED_FROM_SCF_NOT_RESOLVED',
            'occupation_availability':'AVAILABLE' if have_occupations else 'NOT_AVAILABLE',
            'native_stdout':native_stdout,'kpoints':points,'requested_to_xml_kpoint_indices':order,
            'electron_sum_raw':electron_sum,'electron_sum_normalized':electron_sum,
            'lattice_vectors_bohr':lattice,'alat_bohr':alat,'reciprocal_vectors_raw':reciprocal,
            'positions_cartesian_bohr':[cartesian],'positions_fractional':[position],
            'atom_symbols':['Mg'],'n_atoms':1,'ecut_ha':case['cutoffs']['qe_ecutwfc_ry']/2,
            'ecutrho_ha':case['cutoffs']['qe_ecutrho_ry']/2,
            'fft_grid':[positive_int(require(output,'basis_set/fft_grid').attrib['nr'+str(i)]) for i in (1,2,3)],
            'fft_smooth_grid':[positive_int(require(output,'basis_set/fft_smooth').attrib['nr'+str(i)]) for i in (1,2,3)],
            'pseudo_sha256':case['verified_pseudo_sha256'],'pseudo_sha256_evidence':'Caller receipt from actual UPF bytes, not XML-derived',
            'pseudo_files':[case['pseudo']['filename']],'pseudo_type':'NC','nlcc':False,'z_valence':10.,
            'xc':{'functional':text(output,'dft/functional'),'stdout':xc_name.strip(),'indices':indices},
            'scf':None if calculation=='bands' else {'converged':True,'iterations':steps,'error_ha':error,
                   'convergence_evidence':'Last XML output/scf_conv and final native stdout convergence'},
            'input_model':dict(flags, do_magnetization=False, starting_magnetization=0.,
                               starting_magnetization_evidence=starting_magnetization_evidence,
                               nosym=True,noinv=True,no_t_rev=True,diago_full_acc=True,
                               diago_thr_init_ry=controls['diago_thr_init'],conv_thr_ha=controls['conv_thr'],
                               mixing_beta=controls['mixing_beta'],electron_maxstep=case['qe']['electron_maxstep']),
            'precision':{'stdout_spectrum_check':spectrum_check,'diago_full_acc':True,'ethr_history_ry':ethrs,'last_ethr_ry':ethrs[-1],
                         'individual_eigenvector_residual_status':'NOT_AVAILABLE',
                         'individual_eigenvector_residuals_ha':None,
                         'note':'ethr is an eigenvalue convergence threshold, not ||Hpsi-epsilon psi||'},
            'warnings':warnings,'warnings_scope':'Native stdout only; stderr must be retained by the runner','eigenvalue_precision_status':'WARNING_REVIEW_REQUIRED' if warnings else 'REPORTED_THRESHOLD_AVAILABLE',
            'entropy_diagnostic':{'from_published_occupations_dimensionless':entropy,
                                  'minus_tau_S_ha':None if entropy is None else -tau*entropy,
                                  'native_minus_diagnostic_ha':None if calculation=='bands' else demet+tau*entropy,
                                  'scope':'Independent diagnostic from rounded native occupations, not a replacement for native demet'},
            'units_provenance':{'xml_energy_eigenvalue_fermi_smearing':'Ha',
                                'xml_diago_thr_init':'Ry (explicit writer exception)',
                                'xml_conv_thr':'Ha', 'QE_stdout_ev_per_ha':QE_HARTREE_EV,
                                'stdout_total_smearing_energy':'Ry','stdout_band_fermi_energy':'eV',
                                'xml_cell_position':'bohr','xml_k_reciprocal':'Cartesian 2*pi/alat',
                                'coordinates':'fractional_j = a_j dot k_raw / alat; duality checked',
                                'weights':'noncolin weights sum1; no scalar spin-degeneracy factor',
                                'occupations':'QEXSD wg/wk, already capacityone; normalized f=raw f',
                                'format':dict(fmt.attrib),'sources':FORMAT_SOURCES},
            'native_files_sha256':{'xml':hashlib.sha256(Path(xml_path).read_bytes()).hexdigest(),
                                   'stdout':hashlib.sha256(Path(stdout_path).read_bytes()).hexdigest()}}
    json.dumps(result,allow_nan=False)
    return result
