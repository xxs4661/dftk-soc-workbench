#!/usr/bin/env python3
"""Run one fresh, sequential QE/DFTK Si pair; never reuse another run's SCF files."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

from compare_scalar_baseline import compare, finite_tree, lattice_columns, requested_kpoint_count, save_comparison, validate_case, volume
from parse_qe_baseline import parse_qe

ROOT = Path(__file__).resolve().parent.parent


class PrerequisiteError(ValueError):
    pass


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    text = json.dumps(data, indent=2, allow_nan=False) + '\n'
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text)
    temporary.replace(path)


def check_pseudo(path, case):
    if not path.is_file():
        raise PrerequisiteError('Missing Si UPF; follow the case README retrieval instructions')
    if sha256(path) != case['pseudo']['sha256']:
        raise ValueError('Si UPF checksum mismatch')
    tree = ET.parse(path).getroot()
    header = tree.find('PP_HEADER')
    if header is None:
        raise ValueError('Missing UPF header')
    h = header.attrib
    if h['element'].strip() != 'Si' or h['pseudo_type'] != 'NC' or h['relativistic'] != 'scalar' or h['has_so'].lower() not in ('f','false') or float(h['z_valence']) != 4:
        raise ValueError('UPF is outside the Si scalar NC four-electron case')
    nlcc = h['core_correction'].lower() in ('t','true')
    if nlcc != case['pseudo']['nlcc'] or (nlcc and tree.find('PP_NLCC') is None):
        raise ValueError('UPF NLCC mismatch')
    if h['functional'].split() != case['xc']['upf_functional'].split():
        raise ValueError('UPF XC declaration mismatch')
    return {'sha256':sha256(path),'upf_version':tree.attrib['version'],'header':dict(h),'nlcc':nlcc}


def make_inputs(case_path, directory):
    case = json.loads(case_path.read_text())
    finite_tree(case)
    validate_case(case)
    config_hash = sha256(case_path)
    (directory/'case.json').write_bytes(case_path.read_bytes())
    generated = dict(case, source_case_sha256=config_hash,
                     lattice_matrix_bohr=lattice_columns(case['geometry']['lattice_vectors_bohr']))
    write_json(directory/'dftk-input.json', generated)
    g, e, c, q, s = (case[name] for name in ('geometry','electrons','cutoffs','qe','scf'))
    if c['qe_ecutwfc_ry'] != 2*c['dftk_ecut_ha'] or e['temperature_ha'] != 0 or e['occupations'] != 'fixed':
        raise ValueError('Inconsistent cutoff or occupation configuration')
    if not (q['ibrav']==0 and q['nspin']==1 and not q['noncolin'] and not q['lspinorb'] and q['nosym'] and q['noinv'] and q['diago_full_acc'] and not case['dftk']['symmetries']):
        raise ValueError('Unsupported scalar/symmetry/diagonalization configuration')
    requested_kpoint_count(case)
    boolean = lambda value: '.true.' if value else '.false.'
    lines = ["&CONTROL", " calculation='scf', prefix='si', restart_mode='from_scratch',",
             " pseudo_dir='../pseudo', outdir='./scratch', verbosity='high',", "/", "&SYSTEM",
             f" ibrav={q['ibrav']}, nat={len(g['species'])}, ntyp=1, nbnd={e['n_bands']},",
             f" ecutwfc={c['qe_ecutwfc_ry']:.16g}, ecutrho={c['qe_ecutrho_ry']:.16g},",
             f" nspin={q['nspin']}, noncolin={boolean(q['noncolin'])}, lspinorb={boolean(q['lspinorb'])},",
             f" nosym={boolean(q['nosym'])}, noinv={boolean(q['noinv'])}, occupations='{e['occupations']}',",
             "/", "&ELECTRONS", f" conv_thr={s['qe_conv_thr_ry']:.16g}, electron_maxstep={s['maxiter']},",
             f" diago_full_acc={boolean(q['diago_full_acc'])},", "/", "ATOMIC_SPECIES",
             ' Si 28.0855 '+case['pseudo']['filename'], 'CELL_PARAMETERS bohr']
    lines += [' '.join(f'{x:.16g}' for x in row) for row in g['lattice_vectors_bohr']]
    lines += ['ATOMIC_POSITIONS crystal']
    lines += [name+' '+' '.join(f'{x:.16g}' for x in row) for name,row in zip(g['species'],g['positions_fractional'])]
    lines += ['K_POINTS crystal', str(len(case['kpoints']))]
    lines += [' '.join(f'{x:.16g}' for x in [*p['coordinate_fractional'],p['weight_spatial']]) for p in case['kpoints']]
    (directory/'qe.in').write_text('\n'.join(lines)+'\n')
    return case, {'case_sha256':config_hash,'dftk_input_sha256':sha256(directory/'dftk-input.json'),
                  'qe_input_sha256':sha256(directory/'qe.in'),'volume_bohr3':volume(g['lattice_vectors_bohr'])}


def run_command(command, directory, label, env):
    with (directory/(label+'.stdout')).open('w') as out, (directory/(label+'.stderr')).open('w') as err:
        process = subprocess.run(command,cwd=directory,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
    return {'command':list(map(str,command)),'cwd':str(directory),'exit_code':process.returncode,
            'stdout':label+'.stdout','stderr':label+'.stderr'}


def qe_identity(launcher, directory, env):
    """Recognize native executables or the existing simple qe-jll launcher only."""
    selected = Path(launcher).absolute()
    if not selected.is_file():
        raise PrerequisiteError('pw.x is unavailable')
    identity = {'selected_path':str(selected),'resolved_launcher':str(selected.resolve()),
                'launcher_sha256':sha256(selected),'source_commit':None,
                'source_commit_note':'Not confirmed; record actual startup version and binary hash'}
    if selected.read_bytes()[:2] != b'#!':
        binary = selected.resolve()
        identity['installation_source']='Existing native executable; build provenance not independently known'
    else:
        content = selected.read_text()
        match = re.fullmatch(r'#!/bin/sh\s+exec (\S+) --startup-file=no (\S+/qe-runner\.jl) "\$\(basename "\$0"\)" "\$@"\s*',content)
        if not match:
            raise PrerequisiteError('Unrecognized pw.x launcher; provide a native executable or the supported qe-jll launcher')
        julia, runner = match.groups()
        runner_text = Path(runner).read_text()
        if 'using QuantumEspresso_jll' not in runner_text or not re.search(r'"pw.x"\s*=>\s*:pwscf',runner_text):
            raise PrerequisiteError('qe-jll runner does not identify pwscf')
        # Query the same Julia installation and inherited environment as the launcher.
        code = ('using QuantumEspresso_jll, SHA, TOML; '
                'println("jll_version=",pkgversion(QuantumEspresso_jll)); '
                'println("jll_uuid=",Base.PkgId(QuantumEspresso_jll).uuid); '
                'println("jll_source=",pathof(QuantumEspresso_jll)); '
                'println("active_project=",Base.active_project()); '
                'QuantumEspresso_jll.pwscf() do executable; '
                'println("binary=",realpath(executable)); end; '
                'p=joinpath(dirname(dirname(pathof(QuantumEspresso_jll))),"Artifacts.toml"); '
                'println("artifacts_file=",p)')
        probe = run_command([julia,'--startup-file=no','-e',code],directory,'qe-jll-probe',env)
        if probe['exit_code'] != 0:
            raise PrerequisiteError('Existing qe-jll installation could not be queried; see probe logs')
        values = dict(line.split('=',1) for line in (directory/'qe-jll-probe.stdout').read_text().splitlines() if '=' in line)
        binary = Path(values['binary'])
        identity.update(values,runner_path=runner,runner_sha256=sha256(runner),probe=probe,
                        installation_source='Existing QuantumEspresso_jll installation (not installed or upgraded by this run)')
    identity.update(binary_path=str(binary.resolve()),binary_sha256=sha256(binary))
    return identity


def new_run_directory(parent):
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]
    directory = parent/run_id
    directory.mkdir(parents=True,exist_ok=False)
    return directory


def check_reference_environment(environment, qe, reference):
    """Do not mix a changed executable/environment into the Phase 4C sequence."""
    for key in ('julia_version', 'manifest_sha256', 'project_sha256', 'source_lock_sha256'):
        if environment[key] != reference['environment'][key]:
            raise PrerequisiteError('Reference workbench identity mismatch: ' + key)
    for name in ('dftk', 'pseudopotentialio'):
        for key in ('uuid', 'version', 'commit', 'worktree_status'):
            if environment['packages'][name][key] != reference['environment']['packages'][name][key]:
                raise PrerequisiteError('Reference loaded package mismatch: ' + name + '.' + key)
    for key in ('binary_sha256', 'launcher_sha256', 'runner_sha256', 'jll_version', 'jll_uuid'):
        if qe.get(key) != reference['qe_identity'].get(key):
            raise PrerequisiteError('Reference QE identity mismatch: ' + key)


def resolve_reference_result(relative_path):
    """Resolve the one frozen historical reference after public evidence curation."""
    if relative_path == 'results/phase4b/20260905T040945688395Z-1cc8a50c/result.json':
        relative_path = 'results/scalar-si-baseline/B0/result.json'
    return ROOT / relative_path


def run_case(case_path, *, pw_x=None, julia_depot=None):
    directory = new_run_directory(ROOT/'.work/scalar-baseline')
    result = {'schema_version':1,'run_id':directory.name,'execution_status':'BLOCKED',
              'input_comparability_status':'BLOCKED','numerical_agreement_status':'NOT_ASSESSED',
              'convergence_study_status':'NOT_RUN','reasons':['Run started; calculations not complete'],
              'commands':[],'exit_code':1}
    write_json(directory/'result.json',result)
    try:
        case, input_identity = make_inputs(case_path,directory)
        result['inputs']=input_identity
        pseudo = ROOT/case['pseudo']['local_path']
        result['pseudo']=check_pseudo(pseudo,case)
        (directory/'pseudo').mkdir()
        local_pseudo = directory/'pseudo'/case['pseudo']['filename']
        shutil.copyfile(pseudo,local_pseudo)
        check_pseudo(local_pseudo,case)
        env = os.environ.copy()
        for key,setting in [('OMP_NUM_THREADS','omp_num_threads'),('OPENBLAS_NUM_THREADS','openblas_num_threads'),('JULIA_NUM_THREADS','julia_num_threads')]:
            env[key]=str(case['runtime'][setting])
        dftk_env = dict(env,JULIA_LOAD_PATH='@:@stdlib',JULIA_PKG_OFFLINE='true')
        dftk_env['JULIA_DEPOT_PATH']=julia_depot or env.get('JULIA_DEPOT_PATH',str(ROOT/'.work/julia-depot'))
        result['thread_settings']={key:env[key] for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','JULIA_NUM_THREADS')}
        identity_cmd=[sys.executable,str(ROOT/'scripts/run_recorded.py'),'identity']
        identity_run=run_command(identity_cmd,directory,'workbench-identity',dftk_env)
        result['commands'].append(identity_run)
        if identity_run['exit_code'] != 0:
            raise PrerequisiteError('Current workbench identity check failed')
        identity=json.loads((directory/'workbench-identity.stdout').read_text())
        if identity['overall_status']!='PASS' or identity['environment']['status']!='PASS':
            raise PrerequisiteError('Current workbench identity is not PASS')
        result['environment']=identity['environment']
        launcher = pw_x or os.environ.get('PW_X') or shutil.which('pw.x')
        if not launcher:
            raise PrerequisiteError('QE pw.x not found')
        launcher=str(Path(launcher).absolute())
        result['qe_identity']=qe_identity(launcher,directory,env)
        reference = None
        if 'phase4c' in case:
            reference_path = resolve_reference_result(case['phase4c']['reference_result'])
            reference = json.loads(reference_path.read_text())
            check_reference_environment(result['environment'], result['qe_identity'], reference)
            result['reference_identity_check'] = {'status': 'PASS',
                'reference_run_id': reference['run_id'], 'reference_result_sha256': sha256(reference_path)}
        result['reasons']=['Configuration, input hashes and environment recorded; SCF pending']
        write_json(directory/'result.json',result)
        # Both engines read this exact copied UPF. QE's .save starts in a new directory.
        qe_dir=directory/'qe'; qe_dir.mkdir()
        shutil.copyfile(directory/'qe.in',qe_dir/'qe.in')
        print('Run '+directory.name+': QE SCF starting',file=sys.stderr,flush=True)
        qe_run=run_command([launcher,'-in','qe.in'],qe_dir,'qe',env)
        result['commands'].append(qe_run)
        check_pseudo(local_pseudo,case)
        if qe_run['exit_code'] != 0:
            raise ValueError('QE SCF process failed')
        qe=parse_qe(qe_dir/'scratch/si.save/data-file-schema.xml',(qe_dir/'qe.stdout').read_text(),
                    qe_run['exit_code'], expected_n_kpoints=requested_kpoint_count(case))
        if sha256(result['qe_identity']['binary_path']) != result['qe_identity']['binary_sha256']:
            raise PrerequisiteError('QE executable changed during the run')
        if reference is not None and qe['version'] != reference['qe_identity']['startup_version']:
            raise PrerequisiteError('Actual QE startup version differs from the historical reference')
        qe['pseudo_sha256']=sha256(local_pseudo)
        # The two engines' shared file was checked before and after QE; the XML/stdout
        # identify Si.upf. NLCC must also be present in the QE parser's actual evidence.
        result['qe_identity']['startup_version']=qe['version']
        write_json(directory/'qe-result.json',qe)
        print('Run '+directory.name+': QE converged; DFTK SCF starting',file=sys.stderr,flush=True)
        dftk_run=run_command(['julia','--startup-file=no','--color=no','--project='+str(ROOT/'environment/workbench'),
                             str(ROOT/'scripts/run_dftk_baseline.jl'),str(directory/'dftk-input.json'),
                             str(local_pseudo),str(directory/'dftk-result.json')],directory,'dftk',dftk_env)
        result['commands'].append(dftk_run)
        check_pseudo(local_pseudo,case)
        if dftk_run['exit_code'] != 0:
            raise ValueError('DFTK SCF/diagonalization process failed')
        dftk=json.loads((directory/'dftk-result.json').read_text())
        if dftk['input_sha256'] != input_identity['dftk_input_sha256'] or dftk['case_sha256'] != input_identity['case_sha256']:
            raise ValueError('DFTK loaded input/config hash mismatch')
        if dftk['converged'] is not True or dftk['execution_status']!='PASS':
            raise ValueError('DFTK result is not converged')
        result['execution_status']='PASS'
        comparison=compare(case,dftk,qe)
        save_comparison(directory,comparison)
        result.update(input_comparability_status='PASS',numerical_agreement_status='REVIEW_REQUIRED',reasons=[],exit_code=0)
    except PrerequisiteError as error:
        result.update(reasons=[str(error)],exit_code=7)
    except (Exception,KeyboardInterrupt) as error:
        result.update(execution_status='FAIL' if result['execution_status']!='PASS' else 'PASS',
                      input_comparability_status='FAIL',reasons=[type(error).__name__+': '+str(error)],exit_code=1)
    write_json(directory/'result.json',result)
    print(json.dumps({'run_id':directory.name,'result':str(directory/'result.json'),
                      'execution_status':result['execution_status'],'input_comparability_status':result['input_comparability_status'],
                      'numerical_agreement_status':result['numerical_agreement_status'],'exit_code':result['exit_code']}))
    return result['exit_code']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',type=Path,default=ROOT/'benchmarks/si-sr-lda/case.json')
    parser.add_argument('--pw-x',help='Existing pw.x; otherwise PW_X then PATH')
    parser.add_argument('--julia-depot',help='Existing fixed workbench package cache')
    parser.add_argument('--prepare-only',type=Path,help='Generate paired inputs into a new directory; no execution claim')
    args=parser.parse_args()
    if args.prepare_only:
        args.prepare_only.mkdir(parents=True,exist_ok=False)
        make_inputs(args.case,args.prepare_only)
        print('Inputs generated; SCF NOT RUN')
        return 0
    return run_case(args.case,pw_x=args.pw_x,julia_depot=args.julia_depot)


if __name__=='__main__':
    sys.exit(main())
