#!/usr/bin/env julia
# Synthetic finite periodic fields only; no Mg UPF or historical checkpoint is opened.
using Test, LinearAlgebra, JSON3, SHA
include("../scripts/evaluate_common_energy_terms.jl")
const CE=CommonEnergyEvaluation

function synthetic_fields(shape=(40,40,40))
    n=Float64[];v=Float64[]
    for k in 0:shape[3]-1,j in 0:shape[2]-1,i in 0:shape[1]-1
        phase=2pi*(i/shape[1]+2j/shape[2]+3k/shape[3])+.37
        push!(n,.01+.002cos(phase)+.0007sin(2pi*(2i/shape[1]-j/shape[2]+3k/shape[3])))
        push!(v,.4cos(phase)-.1sin(2pi*(2i/shape[1]-j/shape[2]+3k/shape[3])))
    end
    (;n,v)
end

function run_common_energy_tests()
    plan=CE.SD.read_json(joinpath(CE.ROOT,"benchmarks/mg-soc-energy-reference-v1/plan.json"))
    thresholds=plan["thresholds"]
    source_plan=CE.SD.read_json(joinpath(CE.ROOT,plan["historical_binding_plan"]))
    points=source_plan["direct_fourier_miller_points"]
    identity=CE.SD.environment_identity(CE.ROOT,(CE.DFTK,CE.PseudoPotentialIO))
    identity.status=="PASS" && VERSION==v"1.12.7" || error("Frozen synthetic-test environment required")
    CE.DFTK.disable_threading()
    @testset "Synthetic static common density evaluation" begin
        shape=(40,40,40);volume=1000.;lattice=10Matrix{Float64}(I,3,3)
        field=synthetic_fields(shape)
        # Regression for the actual request boundary: JSON3's typed Dict keeps
        # integer-valued JSON numbers as Int64, even from a 1000.0 token.
        parsed=JSON3.read("{\"volume_bohr3\":1000.0,\"fft_size\":[40,40,40]}",Dict{String,Any})
        @test parsed["volume_bohr3"] isa Integer
        setup=CE.evaluation_grid(parsed)
        @test setup.volume isa Float64
        @test setup.grid.fft_normalization isa Float64
        parsed_fft=CE.DFTK.fft(setup.grid,fill(.01,shape))
        @test eltype(parsed_fft)==ComplexF64
        @test abs(real(parsed_fft[1])/sqrt(setup.volume)*setup.volume-10)<=1e-12
        grid=CE.DFTK.FFTGrid(shape,volume,CE.DFTK.CPU())
        modes=[Tuple(g) for g in vec(CE.DFTK.G_vectors(grid))]
        coefficients=vec(CE.DFTK.fft(grid,reshape(field.n,shape)))/sqrt(volume)
        @test length(modes)==64000
        rep=CE.reconstruct_density(modes,coefficients,grid,volume,thresholds;points)
        @test rep.report.status=="PASS"
        @test rep.report.source_support_count==rep.report.native_workspace_count==64000
        @test CE.reconstruction_difference(field.n,rep.n,thresholds).status=="PASS"
        @test rep.report.imaginary_max<=1e-15
        @test rep.report.fourier_roundtrip_relative_l2<=1e-14
        @test maximum(row.absolute_error for row in rep.report.directional_checks)<=1e-14
        @test CE.array_hash(field.n)!=CE.array_hash(rep.n) # FFT rounding is distinct from source identity
        @test rep.report.unsaved_physical_modes=="NOT_ESTABLISHED_ZERO"
        # Independent sparse analytic series, with a genuinely complex coefficient.
        sparse_modes=[(0,0,0),(1,2,3),(-1,-2,-3),(2,-1,3),(-2,1,-3)]
        sparse_coeffs=ComplexF64[.01,.001cis(.37),.001cis(-.37),-.00035im,.00035im]
        sparse_rep=CE.reconstruct_density(sparse_modes,sparse_coeffs,grid,volume,thresholds;points)
        @test maximum(abs,sparse_rep.n-field.n)<=1e-14
        @test sparse_rep.report.source_support_count==5
        @test sparse_rep.report.missing_workspace_bins==63995
        @test sparse_rep.source_millers==sparse_modes
        @test any(!x.source_present for x in sparse_rep.report.directional_checks)
        perm=[5,2,1,4,3]
        shuffled=CE.reconstruct_density(sparse_modes[perm],sparse_coeffs[perm],grid,volume,thresholds;points)
        @test shuffled.n==sparse_rep.n
        @test_throws ErrorException CE.reconstruct_density(sparse_modes,sparse_coeffs[perm],grid,volume,thresholds;points)
        @test_throws ErrorException CE.reconstruct_density(vcat(sparse_modes,[sparse_modes[1]]),vcat(sparse_coeffs,[sparse_coeffs[1]]),grid,volume,thresholds;points)
        @test_throws ErrorException CE.reconstruct_density(vcat(sparse_modes,[(20,0,0)]),vcat(sparse_coeffs,[0im]),grid,volume,thresholds;points)
        @test_throws ErrorException CE.reconstruct_density(vcat(sparse_modes,[(40,0,0)]),vcat(sparse_coeffs,[0im]),grid,volume,thresholds;points)
        @test_throws ErrorException CE.reconstruct_density(sparse_modes[2:end],sparse_coeffs[2:end],grid,volume,thresholds;points)
        @test_throws ErrorException CE.reconstruct_density(sparse_modes,fill(complex(NaN,0.),5),grid,volume,thresholds;points)
        wrongsign=CE.reconstruct_density(sparse_modes,conj.(sparse_coeffs),grid,volume,thresholds;points)
        @test CE.reconstruction_difference(field.n,wrongsign.n,thresholds).status=="FAIL"
        wrongweight=CE.reconstruct_density(sparse_modes,sparse_coeffs/3,grid,volume,thresholds;points)
        @test wrongweight.report.status=="UNSUPPORTED_REPRESENTATION"
        wrongcapacity=CE.reconstruct_density(sparse_modes,2sparse_coeffs,grid,volume,thresholds;points)
        @test wrongcapacity.report.density.electron_count≈20
        @test wrongcapacity.report.status=="UNSUPPORTED_REPRESENTATION"
        complexbad=copy(sparse_coeffs);complexbad[2]+=.0001im
        @test_throws ErrorException CE.reconstruct_density(sparse_modes,complexbad,grid,volume,thresholds;points)
        negative=copy(field.n);negative[1]=-1e-5;negative[2]+=(field.n[1]+1e-5)
        bad=CE.density_diagnostics(negative,volume,thresholds)
        @test bad.status=="UNSUPPORTED_REPRESENTATION"
        @test bad.negative_count==1
        @test !bad.normalization_applied && !bad.clipping_applied
        nyquist=CE.reconstruct_density([(0,0,0),(-20,0,0)],ComplexF64[.01,.002],grid,volume,thresholds;points)
        @test nyquist.report.status=="PASS"
        @test nyquist.n[1]≈.012 && nyquist.n[2]≈.008

        # No atoms or pseudopotential: this is only a synthetic nonuniform GGA
        # evaluation in the frozen scalar-charge basis, with an analytic local V.
        model=CE.DFTK.Model(lattice;n_electrons=10,terms=[CE.DFTK.Xc(CE.IDS)],
            spin_polarization=:none,temperature=.001,smearing=CE.DFTK.Smearing.FermiDirac(),symmetries=false)
        basis=CE.DFTK.PlaneWaveBasis(model;Ecut=15.,fft_size=shape,
            kgrid=CE.DFTK.ExplicitKpoints([[0.,0.,0.]],[1.]))
        static=(;basis,localterm=CE.DFTK.TermAtomicLocal(reshape(field.v,shape)),xcterm=only(basis.terms))
        evaluated=CE.evaluate_density(static,field.n,"SYNTHETIC_NONUNIFORM",thresholds)
        @test evaluated.summary.status=="PASS"
        @test evaluated.summary.xc_call_count==1
        @test abs(evaluated.summary.local_integral_minus_native_energy_ha)<=1e-12
        @test evaluated.summary.backend.libxc_runtime_version=="7.0.0"
        @test evaluated.summary.backend.libxc_wrapper_version=="0.3.26"
        @test !evaluated.summary.backend.generic_dftfunctionals_evaluation_used
        @test evaluated.summary.backend.full_gga_potential
        @test all(r->r.backend=="Libxc Float64 CPU" && r.density_type=="Matrix{Float64}",evaluated.summary.backend.functionals)
        @test [r.identifier for r in evaluated.summary.backend.functionals]==string.(CE.IDS)
        @test all(p.default==p.actual_default_object for row in evaluated.summary.backend.functionals for p in row.parameters)
        @test !isempty(evaluated.summary.backend.functionals[1].parameters)
        @test all(row->row.dispatch_line==479 && row.inner_line==117,evaluated.summary.backend.functionals)
        @test evaluated.summary.backend.potential_threshold==0
        # Integration by parts supplies a distinct full-GGA check. A bare V_rho
        # differs materially on this nonuniform density and cannot substitute.
        density=CE.DFTK.LibxcDensities(basis,1,reshape(field.n,shape...,1),nothing)
        raw=CE.DFTK.potential_terms(static.xcterm.functionals,density)
        bare=vec(raw.Vρ)
        expected_ixc=basis.dvol*(dot(field.n,bare)+2sum(vec(density.σ_real).*vec(raw.Vσ)))
        @test norm(evaluated.arrays.vxc-bare)>1e-3
        @test abs(evaluated.summary.integral_n_vxc_ha-expected_ixc)<=1e-11
        @test abs(evaluated.summary.integral_n_vxc_ha-basis.dvol*dot(field.n,bare))>1e-5
        @test CE.array_hash(evaluated.arrays.n)==CE.array_hash(field.n)
        @test CE.evaluate_density(static,negative,"SYNTHETIC_NEGATIVE",thresholds).summary.xc_call_count==0

        uniform=fill(.01,prod(shape));other=CE.evaluate_density(static,uniform,"SYNTHETIC_UNIFORM",thresholds)
        response=CE.density_response(evaluated,other,basis,thresholds)
        @test response.status=="PASS"
        @test abs(response.local_real_minus_fourier_ha)<=1e-12
        @test abs(response.xc_density_response_ha-response.xc_first_order_at_Q_ha-response.xc_curvature_remainder_ha)<=1e-13
        constant=0.071;ne=basis.dvol*sum(field.n);pc=.123
        before=CE.DFTK.ene_ops(static.localterm,basis,nothing,nothing;ρ=reshape(field.n,shape...,1)).E
        shifted=CE.DFTK.TermAtomicLocal(reshape(field.v.+constant,shape))
        after=CE.DFTK.ene_ops(shifted,basis,nothing,nothing;ρ=reshape(field.n,shape...,1)).E
        @test abs(after-before-ne*constant)<=1e-12
        @test abs((after+pc-ne*constant)-(before+pc))<=1e-12
        @test abs((after+pc)-(before+pc))>0.7
        @test abs((after+pc-ne*constant+ne*constant)-(before+pc))>0.7
        @test abs(other.summary.xc_ha-other.summary.integral_n_vxc_ha)>1e-3
        mktempdir() do tmp
            good=joinpath(tmp,"synthetic.csv")
            write(good,"m1,m2,m3,A_out_real,A_out_imag\n0,0,0,0.01,0.0\n1,2,3,0.1,0.2\n")
            table=CE.read_coefficient_csv(good,["A_out"])
            @test table.data["A_out"][2]==.1+.2im
            open(good,"a") do io;write(io,"1,2,3,0.2,0.1\n");end
            @test_throws ErrorException CE.read_coefficient_csv(good,["A_out"])
            write(good,"m1,m2,m3,A_out_real,A_out_imag\n0,0,0,NaN,0.0\n")
            @test_throws ErrorException CE.read_coefficient_csv(good,["A_out"])
        end
        @test CE.main(["--help"])==0
        @test CE.main(String[])==2
        println("SYNTHETIC_BACKEND_METADATA ",JSON3.write(CE.SD.public_data(evaluated.summary.backend,CE.ROOT)))
    end
end

abspath(PROGRAM_FILE)==(@__FILE__) && run_common_energy_tests()
