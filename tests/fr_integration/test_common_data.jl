# Faults below are owned in-memory adapter copies, never edited UPF files.
function common_test_replace(x;kwargs...)
    names=fieldnames(typeof(x))
    vals=map(n->haskey(kwargs,n) ? kwargs[n] : getfield(x,n),names)
    typeof(x)(vals...)
end

function run_common_data_tests(root,settings)
    mg=load_bound_psp(root;mode=:real_fr)
    si=load_bound_psp(root;mode=:synthetic_scalar_limit)
    @testset "Controlled same-source common data" begin
        @test isnothing(assert_bound_sources(mg))
        @test isnothing(assert_bound_sources(si))
        @test mg.common.element==:Mg && mg.common.z_valence==10
        @test mg.common.functional=="PBESOL" && mg.common.has_so && mg.common.relativistic=="full"
        @test mg.xc_identifiers==[:gga_x_pbe_sol,:gga_c_pbe_sol]
        @test !mg.common.has_nlcc && isnothing(mg.parsed.nlcc)
        @test si.common.element==:Si && si.common.z_valence==4 && si.common.has_nlcc
        @test si.xc_identifiers==[:lda_x,:lda_c_pw]
        @test !si.common.has_so && si.common.relativistic=="scalar"
        @test mg.common.sha256==mg.sha256
        @test si.common.sha256==si.sha256
        @test_throws ArgumentError assert_bound_sources(mg;common=si.common)
        @test_throws ArgumentError assert_bound_sources(mg;channels=si.channels)
        # Copying the genuine token and hash still cannot issue a new bundle.
        forged=common_test_replace(mg)
        @test_throws ArgumentError assert_bound_sources(forged)
        forged_common=common_test_replace(si.common;sha256=mg.sha256,_token=mg._token)
        @test_throws ArgumentError assert_bound_sources(mg;common=forged_common)
        @test_throws ArgumentError assert_bound_sources(mg;channels=deepcopy(mg.channels))
        @test_throws ArgumentError validate_common_request(mg;element=:Si)
        @test_throws ArgumentError validate_common_request(mg;z_valence=8)
        @test_throws ArgumentError validate_common_request(mg;xc_identifiers=[:lda_x,:lda_c_pw])
        @test_throws ArgumentError validate_common_request(si;mode=:real_fr)
        @test_throws ArgumentError validate_common_request(mg;mode=:synthetic_scalar_limit)
        @test_throws ArgumentError load_bound_psp(root;mode=:unknown)
        @test_throws ArgumentError compare_native_common_si(mg,[0.0,0.9])

        c=mg.common; nr=length(c.r); beta_cut=minimum(x.cutoff_radius_index for x in mg.channels.channels)
        @test nr==1510 && beta_cut==160
        @test all(==(nr),values(c.cutoffs))
        @test c.local_ha==mg.parsed.local_./2
        @test c.r2_valence==mg.parsed.rhoatom./(4π)
        @test all(iszero,c.r2_core)
        @test DFTK.eval_psp_local_fourier(c,0.0)==0
        @test DFTK.eval_psp_core_density_fourier(c,0.0)==0
        @test DFTK.eval_psp_core_density_real(c,0.0)==0
        @test isfinite(DFTK.eval_psp_valence_density_fourier(c,0.0))
        @test DFTK.eval_psp_core_density_real(si.common,0.0)==si.parsed.nlcc[1]
        @test DFTK.eval_psp_local_real(c,0.0)==mg.parsed.local_[1]/2
        @test_throws ArgumentError DFTK.eval_psp_valence_density_real(c,0.0)
        @test_throws ArgumentError DFTK.eval_psp_local_real(c,-0.1)
        @test_throws ArgumentError DFTK.eval_psp_core_density_real(si.common,Inf)
        @test_throws ArgumentError DFTK.eval_psp_local_fourier(c,NaN)
        @test_throws ArgumentError DFTK.eval_psp_valence_density_fourier(c,-0.1)
        @test_throws ArgumentError DFTK.eval_psp_core_density_fourier(c,Inf)
        @test_throws ArgumentError DFTK.count_n_proj(c)
        @test_throws ArgumentError DFTK.count_n_proj(c,0)
        @test_throws ArgumentError DFTK.count_n_proj_radial(c,0)
        @test_throws ArgumentError DFTK.eval_psp_projector_fourier(c,1,0,0.9)
        @test_throws ArgumentError DFTK.eval_psp_projector_fourier(c,1,0,[0.9])

        bad=common_test_replace(c;local_ha=copy(c.local_raw_ry))
        @test_throws ArgumentError validate_common_data(bad,mg.parsed)
        @test abs(DFTK.eval_psp_local_fourier(bad,0.9)-DFTK.eval_psp_local_fourier(c,0.9))>1e-3
        bad=common_test_replace(c;r2_valence=c.r.^2 .* c.rhoatom_raw)
        @test_throws ArgumentError validate_common_data(bad,mg.parsed)
        @test abs(DFTK.eval_psp_valence_density_fourier(bad,0.0)-DFTK.eval_psp_valence_density_fourier(c,0.0))>1e-3
        bad=common_test_replace(si.common;r2_core=si.common.nlcc_raw./(4π))
        @test_throws ArgumentError validate_common_data(bad,si.parsed)
        @test abs(DFTK.eval_psp_core_density_fourier(bad,0.0)-DFTK.eval_psp_core_density_fourier(si.common,0.0))>1e-3
        for field in keys(c.cutoffs)
            wrong=merge(c.cutoffs,NamedTuple{(field,)}((beta_cut,)))
            @test_throws ArgumentError validate_common_data(common_test_replace(c;cutoffs=wrong),mg.parsed)
        end
        short=common_test_replace(c;cutoffs=merge(c.cutoffs,(;valence=beta_cut)))
        @test abs(DFTK.eval_psp_valence_density_fourier(short,0.0)-DFTK.eval_psp_valence_density_fourier(c,0.0))>1e-3
        @test_throws ArgumentError validate_common_data(common_test_replace(c;element=:Si),mg.parsed)
        @test_throws ArgumentError validate_common_data(common_test_replace(c;z_valence=2),mg.parsed)
        @test_throws ArgumentError validate_common_data(common_test_replace(c;functional="LDA"),mg.parsed)
        @test_throws ArgumentError validate_common_data(common_test_replace(si.common;has_nlcc=false),si.parsed)
        @test_throws ArgumentError validate_common_data(common_test_replace(c;local_raw_ry=c.local_raw_ry[1:end-1]),mg.parsed)
        nonfinite=copy(c.rhoatom_raw); nonfinite[7]=NaN
        @test_throws ArgumentError validate_common_data(common_test_replace(c;rhoatom_raw=nonfinite),mg.parsed)
        @test_throws ArgumentError validate_common_data(common_test_replace(c;r=reverse(c.r)),mg.parsed)

        # Mutation of an independent loader result is detected even when its
        # identity and hash text remain genuine. The original Mg object is intact.
        mutated=load_bound_psp(root;mode=:real_fr)
        mutated.common.local_ha[1]+=0.1
        @test_throws ArgumentError assert_bound_sources(mutated)
        @test isnothing(assert_bound_sources(mg))
        mutated_channels=load_bound_psp(root;mode=:real_fr)
        mutated_channels.channels.D[1,1]+=0.1
        @test_throws ArgumentError assert_bound_sources(mutated_channels)
        mutated_parsed=load_bound_psp(root;mode=:real_fr)
        mutated_parsed.parsed.rhoatom[8]+=0.1
        @test_throws ArgumentError assert_bound_sources(mutated_parsed)
        # Guard remains active for the actual unchanged FR source.
        @test_throws ErrorException DFTK.PspUpf(mg.parsed;identifier="Expected original SOC rejection")
    end
    qs=Float64.(settings["common_fourier_probes_bohr_inverse"])
    comparison=compare_native_common_si(si,qs)
    @testset "Real scalar Si common-only same-rule reference" begin
        @test comparison.max_error<=settings["thresholds"]["common_data_normalized"]
        @test comparison.local_g0==0
        @test comparison.core_origin==comparison.core_origin_source
        @test all(r->isfinite(r.local_ha)&&isfinite(r.valence)&&isfinite(r.core),comparison.rows)
        @test DFTK.eval_psp_local_fourier(si.common,qs)==[DFTK.eval_psp_local_fourier(si.common,q) for q in qs]
        @test DFTK.eval_psp_valence_density_fourier(si.common,qs)==[DFTK.eval_psp_valence_density_fourier(si.common,q) for q in qs]
        @test DFTK.eval_psp_core_density_fourier(si.common,qs)==[DFTK.eval_psp_core_density_fourier(si.common,q) for q in qs]
    end
    (;si_common=comparison,mg_common=common_data_summary(mg),
      fault_scope="In-memory adapter/channel/parsed copies only; original UPF bytes unchanged")
end
