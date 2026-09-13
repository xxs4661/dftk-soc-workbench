#!/usr/bin/env python3
"""Phase 8C resource gates and native public replay, without a new solver.

Only the four registered QE-reference slots may call the existing executor.
Public replay reads compressed native text and canonical endpoints, never UPF,
save arrays, Julia, QE or a DFTK context. Geometry uses integer reciprocal indices.
"""
import argparse
from contextlib import contextmanager
import copy
import datetime
from fractions import Fraction
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024**3
MAX_RSS = 8*GIB
INTERVAL = .1


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write(path, value, *, exclusive=False):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    raw=json.dumps(value, separators=(',', ':'), allow_nan=False)+'\n'
    with path.open('x' if exclusive else 'w') as stream:
        stream.write(raw)


def head(root):
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()


def close(actual, expected, where='root'):
    require(type(actual) is type(expected), 'Type differs: '+where)
    if isinstance(actual,dict):
        require(actual.keys()==expected.keys(),'Fields differ: '+where)
        for key in actual: close(actual[key],expected[key],where+'/'+key)
    elif isinstance(actual,list):
        require(len(actual)==len(expected),'Length differs: '+where)
        for i,(a,b) in enumerate(zip(actual,expected)):close(a,b,where+'/'+str(i))
    elif isinstance(actual,float):
        require(math.isfinite(actual) and math.isfinite(expected) and
                abs(actual-expected)<=1e-11*max(1,abs(actual),abs(expected)), 'Float differs: '+where)
    else: require(actual==expected,'Value differs: '+where)


def ps_rows():
    result=subprocess.run(['ps','-axo','pid=,ppid=,pgid=,rss='],capture_output=True,text=True,check=True)
    rows=[]
    for line in result.stdout.splitlines():
        values=[int(x) for x in line.split()]
        require(len(values)==4 and all(x>=0 for x in values),'Cannot parse process memory accounting')
        rows.append(dict(zip(('pid','ppid','pgid','rss_kib'),values)))
    require(rows,'Process memory accounting unavailable')
    return rows


def owned_rows(rows, leader):
    ids={r['pid'] for r in rows if r['pgid']==leader}
    while True:
        next_ids=ids|{r['pid'] for r in rows if r['ppid'] in ids}
        if next_ids==ids:break
        ids=next_ids
    return [r for r in rows if r['pid'] in ids]


@contextmanager
def reference_execution_guard(root, directory, action, profile):
    """Exclusive four-slot sequence. Never clear an unexplained stale lock."""
    area=Path(root)/'.work/phase8c';area.mkdir(parents=True,exist_ok=True)
    lock=area/'active-reference.json'
    require(action in ('Q-SCF','Q-GAMMA') and profile in ('K6','K8'),'Unregistered formal slot')
    order=[('K6','Q-SCF'),('K6','Q-GAMMA'),('K8','Q-SCF'),('K8','Q-GAMMA')]
    execution=head(root)
    token=uuid.uuid4().hex
    write(lock,{'owner_pid':os.getpid(),'token':token,'directory':str(directory),
                'profile':profile,'action':action,'created_utc':utc()},exclusive=True)
    try:
        for p,a in order[:order.index((profile,action))]:
            candidates=list((area/p).glob('*/result.json'))
            states=[json.loads(x.read_text()) for x in candidates]
            states=[s for s in states if s.get('action')==a and s.get('execution_status') in ('PASS','FAIL','BLOCKED_PARENT','RESOURCE_BLOCKED')]
            require(len(states)==1,'Previous declared slot has no unique terminal record: '+p+'/'+a)
            prior=states[0]
            require(prior.get('execution_commit')==execution and prior.get('qe_reference_profile')==p,'Previous slot belongs to another execution/profile')
            require(prior.get('source_preservation_status')!='FAIL','Previous source-integrity error blocks related execution')
            if prior['execution_status']=='PASS':
                require(prior.get('worker_started') is True and type(prior.get('process_exit_code')) is int and prior['process_exit_code']==prior.get('exit_code')==0,'Contradictory prior success')
            else:
                require(prior.get('exit_code') not in (None,0),'Prior failure cannot have zero/missing wrapper exit')
        ps_rows()
        yield
    finally:
        require(json.loads(lock.read_text()).get('token')==token,'Execution lock owner changed')
        resource_path=Path(directory)/'resource.json'
        if resource_path.exists():
            require(json.loads(resource_path.read_text()).get('owned_process_cleanup_status')!='UNCONFIRMED','Owned-process cleanup unconfirmed; execution lock retained')
        lock.unlink()


def monitored_execute(executor, command, directory, env, *, limit_bytes=MAX_RSS,
                      observation_callback=None, safe_stop_timeout_seconds=30,
                      cooperative_callback=None, cooperative_grace_seconds=120,
                      termination_grace_seconds=10, cleanup_grace_seconds=5):
    """Sample only the recorded new session/descendants, with an internal hook.

    Default callers retain8 GiB. The exceptional10 GiB call is authenticated by
    its controller before reaching this internal mechanism; it also requires an
    observation callback. This is sampled supervision, not OS memory isolation.
    Callback errors fail closed. A safe request is latched and escalated after
    at most30 seconds, even if later samples decline or the callback retracts it.
    """
    require(type(limit_bytes) is int and limit_bytes in (MAX_RSS, 10*GIB), 'Unsupported internal RSS limit')
    require(observation_callback is None or callable(observation_callback), 'Invalid observation callback')
    require(limit_bytes == MAX_RSS or observation_callback is not None, 'Exceptional limit requires authenticated policy observation')
    require(type(safe_stop_timeout_seconds) in (int, float) and math.isfinite(safe_stop_timeout_seconds) and
            0 < safe_stop_timeout_seconds <= 30, 'Safe-stop deadline must be positive and at most30 seconds')
    require(cooperative_callback is None or callable(cooperative_callback), 'Invalid cooperative callback')
    for name,value,maximum in [('cooperative',cooperative_grace_seconds,120),
                               ('termination',termination_grace_seconds,10),('cleanup',cleanup_grace_seconds,5)]:
        require(type(value) in (int,float) and math.isfinite(value) and 0<value<=maximum,
                'Invalid bounded '+name+' grace')
    directory=Path(directory); initial_rows=ps_rows()
    require(initial_rows and len({r['pid'] for r in initial_rows})==len(initial_rows) and all(
        type(r.get(k)) is int and r[k]>=0 for r in initial_rows for k in ('pid','ppid','pgid','rss_kib')),
        'Initial process accounting unavailable or malformed')
    initial_processes={r['pid'] for r in initial_rows}
    state={'status':'RUNNING','limit_bytes':limit_bytes,'sample_interval_seconds':INTERVAL,
           'peak_aggregate_rss_bytes':0,'samples':0,'nonempty_samples':0,'started_utc':utc(),
           'scope':'Recorded session group plus descendant processes; sampled aggregate RSS, not a continuous upper bound',
           'native_exit_code':None,'numerical_process_pid':None,
           'resource_policy_status':'RUNNING','safe_stop_requested':False,
           'safe_stop_timeout_seconds':safe_stop_timeout_seconds,'safe_stop_escalated':False,
           'control_status':'NOT_ENABLED' if cooperative_callback is None else 'RUNNING',
           'forced_termination':False,'signals':[]}
    result={}; started=time.monotonic()
    def worker():
        try:result['code']=executor(command,directory,env)
        except BaseException as error:result['error']=error
    # An executor that fails to reap even after owned-process termination must
    # produce UNCONFIRMED, not keep the recorder waiting forever.
    thread=threading.Thread(target=worker,daemon=True);thread.start()
    leader=None; violation=None; marker_first_seen=None; stop_requested_at=None; empty_since=None
    observed_owned={}; births={}; ownership_uncertain=set()
    control_requested_at=None; control_forced=False
    def birth(pid):
        if cooperative_callback is None:return None
        found=subprocess.run(['ps','-p',str(pid),'-o','lstart=','-o','comm='],capture_output=True,text=True)
        return found.stdout.strip() if found.returncode==0 and found.stdout.strip() else None
    def live_owned():
        alive=[]
        for pid,pgid in observed_owned.items():
            try:
                if os.getpgid(pid)==pgid:
                    if cooperative_callback is not None:
                        current=birth(pid)
                        if current is None or births.get(pid) is None:ownership_uncertain.add(pid)
                        elif current!=births[pid]:continue  # A reused PID is not our old process.
                    alive.append((pid,pgid))
            except ProcessLookupError:pass
        return alive
    def stop_owned(sig=signal.SIGTERM):
        if leader is None:return
        alive=[item for item in live_owned() if item[0] not in ownership_uncertain]
        if alive:
            state['forced_termination']=True
            state['signals'].append({'signal':signal.Signals(sig).name,'elapsed_seconds':time.monotonic()-started,
                                     'owned_pids':[pid for pid,pgid in alive]})
        if any(pgid==leader for pid,pgid in alive):
            try:os.killpg(leader,sig)
            except ProcessLookupError:pass
        for pid,pgid in alive:
            if pgid!=leader:
                try:os.kill(pid,sig)
                except ProcessLookupError:pass
    try:
        with (directory/'resource-samples.jsonl').open('x') as log:
            while thread.is_alive() or (control_requested_at is not None and live_owned()):
                if cooperative_callback is not None:
                    control=cooperative_callback(dict(monotonic_seconds=time.monotonic(),
                        elapsed_seconds=time.monotonic()-started,leader_pid=leader))
                    require(type(control) is dict and control.get('status') in ('CONTINUE','REQUEST_STOP'),
                            'Invalid cooperative-control result')
                    if control['status']=='REQUEST_STOP':
                        require(control.get('reason') in ('USER_CANCELLED','TIME_BUDGET_EXCEEDED'),
                                'Unsupported cooperative reason')
                        if control_requested_at is None:
                            control_requested_at=time.monotonic()
                            state.update(control_status=control['reason'],control_first_request=dict(control),
                                         control_requested_elapsed_seconds=control_requested_at-started)
                marker=directory/'process-start.json'
                if leader is None and marker.is_file():
                    if marker_first_seen is None:marker_first_seen=time.monotonic()
                    try:record=json.loads(marker.read_text())
                    except json.JSONDecodeError:
                        if time.monotonic()-marker_first_seen<1:
                            time.sleep(.01);continue
                        raise ValueError('Process marker remained incomplete for one second')
                    candidate=record['pid']
                    require(type(candidate)is int and candidate>1 and candidate not in initial_processes and
                            record['command']==command,'Unexpected process ownership marker')
                    leader=candidate
                    observed_owned[leader]=leader
                    if cooperative_callback is not None:births[leader]=birth(leader)
                    state['numerical_process_pid']=leader
                if leader is None:
                    require(time.monotonic()-started<5, 'No valid process ownership marker within five seconds')
                else:
                    table=ps_rows()
                    require(len({r['pid'] for r in table})==len(table) and all(
                        type(r.get(k)) is int and r[k]>=0 for r in table for k in ('pid','ppid','pgid','rss_kib')),
                        'Malformed or duplicate process accounting')
                    rows=owned_rows(table,leader)
                    if cooperative_callback is not None:
                        # Keep already observed independent descendants in accounting after reparenting.
                        existing={r['pid'] for r in rows}
                        rows += [r for r in table if r['pid'] not in existing and observed_owned.get(r['pid'])==r['pgid']]
                    require(not any(r['pid'] in initial_processes for r in rows), 'Owned group contains an existing unrelated process')
                    if not rows:
                        if empty_since is None:empty_since=time.monotonic()
                        require(not thread.is_alive() or time.monotonic()-empty_since<1, 'Owned process accounting absent for one second')
                    else:empty_since=None
                    if cooperative_callback is not None:
                        for r in rows:
                            if r['pid'] not in births:births[r['pid']]=birth(r['pid'])
                    observed_owned.update({r['pid']:r['pgid'] for r in rows})
                    total=sum(r['rss_kib'] for r in rows)*1024
                    state['peak_aggregate_rss_bytes']=max(state['peak_aggregate_rss_bytes'],total)
                    state['samples']+=1
                    if state['samples']==1:state['first_sample_delay_seconds']=time.monotonic()-started
                    if rows and total>0:state['nonempty_samples']+=1
                    now=time.monotonic()
                    sample={'elapsed_s':now-started,'aggregate_rss_bytes':total,'processes':rows}
                    log.write(json.dumps(sample,separators=(',',':'))+'\n');log.flush()
                    decision=None
                    if observation_callback is not None:
                        decision=observation_callback(dict(current_group_rss_bytes=total,
                            peak_group_rss_bytes=state['peak_aggregate_rss_bytes'],elapsed_seconds=now-started,
                            monotonic_seconds=now,processes=rows,leader_pid=leader))
                        require(type(decision) is dict and decision.get('status') in
                            ('CONTINUE','WARNING','STOP_AT_SAFE_BOUNDARY','RESOURCE_LIMIT','MONITORING_UNAVAILABLE'),
                            'Invalid resource-policy callback result')
                        require(decision['status']=='CONTINUE' or type(decision.get('reason')) is str and decision['reason'],
                            'Missing resource-policy reason')
                        if 'limit_bytes' in decision:
                            require(type(decision['limit_bytes']) is int and decision['limit_bytes']==limit_bytes,
                                    'Callback and sampler effective limits differ')
                        if decision['status'] in ('RESOURCE_LIMIT','MONITORING_UNAVAILABLE'):
                            state['resource_policy_status']=decision['status']
                            violation='Resource policy: '+decision['reason'];stop_owned();break
                        if decision['status']=='STOP_AT_SAFE_BOUNDARY' and stop_requested_at is None:
                            stop_requested_at=now;state.update(safe_stop_requested=True,
                                safe_stop_first_decision=dict(decision),safe_stop_elapsed_seconds=now-started,
                                resource_policy_status='STOP_AT_SAFE_BOUNDARY')
                        if decision['status']=='WARNING':state['warning_observed']=True
                    # The bottom sampler applies the effective limit itself;
                    # the callback is not allowed to cancel this hard check.
                    if state['peak_aggregate_rss_bytes']>=limit_bytes:
                        state['resource_policy_status']='RESOURCE_LIMIT'
                        violation='RESOURCE_BLOCKED: sampled process-tree peak reaches '+str(limit_bytes)+' bytes';stop_owned();break
                    if stop_requested_at is not None and now-stop_requested_at>=safe_stop_timeout_seconds:
                        state['safe_stop_escalated']=True
                        violation='RESOURCE_BLOCKED: safe-boundary request unacknowledged at its bounded deadline';stop_owned();break
                if control_requested_at is not None and time.monotonic()-control_requested_at>=cooperative_grace_seconds:
                    control_forced=True
                    violation='Cooperative request exceeded its bounded grace; forced termination'
                    stop_owned(signal.SIGTERM);break
                time.sleep(INTERVAL)
    except BaseException as error:
        violation='Resource monitoring failed: '+str(error)
        state['resource_policy_status']='MONITORING_UNAVAILABLE'
        # Without an authenticated marker there is no safe target to kill.
        # Do not guess ownership from a newly appearing sibling process.
        stop_owned()
    if control_forced:
        deadline=time.monotonic()+termination_grace_seconds
        while (thread.is_alive() or live_owned()) and time.monotonic()<deadline:
            thread.join(min(.05,max(0,deadline-time.monotonic())))
            if not thread.is_alive():time.sleep(.02)
        if thread.is_alive() or live_owned():stop_owned(signal.SIGKILL)
        deadline=time.monotonic()+cleanup_grace_seconds
        while (thread.is_alive() or live_owned()) and time.monotonic()<deadline:
            thread.join(min(.05,max(0,deadline-time.monotonic())))
            if not thread.is_alive():time.sleep(.02)
    else:
        if violation:
            thread.join(30)
            if thread.is_alive():stop_owned(signal.SIGKILL)
        thread.join(3)
        if live_owned():
            violation=violation or 'RESOURCE_BLOCKED: numerical descendants survived their recorded leader'
            stop_owned();deadline=time.monotonic()+1
            while live_owned() and time.monotonic()<deadline:time.sleep(.05)
            if live_owned():stop_owned(signal.SIGKILL)
            deadline=time.monotonic()+2
            while live_owned() and time.monotonic()<deadline:time.sleep(.05)
    state['owned_process_cleanup_status']='PASS' if not live_owned() and not thread.is_alive() else 'UNCONFIRMED'
    state['remaining_observed_processes']=live_owned()
    if state['safe_stop_requested'] and violation is None:
        violation='Resource policy safe-boundary stop: '+state['safe_stop_first_decision']['reason']
    if state['owned_process_cleanup_status']!='PASS':
        violation=violation or 'Owned-process/executor cleanup unconfirmed'
    if state['control_status']=='RUNNING':state['control_status']='NO_REQUEST'
    if state['resource_policy_status']=='RUNNING':state['resource_policy_status']='PASS' if not violation else 'RESOURCE_BLOCKED'
    state.update(status='RESOURCE_BLOCKED' if violation else 'PASS',reason=violation,
                 native_exit_code=result.get('code'),elapsed_seconds=time.monotonic()-started,finished_utc=utc())
    if not state['nonempty_samples']:
        state.update(status='RESOURCE_BLOCKED',reason='No numerical-process RSS sample was obtained',resource_policy_status='MONITORING_UNAVAILABLE')
    write(directory/'resource.json',state)
    if 'error' in result:raise result['error']
    return result.get('code'),state


A = 10.26
FFT = 48
NR = FFT**3
GIB = 1024**3
MAX_RSS = 8*GIB
TWOPIA = 2*math.pi/A
WAVE_BOUND = math.sqrt(60)*A/math.sqrt(2)/(2*math.pi)
DENSITY_BOUND = math.sqrt(240)*A/math.sqrt(2)/(2*math.pi)



def axis(n):
    require(n in (2,4,6,8), 'Only B0/K4 geometry validation plus K6/K8 is in scope')
    return list(range(n//2))+list(range(-n//2,0))


def point_numerators(n):
    return list(itertools.product(axis(n),repeat=3))


def exact_keys(n):
    return {tuple(Fraction(q % n,n) for q in p) for p in point_numerators(n)}


def validate_explicit_grid(n,rows):
    """Validate requested grid/order/weights, not a native-output-order matcher."""
    expected=point_numerators(n)
    require(type(rows) is list and len(rows)==n**3,'Wrong requested point count')
    seen=set()
    for numerators,row in zip(expected,rows):
        require(type(row) is dict,'Malformed point record')
        point=row.get('coordinate_fractional');weight=row.get('weight_spatial')
        require(type(point) is list and len(point)==3,'Fractional reciprocal coordinate triple required')
        require(all(type(x) in (int,float) and math.isfinite(x) for x in point),'Nonfinite or nonnumeric coordinate')
        require(type(weight) in (int,float) and math.isfinite(weight),'Invalid weight')
        require(abs(weight-1/n**3)<=1e-12,'Wrong spatial weight')
        require(all(abs(x-q/n)<=2e-16 for x,q in zip(point,numerators)),'Wrong grid coordinates, units, or requested order')
        key=tuple(q % n for q in numerators)
        require(key not in seen,'Duplicate requested point');seen.add(key)
    require(abs(math.fsum(row['weight_spatial'] for row in rows)-1)<=1e-12,'Spatial weight sum differs')
    return {'nk':len(rows),'unique_mod_integer':True,'gamma_present':(0,0,0) in seen,
            'inversion_complete':all(tuple((-q)%n for q in key) in seen for key in seen)}


def difference_extrema(points):
    require(bool(points),'Cannot bound empty G support')
    minima=[min(g[d] for g in points) for d in range(3)]
    maxima=[max(g[d] for g in points) for d in range(3)]
    return minima,maxima,[hi-lo for lo,hi in zip(minima,maxima)]


def metric(x,y,z):
    return 3*(x*x+y*y+z*z)-2*(x*y+y*z+z*x)


def cartesian(point):
    x,y,z=point
    return [TWOPIA*(-x+y+z),TWOPIA*(x-y+z),TWOPIA*(x+y-z)]


def wave_sphere(n,numerators):
    # |(G+k)_i| <= sqrt(2 Ecut) |a_i|/(2pi); |k_i| <= 1/2.
    bound=math.ceil(WAVE_BOUND+0.5)
    threshold=60*n*n/(TWOPIA*TWOPIA)
    gx,gy,gz=numerators
    selected=[]; max_m=0; distance=float('inf')
    for i,j,k in itertools.product(range(-bound,bound+1),repeat=3):
        x,y,z=n*i+gx,n*j+gy,n*k+gz
        m=metric(x,y,z)
        distance=min(distance,abs(m-threshold))
        if m<=threshold:
            selected.append((i,j,k));max_m=max(max_m,m)
    require(selected,'Empty wavefunction sphere')
    minima,maxima,widths=difference_extrema(selected)
    require(all(w<24 for w in widths),'G-Gprime touches Nyquist')
    max_ha=max_m*TWOPIA*TWOPIA/(2*n*n)
    require(max_ha<=30,'Wavefunction cutoff inconsistency')
    canonical=''.join(f'{i},{j},{k}\n' for i,j,k in selected).encode()
    return {'integer_numerators':list(numerators),'coordinate_fractional':[q/n for q in numerators],
        'weight_spatial':1/n**3,'ng':len(selected),'g_min':minima,'g_max':maxima,
        'max_same_k_difference_component':widths,'maximum_kinetic_ha':max_ha,
        'closest_candidate_cutoff_distance_ha':distance*TWOPIA*TWOPIA/(2*n*n),
        'canonical_integer_G_sha256':hashlib.sha256(canonical).hexdigest()}


def density_sphere():
    require(DENSITY_BOUND<24,'Analytic density support can reach Nyquist')
    selected=[]; threshold=240/(TWOPIA*TWOPIA);distance=float('inf')
    for g in itertools.product(range(-24,24),repeat=3):
        m=metric(*g);distance=min(distance,abs(m-threshold))
        if m<=threshold:selected.append(g)
    minima=[min(g[d] for g in selected) for d in range(3)]
    maxima=[max(g[d] for g in selected) for d in range(3)]
    require(all(-24<lo<=hi<24 for lo,hi in zip(minima,maxima)),'Density sphere touches Nyquist')
    return {'cutoff_ha':120,'cutoff_ry':240,'same_requested_hard_smooth':True,
        'analytic_abs_component_bound':DENSITY_BOUND,'enumerated_fft_box_modes':NR,
        'ng':len(selected),'g_min':minima,'g_max':maxima,
        'closest_candidate_cutoff_distance_ha':distance*TWOPIA*TWOPIA/2,
        'canonical_integer_G_sha256':hashlib.sha256(''.join(','.join(map(str,g))+'\n' for g in selected).encode()).hexdigest()}


def dftk_budget(ngmax,nk):
    require(type(ngmax) is int and ngmax>0 and type(nk) is int and nk>0,'Positive integer geometry dimensions required')
    terms={'retained_orbitals_and_solver':16*2*ngmax*30*(12*nk+60),
           'projectors_and_snapshots':16*2*ngmax*72*nk*4,
           'bounded_fft_workspaces':16*2*NR*24*8,
           'density_core_local_fields':8*NR*100,'runtime_library_margin':2*GIB}
    total=sum(terms.values())
    return {'source':'scripts/run_si_soc.jl:si_grid, frozen source_base; coefficients unchanged',
            'terms_bytes':terms,'total_bytes':total,'total_gib':total/GIB,
            'budget_status':'WITHIN_EXISTING_LIMIT' if total<MAX_RSS else 'BUDGET_EXCEEDS_EXISTING_LIMIT',
            'execution_status':'NOT_RUN','measured_peak_bytes':None}


def qe_budget(ngmax,nk):
    require(type(ngmax) is int and ngmax>0 and type(nk) is int and nk>0,'Positive integer geometry dimensions required')
    terms={'all_k_wavefunctions_and_copy_allowance':2*16*2*ngmax*24*(nk+1),
        'one_k_solver_and_atomic_init_allowance':8*16*2*ngmax*(4*24),
        'one_k_projector_allowance':4*16*2*ngmax*72+8*16*72*72*4,
        'fft_complex_allowance':16*NR*(2*24*4+64),
        'density_mixing_real_allowance':8*NR*4*64,
        'all_k_geometry_indices_allowance':8*nk*ngmax*8,
        'spectral_tables_allowance':8*nk*24*16,'density_G_metadata_allowance':8*NR*32,
        'runtime_jll_python_mpi_library_margin':2*GIB}
    total=sum(terms.values())
    return {'terms_bytes':terms,'total_bytes':total,'total_gib':total/GIB,
        'budget_status':'ESTIMATED_WITHIN_LIMIT' if total<MAX_RSS else 'RESOURCE_BLOCKED',
        'scope':'New independent planning allowances; not native QE allocation report, measured peak, or rigorous upper bound',
        'measured_peak_bytes':None,'runtime_peak_limit_bytes':MAX_RSS}


def single_save_budget(rows):
    nk=len(rows);sum_ng=sum(r['ng'] for r in rows)
    terms={'complex_spinor_coefficients':16*2*24*sum_ng,'integer_G_triplets':12*sum_ng,
           'per_file_header_record_allowance':nk*(512+24*8),
           'charge_upf_xml_metadata_allowance':64*1024**2}
    return {'terms_bytes':terms,'total_bytes':sum(terms.values()),'sum_ng':sum_ng,
        'scope':'One save directory; broad fixed overhead, not exact Fortran-file-size prediction'}


def profile_geometry(n):
    points=point_numerators(n);keys=exact_keys(n)
    require(len(keys)==len(points)==n**3,'Duplicate or missing point')
    require((Fraction(0),)*3 in keys,'Missing Gamma')
    require(all(tuple((-q)%1 for q in key) in keys for key in keys),'Missing inversion partner')
    weight=float(format(1/n**3,'.17g'))
    require(abs(math.fsum([weight]*n**3)-1)<=1e-12,'Printed weights do not sum to one')
    for p in points:
        for numerator in p:
            require(abs(float(format(numerator/n,'.17g'))-float(Fraction(numerator,n)))<=2e-16,'Printed coordinate drift')
    validate_explicit_grid(n,[{'coordinate_fractional':[q/n for q in p],'weight_spatial':weight} for p in points])
    rows=[wave_sphere(n,p) for p in points]
    ngmax=max(r['ng'] for r in rows)
    return {'grid':[n,n,n],'axis_numerators':axis(n),'denominator':n,
        'loop_order':'x outermost, y middle, z innermost','nk':len(rows),
        'weight_spatial':weight,'printed_weight_sum_error':abs(math.fsum([weight]*n**3)-1),
        'mod_integer_unique':True,'inversion_complete':True,'contains_gamma':True,
        'ng_min':min(r['ng'] for r in rows),'ng_max':ngmax,'sum_ng':sum(r['ng'] for r in rows),
        'max_GminusGprime_components':[max(r['max_same_k_difference_component'][i] for r in rows) for i in range(3)],
        'nearest_cutoff_distance_ha':min(r['closest_candidate_cutoff_distance_ha'] for r in rows),
        'rows':rows,'dftk_budget':dftk_budget(ngmax,len(rows)),
        'qe_budget':qe_budget(ngmax,len(rows)),'single_save_budget':single_save_budget(rows)}


def disk_budget(profiles,available_bytes):
    require(type(available_bytes) is int and available_bytes>=0,'Disk available bytes must be a nonnegative integer')
    local_saves=sum(2*profiles[p]['single_save_budget']['total_bytes'] for p in ('K6','K8'))
    local_logs=2*GIB
    terms={'local_scf_and_ordinary_gamma_save_copies':local_saves,
        'local_logs_native_text_tables_and_staging':local_logs,'outside_repository_increment_copy':local_saves+local_logs,
        'sample_restore_allowance':512*1024**2,'additional_free_reserve':10*GIB}
    total=sum(terms.values())
    return {'terms_bytes':terms,'required_available_bytes':total,'required_available_gib':total/GIB,
            'observed_available_bytes':available_bytes,
            'status':'ESTIMATED_WITHIN_AVAILABLE_SPACE' if available_bytes>=total else 'RESOURCE_BLOCKED',
            'volume_scope':'Work directory current filesystem; separately recheck archive target if on another volume'}


def resource_geometry():
    """Exact declared K4/K6/K8 geometry only; K4 is a historical dimension cross-check."""
    profiles={f'K{n}':profile_geometry(n) for n in (4,6,8)}
    require(profiles['K4']['dftk_budget']['total_bytes']==5889778688,'K4 frozen budget reproduction differs')
    require(profiles['K6']['dftk_budget']['total_bytes']==12614633984,'K6 frozen budget reproduction differs')
    density=density_sphere()
    require(density['ng']==16865,'Requested density sphere differs from frozen same-cell geometry')
    keys={n:exact_keys(n) for n in (2,4,6,8)}
    inclusion={'K6_contains_B0':keys[2]<=keys[6],'K6_contains_K4':keys[4]<=keys[6],
        'K8_contains_B0':keys[2]<=keys[8],'K8_contains_K4':keys[4]<=keys[8],
        'K8_contains_K6':keys[6]<=keys[8],
        'K4_intersection_K6_count':len(keys[4]&keys[6]),'K6_intersection_K8_count':len(keys[6]&keys[8])}
    return {'evidence_level':'INDEPENDENT_PYTHON_GEOMETRY_AND_PLANNING_ESTIMATE_REQUIRES_NATIVE_QE_CONFIRMATION',
        'reciprocal_columns_bohr_inverse':[cartesian(v) for v in ((1,0,0),(0,1,0),(0,0,1))],
        'wave_abs_Gplusk_component_bound':WAVE_BOUND,'profiles':profiles,'density_sphere':density,
        'grid_inclusion':inclusion,'DFTK_K6_status':'NOT_RUN','DFTK_K8_status':'NOT_RUN',
        'same_grid_cross_code_agreement':'NOT_ASSESSED'}


def verify_preflights(root,path,execution_commit):
    from si_qe_reference import PROFILE_IDS, prepared_paths, load_case
    path=Path(path);require(path.is_file() and not path.is_symlink(),'Missing ordinary both-case preflight manifest')
    data=json.loads(path.read_text())
    require(data.get('status')=='PASS' and data['execution_commit']==execution_commit,'Wrong or failed preflight execution')
    require(set(data['profiles'])==set(PROFILE_IDS),'Both K6/K8 preflights required')
    require(head(root)==execution_commit,'Current execution commit differs')
    for rel,expected in data['bound_sha256'].items():require(sha(Path(root)/rel)==expected,'Preflight source/input changed: '+rel)
    for profile in PROFILE_IDS:
        load_case(root,profile)
        rec=data['profiles'][profile];require(rec['status']=='PASS','Failed case preflight')
        for rel,expected in rec['identity_files'].items():require(sha(Path(root)/rel)==expected,'Identity preflight receipt changed')
        require(rec['qe_budget']['total_bytes']<MAX_RSS,'QE budget exceeds original limit')
    free=shutil.disk_usage(root).free
    require(free>=data['disk']['required_available_bytes'],'RESOURCE_BLOCKED: insufficient disk for complete increment and reserve')
    ps_rows()
    return data


def preflight(root,path):
    from si_qe_reference import PROFILE_IDS, prepared_paths, load_case, PREPARATION
    from run_si_qe import run, clean_execution
    root=Path(root).resolve(); path=Path(path); execution=head(root);clean_execution(root,execution)
    require(not path.exists(),'Do not overwrite earlier preflight')
    record={'schema_version':1,'status':'INCOMPLETE','execution_commit':execution,'preparation_commit':PREPARATION,
            'created_utc':utc(),'profiles':{},'numerical_executions':0}
    try:
        geometry={p:profile_geometry(int(p[1:])) for p in ('K4','K6','K8')}
        expected=json.loads((root/'benchmarks/si-soc-k-reference-v1/resource-geometry.json').read_text())
        close(density_sphere(),expected['density_sphere'],'density_sphere')
        for p,g in geometry.items():
            rows=g.pop('rows');g['ng_in_declared_order']=[x['ng'] for x in rows];g['G_list_sha256_in_declared_order']=[x['canonical_integer_G_sha256'] for x in rows]
            close(g,expected['profiles'][p],'prepared_geometry/'+p)
        record['disk']=disk_budget(geometry,shutil.disk_usage(root).free)
        require(record['disk']['status']=='ESTIMATED_WITHIN_AVAILABLE_SPACE','RESOURCE_BLOCKED: disk preflight')
        ps_rows()
        for p in PROFILE_IDS:
            load_case(root,p)
            directory=root/'.work/phase8c'/p/('identity-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
            result=run('identity',directory,root=root,qe_reference_profile=p)
            require(result['exit_code']==0 and result['execution_status']=='PASS','Identity preflight failed: '+p)
            record['profiles'][p]={'status':'PASS','qe_budget':geometry[p]['qe_budget'],'geometry':geometry[p],
                'identity_files':{str((directory/f).relative_to(root)):sha(directory/f) for f in ('result.json','identity.json')}}
        files=list(prepared_paths())+['scripts/si_qe_reference.py','scripts/si_qe_reference_evidence.py','scripts/run_si_qe.py','scripts/si_soc_comparison.py']
        record['bound_sha256']={str(f):sha(root/f) for f in files}
        clean_execution(root,execution);record['status']='PASS'
    except BaseException as error:
        record.update(status='BLOCKED',reason=str(error));write(path,record,exclusive=True);raise
    write(path,record,exclusive=True);return record

PUBLIC_DIR='results/si-soc-k-reference'
NATIVE_NAMES=('qe.in','qe.xml','qe.stdout','qe.stderr')
RUNTIME_FIELDS=('run_id','density_source_sha256','source_scf_run_id','fermi_energy_ha',
                'density_binding_scope','scf_acceptance_status','scf_validation','gamma_validation')


def redacted(value, root):
    replacements=((str(Path(root).resolve()),'<WORKBENCH>'),(str(Path.home()),'<HOME>'))
    if isinstance(value,str):
        for before,after in replacements:value=value.replace(before,after)
        return value
    if isinstance(value,list):return [redacted(v,root) for v in value]
    if isinstance(value,dict):return {redacted(k,root):redacted(v,root) for k,v in value.items()}
    return value


def packed(path,raw):
    """Lossless, deterministic gzip; byte and compressed identities are separate."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    require(not path.exists(),'Refuse replacing an earlier public payload: '+str(path))
    compressed=gzip.compress(raw,compresslevel=9,mtime=0);path.write_bytes(compressed)
    return {'gzip_sha256':sha(path),'gzip_bytes':len(compressed),
            'public_sha256':hashlib.sha256(raw).hexdigest(),'public_bytes':len(raw)}


def unpacked(root,rel,identity):
    base=Path(root).resolve(); relative=Path(rel)
    require(not relative.is_absolute() and '..' not in relative.parts,'Public payload path escapes root')
    path=base/relative
    require(path.resolve()==path and base in path.parents,'Public payload path aliases another directory')
    require(path.is_file() and not path.is_symlink(),'Missing ordinary public payload: '+rel)
    b=path.read_bytes()
    require(len(b)==identity['gzip_bytes'] and hashlib.sha256(b).hexdigest()==identity['gzip_sha256'],'Compressed payload identity differs: '+rel)
    raw=gzip.decompress(b)
    require(len(raw)==identity['public_bytes'] and hashlib.sha256(raw).hexdigest()==identity['public_sha256'],'Decompressed payload identity differs: '+rel)
    return raw


def iteration_rows(stdout, parsed):
    """One compact row per actual SCF iteration, plus original line indices."""
    lines=stdout.splitlines();starts=[(i,int(m.group(1))) for i,s in enumerate(lines) if (m:=re.search(r'iteration\s*#\s*(\d+)',s,re.I))]
    trace=parsed['scf']['trace'] if parsed['scf'] is not None else []
    require(len(starts)==len(trace),'Native iteration table count differs')
    rows=[]
    for j,(start,index) in enumerate(starts):
        stop=starts[j+1][0] if j+1<len(starts) else len(lines)
        row=copy.deepcopy(trace[j]);require(row['iteration']==index,'Native iteration order differs')
        row['stdout_start_line_one_based']=start+1
        row['ethr_ry']=[float(m.group(1).replace('D','E').replace('d','e')) for line in lines[start:stop] for m in re.finditer(r'ethr\s*=\s*([\d.eEdD+-]+)',line)]
        row['warning_lines_one_based']=[i+1 for i in range(start,stop) if re.search(r'warning|not converged|c_bands|IEEE',lines[i],re.I)]
        rows.append(row)
    return rows


def parse_public_native(root, profile, native, metadata, parent=None, parent_metadata=None):
    from si_qe_reference import load_case, case_sha256, validate_q_scf, validate_q_gamma
    from si_soc_comparison import parse_si_qe
    case=load_case(root,profile);case.update(verified_pseudo_sha256=case['pseudo']['sha256'],case_sha256=case_sha256(profile,root))
    action=metadata['action'];require(action in ('Q-SCF','Q-GAMMA'),'Unknown native action')
    input_path=Path(root)/'benchmarks/si-soc-k-reference-v1'/profile/('qe-scf.in' if action=='Q-SCF' else 'qe-gamma.in')
    require(native['qe.in']==input_path.read_bytes(),'Native input differs from predeclared profile bytes')
    require(metadata['execution_status']=='PASS' and type(metadata['process_exit_code'])is int and metadata['process_exit_code']==0,'Failed native process is not a successful endpoint')
    require(metadata.get('case_sha256')==case['case_sha256'],'Public metadata case identity differs')
    with tempfile.TemporaryDirectory(prefix='si-q-reference-native-') as directory:
        xml=Path(directory)/'qe.xml';xml.write_bytes(native['qe.xml'])
        value=parse_si_qe(xml,native['qe.stdout'].decode(),native['qe.stderr'].decode(),kind='scf' if action=='Q-SCF' else 'spectrum',case=case,process_exit_code=metadata['process_exit_code'])
    stdout=native['qe.stdout'].decode()
    require(re.findall(r'Parallel version \(MPI\), running on\s+(\d+) processors',stdout)==['1'] and re.findall(r'MPI processes distributed on\s+(\d+) nodes',stdout)==['1'],'Native parallelism differs from single process/node')
    geometry=json.loads((Path(root)/'benchmarks/si-soc-k-reference-v1/resource-geometry.json').read_text())['profiles'][profile]
    expected_npw=geometry['ng_in_declared_order'] if action=='Q-SCF' else [geometry['ng_in_declared_order'][0]]
    require([point['npw'] for point in value['kpoints']]==expected_npw,'Native npw differs from predeclared complete geometry')
    value.update(run_id=metadata['run_id'],density_source_sha256=metadata['density_source_sha256'])
    save=metadata['save_files']
    require(save['charge-density.dat']['sha256']==value['density_source_sha256'],'Native saved charge binding differs')
    require(save['Si_r.upf']['sha256']==case['pseudo']['sha256'],'Native saved UPF binding differs')
    require(save['data-file-schema.xml']['sha256']==metadata['native_files']['qe.xml']['raw_sha256'],'Raw SCF/save XML binding differs')
    needed={f'wfc{i}.dat' for i in range(1,len(case['kpoints'])+1)}
    require(needed<=save.keys(),'Complete original SCF WFC manifest absent')
    if action=='Q-SCF':
        require(parent is None,'SCF cannot substitute another density')
        value['scf_validation']=validate_q_scf(value,case,root=root);value['scf_acceptance_status']='PASS'
    else:
        require(parent is not None and metadata['source_preservation_status']=='PASS','Gamma lacks unchanged successful parent')
        binding=metadata['parent_binding']
        require(isinstance(parent_metadata,dict),'Gamma lacks published original SCF provenance')
        expected={'run_id':parent_metadata['run_id'],'save_files':parent_metadata['save_files'],
            'parent_result_sha256':parent_metadata['raw_result_sha256'],'parent_parsed_sha256':parent_metadata['raw_parsed_sha256'],
            'charge_sha256':parent_metadata['density_source_sha256'],'case_sha256':parent_metadata['case_sha256'],
            'qe_reference_profile':profile,'profile_type':'QE_REFERENCE','save_path':'scratch/'+case['qe']['prefix']+'.save',
            'directory':'<WORKBENCH>/'+parent_metadata['source_run_path']}
        require(all(binding.get(k)==v for k,v in expected.items()),'Gamma complete original parent binding differs')
        require(binding['run_id']==parent['run_id'] and binding['charge_sha256']==parent['density_source_sha256'],'Wrong own-SCF Gamma binding')
        require(binding['fermi_energy_ha']==parent['fermi_energy_ha'],'Gamma replaced original SCF mu')
        value.update(source_scf_run_id=parent['run_id'],fermi_energy_ha=parent['fermi_energy_ha'],
          density_binding_scope='Original Q-SCF saved charge copied exactly before bands; atomic+random new-k orbitals')
        value['gamma_validation']=validate_q_gamma(value,parent,case,root=root)
    return value


def export_runs(root,index_path):
    """Explicit four-entry index; never recursively publish a raw run directory."""
    from si_qe_reference import load_history, compare_trend, BASE, PREPARATION
    root=Path(root).resolve();out=root/PUBLIC_DIR
    index=json.loads(Path(index_path).read_text())
    declared_execution=index.get('expected_execution_commit');index=index.get('profiles',index)
    require(declared_execution is None or isinstance(declared_execution,str) and re.fullmatch('[0-9a-f]{40}',declared_execution),'Invalid declared execution identity')
    require(set(index)=={'K6','K8'} and all(set(x)=={'Q-SCF','Q-GAMMA'} for x in index.values()),'Exactly four declared slot references required')
    manifest={'schema_version':1,'base':BASE,'preparation_commit':PREPARATION,'created_utc':utc(),'profiles':{},
              'canonical_scope':'Full native parse, all final SCF k/e/f, Gamma24 and original parent mu; no private array replay',
              'public_transformation':'Only replace actual workbench/home path prefixes by <WORKBENCH>/<HOME>; every numerical token and warning retained'}
    points=load_history(root)
    execution=None
    for profile in ('K6','K8'):
        manifest['profiles'][profile]={};parent=None;parent_metadata=None
        for action in ('Q-SCF','Q-GAMMA'):
            directory=root/index[profile][action];require(directory.resolve()==directory,'Raw directory alias')
            require(root/'.work/phase8c'/profile in directory.parents,'Wrong profile run path')
            receipt=json.loads((directory/'result.json').read_text())
            require(receipt['run_id']==directory.name and receipt['action']==action,'Stale or wrong slot receipt')
            observed=receipt.get('execution_commit')
            if observed is not None:
                require(isinstance(observed,str) and re.fullmatch('[0-9a-f]{40}',observed),'Invalid actual execution SHA')
                execution=execution or observed;require(observed==execution,'Mixed execution commits')
                require(declared_execution is None or observed==declared_execution,'Observed execution differs from explicitly declared index')
            else:require(receipt['execution_status']!='PASS','Successful slot lacks observed execution identity')
            entry={'action':action,'run_id':receipt['run_id'],'execution_status':receipt['execution_status'],'exit_code':receipt['exit_code'],
                'process_exit_code':receipt['process_exit_code'],'execution_commit':observed,'case_sha256':receipt.get('case_sha256'),
                'native_files':{},'payloads':{}}
            for name in NATIVE_NAMES:
                if not (directory/name).exists():continue
                raw=(directory/name).read_bytes();public=redacted(raw.decode(),root).encode()
                rel=f'{PUBLIC_DIR}/{profile}/{action}/{name}.gz';idn=packed(root/rel,public)
                idn.update(path=rel,raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=len(raw))
                entry['native_files'][name]=idn
            if receipt['execution_status']!='PASS':
                entry['failure_reason']=redacted(receipt.get('reason'),root)
                rel=f'{PUBLIC_DIR}/{profile}/{action}/failure.json.gz';idn=packed(root/rel,(json.dumps(redacted(receipt,root),separators=(',',':'),allow_nan=False)+'\n').encode())
                idn.update(path=rel,raw_sha256=sha(directory/'result.json'));entry['payloads']['failure']=idn
                manifest['profiles'][profile][action]=entry
                if action=='Q-GAMMA':points[profile]=None
                continue
            require(set(entry['native_files'])==set(NATIVE_NAMES),'Successful endpoint lacks complete native files')
            metadata=redacted({k:receipt[k] for k in ('action','run_id','execution_status','exit_code','process_exit_code','execution_commit',
                'preparation_commit','case_sha256','density_source_sha256','save_files','source_preservation_status','resource','source_sha256','prepared_sha256','frozen_sha256','upstream','parallelism') if k in receipt},root)
            metadata['source_sha256']=receipt['executed_source_sha256']
            metadata.update(raw_result_sha256=sha(directory/'result.json'),raw_parsed_sha256=sha(directory/'qe-result.json'),source_run_path=directory.relative_to(root).as_posix())
            metadata['upstream']=json.loads((directory/'preflight.json').read_text())['preparation']['upstream']
            metadata['native_files']=entry['native_files']
            if action=='Q-GAMMA':metadata['parent_binding']=redacted(json.loads((directory/'parent-binding.json').read_text()),root)
            native={k:unpacked(root,v['path'],v) for k,v in entry['native_files'].items()}
            actual=parse_public_native(root,profile,native,metadata,parent,parent_metadata)
            require(sha(directory/'qe-result.json')==receipt['parsed_sha256'],'Worker endpoint bytes changed after completion')
            original=redacted(json.loads((directory/'qe-result.json').read_text()),root)
            for key,name in (('xml','qe.xml'),('stdout','qe.stdout'),('stderr','qe.stderr')):
                require(original['raw_sha256'][key]==entry['native_files'][name]['raw_sha256'],'Raw worker output changed after completion: '+name)
            original['raw_sha256']=actual['raw_sha256']
            close(actual,original,'native-vs-worker/'+profile+'/'+action)
            iterations=iteration_rows(native['qe.stdout'].decode(),actual)
            for name,value in (('metadata',metadata),('endpoint',actual),('iterations',iterations),
                               ('identity',redacted(json.loads((directory/'identity.json').read_text()),root))):
                raw=(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n').encode()
                rel=f'{PUBLIC_DIR}/{profile}/{action}/{name}.json.gz';identity=packed(root/rel,raw);identity['path']=rel;entry['payloads'][name]=identity
            entry.update(density_source_sha256=actual['density_source_sha256'],scf_iterations=actual['scf']['iterations'] if actual['scf'] else None,
                         resource=redacted(receipt['resource'],root))
            manifest['profiles'][profile][action]=entry
            if action=='Q-SCF':parent=actual;parent_metadata=metadata
            else:points[profile]=actual['gamma_validation']
    manifest.update(execution_commit=execution,expected_execution_commit=declared_execution,provenance_schema_version=2,
        replay_commit=head(root),replay_source_sha256=sha(Path(__file__)))
    trend=compare_trend(points);write(out/'trend.json',trend,exclusive=True)
    manifest['trend_sha256']=sha(out/'trend.json')
    write(out/'evidence.json',manifest,exclusive=True)
    return replay(root)


def replay(root):
    """Validate every new native gzip, parse it afresh, then recompute all trends."""
    from si_qe_reference import load_history, compare_trend
    root=Path(root).resolve();out=root/PUBLIC_DIR;manifest=json.loads((out/'evidence.json').read_text());points=load_history(root)
    require(manifest['schema_version']==1 and set(manifest['profiles'])=={'K6','K8'},'Invalid public evidence schema')
    require(manifest.get('provenance_schema_version')==2,'Missing complete public parent provenance')
    require(isinstance(manifest.get('replay_commit'),str) and re.fullmatch('[0-9a-f]{40}',manifest['replay_commit']),'Replay commit must be a full SHA')
    for key in ('execution_commit','expected_execution_commit'):
        require(manifest.get(key) is None or isinstance(manifest[key],str) and re.fullmatch('[0-9a-f]{40}',manifest[key]),'Invalid execution SHA: '+key)
    replay_path='scripts/si_qe_reference_evidence.py'
    require(sha(root/replay_path)==manifest['replay_source_sha256']==hashlib.sha256(subprocess.check_output(['git','show',manifest['replay_commit']+':'+replay_path],cwd=root)).hexdigest(),'Public replay implementation identity differs')
    checked=0
    for profile in ('K6','K8'):
        parent=None;parent_metadata=None
        for action in ('Q-SCF','Q-GAMMA'):
            entry=manifest['profiles'][profile][action]
            require(type(entry.get('exit_code')) is int and (entry.get('process_exit_code') is None or type(entry['process_exit_code']) is int),'Invalid native/wrapper exit type')
            require(entry['action']==action and (entry['execution_commit']==manifest['execution_commit'] or entry['execution_commit'] is None and entry['execution_status']!='PASS'),'Mixed public slot identity')
            native={k:unpacked(root,v['path'],v) for k,v in entry['native_files'].items()}
            if entry['execution_status']!='PASS':
                require(entry['exit_code']!=0 and entry.get('failure_reason'),'Unexplained failed slot')
                failure=json.loads(unpacked(root,entry['payloads']['failure']['path'],entry['payloads']['failure']))
                require(all(failure[k]==entry[k] for k in ('action','run_id','execution_status','exit_code','process_exit_code')),'Failure discriminator differs from complete failure receipt')
                if action=='Q-GAMMA':points[profile]=None
                continue
            payload={k:json.loads(unpacked(root,v['path'],v)) for k,v in entry['payloads'].items()}
            metadata=payload['metadata'];require(metadata['native_files']==entry['native_files'],'Conflicting native hash index')
            from run_si_qe import SOURCES, ENV_FILES, HISTORICAL
            from si_qe_reference import prepared_paths
            expected_sets={'source_sha256':set(SOURCES)|{'scripts/si_qe_reference.py','scripts/si_qe_reference_evidence.py','scripts/si_soc_sensitivity.py'},
                           'prepared_sha256':set(prepared_paths())|{'benchmarks/si-soc-splitting-v1/source.json'},
                           'frozen_sha256':set(ENV_FILES)|set(HISTORICAL)}
            for category in ('source_sha256','prepared_sha256','frozen_sha256'):
                require(set(metadata.get(category,{}))==expected_sets[category],'Incomplete executed source/input map: '+category)
                require(isinstance(metadata.get(category),dict) and metadata[category],'Missing executed source/input hash map')
                for rel,expected_hash in metadata[category].items():
                    actual_hash=hashlib.sha256(subprocess.check_output(['git','show',metadata['execution_commit']+':'+rel],cwd=root)).hexdigest() if category=='source_sha256' else sha(root/rel)
                    require(actual_hash==expected_hash,'Recorded execution source/input bytes differ: '+rel)
                    if category=='source_sha256' and rel!=replay_path:require(sha(root/rel)==expected_hash,'Current scientific/parser source differs from actual execution: '+rel)
            require(metadata['run_id']==entry['run_id'] and metadata['execution_commit']==manifest['execution_commit'],'Wrong current slot metadata')
            identity=payload['identity'];require(identity['status']=='PASS' and identity['numerical_executions']==0,'Missing read-only build identity')
            locked=json.loads((root/'benchmarks/si-soc-k-reference-v1/sources.json').read_text())
            require(identity['qe_identity']['binary_sha256']==locked['QE_binary_sha256'],'QE binary identity differs from frozen historical build')
            historical_identity=root/'results/si-soc-sensitivity/Q-environment.json'
            require(sha(historical_identity)=='ab15512328813705856bd42c8cf6e75c22b2fbc7d3bf714bd0081e16df565ad8','Historical build reference bytes changed')
            reference=json.loads(historical_identity.read_text())
            for field in ('julia_version','global_project_sha256','global_manifest_sha256','selected_libraries'):
                require(identity[field]==reference[field],'Different historical build identity: '+field)
            for field,value in reference['qe_identity'].items():require(identity['qe_identity'][field]==value,'Different launcher/JLL identity: '+field)
            resource=metadata['resource']
            require(resource['status']=='PASS' and resource['owned_process_cleanup_status']=='PASS' and type(resource['peak_aggregate_rss_bytes']) is int and 0<resource['peak_aggregate_rss_bytes']<MAX_RSS and resource['nonempty_samples']>0,'Missing or failed resource measurement')
            value=parse_public_native(root,profile,native,metadata,parent,parent_metadata)
            close(value,payload['endpoint'],profile+'/'+action+'/all-native-fields')
            close(iteration_rows(native['qe.stdout'].decode(),value),payload['iterations'],profile+'/'+action+'/iterations')
            if action=='Q-SCF':parent=value;parent_metadata=metadata
            else:points[profile]=value['gamma_validation']
            checked+=1
    expected=json.loads((out/'trend.json').read_text());require(sha(out/'trend.json')==manifest['trend_sha256'],'Trend source hash differs')
    actual=compare_trend(points);close(actual,expected,'trend')
    return {'schema_version':1,'replay_status':'PASS','native_slots_reparsed':checked,'exit_code':0,
            'execution_commit':manifest['execution_commit'],'physical_convergence':'NOT_ESTABLISHED',
            'scope':'All public native bytes and complete endpoint fields; retained failed/review states are not converted into scientific PASS'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('preflight','export','replay'))
    p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--output',type=Path);p.add_argument('--index',type=Path)
    a=p.parse_args(argv)
    try:
        if a.action=='preflight':require(a.output is not None,'Preflight requires unique --output');result=preflight(a.root,a.output)
        elif a.action=='export':require(a.index is not None,'Export requires exact --index');result=export_runs(a.root,a.index)
        else:result=replay(a.root)
        print(json.dumps(result,separators=(',',':'),allow_nan=False));return 0
    except (Exception,KeyboardInterrupt) as error:
        print(json.dumps({'status':'FAIL','exit_code':9,'reason':str(error)},allow_nan=False),file=sys.stderr);return 9


if __name__=='__main__':sys.exit(main())
