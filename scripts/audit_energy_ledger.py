#!/usr/bin/env python3
"""Public historical energy tokens and signed ledger; no electronic-structure calls."""
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
QE = 'results/mg-soc-qe-diagnostics/G40/'
PLAN = 'benchmarks/mg-soc-energy-reference-v1/plan.json'
QE_TAG = 'https://github.com/QEF/q-e/blob/qe-7.5/'
DEFINITIONS = {
    'qe_energy': QE_TAG + 'PW/src/electrons.f90#L1130-L1203',
    'qe_print': QE_TAG + 'PW/src/electrons.f90#L1689-L1728',
    'qe_state': QE_TAG + 'PW/src/electrons.f90#L843-L1005',
    'qe_units': QE_TAG + 'PW/src/pw_restart_new.f90#L719-L727',
    'qe_etxcc': QE_TAG + 'PW/src/pwcom.f90#L353-L354',
    'qe_vtxc': QE_TAG + 'PW/src/v_of_rho.f90#L507-L600',
    'dftk_energy': 'prototypes/fr_integration/energy.jl',
    'dftk_entropy': 'prototypes/soc_scf/ensemble.jl',
}
ARITHMETIC_ATOL = 1e-10
PRINT_SLACK_HA = 1e-12
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?'
TERMS = ('Kinetic', 'AtomicLocal', 'AtomicNonlocalFR', 'Hartree', 'Xc', 'Ewald', 'PspCorrection')
PUBLIC_SOURCES = (QE+'qe.xml', QE+'qe.stdout', 'results/mg-soc-qe-diagnostics/canonical.json',
    'results/mg-soc-scf/A/endpoint.json', 'results/mg-soc-scf/B/endpoint.json',
    'benchmarks/mg-soc-qe-diagnostics-v1/G40.in', 'results/mg-soc-density-hartree/comparison.json')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_source_bindings(root, plan):
    require(plan['source_sha256'] and plan['source_sha256'].keys()==plan['source_bytes'].keys(),
            'Incomplete source identity map')
    for path, expected in plan['source_sha256'].items():
        require(sha256(root/path)==expected and (root/path).stat().st_size==plan['source_bytes'][path],
                'Frozen energy source differs from plan: '+path)


def decimal_token(token):
    require(isinstance(token, str) and re.fullmatch(NUMBER, token.strip()), 'Invalid numeric token')
    value = Decimal(token.strip().replace('D', 'E').replace('d', 'e'))
    require(value.is_finite() and math.isfinite(float(value)), 'Nonfinite numeric token')
    return value


def token_measurement(token, unit, *, printed=True):
    """Nearest decimal printing interval, including scientific-notation exponent.

    A JSON round-trip number is an exact recorded Float64 token, not a claim
    about the underlying physical rounding error; its interval is zero-width.
    """
    require(unit in ('Ha', 'Ry'), 'Unsupported energy unit')
    with localcontext() as context:
        context.prec = 80
        value = decimal_token(token)
        factor = Decimal('0.5') if unit == 'Ry' else Decimal(1)
        radius = Decimal(5).scaleb(value.as_tuple().exponent - 1) if printed else Decimal(0)
        center, radius = value * factor, radius * factor
        return {'raw_token': token, 'original_unit': unit, 'value_ha': float(center),
                'quantization_half_width_ha': float(radius),
                'quantization_interval_ha': [float(center-radius), float(center+radius)],
                'displayed_zero_is_exact_zero_claim': False,
                'precision_basis': 'HALF_LAST_PRINTED_DECIMAL_PLACE' if printed else 'EXACT_RECORDED_JSON_TOKEN'}


def interval_combination(rows, coefficients):
    require(len(rows) == len(coefficients) and rows, 'Invalid interval combination')
    center = math.fsum(c*r['value_ha'] for c, r in zip(coefficients, rows))
    half = math.fsum(abs(c)*r['quantization_half_width_ha'] for c, r in zip(coefficients, rows))
    return {'value_ha': center, 'quantization_half_width_ha': half,
            'quantization_interval_ha': [center-half, center+half]}


def interval_check(left, right):
    difference = left['value_ha'] - right['value_ha']
    bound = left['quantization_half_width_ha'] + right['quantization_half_width_ha'] + PRINT_SLACK_HA
    return {'status': 'PASS' if abs(difference) <= bound else 'FAIL',
            'difference_ha': difference, 'bound_ha': bound,
            'bound_rule': 'Sum of the participating tokens half-place intervals plus 1e-12 Ha'}


def derived_row(identifier, program, formula, rows, coefficients, state):
    result = interval_combination(rows, coefficients)
    result.update(id=identifier, program=program, native_field=None, raw_token=None,
                  original_unit='Ha (derived)', record_kind='DERIVED_COMBINATION',
                  operator_measurement_status='NOT_A_DIRECT_OPERATOR_MEASUREMENT',
                  formula=formula, operands=[r['id'] for r in rows], state=state,
                  source=[r['source'] for r in rows], definition='Algebra on the cited source fields')
    return result


def assert_same_density_state(band, potential):
    require(band['state'] == potential['state'],
            'Different input/output Hamiltonian states cannot form an exact double-counting identity')


def require_operator_measurement(row):
    require(row['record_kind'] == 'DIRECT_OPERATOR_EXPECTATION',
            'Derived ledger combination is not a directly measured operator expectation')


def endpoint_block(stdout):
    """Select the final ! total-energy block of a successful SCF termination.

    Never fall back to an earlier block when the last run or block is damaged.
    """
    lines = stdout.splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r'^\s*!\s*total energy\s*=', line)]
    require(starts, 'Missing converged endpoint total-energy block')
    start = starts[-1]
    end_scf = [i for i, line in enumerate(lines) if 'End of self-consistent calculation' in line]
    require(end_scf and end_scf[-1] < start, 'Final energy is not after the last completed SCF section')
    converged = [i for i in range(start+1, len(lines)) if 'convergence has been achieved' in lines[i]]
    require(len(converged) == 1, 'Missing or ambiguous endpoint convergence marker')
    end = converged[0]
    require(any('JOB DONE.' in line for line in lines[end+1:]), 'Missing final JOB DONE')
    require(not any(re.search(r'convergence NOT achieved|Error in routine|iteration\s+#|Program PWSCF|total energy\s*=', line)
                    for line in lines[end+1:]), 'A later incomplete/failed run or energy block follows the endpoint')
    labels = {
        'F': 'total energy', 'minus_TS': 'smearing contrib. (-TS)',
        'E_printed': 'internal energy E=F+TS', 'O_printed': 'one-electron contribution',
        'H_printed': 'hartree contribution', 'XC_printed': 'xc contribution',
        'Ew_printed': 'ewald contribution',
    }
    result = {}
    for key, label in labels.items():
        pattern = re.compile(r'^\s*!?\s*' + re.escape(label) + r'\s*=\s*(' + NUMBER + r')\s+Ry\s*$')
        matches = [(i, pattern.match(lines[i])) for i in range(start, end) if pattern.match(lines[i])]
        require(len(matches) == 1, 'Missing/duplicate or malformed final stdout field: ' + label)
        i, match = matches[0]
        result[key] = {**token_measurement(match.group(1), 'Ry'), 'label': label, 'line': i+1}
    # Extra endpoint contributions are not silently folded into one-electron.
    known = set(labels.values())
    for line in lines[start:end]:
        if re.search(r'contribution\s*=', line):
            label = line.split('=')[0].strip()
            require(label in known, 'Unsupported extra endpoint energy contribution: ' + label)
    return {'start_line': start+1, 'end_line': end+1,
            'selection_rule': 'Last ! total-energy block after last End of self-consistent calculation, followed by convergence and JOB DONE; no later run/energy',
            'fields': result}


def _source(path, content, locator, line=None):
    return {'path': path, 'sha256': hashlib.sha256(content.encode()).hexdigest(), 'locator': locator, 'line': line}


def _json_row(root, path, pointer, identifier, state, definition, *, operator=False):
    content = (root/path).read_text()
    # Decimal preserves exact lexical tokens, including exponent/trailing zero.
    data = json.loads(content, parse_float=str, parse_int=str)
    node = data
    for key in pointer.split('/')[1:]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    measurement = token_measurement(node, 'Ha', printed=False)
    key = pointer.rsplit('/', 1)[-1]
    hits = [i+1 for i,line in enumerate(content.splitlines())
            if re.search(r'"'+re.escape(key)+r'"\s*:\s*'+re.escape(node)+r'\s*[,}]?\s*$', line)]
    source = _source(path, content, 'JSON pointer ' + pointer, hits[0] if len(hits)==1 else None)
    if len(hits) != 1:
        source['line_candidates'] = hits
    return dict(measurement, id=identifier, program='DFTK', native_field=pointer,
                source=source, state=state, definition=definition,
                record_kind='DIRECT_OPERATOR_EXPECTATION' if operator else 'DIRECT_RECORDED_VALUE')


def parse_qe_energy(xml_text, stdout, xml_path=QE+'qe.xml', stdout_path=QE+'qe.stdout'):
    root = ET.fromstring(xml_text)
    require(root.attrib.get('Units') == 'Hartree atomic units', 'QE XML energy units not established')
    for element in root.iter():
        element.tag = element.tag.split('}')[-1]
    require(root.findtext('input/control_variables/calculation') == 'scf' and root.findtext('exit_status') == '0' and
            root.findtext('output/convergence_info/scf_conv/convergence_achieved') == 'true',
            'Energy ledger requires successful original SCF, not bands or a failed endpoint')
    require(root.findtext('input/dft/functional') == 'PBESOL' and
            root.findtext('input/control_variables/fcp') == 'false' and
            root.findtext('input/control_variables/rism') == 'false' and
            root.findtext('output/magnetization/do_magnetization') == 'false' and
            float(root.findtext('input/bands/tot_charge')) == 0.0, 'Unsupported energy accounting settings')
    require([x.tag for x in root.find('input/dft')] == ['functional'], 'Extra DFT corrections are outside this ledger')
    block = endpoint_block(stdout)
    total = root.find('output/total_energy')
    require(total is not None and {x.tag for x in total} == {'etot','demet','ehart','etxc','ewald','eband','vtxc'},
            'Missing or extra native XML energy fields')
    definitions = {'etot':'F, native finite-temperature free energy', 'demet':'-TS, entropy energy',
        'ehart':'Hartree at final unmixed output rho', 'etxc':'XC at final unmixed output rho; etxcc is obsolete zero in tag',
        'ewald':'Ionic periodic Ewald energy', 'eband':'Occupied eigenvalue sum from the final H[n_in] solve',
        'vtxc':'Integral of final valence n_out times full GGA vxc[n_out]'}
    rows = {}
    for name in definitions:
        nodes = total.findall(name)
        require(len(nodes)==1 and nodes[0].text is not None, 'Ambiguous native energy: '+name)
        token = nodes[0].text.strip()
        lines = [i+1 for i,line in enumerate(xml_text.splitlines()) if '<'+name+'>'+token+'</'+name+'>' in line]
        state = 'G40:H[n_in] solved orbitals' if name == 'eband' else 'G40:final output rho / fixed ions'
        rows[name] = dict(token_measurement(token, 'Ha'), id='G40.'+name, program='QE', native_field=name,
            source=_source(xml_path,xml_text,'XML output/total_energy/'+name,lines[0] if len(lines)==1 else None),
            state=state, record_kind='DIRECT_RECORDED_VALUE', definition=definitions[name],
            source_definition=[DEFINITIONS['qe_units'], DEFINITIONS['qe_state'], DEFINITIONS['qe_vtxc']])
    printed = {}
    for key, measurement in block['fields'].items():
        printed[key] = dict(measurement,id='G40.stdout.'+key,program='QE',native_field=measurement['label'],
            source=_source(stdout_path,stdout,'Final successful SCF energy block',measurement['line']),
            state='G40:final SCF block; O uses original deband', record_kind='DIRECT_RECORDED_VALUE',
            definition='eband+deband' if key=='O_printed' else measurement['label'],
            source_definition=DEFINITIONS['qe_print'])
    energy = derived_row('G40.E','QE','etot-demet',[rows['etot'],rows['demet']],[1,-1], 'G40:final SCF internal energy')
    one = derived_row('G40.O_ledger','QE','E-ehart-etxc-ewald',
                      [energy,rows['ehart'],rows['etxc'],rows['ewald']],[1,-1,-1,-1], 'G40:derived final energy ledger')
    checks = {key:interval_check(rows[native],printed[key]) for key,native in
              [('F','etot'),('minus_TS','demet'),('H_printed','ehart'),('XC_printed','etxc'),('Ew_printed','ewald')]}
    checks['E_printed'] = interval_check(energy, printed['E_printed'])
    checks['O_ledger_vs_one_electron'] = interval_check(one, printed['O_printed'])
    printed_sum = interval_combination([printed[k] for k in ('O_printed','H_printed','XC_printed','Ew_printed')], [1,1,1,1])
    checks['stdout_component_sum_vs_internal'] = interval_check(printed_sum,printed['E_printed'])
    # This remains a diagnostic; the earlier eband/deband stage is not repaired
    # by substituting final-density XML 2H+vtxc.
    stale = rows['eband']['value_ha'] - 2*rows['ehart']['value_ha'] - rows['vtxc']['value_ha']
    return {'rows':list(rows.values())+list(printed.values())+[energy,one], 'native':rows,
            'E':energy,'O':one,'stdout_block':{k:v for k,v in block.items() if k!='fields'},
            'stdout_crosschecks':checks,
            'cross_stage_diagnostic':{'status':'NOT_A_SAME_STATE_IDENTITY',
                'O_ledger_minus_eband_minus_2H_minus_vtxc_ha':one['value_ha']-stale,
                'historical_deband_status':'NOT_DIRECTLY_PUBLISHED',
                'reason':'deband used pre-update HXC; final XML H and vtxc use n_out; no substitution or attribution'}}


def signed_ledger(dftk, qe):
    require(set(dftk['terms']) == set(TERMS), 'Wrong DFTK seven-term ledger')
    terms = dftk['terms']
    od = math.fsum(terms[key] for key in ('Kinetic','AtomicLocal','AtomicNonlocalFR','PspCorrection'))
    require(abs(math.fsum(terms.values()) - dftk['E']) <= ARITHMETIC_ATOL, 'DFTK native term sum fails')
    delta = {'E':dftk['E']-qe['E'], 'H':terms['Hartree']-qe['H'], 'XC':terms['Xc']-qe['XC'],
             'Ew':terms['Ewald']-qe['Ew'], 'O':od-qe['O']}
    closure = delta['E'] - math.fsum(delta[key] for key in ('H','XC','Ew','O'))
    require(abs(closure)<=ARITHMETIC_ATOL, 'Signed energy ledger does not close')
    return {'status':'PASS','direction':'DFTK minus G40','delta_ha':delta,
            'R_after_H_ha':delta['E']-delta['H'],
            'R_after_H_XC_Ew_ha':delta['E']-math.fsum(delta[k] for k in ('H','XC','Ew')),
            'signed_closure_error_ha':closure,'O_D_ha':od,
            'T_D_plus_NL_D_ha':math.fsum(terms[k] for k in ('Kinetic','AtomicNonlocalFR')),
            'L_D_plus_Pc_D_ha':terms['AtomicLocal']+terms['PspCorrection'],
            'O_Q_ledger_ha':qe['O'],'O_Q_record_kind':'DERIVED_COMBINATION',
            'qe_separate_kinetic_nonlocal_status':'NOT_AVAILABLE',
            'residual_attribution_status':'SIGNED_COMBINATION_ONLY_NOT_SOC_ERROR'}


def build_energy_ledger(root=ROOT):
    root = Path(root)
    plan = json.loads((root/PLAN).read_text())
    require(set(PUBLIC_SOURCES).issubset(plan['source_sha256']), 'Required historical source absent from plan')
    check_source_bindings(root, plan)
    qe = parse_qe_energy((root/(QE+'qe.xml')).read_text(),(root/(QE+'qe.stdout')).read_text())
    canonical_path = 'results/mg-soc-qe-diagnostics/canonical.json'
    canonical = json.loads((root/canonical_path).read_text())['G40']
    require(canonical['calculation']=='scf' and canonical['execution_status']=='PASS' and
            canonical['pseudo_type']=='NC' and canonical['nlcc'] is False and canonical['z_valence']==10 and
            canonical['xc']['indices'][:4]==[1,4,10,8], 'Historical G40 scope is not this no-NLCC PBEsol case')
    for key,row in qe['native'].items():
        require(row['value_ha']==canonical['energy']['native_components_ha'][key], 'Native XML/canonical energy changed: '+key)
    require(all(item['status']=='PASS' for item in qe['stdout_crosschecks'].values()), 'Native stdout/XML printed intervals disagree')
    field_dictionary = list(qe['rows'])
    native_values = {'G40':{'E':qe['E']['value_ha'],'F':qe['native']['etot']['value_ha'],
        'minus_TS':qe['native']['demet']['value_ha'],'H':qe['native']['ehart']['value_ha'],
        'XC':qe['native']['etxc']['value_ha'],'Ew':qe['native']['ewald']['value_ha'],
        'O':qe['O']['value_ha'],'Ixc':qe['native']['vtxc']['value_ha']}}
    comparisons = {}
    for label in ('A','B'):
        path = 'results/mg-soc-scf/'+label+'/endpoint.json'
        endpoint = json.loads((root/path).read_text())
        diag = endpoint['diagnostics']
        require(endpoint['n_out_sha256']==diag['orbital_density_sha256'] and
                endpoint['n_in_sha256']==diag['consumed_input_sha256'] and
                'n_out' in diag['energy_density_source'], 'Historical DFTK energy/density state mismatch')
        require(diag['energy_checks']['nlcc_present'] is False and set(diag['energy_terms_ha'])==set(TERMS),
                'Wrong historical DFTK common-term scope')
        state = label+':n_out='+endpoint['n_out_sha256']+'; original X/f, H[n_out] expectation'
        rows = {}
        for name in TERMS:
            rows[name] = _json_row(root,path,'/diagnostics/energy_terms_ha/'+name,label+'.'+name,state,
                                  DEFINITIONS['dftk_energy'],operator=name in ('Kinetic','AtomicLocal','AtomicNonlocalFR'))
        for key, pointer in [('E','internal_energy_ha'),('F','free_energy_ha'),('minus_TS','entropy_energy_ha')]:
            rows[key] = _json_row(root,path,'/diagnostics/'+pointer,label+'.'+key,state,DEFINITIONS['dftk_entropy'])
        for key,pointer in [('Ixc','integral_n_vxc_ha'),('band_expectation','band_expectation_ha')]:
            rows[key] = _json_row(root,path,'/diagnostics/energy_checks/'+pointer,label+'.'+key,state,DEFINITIONS['dftk_energy'],operator=True)
        require(abs(rows['F']['value_ha']-rows['E']['value_ha']-rows['minus_TS']['value_ha'])<=ARITHMETIC_ATOL,
                'DFTK E/F/-TS sign mismatch')
        one = derived_row(label+'.O','DFTK','Kinetic+AtomicLocal+AtomicNonlocalFR+PspCorrection',
             [rows[k] for k in ('Kinetic','AtomicLocal','AtomicNonlocalFR','PspCorrection')],[1,1,1,1],state)
        field_dictionary.extend(list(rows.values())+[one])
        native_values[label] = {k:rows[k]['value_ha'] for k in ('E','F','minus_TS','Ixc','band_expectation')}
        native_values[label]['terms'] = {k:rows[k]['value_ha'] for k in TERMS}
        comparisons[label+'_minus_G40'] = signed_ledger(native_values[label],native_values['G40'])
    source_hashes = {p:sha256(root/p) for p in sorted(PUBLIC_SOURCES)}
    old_h = json.loads((root/'results/mg-soc-density-hartree/comparison.json').read_text())
    hartree_crosschecks = {label:{key:old_h['sources'][label][key] for key in
        ('native_hartree_ha','historical_hartree_ha','self_hartree_difference_ha','density_state_binding_status')}
        for label in ('A_out','B_out','QE')}
    return {'schema_version':1,'case':'mg-soc-energy-reference-v1',
        'derivation_status':'NEW_POSTPROCESSING_OF_HISTORICAL_STATES',
        'energy_field_semantics_status':'PASS_WITH_QE_TAGGED_SOURCE_LIMITATION',
        'historical_energy_ledger_status':'PASS','source_binding_status':'PASS','source_sha256':source_hashes,
        'field_dictionary':field_dictionary,'native_values':native_values,'comparisons':comparisons,
        'stdout_endpoint_block':qe['stdout_block'],'stdout_crosschecks':qe['stdout_crosschecks'],
        'cross_stage_diagnostic':qe['cross_stage_diagnostic'],
        'hartree_source_policy':'Main ledger uses native historical energies; Phase7C coefficient recomputation is separate',
        'phase7c_hartree_crosschecks':hartree_crosschecks,
        'qe_applicability':{'status':'TAGGED_SOURCE_CONVENTION_FOR_BOUND_G40_SETTINGS',
            'source_definitions':DEFINITIONS,
            'etxcc':{'status':'SOURCE_CONVENTION_ZERO_NOT_RUNTIME_EXTRACTION','value_ha':0.0,'source':DEFINITIONS['qe_etxcc']},
            'descf':{'status':'CONVERGED_BRANCH_ZERO_NOT_RUNTIME_EXTRACTION','value_ha':0.0,'source':DEFINITIONS['qe_state']},
            'extra_terms':'Bound plain periodic neutral NC/PBEsol input has no PAW, Hubbard, hybrid/meta/nonlocal-XC, dispersion, field, FCP/RISM or external-plugin request; final stdout has only four listed components',
            'installed_source_commit':None,
            'limitation':'Actual executable identity is historically bound; tagged source is not proof of every build-time modification'},
        'qe_native_local_potential_status':'NOT_EXTRACTED','qe_separate_kinetic_nonlocal_status':'NOT_AVAILABLE',
        'numerical_agreement_status':'REVIEW_REQUIRED','physical_convergence_status':'NOT_ESTABLISHED',
        'new_scf_status':'NOT_RUN','new_eigensolve_status':'NOT_RUN','new_qe_numerical_status':'NOT_RUN'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(build_energy_ledger(args.root),indent=2,allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps({'historical_energy_ledger_status':'FAIL','reason':str(error)},allow_nan=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
