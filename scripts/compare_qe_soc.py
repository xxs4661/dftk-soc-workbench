#!/usr/bin/env python3
"""Compare the prescribed Mg SOC case, retaining raw spectra and energy semantics.

DFTK A is fixed as the primary reference; B is an independent historical
reproducibility reference. No calculation, per-k fit or energy correction runs.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from compare_scalar_baseline import HARTREE_EV, energy_to_ha, finite_tree, match_kpoints, same_point


def require(ok, message):
    if not ok:
        raise ValueError(message)


def finite_number(value, name):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value), name + " must be finite")
    return value


def close(a, b, tolerance, name):
    finite_number(a, name); finite_number(b, name)
    require(abs(a-b) <= tolerance, name + " differs")


def read_json(path):
    data = json.loads(Path(path).read_text())
    finite_tree(data)
    return data


def filehash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def matched_points(expected, actual):
    matched = match_kpoints(expected, actual)
    for p, q in zip(expected, matched):
        require(same_point(p["coordinate_fractional"], q["coordinate_fractional"], 1e-10),
                "K coordinate exceeds the predeclared 1e-10 tolerance")
    return matched


def validate_spectrum(points, *, n_bands=24, electrons=10, electron_atol=1e-8):
    require(len(points) == 3, "Expected exactly three spatial k points")
    matched_points(points, points)  # Reject duplicated coordinates modulo integers.
    total = 0.0
    for p in points:
        w = finite_number(p["weight_spatial"], "Spatial k weight")
        require(0 < w <= 1, "Invalid spatial k weight")
        levels, f = p["eigenvalues_ha"], p["occupations"]
        require(len(levels) == len(f) == n_bands, "Missing or extra target bands/occupations")
        require(all(finite_number(v, "Eigenvalue") == v for v in levels), "Invalid levels")
        require(all(x <= y+1e-10 for x,y in zip(levels,levels[1:])),
                "Target eigenvalues exceed the predeclared native-order tolerance; no sorting is applied")
        require(all(0 <= finite_number(v, "Physical spinor occupation") <= 1 for v in f),
                "Explicit spinor occupation capacity is one")
        total += w*sum(f)
    close(sum(p["weight_spatial"] for p in points), 1, 1e-12, "Spatial weight sum")
    close(total, electrons, electron_atol, "Global weighted electron count")
    return total


def global_homo(points, *, occupied_threshold=.5, saturation_tolerance=1e-8):
    """One reference for every k/state; ambiguous finite-temperature filling is explicit."""
    require(occupied_threshold == .5 and saturation_tolerance == 1e-8,
            "Predeclared occupation boundary changed")
    occupied, empty = [], []
    for p in points:
        for e, f in zip(p["eigenvalues_ha"], p["occupations"]):
            if not (f <= saturation_tolerance or f >= 1-saturation_tolerance):
                return {"status": "UNSUPPORTED", "homo_ha": None,
                        "reason": "A physical occupation is not saturated at the predeclared 1e-8 boundary"}
            (occupied if f >= occupied_threshold else empty).append(e)
    if not occupied or not empty or max(occupied) >= min(empty):
        return {"status": "UNSUPPORTED", "homo_ha": None,
                "reason": "No globally separated occupied/empty spectrum"}
    return {"status": "SUPPORTED", "homo_ha": max(occupied), "lumo_ha": min(empty),
            "gap_ha": min(empty)-max(occupied), "occupied_states": len(occupied),
            "empty_states": len(empty), "rule": "Maximum occupied energy across the entire three-k set"}


def error_summary(values):
    if not values:
        return {"count": 0, "status": "EMPTY_GROUP", "max_abs_ha": None, "rms_ha": None,
                "max_abs_ev": None, "rms_ev": None}
    maximum = max(abs(v) for v in values)
    rms = math.sqrt(sum(v*v for v in values)/len(values))
    return {"count": len(values), "status": "REPORTED", "max_abs_ha": maximum,
            "rms_ha": rms, "max_abs_ev": maximum*HARTREE_EV, "rms_ev": rms*HARTREE_EV,
            "signed_mean_ha": sum(values)/len(values),
            "definition": "Unweighted RMS over the explicitly included k/state entries"}


def spectra(reference, qe, *, occupied_threshold=.5, saturation_tolerance=1e-8,
            reference_name='DFTK', candidate_name='QE'):
    """Coordinate match, all 3x24 raw differences, and a single global HOMO per code."""
    validate_spectrum(reference); validate_spectrum(qe)
    matched = matched_points(reference, qe)
    for p, q in zip(reference, matched):
        close(p["weight_spatial"], q["weight_spatial"], 1e-12, "Matched spatial weight")
    rh = global_homo(reference, occupied_threshold=occupied_threshold, saturation_tolerance=saturation_tolerance)
    qh = global_homo(matched, occupied_threshold=occupied_threshold, saturation_tolerance=saturation_tolerance)
    supported = rh["status"] == qh["status"] == "SUPPORTED"
    rows = []
    for k, (p, q) in enumerate(zip(reference, matched), 1):
        for band, (re, qe_e, rf, qf) in enumerate(zip(p["eigenvalues_ha"], q["eigenvalues_ha"],
                                                     p["occupations"], q["occupations"]), 1):
            raw = re-qe_e
            aligned = (re-rh["homo_ha"])-(qe_e-qh["homo_ha"]) if supported else None
            rows.append({"k_index": k, "coordinate_fractional": p["coordinate_fractional"],
                         "band_index": band, "reference_eigenvalue_ha": re, "qe_eigenvalue_ha": qe_e,
                         "reference_occupation": rf, "qe_occupation": qf,
                         "reference_group": "occupied" if rf >= occupied_threshold else "empty",
                         "occupation_classification_matches": (rf >= occupied_threshold) == (qf >= occupied_threshold),
                         "raw_difference_ha": raw, "raw_difference_ev": raw*HARTREE_EV,
                         "global_reference_difference_ha": aligned,
                         "global_reference_difference_ev": None if aligned is None else aligned*HARTREE_EV})
    summary = {}
    for count in (16, 24):
        summary[str(count)] = {}
        for group in ("all", "occupied", "empty"):
            subset = [r for r in rows if r["band_index"] <= count and
                      (group == "all" or r["reference_group"] == group)]
            summary[str(count)][group] = {
                "raw": error_summary([r["raw_difference_ha"] for r in subset]),
                "single_global_reference": error_summary([r["global_reference_difference_ha"] for r in subset]) if supported else
                    {"status": "UNSUPPORTED", "reason": "Global HOMO applicability failed; raw results retained"}}
    return {"difference_convention": reference_name+" minus "+candidate_name+"; no total-energy adjustment",
            "global_reference_status": "SUPPORTED" if supported else "UNSUPPORTED",
            "references": {reference_name: rh, candidate_name: qh}, "rows": rows, "summary": summary,
            "occupation_classification_matches": all(r["occupation_classification_matches"] for r in rows),
            "group_definition": "Occupied/empty statistics use "+reference_name+" f>=0.5 classification",
            "alignment_rule": "Exactly one global occupied maximum per program, applied to every k and band; no fitting"}


def energy_record(internal, free, entropy, *, source, native_free=None, native_entropy=None):
    for value in (internal, free, entropy): finite_number(value, "Energy [Ha/cell]")
    require(entropy <= 0, "Fermi entropy contribution must be nonpositive")
    close(internal+entropy, free, 1e-10, "E + (-TS) = F")
    if native_free is not None: close(free,native_free,1e-10,"Native QE total energy is F")
    if native_entropy is not None: close(entropy,native_entropy,1e-10,"Native QE demet is -TS")
    return {"internal_ha": internal, "free_ha": free, "entropy_ha": entropy,
            "internal_ev": internal*HARTREE_EV, "free_ev": free*HARTREE_EV,
            "entropy_ev": entropy*HARTREE_EV, "unit": "Ha/cell", "atoms_per_cell": 1,
            "per_atom_equals_per_cell_for_this_case": True, "source": source,
            "arithmetic_residual_ha": free-internal-entropy}


def energy_difference(reference, qe):
    result = {}
    for key in ("internal", "free", "entropy"):
        delta = reference[key+"_ha"]-qe[key+"_ha"]
        result[key] = {"signed_ha": delta, "absolute_ha": abs(delta),
                       "signed_ev": delta*HARTREE_EV, "absolute_ev": abs(delta)*HARTREE_EV}
    return result


def comparable_energy_terms(reference_terms, native_qe_terms):
    """Only Hartree, XC and ion-ion Ewald have a direct term mapping here."""
    terms = {}
    for name, native_key in [('Hartree','ehart'),('Xc','etxc'),('Ewald','ewald')]:
        left = finite_number(reference_terms[name], 'Historical '+name)
        right = finite_number(native_qe_terms[native_key], 'Native QE '+native_key)
        delta = left-right
        terms[name] = {'historical_ha':left,'qe_ha':right,'qe_xml_field':native_key,
                       'signed_ha':delta,'absolute_ha':abs(delta),
                       'signed_ev':delta*HARTREE_EV,'absolute_ev':abs(delta)*HARTREE_EV}
    return {'status':'REPORTED_WITH_DISTINCT_FINAL_DENSITIES', 'unit':'Ha/cell',
            'terms':terms,
            'scope':'Hartree and XC evaluated on each engine\'s own final density; Ewald is the ion-ion term. No cross-code density-array validation.',
            'qe_units_source':'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_restart_new.f90#L719-L727',
            'not_mapped':['Kinetic','AtomicLocal','AtomicNonlocalFR','PspCorrection'],
            'note':'QE native band/one-electron expressions are retained separately, not forced into the remaining historical terms'}


def spectral_symmetry(points):
    """Additional spectrum diagnostics; no spin/channel labels or agreement verdict."""
    target = [{'coordinate_fractional':p} for p in
              [[0.,0.,0.],[.125,.0625,-.1875],[-.125,-.0625,.1875]]]
    gamma, plus, minus = matched_points(target, points)
    ge = gamma['eigenvalues_ha']
    return {'status':'DIAGNOSTIC_ONLY',
            'gamma_adjacent_pair_max_ha':max(abs(ge[i+1]-ge[i]) for i in range(0,24,2)),
            'plus_minus_spectrum_max_ha':max(abs(x-y) for x,y in
                                          zip(plus['eigenvalues_ha'],minus['eigenvalues_ha'])),
            'pair_rule':'Adjacent sorted Gamma levels and equal band indices at uniquely matched k+/k-; no channel assignment'}


def validate_case(case):
    """This adapter accepts the one predeclared Mg experiment, not scalar Si."""
    require(type(case['schema_version']) is int and case['schema_version'] == 1, 'Unsupported case schema')
    require(case['case'] == 'mg-soc-qe-v1', 'Wrong case')
    require(case['electrons'] == {'n_electrons': 10, 'n_bands': 24,
            'occupation_capacity': 1, 'temperature_ha': .001}, 'Wrong spinor/electron/temperature case')
    require(case['geometry'] == {'lattice_vectors_bohr': [[10.,0.,0.],[0.,10.,0.],[0.,0.,10.]],
            'positions_fractional': [[.17,.23,.31]], 'species': ['Mg']}, 'Wrong Mg geometry')
    require(case['pseudo']['sha256'] == '19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256',
            'Wrong predeclared Mg pseudo hash')
    for key, value in {'element': 'Mg', 'pseudo_type': 'NC', 'relativistic': 'full',
                       'has_so': True, 'z_valence': 10, 'nlcc': False}.items():
        require(case['pseudo'][key] == value, 'Wrong Mg pseudo ' + key)
    # QE 7.5 Modules/funct.f90: PBESOL=sla+pw+psx+psc, IDs 1/4/10/8.
    # https://github.com/QEF/q-e/blob/qe-7.5/Modules/funct.f90#L61-L190
    require(case['xc'] == {'functional':'PBESOL', 'qe_indices':[1,4,10,8],
            'dftk_identifiers':['gga_x_pbe_sol','gga_c_pbe_sol']}, 'Wrong XC mapping')
    require(case['cutoffs'] == {'qe_ecutwfc_ry':30., 'qe_ecutrho_ry':120.}, 'Wrong prescribed cutoff')
    c = case['comparison']
    for key, value in {'primary_reference':'A', 'auxiliary_reference':'B', 'lowest_states':16,
                       'all_states':24, 'occupied_threshold':.5, 'saturation_tolerance':1e-8,
                       'numerical_agreement_status':'REVIEW_REQUIRED',
                       'physical_convergence_status':'NOT_ESTABLISHED',
                       'no_fitted_or_total_energy_correction':True}.items():
        require(c[key] == value, 'Predeclared comparison rule changed: ' + key)
    expected = [{'coordinate_fractional': p} for p in
                [[0.,0.,0.],[.125,.0625,-.1875],[-.125,-.0625,.1875]]]
    for point in matched_points(expected, case['kpoints']):
        close(point['weight_spatial'], 1/3, 1e-12, 'Prescribed spatial weight')
    require(case['historical']['status'] == 'HISTORICAL_REUSED', 'Historical status changed')
    require(case['historical']['commit'] == 'ac22a64421c4a5444a399477b9a3215dbd913487',
            'Historical published reference changed')


def load_historical(root, case):
    """Check actual bytes before returning the two named immutable references."""
    root = Path(root)
    h = case['historical']
    evidence_path = root / h['evidence']['path']
    require(filehash(evidence_path) == h['evidence']['sha256'], 'Historical evidence hash mismatch')
    evidence = read_json(evidence_path)
    # The shared environment/settings remain references, not duplicated bodies.
    for item in (evidence['environment'], evidence['settings']):
        require(filehash(root / item['path']) == item['sha256'], 'Historical environment/settings hash mismatch')
    result = []
    for label in ('A', 'B'):
        item = h['references'][label]
        require(filehash(root/item['path']) == item['sha256'], 'Historical endpoint hash mismatch: '+label)
        require(evidence['public_sha256'][label+'/endpoint.json'] == item['sha256'],
                'Historical evidence/endpoint binding differs')
        require(evidence['runs'][label]['run_id'] == item['run_id'], 'Historical run identity differs')
        result.append({'endpoint': read_json(root/item['path']), 'evidence': evidence, 'label':label,
                       'source': {'status':'HISTORICAL_REUSED', 'commit':h['commit'],
                                  'endpoint_path':item['path'], 'endpoint_sha256':item['sha256'],
                                  'evidence_path':h['evidence']['path'], 'evidence_sha256':h['evidence']['sha256'],
                                  'run_id':item['run_id'], 'environment':evidence['environment'],
                                  'executed_source_map_field':'executed_source_sha256'}})
    return tuple(result)


def historical_record(case, record, label):
    require(record['label'] == label, 'Primary/auxiliary historical reference was swapped')
    d, ev = record['endpoint'], record['evidence']
    basis, header = ev['basis'], ev['input']
    run = ev['runs'][label]
    require(run['exit_code'] == 0 and run['execution_status'] == 'PASS', 'Historical execution failed')
    require(run['run_id'] == case['historical']['references'][label]['run_id'], 'Wrong historical run')
    require(header['sha256'] == case['pseudo']['sha256'] and header['element'] == 'Mg'
            and header['z_valence'] == 10 and header['relativistic'] == 'full'
            and header['has_so'] is True and header['nlcc_present'] is False, 'Historical Mg header differs')
    require(header['functional'] == 'PBESOL' and header['xc_identifiers'] == case['xc']['dftk_identifiers'],
            'Historical XC differs')
    require(basis['lattice_bohr'] == case['geometry']['lattice_vectors_bohr']
            and basis['positions_fractional'] == case['geometry']['positions_fractional'], 'Historical geometry differs')
    require(basis['n_electrons'] == 10 and basis['ecut_ha'] == 15 and d['target_states'] == 24,
            'Historical electrons, cutoff or target count differs')
    diag = d['diagnostics']; occupation = diag['occupations']
    require(occupation['capacity_per_state'] == 1 and occupation['tau_ha'] == .001
            and occupation['smearing'] == 'FermiDirac', 'Historical occupation convention differs')
    require(len(d['eigenvalues_ha']) == len(d['occupations']) == len(basis['kpoints']) == 3,
            'Historical three-k arrays differ')
    points = [{**p, 'eigenvalues_ha':es, 'occupations':f} for p,es,f in
              zip(basis['kpoints'],d['eigenvalues_ha'],d['occupations'])]
    for p, q in zip(case['kpoints'], matched_points(case['kpoints'], points)):
        close(p['weight_spatial'], q['weight_spatial'], 1e-12, 'Historical weight')
    count = validate_spectrum(points)
    close(diag['real_electron_count'], 10, 1e-8, 'Historical recorded real electron count')
    close(diag['orbital_electron_count'], count, 1e-8, 'Historical orbital electron count')
    energy = energy_record(diag['internal_energy_ha'],diag['free_energy_ha'],diag['entropy_energy_ha'],
                           source='Historical endpoint diagnostics: seven-term E and capacity-one -TS once')
    require(set(diag['energy_terms_ha']) == {'Kinetic','AtomicLocal','AtomicNonlocalFR','Hartree','Xc','Ewald','PspCorrection'},
            'Historical seven-term definition differs')
    close(sum(diag['energy_terms_ha'].values()), energy['internal_ha'], 1e-10, 'Historical seven-term energy sum')
    return {'energy':energy, 'electrons':count, 'kpoints':points, 'mu_ha':d['mu_ha'],
            'energy_terms_ha':diag['energy_terms_ha'], 'source':record['source'],
            'map_count':d['map_count'], 'fft_grid':basis['fft_grid'],
            'precision': {'eigenvalue_source':diag['formal_occupation_source'],
                          'self_density_old_lambda_max_ha':diag['max_self_density_h_residual_ha'],
                          'self_density_rayleigh_max_ha':diag['max_self_rayleigh_residual_ha'],
                          'input_hamiltonian_target_residual_max_ha':max(max(r['explicit_residuals_ha']) for r in d['solver_records']),
                          'status':'HISTORICAL_RUNNER_REPORTED; private physical arrays not rechecked'}}


def validate_qe_model(case, qe):
    """Shared SCF/refinement input checks, without accepting refinement energies."""
    require(type(qe['schema_version']) is int and qe['schema_version'] == 1 and qe['code'] == 'QE',
            'Unsupported QE schema/code')
    for key in ('execution_status','input_comparability_status'):
        require(qe[key] == 'PASS', 'QE prerequisite did not pass: ' + key)
    require(qe['electrons'] == 10 and qe['n_bands'] == 24
            and type(qe['occupation_capacity']) is int and qe['occupation_capacity'] == 1,
            'QE must have ten electrons and 24 capacity-one spinors')
    require(qe['tau_ha'] == .001 and qe['smearing'] == 'Fermi-Dirac', 'QE tau/smearing differs')
    require(qe['pseudo_sha256'] == case['pseudo']['sha256'], 'QE pseudo hash differs')
    indices = qe['xc']['indices']
    require(qe['xc']['functional'] == 'PBESOL' and indices[:4] == [1,4,10,8]
            and all(v == 0 for v in indices[4:]), 'QE XC differs')
    for p, q in zip(case['kpoints'], matched_points(case['kpoints'],qe['kpoints'])):
        close(p['weight_spatial'], q['weight_spatial'], 1e-10, 'QE prescribed weight')
    return validate_spectrum(qe['kpoints'])


def compare(case, qe, a, b):
    """Pure numerical comparison; callers bind parsed QE to its recorded native bytes."""
    finite_tree([case,qe,a,b]); validate_case(case)
    require(qe['calculation'] == 'scf', 'SCF energy comparison cannot consume NSCF/bands results')
    qcount = validate_qe_model(case,qe)
    require(qe['energy_semantics_status'] == 'PASS', 'QE prerequisite did not pass: energy_semantics_status')
    require(qe['scf']['converged'] is True, 'QE SCF is not converged')
    e = qe['energy']
    finite_number(e['native_etot_ha'],'Native QE total energy')
    finite_number(e['native_demet_ha'],'Native QE entropy contribution')
    qenergy = energy_record(e['internal_ha'],e['free_ha'],e['entropy_ha'],source=e['sources'],
                            native_free=e['native_etot_ha'],native_entropy=e['native_demet_ha'])
    references = {label:historical_record(case,item,label) for label,item in [('A',a),('B',b)]}
    comparisons = {}
    for label, r in references.items():
        comparisons[label+'_minus_QE'] = {'role':'primary' if label == 'A' else 'auxiliary_reproducibility_reference',
            'energy':energy_difference(r['energy'],qenergy),
            'same_definition_energy_terms':comparable_energy_terms(r['energy_terms_ha'],e['native_components_ha']),
            'electrons':{'signed':r['electrons']-qcount,'absolute':abs(r['electrons']-qcount)},
            'spectrum':spectra(r['kpoints'],qe['kpoints']),
            'chemical_potential':{'historical_ha':r['mu_ha'],'qe_ha':qe['fermi_energy_ha'],
                'signed_difference_ha':r['mu_ha']-qe['fermi_energy_ha'],
                'status':'DIAGNOSTIC_ONLY; plateau chemical potentials need not agree'}}
    qa = matched_points(references['A']['kpoints'], qe['kpoints'])
    pw = [{'coordinate_fractional':p['coordinate_fractional'],'DFTK_spatial_npw':p['ng'],'QE_spatial_npw':q['npw']}
          for p,q in zip(references['A']['kpoints'],qa)]
    same_fft = references['A']['fft_grid'] == qe['fft_grid']
    same_pw = all(p['DFTK_spatial_npw'] == p['QE_spatial_npw'] for p in pw)
    result = {'schema_version':1,'case':case['case'],
        'comparison_execution_status':'PASS', 'qe_execution_status':qe['execution_status'],
        'input_comparability_status':'PASS', 'energy_semantics_status':'PASS',
        'numerical_agreement_status':'REVIEW_REQUIRED', 'physical_convergence_status':'NOT_ESTABLISHED',
        'noncollinear_magnetic_xc_status':'NOT_IMPLEMENTED',
        'upstream_native_support':'NOT_IMPLEMENTED_BY_THIS_WORKBENCH',
        'units':{'energy':'Ha/cell','display_energy':'eV/cell','hartree_ev':HARTREE_EV,'atoms_per_cell':1},
        'references':{label:{k:v for k,v in r.items() if k != 'kpoints'} for label,r in references.items()},
        'QE':{'energy':qenergy,'electrons':qcount,'fermi_energy_ha':qe['fermi_energy_ha'],
              'precision':qe.get('precision'), 'warnings':qe.get('warnings',[]),
              'entropy_diagnostic':qe.get('entropy_diagnostic')},
        'comparisons':comparisons,
        'spectral_symmetry':{**{label:spectral_symmetry(r['kpoints']) for label,r in references.items()},
                             'QE':spectral_symmetry(qe['kpoints'])},
        'numerical_settings_match':{'status':'MATCH_RECORDED' if same_fft and same_pw else 'INPUT_PASS_WITH_NUMERICAL_DIFFERENCES',
              'DFTK_fft_grid':references['A']['fft_grid'],'QE_fft_grid':qe['fft_grid'],
              'QE_fft_smooth_grid':qe.get('fft_smooth_grid'), 'spatial_plane_waves':pw,
              'scope':'FFT and spatial plane-wave counts only; quadrature and solver implementations are not asserted equal'},
        'mg_local_zero_diagnostic':{'psp_correction_ha':references['A']['energy_terms_ha']['PspCorrection'],
              'electrons':10,'correction_per_electron_ha':references['A']['energy_terms_ha']['PspCorrection']/10,
              'status':'NON_FITTED_DIAGNOSTIC_ONLY', 'qe_internal_g0':'NOT_DIRECTLY_EXTRACTED',
              'energy_or_spectrum_adjustment_applied':False,
              'interpretation':'Mg constant from the existing DFTK PspCorrection. No causal attribution of residual differences or use of a Si constant.'},
        'array_revalidation':{'DFTK_density_orbitals':'NOT_RUN; existing runner records only',
                              'cross_code_density_l2':'NOT_RUN'},
        'scientific_limitations':['Single Mg case, cutoff, k set and temperature; no physical convergence study',
             'Historical eigenpairs belong to H[n_in]; recorded H[n_out] residuals bound their interpretation',
             'A/B repeatability does not imply equal absolute accuracy',
             'No wavefunction/channel matching: no j-labelled or material SOC-splitting attribution',
             'Native QE energy terms are not forced into the historical seven-term decomposition']}
    finite_tree(result)
    return result


def compare_refinement(case, qe_scf, qe_refined, a, b):
    """Separate spectra only; the SCF result and E/F remain untouched.

    The run/evidence layer must independently bind copied scratch to the SCF;
    this arithmetic function checks the two parsed sets and retains their hashes.
    """
    scf_comparison = compare(case,qe_scf,a,b)
    finite_tree(qe_refined)
    require(qe_refined['calculation'] in ('bands','nscf'), 'Expected a separate bands/NSCF refinement')
    require(qe_refined['energy'] is None and qe_refined['energy_semantics_status'] == 'NOT_APPLICABLE_SPECTRUM_ONLY',
            'Refinement must not provide SCF internal/free energies')
    validate_qe_model(case,qe_refined)
    for key in ('occupations_source','chemical_potential_source'):
        require(isinstance(qe_refined[key],str) and bool(qe_refined[key]), 'Missing refinement '+key)
    if qe_refined['chemical_potential_source'] == 'INHERITED_FROM_SCF_NOT_RESOLVED':
        close(qe_refined['fermi_energy_ha'],qe_scf['fermi_energy_ha'],1e-10,'Inherited SCF chemical potential')
    refined = {}
    for label,record in [('A',a),('B',b)]:
        r = historical_record(case,record,label)
        refined[label+'_minus_QE'] = {'role':'primary' if label == 'A' else 'auxiliary_reproducibility_reference',
                                    'spectrum':spectra(r['kpoints'],qe_refined['kpoints'])}
    return {'schema_version':1,'case':case['case'],'comparison_execution_status':'PASS',
            'calculation':qe_refined['calculation'], 'energy_semantics_status':'NOT_APPLICABLE_SPECTRUM_ONLY',
            'numerical_agreement_status':'REVIEW_REQUIRED','physical_convergence_status':'NOT_ESTABLISHED',
            'comparisons':refined,
            'refined_minus_scf_spectrum':spectra(qe_refined['kpoints'],qe_scf['kpoints'],
                                                reference_name='QE_refinement',candidate_name='QE_SCF'),
            'energy_source':'Original SCF E/F/-TS only, retained in the separate SCF comparison; no refinement energies used',
            'scf_comparison_execution_status':scf_comparison['comparison_execution_status'],
            'native_sources':{'SCF':qe_scf.get('native_files_sha256'),
                              'refinement':qe_refined.get('native_files_sha256')},
            'refinement_precision':qe_refined.get('precision'), 'refinement_warnings':qe_refined.get('warnings',[]),
            'refinement_occupation_source':qe_refined['occupations_source'],
            'refinement_chemical_potential_source':qe_refined['chemical_potential_source'],
            'refinement_spectral_symmetry':spectral_symmetry(qe_refined['kpoints']),
            'scratch_density_binding':'Established by the separate run/evidence receipt, not eigenvalue arithmetic'}


def write_eigenvalues_csv(path, result):
    rows = []
    for label in ('A','B'):
        for row in result['comparisons'][label+'_minus_QE']['spectrum']['rows']:
            rows.append({'reference':label, **row,
                         'coordinate_fractional':json.dumps(row['coordinate_fractional'],separators=(',',':'))})
    with Path(path).open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--case',type=Path,default=Path('benchmarks/mg-soc-qe-v1/case.json'))
    parser.add_argument('--qe',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--csv',type=Path)
    args = parser.parse_args()
    try:
        case = read_json(args.root/args.case)
        a,b = load_historical(args.root,case)
        result = compare(case,read_json(args.qe),a,b)
        if args.csv: write_eigenvalues_csv(args.csv,result)
    except (ValueError,KeyError,TypeError,OSError) as exc:
        result = {'schema_version':1,'comparison_execution_status':'FAIL',
                  'numerical_agreement_status':'REVIEW_REQUIRED','reason':str(exc)}
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return 0 if result['comparison_execution_status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
