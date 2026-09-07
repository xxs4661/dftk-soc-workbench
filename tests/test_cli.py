"""Fresh-process CLI checks; requires the locked environment and real Mg sample."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
env = os.environ.copy()
env['JULIA_LOAD_PATH'] = '@:@stdlib'
julia = ['julia', '--startup-file=no', '--color=no', '--project=' + str(ROOT / 'environment/workbench')]
worker = julia + [str(ROOT / 'scripts/inspect_relativistic_upf.jl')]
wrapper = ['bash', str(ROOT / 'scripts/run_upf_inspection.sh')]
ledger = []


def check(label, command, expected_exit, status=None):
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == expected_exit, (label, result.returncode, result.stderr)
    data = json.loads(result.stdout) if status else None
    if status:
        assert data['overall_status'] == status, (label, data)
        assert data['exit_code'] == expected_exit
    ledger.append(dict(check=label, exit_code=result.returncode,
                       input_status=status, run_id=data.get('run_id') if data else None,
                       negative_test_passed=expected_exit != 0))
    print(label + ': PASS; process exit=' + str(result.returncode))
    return data


historical = ROOT / 'results/upf-acceptance/phase3-inspection.json'
before = hashlib.sha256(historical.read_bytes()).hexdigest()
check('wrapper help', wrapper + ['--help'], 0)
check('Julia help', worker + ['--help'], 0)
check('extra arguments', wrapper + ['one', 'two'], 2, 'ARGUMENT_ERROR')
missing = check('missing input', wrapper + [str(ROOT / '.work/no-such-input.upf')], 7, 'BLOCKED')
with tempfile.TemporaryDirectory(dir=ROOT / '.work') as temp:
    invalid = Path(temp) / 'not-a-pseudopotential.txt'
    invalid.write_text('Explicit invalid text for parser failure testing; not a UPF.\n')
    check('parse failure', wrapper + [str(invalid)], 3, 'FAIL')
info = check('information is not acceptance', worker + ['--mode', 'inspect', str(ROOT / '.work/pseudos/Mg.upf')], 0, 'INFO_ONLY')
assert info['metadata_validation_status'] == 'NOT_RUN'
assert info['dftk_construction_status'] == 'NOT_RUN'
with tempfile.TemporaryDirectory(dir=ROOT / '.work') as temp:
    isolated = Path(temp)
    for directory in ['scripts', 'config', 'environment/workbench']:
        (isolated / directory).mkdir(parents=True, exist_ok=True)
    for file in ['scripts/inspect_relativistic_upf.jl', 'scripts/workbench_environment.jl',
                 'scripts/upf_validation.jl', 'config/sources.lock',
                 'environment/workbench/Project.toml', 'environment/workbench/Manifest.toml',
                 'environment/workbench/checksums.toml']:
        shutil.copy2(ROOT / file, isolated / file)
    check('missing source prerequisite',
          ['julia', '--startup-file=no', '--project=' + str(isolated / 'environment/workbench'),
           str(isolated / 'scripts/inspect_relativistic_upf.jl'), '--mode', 'fr-nc', '--default-input'],
          7, 'BLOCKED')
assert hashlib.sha256(historical.read_bytes()).hexdigest() == before
assert len({x['run_id'] for x in ledger if x['run_id']}) == sum(bool(x['run_id']) for x in ledger)
print('historical PASS preserved as history; current failures have distinct run IDs: PASS')
ledger_path = ROOT / '.work/phase4a-evidence/cli-ledger.json'
ledger_path.parent.mkdir(parents=True, exist_ok=True)
ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
