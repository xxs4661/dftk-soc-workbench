#!/usr/bin/env python3
"""Finite local-potential reference diagnostics, independent of DFTK/QE kernels.

The r-space rule integrates Newton polynomials over the supplied nonuniform
nodes; it never consumes PP_RAB. The separate index-space Simpson rule consumes
one Jacobian PP_RAB. Neither rule truncates the primary full-grid integral,
rescales an input to match a reference, or computes a divergent Coulomb G=0.
Only bounded source parsing and standard arithmetic are provided here.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NORMALIZATION_ABS = 1e-11
SAME_SOURCE_PC_ABS_HA = 1e-10
QE_TAGGED_CUTOFF_BOHR = 10.0
MAX_RADIAL_POINTS = 1_000_000


def _number(x, label):
    if isinstance(x, bool):
        raise ValueError(label + " must be finite numeric data")
    try:
        y = float(x)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(label + " must be finite numeric data") from exc
    if not math.isfinite(y):
        raise ValueError(label + " is nonfinite")
    return y


def _arrays(r, values):
    if not 3 <= len(r) <= MAX_RADIAL_POINTS or len(r) != len(values):
        raise ValueError("Radial arrays require equal bounded length >=3")
    x = [_number(v, "radius") for v in r]
    y = [_number(v, "integrand") for v in values]
    if x[0] < 0 or any(b <= a for a, b in zip(x, x[1:])):
        raise ValueError("Radii must be nonnegative and strictly increasing")
    return x, y


def _quadratic_panel(x0, x1, x2, y0, y1, y2, lower, upper):
    """Integrate the unique Newton interpolating polynomial on a subinterval."""
    h = x1-x0
    slope = (y1-y0)/h
    curvature = ((y2-y1)/(x2-x1)-slope)/(x2-x0)
    a = lower-x0; b = upper-x0
    return math.fsum([y0*(b-a), slope*(b*b-a*a)/2,
                      curvature*((b*b*b-a*a*a)/3-h*(b*b-a*a)/2)])


def integrate_nonuniform_quadratic(r, values):
    x, y = _arrays(r, values)
    panels = []
    last_complete = len(x)-1 if len(x) % 2 else len(x)-2
    for i in range(0, last_complete, 2):
        panels.append(_quadratic_panel(*x[i:i+3], *y[i:i+3], x[i], x[i+2]))
    if len(x) % 2 == 0:
        # Predeclared unmatched final interval: one trapezoid, no duplicate panel.
        panels.append((x[-1]-x[-2])*(y[-1]+y[-2])/2)
    result = math.fsum(panels)
    if not math.isfinite(result):
        raise ValueError("Nonfinite radial integral")
    return result


def integrate_trapezoid(r, values):
    x, y = _arrays(r, values)
    result = math.fsum((x[i+1]-x[i])*(y[i]+y[i+1])/2 for i in range(len(x)-1))
    if not math.isfinite(result):
        raise ValueError("Nonfinite radial trapezoid integral")
    return result


def integrate_index_simpson(values, rab):
    """Standard odd-node Simpson rule in unit-spaced index coordinates.

    rab is dr/di, including the index step. Multiply it exactly once. This
    helper is not a general QE integration implementation and accepts no even
    node endpoint policy: the separately certified tagged msh must be odd.
    """
    if len(values) != len(rab) or len(values) < 3 or len(values) % 2 == 0:
        raise ValueError("Jacobian Simpson requires an odd number of >=3 nodes")
    y = [_number(v, "integrand") for v in values]
    jac = [_number(v, "PP_RAB") for v in rab]
    if any(v <= 0 for v in jac):
        raise ValueError("PP_RAB must be positive")
    terms = []
    for i, (v, j) in enumerate(zip(y, jac)):
        weight = 1 if i in (0, len(y)-1) else (4 if i % 2 else 2)
        terms.append(weight*v*j/3)
    result = math.fsum(terms)
    if not math.isfinite(result):
        raise ValueError("Nonfinite Jacobian Simpson result")
    return result


def finite_integrand(r, local_ry, z_valence):
    x, potential = _arrays(r, local_ry)
    z = _number(z_valence, "valence charge")
    if z <= 0:
        raise ValueError("Valence charge must be positive")
    # Potential energy Ry -> Ha once. No RAB, rcut, beta or screened erf here.
    local_ha = [v/2 for v in potential]
    values = [ri*ri*vi+z*ri for ri, vi in zip(x, local_ha)]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Nonfinite finite-part integrand")
    return x, local_ha, values


def reference_factors(alpha_ha_bohr3, n_atoms, volume_bohr3, n_electrons, z_valence):
    alpha = _number(alpha_ha_bohr3, "alpha")
    volume = _number(volume_bohr3, "volume")
    ne = _number(n_electrons, "electron count")
    z = _number(z_valence, "valence charge")
    if type(n_atoms) is not int or n_atoms < 1 or volume <= 0 or ne <= 0 or z <= 0:
        raise ValueError("Invalid atom count, volume, electron count or valence charge")
    if abs(ne-n_atoms*z) > 1e-8:
        raise ValueError("Pc=N_e*C interpretation is restricted to this neutral model")
    c = n_atoms*alpha/volume
    return {"alpha_ha_bohr3_per_atom": alpha, "C_ha": c, "Pc_neutral_candidate_ha": ne*c,
            "n_atoms": n_atoms, "volume_bohr3": volume, "n_electrons": ne,
            "n_electrons_from_atoms": n_atoms*z,
            "scope": "Finite local/background bookkeeping only, not an E/F correction"}


def qe_tagged_range(r, rab, *, ordinary_periodic):
    """Certify the metadata rule, never infer an endpoint from energy agreement.

    Only the demonstrably affine grid/Jacobian case is supported here. Other
    UPF grid families can be physically valid but lack this audit's proof.
    """
    if ordinary_periodic is not True:
        return {"status": "NOT_ESTABLISHED", "reason": "Ordinary periodic, unmodified Coulomb context has not been certified"}
    x, jac = _arrays(r, rab)
    step = (x[-1]-x[0])/(len(x)-1)
    affine_error = max(abs(ri-(x[0]+i*step)) for i, ri in enumerate(x))
    jac_error = max(abs(j-step) for j in jac)
    if abs(x[0]) > 1e-12 or affine_error > 1e-12 or jac_error > 1e-12:
        return {"status": "NOT_ESTABLISHED", "reason": "Actual r/PP_RAB do not establish the supported affine index Jacobian; no other grid family is guessed",
                "affine_grid_max_abs_bohr": affine_error, "rab_minus_step_max_abs_bohr": jac_error}
    # Metadata selection: first node beyond tagged 10 bohr bound, then the
    # largest odd node count no larger than that selected one-based index.
    first_beyond = next((i+1 for i, ri in enumerate(x) if ri > QE_TAGGED_CUTOFF_BOHR), None)
    selected = len(x) if first_beyond is None else first_beyond
    msh = selected if selected % 2 else selected-1
    if msh < 3:
        return {"status": "NOT_ESTABLISHED", "reason": "Tagged radial range has fewer than three points"}
    return {"status": "ESTABLISHED_TO_QE_7_5_TAGGED_CONVENTION", "msh_points": msh,
            "source_point_count": len(x), "first_index_beyond_10_bohr": first_beyond,
            "first_radius_beyond_10_bohr": None if first_beyond is None else x[first_beyond-1],
            "integration_lower_bohr": x[0], "integration_upper_bohr": x[msh-1],
            "affine_step_bohr": step, "affine_grid_max_abs_bohr": affine_error,
            "rab_minus_step_max_abs_bohr": jac_error,
            "endpoint_rule": "First r>10 node index, capped to odd count; standard closed Simpson endpoints 1/3",
            "jacobian_rule": "Actual PP_RAB=dr/di, once; no extra dr",
            "source_scope": "qe-7.5 tag prediction; actual installed source commit/table not extracted"}


def gauge_bookkeeping(local_ha, pc_ha, n_electrons, shift_ha):
    local, pc, ne, shift = (_number(x, label) for x, label in zip(
        [local_ha, pc_ha, n_electrons, shift_ha], ["local energy", "Pc", "Ne", "gauge shift"]))
    if ne <= 0:
        raise ValueError("Electron count must be positive")
    new_local = local+ne*shift; new_pc = pc-ne*shift
    return {"local_after_ha": new_local, "pc_after_ha": new_pc,
            "combined_before_ha": local+pc, "combined_after_ha": new_local+new_pc,
            "difference_ha": (new_local+new_pc)-(local+pc),
            "scope": "Synthetic gauge identity only; never changes a saved physical result"}


def analyze_local_reference(r, local_ry, rab, z_valence, *, n_atoms, volume_bohr3,
                            n_electrons, dftk_constants=None, ordinary_periodic=None):
    x, local_ha, values = finite_integrand(r, local_ry, z_valence)
    if len(rab) != len(x) or any(_number(v, "PP_RAB") <= 0 for v in rab):
        raise ValueError("PP_RAB length/positivity mismatch")
    alpha_q = 4*math.pi*integrate_nonuniform_quadratic(x, values)
    alpha_t = 4*math.pi*integrate_trapezoid(x, values)
    primary = reference_factors(alpha_q, n_atoms, volume_bohr3, n_electrons, z_valence)
    secondary = reference_factors(alpha_t, n_atoms, volume_bohr3, n_electrons, z_valence)
    proof = qe_tagged_range(x, rab, ordinary_periodic=ordinary_periodic)
    qe = {"range_proof": proof, "status": "NOT_ESTABLISHED"}
    if proof['status'] == "ESTABLISHED_TO_QE_7_5_TAGGED_CONVENTION":
        n = proof['msh_points']
        predicted = 4*math.pi*integrate_index_simpson(values[:n], rab[:n])
        qe.update(reference_factors(predicted, n_atoms, volume_bohr3, n_electrons, z_valence))
        qe['status'] = "PREDICTED_QE_7_5_TAGGED_CONVENTION"
        qe['finite_G0_definition'] = "Unscreened finite alpha/Omega: QE tab_vloc(0); convert internal Ry to Ha once"
        qe['actual_QE_table_status'] = "NOT_EXTRACTED"
    dftk = {"status": "NOT_AVAILABLE"}
    if dftk_constants is not None:
        required = ['psp_correction_ha', 'n_electrons_from_atoms_actual', 'model_ne', 'volume_bohr3', 'natoms',
                    'alpha_from_common_native', 'psp_local_fourier_G0']
        if not isinstance(dftk_constants, dict) or any(k not in dftk_constants for k in required):
            raise ValueError("Incomplete native DFTK constants receipt")
        actual = {key: _number(dftk_constants[key], key) for key in required}
        if actual['natoms'] != n_atoms or actual['n_electrons_from_atoms_actual'] != n_atoms*z_valence or abs(actual['model_ne']-n_electrons)>1e-8 or abs(actual['volume_bohr3']-volume_bohr3)>1e-12:
            raise ValueError("DFTK native constant receipt belongs to a different model")
        native_pred = reference_factors(actual['alpha_from_common_native'],n_atoms,volume_bohr3,n_electrons,z_valence)
        native_identity = actual['psp_correction_ha']-native_pred['Pc_neutral_candidate_ha']
        independent_pc = primary['Pc_neutral_candidate_ha']-actual['psp_correction_ha']
        dftk = {"status": "PASS" if abs(native_identity)<=SAME_SOURCE_PC_ABS_HA and abs(actual['psp_local_fourier_G0'])<=NORMALIZATION_ABS else "FAIL",
                "native_constants": actual, "native_C_ha": native_pred['C_ha'],
                "native_Pc_minus_Ne_C_ha": native_identity,
                "independent_primary_minus_native_alpha_ha_bohr3": alpha_q-actual['alpha_from_common_native'],
                "independent_primary_minus_native_Pc_ha": independent_pc,
                "independent_quadrature_scope": "Difference measured, no dependency or quadrature tuned to force agreement"}
        if qe['status'] == "PREDICTED_QE_7_5_TAGGED_CONVENTION":
            dftk['Ne_times_C_D_minus_C_Q_tagged_ha'] = n_electrons*(native_pred['C_ha']-qe['C_ha'])
            dftk['candidate_scope'] = "Signed bookkeeping scale from independent known conventions, not a cause or correction to historical E/F"
    return {"schema_version":1, "g0_integral_diagnostic_status":"MEASURED",
            "derivation_status":"NEW_POSTPROCESSING_OF_HISTORICAL_STATES",
            "input_convention":{"PP_LOCAL":"Ry potential energy, divided by two once", "PP_R":"bohr", "PP_RAB":"dr/di in bohr per unit index; unused by r-space rules", "finite_integrand":"r^2 Vlocal_Ha + Z*r", "z_valence":z_valence},
            "primary_full_native_grid": {**primary, "method":"Piecewise quadratic Newton interpolation on actual r, with final unmatched interval trapezoid when needed", "point_count":len(x), "integration_lower_bohr":x[0], "integration_upper_bohr":x[-1], "rab_used":False},
            "trapezoid_full_native_grid": {**secondary, "method":"Composite trapezoid on actual r, all native nodes", "rab_used":False},
            "quadrature_sensitivity":{"alpha_primary_minus_trapezoid_ha_bohr3":alpha_q-alpha_t, "Pc_primary_minus_trapezoid_ha":primary['Pc_neutral_candidate_ha']-secondary['Pc_neutral_candidate_ha'], "scope":"Fixed-method sensitivity, not a strict error bound; no cutoff scan or resampling"},
            "radial_tail":{"first_integrand":values[0], "last_integrand":values[-1], "last_10_nodes_max_abs_integrand":max(abs(v) for v in values[-10:]), "full_grid_rmax_bohr":x[-1], "lower_endpoint_status":"INCLUDES_ZERO" if x[0]==0 else "UNSAMPLED_INNER_INTERVAL_NOT_ADDED", "outside_grid_status":"NOT_INTEGRATED; finite-part interpretation assumes Coulomb tail beyond supplied range; no analytic tail patch or fitted constant"},
            "qe_tagged_prediction":qe, "dftk_bookkeeping":dftk,
            "screened_short_range_q0":{"status":"NOT_COMPUTED_NOT_THE_FINITE_G0_OBJECT", "integrand_Ha":"r^2 Vlocal_Ha + Z*r*erf(r)", "distinction":"For the infinite-domain unit-erf convention, unscreened alpha minus screened q->0 numerator is pi*Z; their tabulated zero entries are not interchangeable"},
            "qe_native_local_potential_status":"NOT_EXTRACTED", "applied_energy_correction":False,
            "public_replay_scope":"Arithmetic on saved summaries only unless the separately obtained hash-bound UPF is supplied; raw radial arrays are not redistributed"}


def read_bound_local_upf(path, expected_sha256):
    path = Path(path)
    if path.stat().st_size > 32_000_000:
        raise ValueError("UPF exceeds bounded local-reader size")
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected_sha256:
        raise ValueError("UPF source SHA-256 mismatch before parsing")
    root = ET.fromstring(payload)
    if root.tag != 'UPF' or root.attrib.get('version') != '2.0.1':
        raise ValueError("Unsupported UPF version")
    header = root.find('PP_HEADER'); mesh = root.find('PP_MESH')
    if header is None or mesh is None:
        raise ValueError("Missing UPF header or radial mesh")
    count = int(header.attrib['mesh_size'])
    if not 3 <= count <= MAX_RADIAL_POINTS:
        raise ValueError("Invalid UPF mesh size")
    def field(parent, tag):
        matches = parent.findall(tag)
        if len(matches) != 1 or not matches[0].text:
            raise ValueError("Missing/duplicate radial field " + tag)
        element = matches[0]
        if int(element.attrib['size']) != count:
            raise ValueError("Radial field declared size mismatch")
        values = [_number(t.replace('D','E').replace('d','e'),tag) for t in element.text.split()]
        if len(values) != count:
            raise ValueError("Radial field data size mismatch")
        return values
    r=field(mesh,'PP_R');rab=field(mesh,'PP_RAB');local=field(root,'PP_LOCAL')
    _arrays(r,local)
    if any(v<=0 for v in rab):raise ValueError("Nonpositive PP_RAB")
    return {"r":r,"rab":rab,"local_ry":local,"z_valence":_number(header.attrib['z_valence'],'Z'),
            "header":dict(header.attrib),"mesh_attributes":dict(mesh.attrib),
            "source_sha256":actual,"source_bytes":len(payload),"filename":path.name}


def audit_bound_upf(path, expected_sha256, *, n_atoms, volume_bohr3, n_electrons,
                    dftk_constants=None, ordinary_periodic=None):
    data=read_bound_local_upf(path,expected_sha256)
    result=analyze_local_reference(data['r'],data['local_ry'],data['rab'],data['z_valence'],
        n_atoms=n_atoms,volume_bohr3=volume_bohr3,n_electrons=n_electrons,
        dftk_constants=dftk_constants,ordinary_periodic=ordinary_periodic)
    result['source']={key:data[key] for key in ['source_sha256','source_bytes','filename','header','mesh_attributes']}
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected_sha256:
        raise ValueError("UPF source changed during read-only finite integral")
    result['source_binding_status']='PASS'
    result['source_bytes_unchanged']=True
    return result


def qe_periodic_context(qe_input, qe_xml):
    """Bounded proof for the saved G40 input, not a general namelist parser.

    The supported input omits both isolation settings. Their qe-7.5 defaults
    are documented in read_namelists.f90:282,308. Explicit settings, including
    potentially valid other cases, are not silently interpreted here.
    """
    result = {'status':'NOT_ESTABLISHED', 'ordinary_periodic':False,
              'source_scope':'Saved input plus qe-7.5 defaults; not an extracted runtime Coulomb flag',
              'defaults_source':'https://github.com/QEF/q-e/blob/qe-7.5/Modules/read_namelists.f90#L281-L308',
              'caller_source':'https://github.com/QEF/q-e/blob/qe-7.5/PW/src/init_vloc.f90#L41-L70'}
    active = '\n'.join(line.split('!',1)[0] for line in qe_input.splitlines()).lower()
    if len(re.findall(r'&system\b',active)) != 1:
        return dict(result,reason='Expected one saved SYSTEM namelist')
    if re.search(r'\b(?:assume_isolated|esm_bc)\b',active):
        return dict(result,reason='Explicit isolation settings require a separate proof; not guessed')
    xml = ET.fromstring(qe_xml)
    creator=xml.find('./general_info/creator')
    if creator is None or creator.attrib.get('VERSION') != '7.5':
        return dict(result,reason='Saved XML does not identify QE 7.5')
    if xml.find('./input') is None or xml.find('.//boundary_conditions') is not None:
        return dict(result,reason='Missing saved input or explicit XML boundary conditions')
    return dict(result,status='ESTABLISHED_TO_QE_7_5_TAGGED_CONVENTION',ordinary_periodic=True,
                assume_isolated='none (tagged default; absent from saved input)',
                esm_bc='pbc (tagged default; absent from saved input)',
                limitation='Installed QE exact source commit is unknown; this certifies only the tagged prediction context')


def build_local_g0_audit(root, common_summary):
    """Run the single predeclared radial comparison after source receipt checks.

    Called once by the Phase 7D recorder after its fixed-density worker. It
    needs Python 3.11+ for stdlib TOML, never loads a scientific package, and
    publishes no files itself. Missing sources or malformed receipts raise.
    """
    import tomllib
    root=Path(root).resolve()
    plan_path='benchmarks/mg-soc-energy-reference-v1/plan.json'
    plan_bytes=(root/plan_path).read_bytes()
    plan=json.loads(plan_bytes)
    plan_sha=hashlib.sha256(plan_bytes).hexdigest()
    if type(plan.get('schema_version')) is not int or plan['schema_version']!=1 or plan.get('case')!='mg-soc-energy-reference-v1':
        raise ValueError('Unsupported radial audit plan')
    if (not isinstance(common_summary,dict) or type(common_summary.get('schema_version')) is not int
            or common_summary['schema_version']!=1 or common_summary.get('execution_status')!='PASS'
            or type(common_summary.get('exit_code')) is not int or common_summary['exit_code']!=0
            or common_summary.get('plan_sha256')!=plan_sha
            or not isinstance(common_summary.get('run_id'),str) or not common_summary['run_id']):
        raise ValueError('Native common receipt did not pass under the current plan')
    def bound_bytes(relative):
        path=Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Only repository-relative bound sources are supported')
        payload=(root/path).read_bytes()
        if (hashlib.sha256(payload).hexdigest()!=plan['source_sha256'][relative]
                or len(payload)!=plan['source_bytes'][relative]):
            raise ValueError('Plan-bound source changed: '+relative)
        return payload
    lock=tomllib.loads(bound_bytes('config/sources.lock').decode())['pseudopotentials']
    if (plan['pseudo_sha256']!=lock['file_sha256'] or plan['pseudo_path']!=lock['local_path']
            or lock['element']!='Mg'):
        raise ValueError('Plan and source lock disagree on Mg UPF')
    pseudo_path=Path(plan['pseudo_path'])
    if pseudo_path.is_absolute() or '..' in pseudo_path.parts:
        raise ValueError('Only the source-locked relative UPF path is supported')
    physical=plan['physical']; constants=common_summary.get('constants')
    if (not isinstance(constants,dict) or constants.get('source_sha256')!=plan['pseudo_sha256']
            or constants.get('nlcc') is not False or physical['nlcc'] is not False):
        raise ValueError('Native constant receipt has a different source/NLCC identity')
    for key in ('psp_correction_ha','alpha_from_common_native','psp_local_fourier_G0'):
        _number(constants[key],key)
    for key, expected in [('volume_bohr3',physical['volume_bohr3']),('natoms',physical['atoms']),
                          ('model_ne',physical['expected_electrons']),
                          ('n_electrons_from_atoms_actual',physical['expected_electrons'])]:
        if _number(constants[key],key)!=_number(expected,'physical '+key):
            raise ValueError('Native constant receipt belongs to a different physical model: '+key)
    input_path='benchmarks/mg-soc-qe-diagnostics-v1/G40.in'
    xml_path='results/mg-soc-qe-diagnostics/G40/qe.xml'
    context=qe_periodic_context(bound_bytes(input_path).decode(),bound_bytes(xml_path))
    context['input_source']={'path':input_path,'sha256':plan['source_sha256'][input_path]}
    context['xml_source']={'path':xml_path,'sha256':plan['source_sha256'][xml_path]}
    result=audit_bound_upf(root/pseudo_path,plan['pseudo_sha256'],
        n_atoms=physical['atoms'],volume_bohr3=physical['volume_bohr3'],
        n_electrons=physical['expected_electrons'],dftk_constants=constants,
        ordinary_periodic=context['ordinary_periodic'])
    result['qe_tagged_prediction']['periodic_context_proof']=context
    result.update(run_id=common_summary['run_id'],plan_sha256=plan_sha,
        native_constants_receipt_ref='common-terms.json#/constants')
    # Returned scalar data must serialize without NaN/Inf before the recorder
    # persists them. No PASS is decided here on behalf of the parent recorder.
    json.dumps(result,allow_nan=False)
    return result
