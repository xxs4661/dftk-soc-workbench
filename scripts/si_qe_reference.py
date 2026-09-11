#!/usr/bin/env python3
"""Frozen Phase 8C QE-only case contract and public scalar trend arithmetic.

No solver, UPF reader, density reconstruction or fitted reference. Native parsing
remains in si_soc_comparison; original spectral and FD formulas are imported.
"""
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path

from si_soc_comparison import analyze_gamma, check, hash_string, number, _fd_diagnostic, _levels
from parse_qe_soc import match_points

ROOT = Path(__file__).resolve().parents[1]
BASE = '557571fa6beb29e1ee57a5a0701ab3bded41fc78'
PREPARATION = '4ba043c42141cce775dd5e5beed0f16b84b1e91b'
CASE_DIR = 'benchmarks/si-soc-k-reference-v1'
PROFILE_IDS = ('K6', 'K8')
PREPARED_HASHES = {
    "benchmarks/si-soc-k-reference-v1/K6/case.json": "e63471b90f7673524beabd7a240f069619bac807884bc0d60e7d37f5c598fc03",
    "benchmarks/si-soc-k-reference-v1/K6/qe-gamma.in": "4c495b4118777515b9b2edd31bfc0ec459f41e658fd265a5a92889d7cdb1989b",
    "benchmarks/si-soc-k-reference-v1/K6/qe-scf.in": "6e3cfbaceb4d65aaca48441daf584088ae6158636a68d0863b69b409ff923823",
    "benchmarks/si-soc-k-reference-v1/K8/case.json": "03988993f76efbf68baadfb328e7e5196ad10ab5b99a12a9457f766da8933941",
    "benchmarks/si-soc-k-reference-v1/K8/qe-gamma.in": "4cbbe8a9585a4c4ec5f8fa3af6aec0fa97378e4e8341483383d06db6f17c8d4d",
    "benchmarks/si-soc-k-reference-v1/K8/qe-scf.in": "eddf4e57256de0bc7875742109b2998147b188151b60f4bde307ad0818b243d1",
    "benchmarks/si-soc-k-reference-v1/README.md": "e7cdd57d9cd6957b0cc50c091b64ea9d6f72bc65a696f231fc54736ec0b95b81",
    "benchmarks/si-soc-k-reference-v1/allowed-differences.json": "77323838aa068dfa08d745d0806ae6a21ae66de1c31ebcac51bf3edb5bb21162",
    "benchmarks/si-soc-k-reference-v1/plan.json": "b278a61159227af562fd9ecb0463ae309524b84a187bed3e26392aaf0deafa31",
    "benchmarks/si-soc-k-reference-v1/replay-contract.json": "2053d8e3251ea4e996d555ca98b82e4777cbfbf9e99fbd409d3b35f2799e8bba",
    "benchmarks/si-soc-k-reference-v1/resource-geometry.json": "60d1cfa53ce2051fad10bc0369f6abe5133834ecb2b81987015d21f9d7be3775",
    "benchmarks/si-soc-k-reference-v1/resource-plan.json": "c43affa73654ed70c62b2c845def0789682fe7123ca9906dc7457ff7847392b6",
    "benchmarks/si-soc-k-reference-v1/sources.json": "ad07070b4c41f1340d0fc924c0bcd4f468a087eb1e5c84dfca0a083e07c9e6cf"
}
RUNTIME_FIELDS = {'verified_pseudo_sha256', 'case_sha256'}
REPLAY_ATOL = 1e-11
WINDOW_EV = 1e-4


def read(path):
    def invalid(token):
        raise ValueError('Nonfinite JSON token: ' + token)
    return json.loads(Path(path).read_text(), parse_constant=invalid)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _bytes(root, relative, digest, size=None):
    root, rel = Path(root).resolve(), Path(relative)
    check(not rel.is_absolute() and '..' not in rel.parts, 'Unconfined public input')
    path = root / rel
    check(path.resolve().is_relative_to(root) and not any(p.is_symlink() for p in [path, *path.parents] if p != root),
          'Symlink or escaped public input: ' + relative)
    raw = path.read_bytes()
    check(hashlib.sha256(raw).hexdigest() == digest and (size is None or len(raw) == size),
          'Prepared/historical byte mismatch: ' + relative)
    return raw


def prepared_paths(profile=None):
    check(profile is None or profile in PROFILE_IDS, 'Unregistered QE reference profile')
    selected = PROFILE_IDS if profile is None else (profile,)
    return [p for p in PREPARED_HASHES if not any('/'+other+'/' in p for other in PROFILE_IDS if other not in selected)]


def _prepared(root, profile=None):
    for path in prepared_paths(profile):
        _bytes(root, path, PREPARED_HASHES[path])
    return read(Path(root) / CASE_DIR / 'sources.json')


def case_sha256(profile, root=ROOT):
    check(profile in PROFILE_IDS, 'Unregistered QE reference profile')
    _prepared(root, profile)
    return PREPARED_HASHES[f'{CASE_DIR}/{profile}/case.json']


def _history_bytes(root, sources, path):
    item = sources['historical_files'][path]
    _bytes(root, path, item['sha256'], item['bytes'])
    return read(Path(root) / path)


def load_case(root, profile):
    sources = _prepared(root, profile)
    base = _history_bytes(root, sources, 'benchmarks/si-soc-sensitivity-v1/K4/case.json')
    _history_bytes(root, sources, sources['pseudo_reference'])
    n = int(profile[1:])
    numerators = list(range(n//2)) + list(range(-n//2, 0))
    expected = copy.deepcopy(base)
    del expected['sensitivity_profile']
    expected.update(qe_reference_profile=profile, profile_type='QE_REFERENCE',
                    case='si-soc-k-reference-v1-'+profile, dftk_execution_status='NOT_RUN',
                    k_grid={'denominator': n, 'axis_numerators': numerators,
                            'loop_order': 'itertools.product(axis, repeat=3); last coordinate fastest'})
    expected['qe']['prefix'] = 'si8c_'+profile.lower()
    expected['kpoints'] = [{'coordinate_fractional': [x/n for x in p], 'weight_spatial': 1/n**3}
                          for p in itertools.product(numerators, repeat=3)]
    case = read(Path(root) / CASE_DIR / profile / 'case.json')
    check(_canonical(case) == _canonical(expected), 'Case exceeds the exact registered K4 differences')
    return case


def validate_case(case, root=ROOT):
    check(isinstance(case, dict), 'QE-reference case must be an object')
    profile = case.get('qe_reference_profile')
    check(profile in PROFILE_IDS and 'sensitivity_profile' not in case, 'Wrong or ambiguous profile type')
    declared = {k:v for k,v in case.items() if k not in RUNTIME_FIELDS}
    expected = load_case(root, profile)
    check(_canonical(declared) == _canonical(expected), 'Unapproved case override, field or type')
    if 'case_sha256' in case:
        check(case['case_sha256'] == case_sha256(profile, root), 'Runtime case hash mismatch')
    if 'verified_pseudo_sha256' in case:
        check(case['verified_pseudo_sha256'] == expected['pseudo']['sha256'], 'Runtime UPF receipt mismatch')
    return case


def _exact(actual, expected, reason):
    check(_canonical(actual) == _canonical(expected), reason)


def _close(a, b, reason, tolerance=REPLAY_ATOL):
    a, b = number(a), number(b)
    check(abs(a-b) <= tolerance*max(1., abs(a), abs(b)), reason)


def _identity(receipt, case, kind, root):
    validate_case(case, root)
    check(isinstance(receipt, dict), 'Missing current QE receipt')
    expected = {'schema_version':1, 'case':case['case'], 'qe_reference_profile':case['qe_reference_profile'],
        'case_sha256':case_sha256(case['qe_reference_profile'], root), 'code':'QE', 'kind':kind,
        'execution_status':'PASS', 'process_exit_code':0, 'input_comparability_status':'PASS',
        'physical_operator':'full_soc', 'pseudo_sha256':case['pseudo']['sha256'], 'n_electrons':8,
        'n_bands':24, 'occupation_capacity':1, 'temperature_ha':.001,
        'cutoffs':case['cutoffs'], 'requested_kpoint_count':len(case['kpoints']) if kind=='scf' else 1}
    for key, value in expected.items():
        check(key in receipt, 'Missing receipt field: '+key)
        _exact(receipt[key], value, 'Receipt identity/input mismatch: '+key)
    check('sensitivity_profile' not in receipt, 'Paired sensitivity profile cannot substitute QE reference')
    check(isinstance(receipt.get('run_id'), str) and receipt['run_id'], 'Missing run identity')
    check(hash_string(receipt.get('density_source_sha256')), 'Missing authenticated density identity')
    for key in ('fitted_shift','per_k_shift','per_band_shift','energy_correction_ha'):
        check(key not in receipt, 'Fitting/correction not permitted')
    warning = receipt.get('warning_evidence')
    check(isinstance(warning, dict) and type(warning.get('eigenvalues_not_converged')) is bool,
          'Missing native warning evidence')


def _scf_quantities(receipt, points, tau):
    scf = receipt.get('scf')
    check(isinstance(scf, dict) and scf.get('converged') is True, 'SCF did not converge')
    check(type(scf.get('iterations')) is int and 0 < scf['iterations'] <= 200, 'Invalid SCF iteration count')
    check(0 <= number(scf['error_ha']) <= 5e-13, 'SCF error exceeds the native criterion')
    actual = receipt.get('kpoints')
    check(isinstance(actual, list), 'Missing all SCF endpoints')
    order = match_points([p['coordinate_fractional'] for p in points],
                         [p['coordinate_fractional'] for p in actual], 1e-10)
    mu = number(receipt['fermi_energy_ha'])
    ne = entropy = fd_error = tail = weight_sum = 0.
    for wanted, i in zip(points, order):
        p = actual[i]
        w = number(p['weight_spatial'])
        check(abs(w-number(wanted['weight_spatial'])) <= 1e-10 and w > 0, 'Wrong native spatial weight')
        values = _levels(p['eigenvalues_ha'])
        occ = p.get('occupations')
        check(isinstance(occ, list) and len(occ)==24, 'Expected24 physical SCF occupations')
        occ = [number(f) for f in occ]
        check(all(0 <= f <= 1 for f in occ), 'Occupation outside capacity one')
        weight_sum += w
        ne += w*sum(occ)
        entropy -= w*sum(f*math.log(f)+(1-f)*math.log1p(-f) for f in occ if 0 < f < 1)
        fd_error = max(fd_error, max(abs(f-g) for f,g in zip(occ, _fd_diagnostic(values,mu,tau=tau))))
        tail = max(tail, *occ[-2:])
    check(abs(weight_sum-1) <= 1e-10, 'Spatial weights do not sum to one')
    check(abs(ne-8) <= 1e-8, 'SCF electron-count failure')
    check(fd_error <= 1e-11, 'SCF FD mismatch at actual parent mu/tau')
    check(tail <= 1e-10, 'Insufficient physical bands: occupied top-two states')
    energy = receipt.get('energy')
    check(isinstance(energy, dict), 'SCF native energy missing; bands values cannot substitute')
    for key in ('internal_ha','free_ha','minus_TS_ha','entropy_dimensionless'):
        number(energy[key])
    check(energy['entropy_dimensionless'] >= 0, 'Negative entropy')
    _close(energy['free_ha'],energy['internal_ha']+energy['minus_TS_ha'],'E/F/-TS arithmetic mismatch',1e-12)
    _close(energy['minus_TS_ha'],-tau*energy['entropy_dimensionless'],'Entropy temperature mismatch')
    _close(energy['entropy_dimensionless'],entropy,'Entropy differs from complete original occupations')
    _close(receipt['electron_sum'],ne,'Stored electron count differs from full endpoints')
    return {'status':'PASS','electron_sum':ne,'electron_error':ne-8,'weight_sum':weight_sum,
        'FD_max_abs':fd_error,'top_two_occupation_max':tail,'entropy_dimensionless':entropy,
        'fermi_energy_ha':mu,'temperature_ha':tau,'n_kpoints':len(points),'n_bands':24,
        'scope':'Original full SCF capacity-one occupations; no renormalization or mu solve'}


def validate_q_scf(receipt, case, *, root=ROOT):
    """Return pure diagnostics before runner success publication; never mutate."""
    _identity(receipt,case,'scf',root)
    check(receipt.get('occupations_use')=='SCF_DENSITY','Wrong SCF occupation role')
    return _scf_quantities(receipt,case['kpoints'],case['electrons']['temperature_ha'])


def _gamma_quantities(receipt, parent, point):
    check(receipt.get('source_scf_run_id')==parent['run_id'],'Wrong Gamma parent run')
    check(receipt.get('density_source_sha256')==parent['density_source_sha256'],'Wrong Gamma parent density')
    check(number(receipt['fermi_energy_ha'])==number(parent['fermi_energy_ha']),'Gamma changed parent SCF mu')
    check(number(receipt['temperature_ha'])==number(parent['temperature_ha']),'Gamma changed parent tau')
    gamma = analyze_gamma(point['eigenvalues_ha'])
    values = gamma['values_ha']
    precision, warning = receipt['precision'], receipt['warning_evidence']
    check(isinstance(precision,dict) and isinstance(warning,dict),'Missing native Gamma precision/warnings')
    _exact(precision.get('diago_thr_init_ry'),1e-13,'Wrong native Gamma CG threshold')
    thresholds=precision.get('ethr_history_ry')
    check(isinstance(thresholds,list) and thresholds and all(number(x)==1e-13 for x in thresholds),
          'Missing actual CG1e-13Ry threshold history')
    check(type(warning.get('eigenvalues_not_converged')) is bool,'Missing native target warning status')
    pairing=max(abs(values[i]-values[i+1]) for i in range(0,24,2))
    structure=all(gamma[k]=='PASS' for k in ('manifold_assignment_status','multiplet_structure_status'))
    precision_status='INCONCLUSIVE' if warning['eigenvalues_not_converged'] else 'PASS'
    mu,tau=number(parent['fermi_energy_ha']),number(parent['temperature_ha'])
    occ=_fd_diagnostic(values,mu,tau=tau)
    gamma.update(gamma_structure_status='PASS' if structure else 'MISMATCH',
        fixed_window_interpretation='ISOLATED_FIXED_WINDOW' if structure else 'WINDOW_ONLY_NOT_IDENTIFIED',
        kramers_max_ha=pairing,gamma_pairing_status='PASS' if pairing<=1e-7 else 'MISMATCH',
        precision_status=precision_status,
        precision={'status':precision_status,'native':copy.deepcopy(precision),'explicit_wavefunction_residuals':'NOT_AVAILABLE'},
        occupation={'values':occ,'minimum_3_to_8':min(occ[2:8]),'maximum_hole_3_to_8':max(1-f for f in occ[2:8]),
            'mu_minus_upper_max_over_tau':(mu-max(values[4:8]))/tau,'mu_ha':mu,'temperature_ha':tau,
            'threshold':.99999999,'status':'PASS' if min(occ[2:8])>=.99999999 else 'REVIEW_REQUIRED',
            'scope':'Original parent SCF mu; Gamma electron sum not constrained to8'},
        warning_evidence=copy.deepcopy(warning),
        trend_usable=structure and gamma['resolvable_soc_status']=='PASS' and pairing<=1e-7 and precision_status=='PASS')
    gamma['unusable_reasons']=[k for k in ('gamma_structure_status','resolvable_soc_status','gamma_pairing_status','precision_status') if gamma[k]!='PASS']
    return gamma


def validate_q_gamma(receipt, parent, case, *, root=ROOT):
    """Bad identity raises; finite failed scientific gates retain their algebra."""
    _identity(receipt,case,'spectrum',root)
    validate_q_scf(parent,case,root=root)
    check(parent.get('scf_acceptance_status')=='PASS','Gamma parent not accepted')
    check(receipt['run_id']!=parent['run_id'],'Gamma cannot reuse SCF run ID')
    check(receipt.get('energy') is None and receipt.get('scf') is None and receipt.get('electron_sum') is None,
          'Bands thermodynamics cannot become SCF thermodynamics')
    check(receipt.get('occupations_use')=='DIAGNOSTIC_ONLY_NOT_DENSITY_FEEDBACK','Wrong Gamma occupation role')
    points=receipt.get('kpoints')
    check(isinstance(points,list),'Missing Gamma spectrum')
    match_points([[0.,0.,0.]],[p['coordinate_fractional'] for p in points],1e-10)
    check(number(points[0]['weight_spatial'])==1.,'Gamma diagnostic spatial weight must be one')
    result=_gamma_quantities(receipt,parent,points[0])
    result['source']={'status':'NEW_EXECUTION','profile':case['qe_reference_profile'],
        'run_id':receipt['run_id'],'source_scf_run_id':parent['run_id'],
        'density_source_sha256':parent['density_source_sha256'],'case_sha256':receipt['case_sha256']}
    return result


def load_history(root=ROOT):
    sources=_prepared(root)
    for path,item in sources['historical_files'].items():
        _bytes(root,path,item['sha256'],item['bytes'])
    bcase=read(Path(root)/'benchmarks/si-soc-splitting-v1/case.json')
    bscf=read(Path(root)/'results/si-soc-splitting/Q-SCF/qe-result.json')
    bg=read(Path(root)/'results/si-soc-splitting/Q-spectrum.json')
    kc=read(Path(root)/'benchmarks/si-soc-sensitivity-v1/K4/case.json')
    kd=read(Path(root)/'results/si-soc-sensitivity/K4/data.json')
    result={}
    for label,case,scf,gamma in [('B0',bcase,bscf,bg),('K4',kc,kd['Q-SCF'],kd['Q-GAMMA'])]:
        for receipt,kind in [(scf,'scf'),(gamma,'spectrum')]:
            check(receipt['execution_status']=='PASS' and type(receipt['process_exit_code']) is int
                  and receipt['process_exit_code']==0 and receipt['kind']==kind and receipt['code']=='QE'
                  and receipt['physical_operator']=='full_soc','Invalid historical Q source')
        _scf_quantities(scf,case['kpoints'],.001)
        order=match_points(case['probe_kpoints'],[p['coordinate_fractional'] for p in gamma['kpoints']],1e-10)
        result[label]=_gamma_quantities(gamma,scf,gamma['kpoints'][order[0]])
        result[label]['source']={'status':'HISTORICAL_REUSED','profile':label,'run_id':gamma['run_id'],
            'source_scf_run_id':scf['run_id'],'density_source_sha256':scf['density_source_sha256'],
            'execution_commit':sources['B0_execution' if label=='B0' else 'K4_execution'],
            'publication_commit':sources['B0_publication'] if label=='B0' else BASE}
    return result


def step_status(step, usable=True):
    check(type(usable) is bool, 'Step usability must be a boolean')
    if step is None or not usable:
        return 'INCONCLUSIVE'
    return 'WITHIN_SCREENING_WINDOW' if abs(number(step))<=WINDOW_EV else 'CHANGE_EXCEEDS_SCREENING_WINDOW'


def compare_trend(points):
    """Pure scalar summary; caller authenticates all endpoint/native evidence.

    None denotes a missing/failed point, never a replacement by another grid.
    Invalid nonfinite data is a hard failure rather than an inconclusive number.
    """
    check(isinstance(points,dict) and set(points)=={'B0','K4','K6','K8'},'Expected exactly four named QE reference points')
    for value in points.values():
        if value is not None:
            check(isinstance(value,dict) and type(value.get('trend_usable')) is bool,'Invalid point usability')
            number(value['delta_so_ev'])
    steps={}
    for name,left,right in [('s24','B0','K4'),('s46','K4','K6'),('s68','K6','K8')]:
        a,b=points[left],points[right]
        value=None if a is None or b is None else b['delta_so_ev']-a['delta_so_ev']
        usable=a is not None and b is not None and a['trend_usable'] and b['trend_usable']
        steps[name]={'from':left,'to':right,'signed_ev':value,'absolute_ev':None if value is None else abs(value),
                     'signed_mev':None if value is None else value*1000,'status':step_status(value,usable)}
    statuses=[steps[k]['status'] for k in ('s46','s68')]
    last_two='INCONCLUSIVE' if 'INCONCLUSIVE' in statuses else ('WITHIN_SCREENING_WINDOW' if all(s=='WITHIN_SCREENING_WINDOW' for s in statuses) else 'CHANGE_EXCEEDS_SCREENING_WINDOW')
    three=[points[k] for k in ('K4','K6','K8')]
    span=None if any(v is None for v in three) else max(v['delta_so_ev'] for v in three)-min(v['delta_so_ev'] for v in three)
    return {'schema_version':1,'profile_type':'QE_REFERENCE','trend_execution_status':'PASS',
        'delta_so_ev':{k:None if v is None else v['delta_so_ev'] for k,v in points.items()},'steps':steps,
        'last_step_status':steps['s68']['status'],'last_two_QE_steps_status':last_two,
        'last_three_QE_range_ev':span,'last_three_QE_range_mev':None if span is None else span*1000,
        'range_interpretation_status':'INCONCLUSIVE' if any(v is None or not v['trend_usable'] for v in three) else 'FINITE_OBSERVATION',
        'range_exceeds_window':None if span is None else span>WINDOW_EV,'window_ev':WINDOW_EV,
        'DFTK_K6_status':'NOT_RUN','DFTK_K8_status':'NOT_RUN','same_grid_cross_code_agreement':'NOT_ASSESSED',
        'physical_convergence':'NOT_ESTABLISHED','physical_manifold_interpretation':'REVIEW_REQUIRED',
        'QE_explicit_wavefunction_residuals':'NOT_AVAILABLE',
        'scope':'Fixed-setting finite QE sequence; no D extrapolation, fitted limit or convergence bound'}


# Public evidence-facing names; all callers use the same implementation.
historical_points = load_history
build_trend = compare_trend
