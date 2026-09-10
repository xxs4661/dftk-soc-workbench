#!/usr/bin/env python3
"""Public endpoint arithmetic, never a solver or a replacement for private n_out."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from si_soc_comparison import analyze_gamma, number
HISTORICAL_SCF = 'results/si-soc-splitting/D-SCF.json'
HISTORICAL_SPECTRUM = 'results/si-soc-splitting/D-spectrum.json'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def historical_path(root, relative):
    """Require the exact Git path even on a case-insensitive host volume."""
    require(relative in (HISTORICAL_SCF, HISTORICAL_SPECTRUM), 'Unregistered historical endpoint path')
    root = root.resolve()
    tracked = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '--', relative], text=True).split('\0')
    require(relative in tracked, 'Historical endpoint is not tracked with exact case: ' + relative)
    current = root
    for component in Path(relative).parts:
        require(component in {entry.name for entry in current.iterdir()}, 'Historical endpoint component case differs: ' + component)
        current /= component
        require(not current.is_symlink(), 'Aliased historical endpoint path')
    require(current.is_file(), 'Historical endpoint file is missing')
    return current


def evaluate(old_scf, new_scf, old_spectrum, new_spectrum, density, contract):
    require(new_scf['action']=='OPT-B0-SCF' and new_scf['backend']=='soc-core'
            and new_scf['execution_status']=='PASS' and type(new_scf['exit_code']) is int
            and new_scf['exit_code']==0 and new_scf['runtime_closed'] is True,
            'New successful owned SCF required')
    require(new_spectrum['execution_status']=='PASS' and type(new_spectrum['process_exit_code']) is int
            and new_spectrum['process_exit_code']==0, 'Gamma execution failed')
    require(new_spectrum['backend']=='soc-core' and new_spectrum['physical_operator']=='full_soc'
            and new_spectrum['source_scf_run_id']==new_scf['run_id']
            and new_spectrum['density_source_sha256']==new_scf['final']['n_out_sha256'],
            'Gamma must use this new SCF n_out')
    require(new_spectrum['n_bands']==24 and new_spectrum['n_electrons']==8
            and new_spectrum['occupation_capacity']==1 and len(new_spectrum['kpoints'])==1,
            'Only Gamma24/capacity1 allowed')
    point=new_spectrum['kpoints'][0]
    require(point['coordinate_fractional']==[0.,0.,0.], 'New probe is not Gamma')
    old=next(p for p in old_spectrum['kpoints'] if p['coordinate_fractional']==[0.,0.,0.])
    a,b=analyze_gamma(old['eigenvalues_ha']),analyze_gamma(point['eigenvalues_ha'])
    levels=[y-x for x,y in zip(a['values_ha'],b['values_ha'])]
    delta=b['delta_so_ev']-a['delta_so_ev']
    accuracy=contract['endpoint'];energies=[]
    olddiag,newdiag=old_scf['final']['diagnostics'],new_scf['final']['diagnostics']
    for key in ('internal_energy_ha','free_energy_ha','entropy_energy_ha'):
        x,y=number(olddiag[key]),number(newdiag[key]);difference=y-x
        energies.append(dict(field=key,reference=x,candidate=y,difference=difference,unit='Ha/cell',
             limit=accuracy['internal_and_free_energy_abs_ha'] if key!='entropy_energy_ha' else None,
             status=('PASS' if abs(difference)<=accuracy['internal_and_free_energy_abs_ha'] else 'FAIL')
                      if key!='entropy_energy_ha' else 'DIAGNOSTIC_ONLY'))
    oldterms,newterms=olddiag['energy_terms_ha'],newdiag['energy_terms_ha']
    require(set(oldterms)==set(newterms) and len(oldterms)==7, 'Seven uncorrected energy terms required')
    terms=[dict(term=k,reference=number(oldterms[k]),candidate=number(newterms[k]),
                difference=number(newterms[k])-number(oldterms[k]),unit='Ha/cell') for k in sorted(oldterms)]
    fd=point['occupations']
    require(isinstance(fd,list) and len(fd)==24 and all(0<=number(f)<=1 for f in fd),'Invalid actual Gamma occupation diagnostics')
    occupied=min(fd[2:8])>=.99999999
    structure=(b['manifold_assignment_status']=='PASS' and b['multiplet_structure_status']=='PASS')
    require(density['sources']['new_scf_run_id']==new_scf['run_id']
            and density['n_out']['candidate_sha256']==new_scf['final']['n_out_sha256'], 'Unbound density comparison')
    g=dict(reference_delta_so_ev=a['delta_so_ev'],candidate_delta_so_ev=b['delta_so_ev'],
           difference_ev=delta,limit_ev=accuracy['Gamma_fixed_window_delta_abs_ev'],
           raw_differences_ha=levels,raw_max_abs_ha=max(map(abs,levels)),raw_limit_ha=accuracy['Gamma_raw_max_abs_ha'],
           raw_RMS_ha=math.sqrt(sum(x*x for x in levels)/24),metrics=b,
           status='PASS' if abs(delta)<=accuracy['Gamma_fixed_window_delta_abs_ev']
             and max(map(abs,levels))<=accuracy['Gamma_raw_max_abs_ha'] and structure else 'FAIL')
    passed=all(e['status'] in ('PASS','DIAGNOSTIC_ONLY') for e in energies) and g['status']=='PASS' and density['overall_status']=='PASS'
    result=dict(schema_version=1,phase='9A',execution_commit=new_scf['execution_commit'],
        overall_status='PASS' if passed else 'FAIL',exit_code=0 if passed else 9,
        energy=energies,energy_terms=terms,gamma=g,n_out=density['n_out'],
        historical=dict(status='HISTORICAL_REUSED',scf_run_id=old_scf['run_id'],spectrum_run_id=old_spectrum['run_id']),
        current=dict(scf_run_id=new_scf['run_id'],spectrum_run_id=new_spectrum['run_id'],map_count=new_scf['final']['map_count']),
        gamma_occupation_diagnostic=dict(minimum=min(fd[2:8]),minimum_inclusive=.99999999,
            status='PASS' if occupied else 'REVIEW_REQUIRED',source='Actual own-parent-mu Gamma diagnostics; no occupation solve'),
        fixed_window_structure_status='PASS' if structure else 'REVIEW_REQUIRED',
        manifold_assignment_status='MANIFOLD_ASSIGNMENT_REVIEW_REQUIRED',
        manifold_scope='No new null or QE pair, irreps or continuous-band tracking; historical reviews untouched',
        physical_interpretation='REVIEW_REQUIRED',physical_convergence='NOT_ESTABLISHED',
        new_QE='NOT_RUN',new_DFTK_K6_K8='NOT_RUN',
        evidence_scope='Public energy/spectrum arithmetic; density-array difference RUNNER_REPORTED')
    json.dumps(result,allow_nan=False)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--scf',type=Path,required=True);parser.add_argument('--gamma',type=Path,required=True)
    parser.add_argument('--density',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();read=lambda p:json.loads(p.read_text())
    require(not args.output.exists(),'Refusing existing endpoint arithmetic record')
    result=evaluate(read(historical_path(args.root,HISTORICAL_SCF)),read(args.scf),
        read(historical_path(args.root,HISTORICAL_SPECTRUM)),read(args.gamma),read(args.density),
        read(args.root/'benchmarks/soc-core-memory-v1/contract.json'))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(overall_status=result['overall_status'],exit_code=result['exit_code'])))
    return result['exit_code']
if __name__=='__main__':sys.exit(main())
