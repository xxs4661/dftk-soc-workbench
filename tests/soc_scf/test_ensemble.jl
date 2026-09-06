# Synthetic spectra/occupations only. No physical eigensolve or SCF is run here.
function run_ensemble_tests(settings)
    cfg=settings["ensemble"]
    tau=.02;mu_known=.17;weights=[.25,.75]
    expected=[[.8,.4,.1],[.7,.2,.05]]
    levels=[[mu_known+tau*log((1-f)/f) for f in fk] for fk in expected]
    ne=sum(weights.*sum.(expected))
    solved=fermi_occupations(levels,weights,ne,tau;
        electron_tol=cfg["root_electron_atol"],maxiter=cfg["root_maxiter"])
    @testset "Global weighted capacity-one Fermi root" begin
        @test abs(solved.mu-mu_known)<=1e-12
        @test maximum(maximum(abs.(a-b)) for (a,b) in zip(solved.f,expected))<=1e-11
        @test abs(solved.report.electron_residual)<=cfg["root_electron_atol"]
        @test solved.report.capacity_per_state==1
        @test 0<solved.report.iterations<=256
        @test abs(sum(weights.*sum.(solved.f))-ne)<=1e-12
        @test abs(sum(solved.f[1])-sum(solved.f[2]))>.1
        @test solved.report.electrons_per_k_weighted==weights.*sum.(solved.f)
        @test abs(sum(weights.*sum.(2 .* solved.f))-ne)>.5
        @test_throws EnsembleError ensemble_free_energy(0.0,2 .* solved.f,weights,tau)
        @test_throws EnsembleError fermi_occupations([[0.,1.]],[1.],3.,tau)
        @test_throws EnsembleError fermi_occupations([[0.,1.]],[1.],2.,tau)
        @test_throws EnsembleError fermi_occupations(levels,weights,ne,tau;maxiter=1)
        @test_throws EnsembleError fermi_occupations(levels,weights,ne,tau;maxiter=257)
        @test_throws EnsembleError fermi_occupations(levels,weights,ne,tau;electron_tol=1e-6)
        @test_throws EnsembleError fermi_occupations(levels,[.5,.4],ne,tau)
        @test_throws EnsembleError fermi_occupations(levels,[1.1,-.1],ne,tau)
        @test_throws EnsembleError fermi_occupations(levels,[NaN,.5],ne,tau)
        @test_throws EnsembleError fermi_occupations([[NaN,1.]],[1.],1.,tau)
        perm=[3,1,2]
        reordered=fermi_occupations([e[perm] for e in levels],weights,ne,tau)
        @test maximum(maximum(abs.(a-b[perm])) for (a,b) in zip(reordered.f,solved.f))<=1e-11
        @test abs(reordered.mu-solved.mu)<=1e-11
        @test maximum(maximum(abs.(a-b)) for (a,b) in zip(reordered.report.highest_two,solved.report.highest_two))<=1e-11
        @test_throws EnsembleError fermi_occupations([Float64[]],[1.],1.,tau)
        @test_throws EnsembleError fermi_occupations(levels,weights,ne,0.)
        @test_throws EnsembleError fermi_occupations(levels,weights,-1.,tau)
        @test_throws EnsembleError fermi_occupations(levels,weights,ne,Inf)
        @test_throws EnsembleError fermi_occupations([[-1e308,1e308]],[1.],1.,1e308)
    end

    shifted=fermi_occupations([e .+ 7.25 for e in levels],weights,ne,tau)
    entropy=ensemble_free_energy(-3.0,solved.f,weights,tau)
    shifted_entropy=ensemble_free_energy(-3.0,shifted.f,weights,tau)
    @testset "Energy reference shift preserves occupations and entropy" begin
        @test abs(shifted.mu-solved.mu-7.25)<=1e-11
        @test maximum(maximum(abs.(a-b)) for (a,b) in zip(shifted.f,solved.f))<=1e-11
        @test abs(shifted_entropy.entropy_dimensionless-entropy.entropy_dimensionless)<=1e-11
        @test levels==[[mu_known+tau*log((1-f)/f) for f in fk] for fk in expected]
    end

    plateau_levels=[[-10.,10.],[-8.,12.]]
    plateau=fermi_occupations(plateau_levels,[.2,.8],1.,cfg["tau_ha"])
    @testset "Stable extremes and reproducible gap plateau" begin
        @test fermi_logistic(Inf)==0
        @test fermi_logistic(-Inf)==1
        @test fermi_logistic(1e6)==0 && fermi_logistic(-1e6)==1
        @test 0<fermi_logistic(700.)<1e-300
        @test fermi_logistic(0.)==.5
        @test_throws EnsembleError fermi_logistic(NaN)
        extreme=fermi_occupations([[-1e4,0.,1e4]],[1.],1.5,cfg["tau_ha"])
        @test extreme.f==[[1.,.5,0.]]
        @test all(isfinite,extreme.f[1])
        @test plateau.report.numerical_plateau
        @test plateau.mu==1.0
        @test plateau.report.plateau_gap_ha==(-8.,10.)
        @test plateau.report.plateau_interval_ha==(-3.5,5.5)
        @test plateau.f==[[1.,0.],[1.,0.]]
        @test plateau.report.iterations==0
        again=fermi_occupations(plateau_levels,[.2,.8],1.,cfg["tau_ha"])
        @test again.mu==plateau.mu && again.f==plateau.f && again.report==plateau.report
        changed=fermi_occupations([e .+ 4.25 for e in plateau_levels],[.2,.8],1.,cfg["tau_ha"])
        @test changed.mu==plateau.mu+4.25 && changed.f==plateau.f
        stationarity=occupation_stationarity(plateau_levels,plateau.f,plateau.mu,cfg["tau_ha"])
        @test stationarity.checked_states==0 && stationarity.excluded_states==4
        @test stationarity.status=="NO_RESOLVABLE_PARTIAL_OCCUPATIONS"
    end

    @testset "Physical spinor entropy and one E to F conversion" begin
        endpoint=ensemble_free_energy(-2.,[[0.,1.]],[1.],tau)
        half=ensemble_free_energy(-2.,[[.5]],[1.],tau)
        tiny=ensemble_free_energy(0.,[[fermi_logistic(700.)]],[1.],tau)
        @test endpoint.entropy_dimensionless==0 && endpoint.entropy_energy_ha==0
        @test endpoint.free_energy_ha==endpoint.internal_energy_ha
        @test abs(half.entropy_dimensionless-log(2))<=1e-15
        @test half.entropy_energy_ha<0 && half.free_energy_ha<half.internal_energy_ha
        @test tiny.entropy_dimensionless>0 && isfinite(tiny.entropy_dimensionless)
        @test entropy.entropy_dimensionless>=0 && entropy.entropy_energy_ha<=0
        @test abs(entropy.free_energy_ha-entropy.internal_energy_ha-entropy.entropy_energy_ha)<=1e-12
        @test entropy.entropy_capacity_per_state==1
        doubled=ensemble_free_energy(-3.,[vcat(f,f) for f in solved.f],weights,tau)
        @test abs(doubled.entropy_dimensionless-2entropy.entropy_dimensionless)<=1e-14
        @test abs(doubled.entropy_energy_ha-entropy.entropy_energy_ha)>1e-3
        @test_throws EnsembleError ensemble_free_energy(NaN,solved.f,weights,tau)
        @test_throws EnsembleError ensemble_free_energy(0.,[[NaN]],[1.],tau)
        @test_throws EnsembleError ensemble_free_energy(0.,[[-.01]],[1.],tau)
        @test_throws EnsembleError ensemble_free_energy(0.,[[1.01]],[1.],tau)
        @test_throws EnsembleError ensemble_free_energy(0.,[[.5]],[1.],-tau)
    end

    stationarity=occupation_stationarity(levels,solved.f,solved.mu,tau;
        endpoint_margin=cfg["stationarity_endpoint_margin"])
    energy(f)=sum(weights[k]*sum(levels[k].*f[k]) for k in eachindex(weights))
    function free(f;entropy_factor=1.)
        e=ensemble_free_energy(energy(f),f,weights,tau)
        e.internal_energy_ha+entropy_factor*e.entropy_energy_ha
    end
    function perturb(f,t)
        changed=deepcopy(f);changed[1][1]+=t;changed[1][2]-=t;changed
    end
    @testset "Finite-temperature constrained occupation stationarity" begin
        @test stationarity.checked_states==6 && stationarity.excluded_states==0
        @test stationarity.max_abs_residual_ha<=cfg["stationarity_abs_ha"]
        @test_throws EnsembleError occupation_stationarity(levels,[[.5]],solved.mu,tau)
        @test_throws EnsembleError occupation_stationarity(levels,solved.f,NaN,tau)
        h=1e-6
        derivative=(free(perturb(solved.f,h))-free(perturb(solved.f,-h)))/(2h)
        @test abs(derivative)<=1e-9
        @test abs(sum(weights.*sum.(perturb(solved.f,h)))-ne)<=1e-12
        wrong_sign=(free(perturb(solved.f,h);entropy_factor=-1)-free(perturb(solved.f,-h);entropy_factor=-1))/(2h)
        wrong_twice=(free(perturb(solved.f,h);entropy_factor=2)-free(perturb(solved.f,-h);entropy_factor=2))/(2h)
        @test abs(wrong_sign)>1e-3 && abs(wrong_twice)>1e-3
        center=perturb(solved.f,.04)
        gradient(o,e)=e+tau*(log(o)-log1p(-o))
        analytic=weights[1]*(gradient(center[1][1],levels[1][1])-gradient(center[1][2],levels[1][2]))
        numeric=(free(perturb(center,h))-free(perturb(center,-h)))/(2h)
        @test abs(numeric-analytic)<=1e-9
        @test abs(analytic)>1e-3
    end

    trlevels=[[-1.,-1.,.1,.1,.8,.8],[-.8,-.3,0.,.4,.9,1.3],[-.8,-.3,0.,.4,.9,1.3]]
    trresult=fermi_occupations(trlevels,fill(1/3,3),3.1,.2)
    @testset "Global TR pairs and degenerate states share occupations" begin
        @test trresult.f[2]==trresult.f[3]
        @test all(trresult.f[1][i]==trresult.f[1][i+1] for i in 1:2:5)
        @test trresult.f[2][1]!=trresult.f[2][2]
        @test abs(sum(trresult.f[1])-sum(trresult.f[2]))>1e-3
        @test abs(trresult.report.electron_residual)<=1e-12
    end

    events=NamedTuple[]
    @testset "Highest two physical target bands and bounded expansion" begin
        for target in (24,32,40,48)
            f=[vcat(ones(10),zeros(target-10)) for _ in 1:3]
            good=band_completeness(f;threshold=cfg["boundary_occupation_max"])
            @test good.status=="PASS" && isnothing(good.next_target)
            unresolved=[fill(.2,target) for _ in 1:3]
            event=band_completeness(unresolved);push!(events,event)
            @test event.status==(target==48 ? "INSUFFICIENT_BANDS" : "EXPAND")
            @test event.next_target==(target==48 ? nothing : target+8)
        end
        @test [e.target for e in events]==[24,32,40,48]
        penultimate=[vcat(ones(10),fill(1e-9,13),0.)]
        @test band_completeness(penultimate).status=="EXPAND"
        edge=[vcat(ones(10),fill(1e-10,14))]
        @test band_completeness(edge).status=="PASS"
        @test_throws EnsembleError band_completeness([zeros(24),zeros(32)])
        @test_throws EnsembleError band_completeness([zeros(30)]) # Six auxiliaries cannot be counted as targets.
        @test_throws EnsembleError band_completeness([zeros(56)])
        @test_throws EnsembleError band_completeness([vcat(zeros(23),.1)])
        @test_throws EnsembleError band_completeness([fill(NaN,24)])
        @test_throws EnsembleError band_completeness([zeros(24)];threshold=1e-3)
    end
    (;scope="Synthetic finite-temperature spectra, occupations, entropy and band-tail diagnostics; no physical solve",
      known_spectrum=solved.report,stationarity,plateau=plateau.report,entropy,band_expansion_events=events,
      tr_occupation_max_difference=maximum(abs.(trresult.f[2]-trresult.f[3])))
end
