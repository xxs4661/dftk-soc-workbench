"""Synthetic driver helpers with stdlib Julia only; never builds a Si context.

These tests load function definitions and use invented in-memory metadata,
arrays and a routing stub. They do not execute SCF, eigen/occupation solving,
a real pseudopotential or the workbench Julia environment.
"""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(os.environ.get('SOC_EXTRA_TEST_ROOT', Path(__file__).resolve().parents[1]))
DRIVER = Path(os.environ.get('SOC_EXTRA_TEST_DRIVER', ROOT / 'benchmarks/soc-extra-v1/driver.jl'))
SCF = Path(os.environ.get('SOC_EXTRA_TEST_SCF', ROOT / 'prototypes/soc_scf/scf.jl'))
ENTRY = Path(os.environ.get('SOC_EXTRA_TEST_ENTRY', ROOT / 'scripts/run_si_soc.jl'))
SOLVER = Path(os.environ.get('SOC_EXTRA_TEST_SOLVER', ROOT / 'prototypes/soc_scf/solver.jl'))
JULIA = shutil.which('julia')


@unittest.skipUnless(JULIA, 'NOT_RUN: existing Julia executable unavailable')
class SyntheticDriver(unittest.TestCase):
    def run_julia(self, source):
        environment = dict(os.environ, JULIA_PKG_OFFLINE='true', JULIA_NUM_THREADS='1',
                           OPENBLAS_NUM_THREADS='1', JULIA_LOAD_PATH='@stdlib')
        program = ('using Test, Serialization\n'
                   'const PHASE6C_ROOT=ARGS[1]\n'
                   'include(ARGS[2])\n' + source)
        result = subprocess.run([JULIA, '--startup-file=no', '--project=@stdlib', '-e', program, str(ROOT), str(DRIVER), str(SCF), str(ENTRY), str(SOLVER)],
                                env=environment, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, 'Synthetic Julia helper failed:\n' + result.stdout + result.stderr)

    def test_explicit_extra_route_and_rejections(self):
        self.run_julia(r'''
            called=Ref{Any}(nothing)
            function si_run(action,outdir,parent;kwargs...)
                called[]=(;action,outdir,parent,options=(;kwargs...));return 0
            end
            @test si_extra_main(["X-K6-SCF","synthetic-output","--extra-profile","K6","--extra-contract","synthetic-auth"])==0
            @test called[].options.backend=="soc-core"
            @test called[].options.extra_profile=="K6"
            @test isnothing(called[].parent)
            @test si_extra_main(["X-K6-GAMMA","synthetic-output","synthetic-parent","--extra-profile","K6","--extra-contract","synthetic-auth"])==0
            @test called[].parent=="synthetic-parent"
            for args in (["X-K8-SCF","out","--extra-profile","K8","--extra-contract","auth"],
                         ["X-B0-SCF","out","--extra-profile","K6","--extra-contract","auth"],
                         ["X-K6-GAMMA","out","--extra-profile","K6","--extra-contract","auth"],
                         ["X-K6-SCF","out","--extra-profile","K6"])
                old=called[];@test si_extra_main(args)==2;@test called[]===old
            end
        ''')

    def test_actual_coordinate_pairs_include_half_boundary(self):
        self.run_julia(r'''
            axis=[0.,1/6,1/3,-1/2,-1/3,-1/6]
            k=[(;coordinate=[x,y,z]) for x in axis for y in axis for z in axis]
            b=(;kpoints=k)
            e=[fill(sum(abs2,p.coordinate),24) for p in k]
            # Full inverse pairs have identical invented spectra/occupations.
            raw=(;eigenvalues=e,f=[fill(.25,24) for _ in k])
            settings=Dict("thresholds"=>Dict("time_reversed_spectrum_ha"=>1e-7,"paired_occupation_abs"=>1e-6))
            result=si_extra_spectral_pairs(b,raw,settings)
            @test result.status=="PASS"
            @test length(result.records)==216
            @test sort([r.target for r in result.records])==collect(1:216)
            boundary=findfirst(x->x.coordinate==[-.5,-.5,-.5],k)
            @test result.records[boundary].target==boundary
            @test result.max_eigenvalue_difference_ha<=1e-14
            broken=(;kpoints=vcat(k,k[1:1]))
            @test_throws ErrorException si_extra_spectral_pairs(broken,raw,settings)
            # Remove one member of a non-self pair, not the self-inverse boundary.
            absent=(;kpoints=[p for p in k if p.coordinate!=[0.,0.,1/6]])
            @test_throws ErrorException si_extra_spectral_pairs(absent,raw,settings)
            altered=deepcopy(raw);altered.eigenvalues[2][1]+=1e-3
            @test si_extra_spectral_pairs(b,altered,settings).status=="REVIEW_REQUIRED"
        ''')

    def test_counting_serializer_observes_exact_bytes(self):
        self.run_julia(r'''
            using SHA
            filehash(path)=bytes2hex(SHA.sha256(read(path)))
            @test si_extra_buffer_sources()==SI_EXTRA_BUFFER_SOURCES
            for n in (1,31,32,33,128,100000,100000000)
                bits=8sizeof(Int)-leading_zeros(n)
                independently_evaluated=max(32,n+3*(1<<(bits*7÷8))+n÷8)
                @test max(32,Base.overallocation(n))==independently_evaluated
            end
            for value in ((;a=reshape(ComplexF64.(1:24),4,6),b=[1.,2.],label="synthetic"),
                          Dict("synthetic"=>Any[[1,2,3],nothing,true]), UInt8[0,1,255])
                original=deepcopy(value)
                io=IOBuffer();serialize(io,value);actual=take!(io)
                @test si_extra_serialized_length(value)==length(actual)
                @test value==original
            end
        ''')

    def test_compact_record_retains_scientific_scalars_without_mutation(self):
        self.run_julia(r'''
            diag=(;target_states=24,internal_energy_ha=-1.,free_energy_ha=-1.1,
                   entropy_energy_ha=-.1,energy_terms_ha=Dict("synthetic"=>-1.),
                   real_electron_count=8.,max_gram_norm=1e-12,
                   self_density_h_rayleigh_residuals_ha=[[1.,2.]])
            record=Dict{String,Any}("map_index"=>2,"map_role"=>"iteration","status"=>"CONTINUE",
                "unmixed_residual_l2"=>.2,"closure_checks_passed"=>false,"diagnostics"=>diag)
            old=deepcopy(record);small=si_extra_compact_map(record)
            @test record==old
            @test small["map_index"]==2 && small["unmixed_residual_l2"]==.2
            @test small["diagnostics"].energy_terms_ha==diag.energy_terms_ha
            @test small["diagnostics"].max_gram_norm==1e-12
            @test !hasproperty(small["diagnostics"],:self_density_h_rayleigh_residuals_ha)
        ''')


    def test_complete_edited_julia_files_parse(self):
        self.run_julia(r'''
            function reject_parse_errors(value)
                value isa Expr || return
                @test !(value.head in (:error,:incomplete))
                foreach(reject_parse_errors,value.args)
            end
            foreach(path->reject_parse_errors(Meta.parseall(read(path,String))),ARGS[2:5])
        ''')

    def test_two_map_stop_reuses_controller_and_preserves_failures(self):
        self.run_julia(r'''
            module Controller
                using LinearAlgebra,SHA
                include(joinpath(Main.PHASE6C_ROOT,"prototypes/spinor/scf.jl"))
            end
            module FI
                runtime_enabled(ctx)=ctx==:owned
            end
            # Definitions only: the test never calls soc_map or soc_scf.
            include(ARGS[3])
            function synthetic_map(n,imap,closing)
                out=[4+1/(imap+1),4-1/(imap+1)]
                sin=Controller.density_summary(n,1.;n_electrons=8)
                sout=Controller.density_summary(out,1.;n_electrons=8)
                (;n_out=out,raw=(;synthetic=true,map=imap),closure_ok=false,
                  diagnostics=(;consumed_input_sha256=sin.sha256,orbital_density_sha256=sout.sha256))
            end
            options=(;dvol=1.,alpha=.1,max_maps=400,density_tol=1e-8,electron_tol=1e-8,n_electrons=8)
            for ctx in (:legacy,:owned)
                seen=Any[]
                observe=(r,raw)->push!(seen,(;map=r["map_index"],status=r["status"]))
                result=_extra_diagnostic_iteration(ctx,synthetic_map,[4.,4.];callback=observe,limit=2,options...)
                @test result.status=="PILOT_COMPLETED_NOT_SCF_CONVERGED"
                @test result.map_count==length(result.history)==length(seen)==2
                @test result.formal_scf===false && result.converged===false
                @test all(r.status=="CONTINUE" for r in seen)
                @test result.raw==(;synthetic=true,map=2)
                @test_throws ErrorException _extra_diagnostic_iteration(ctx,synthetic_map,[4.,4.];callback=observe,limit=3,options...)
                fault=(n,i,c)->i==2 ? Base.error("Synthetic map failure") : synthetic_map(n,i,c)
                error=try
                    _extra_diagnostic_iteration(ctx,fault,[4.,4.];callback=observe,limit=2,options...);nothing
                catch e;e;end
                @test error isa Controller.DensityMapFailure
                @test occursin("Synthetic map failure",sprint(showerror,error))
                broken_callback=(r,raw)->r["map_index"]==2 && r["status"]=="CONTINUE" ? Base.error("Synthetic callback failure") : nothing
                error=try
                    _extra_diagnostic_iteration(ctx,synthetic_map,[4.,4.];callback=broken_callback,limit=2,options...);nothing
                catch e;e;end
                @test !isnothing(error)
                @test occursin("Synthetic callback failure",sprint(showerror,error))
            end
        ''')


if __name__ == '__main__':
    unittest.main()
