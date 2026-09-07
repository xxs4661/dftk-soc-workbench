# In-memory malformed metadata and Gaussian functions are synthetic test fixtures.
# They are never written as UPF files or represented as physical pseudopotentials.
channel_test_error(a,b) = norm(a-b)/max(norm(a),norm(b),1)
function channel_test_replace(object;kwargs...)
    typeof(object)((get(kwargs,name,getfield(object,name)) for name in fieldnames(typeof(object)))...)
end

function channel_test_record(l,tj,position;source_index=position,r=collect(range(0,2;length=41)))
    (;source_index,parsed_position=position,l,two_j=tj,r,
      beta_raw=r.^(l+1).*exp.(-r.^2),cutoff_index=length(r))
end

# Independent elementary recurrence evaluated with 256-bit arithmetic avoids the
# cancellation of Float64 sin/cos at small arguments. It does not call DFTK's
# Bessel/Hankel functions or the production power series.
function independent_jl(l,x)
    iszero(x) && return l == 0 ? 1.0 : 0.0
    setprecision(BigFloat,256) do
        z=BigFloat(x); jm=sin(z)/z
        l == 0 && return Float64(jm)
        j=(sin(z)-z*cos(z))/z^2
        for order in 1:l-1
            jm,j=j,(2order+1)*j/z-jm
        end
        Float64(j)
    end
end

function independent_radial_trapz(model,index,q)
    c=model.channels[index]; stop=c.cutoff_radius_index
    r=c.r[1:stop]; b=c.beta_internal[1:stop]
    values=[4π*r[i]*b[i]*independent_jl(c.l,q*r[i]) for i in eachindex(r)]
    sum((r[i+1]-r[i])*(values[i+1]+values[i])/2 for i in 1:length(r)-1)
end

function run_channels_radial_tests(mg,si,settings)
    gaussian_diagnostics=NamedTuple[]; real_diagnostics=NamedTuple[]
    @testset "FR source/parsed positions and paired units" begin
        saved_betas=deepcopy(mg.nonlocal.betas);saved_d=copy(mg.nonlocal.dij)
        model=fr_channels(mg)
        @test length(model.channels)==length(mg.nonlocal.betas)
        @test model.D_raw_parsed==mg.nonlocal.dij
        @test mg.nonlocal.dij==saved_d
        @test all(a.beta==b.beta for (a,b) in zip(mg.nonlocal.betas,saved_betas))
        for (i,a) in enumerate(model.channels),(j,b) in enumerate(model.channels)
            @test model.D[i,j]==2mg.nonlocal.dij[a.parsed_beta_position,b.parsed_beta_position]
        end
        @test all(c.relbeta_source_index==c.source_beta_index for c in model.channels)
        @test any(count(c->(c.l,c.two_j)==key,model.channels)>1 for key in unique((c.l,c.two_j) for c in model.channels))
        alternative=fr_channels(mg;unit_convention=:alternative)
        @test alternative.D==model.D/4
        @test all(a.beta_internal==2b.beta_internal for (a,b) in zip(alternative.channels,model.channels))

        # Source IDs intentionally disagree with parsed/D positions. Reordering
        # by l must permute both D axes using parsed positions, never source IDs.
        rec=[channel_test_record(1,1,1;source_index=2),channel_test_record(0,1,2;source_index=1)]
        small=synthetic_channel_model(rec,[3.0 0;0 7.0])
        @test [c.parsed_beta_position for c in small.channels]==[2,1]
        @test [c.source_beta_index for c in small.channels]==[1,2]
        @test diag(small.D)==[14.0,6.0]
        @test diag(small.D)!=2 .* [3.0,7.0]  # Would expose direct source-ID indexing.
        equal=[channel_test_record(1,3,1),channel_test_record(1,3,2)]
        non_diagonal=[1.0 .3;.3 -.7]
        same=synthetic_channel_model(equal,non_diagonal)
        @test length(same.channels)==2
        @test [c.radial_projector for c in same.channels]==[1,2]
        @test same.D==2non_diagonal
        @test minimum(eigvals(Hermitian(same.D)))<0
        @test_throws ChannelError synthetic_channel_model(rec,[3.0 .1;.1 7.0])
        @test_throws ChannelError synthetic_channel_model(equal,[1.0 .3;.2 1.0])
        @test_throws ChannelError synthetic_channel_model(equal,[1.0 NaN;NaN 1.0])
        @test_throws ChannelError synthetic_channel_model(equal,ones(3,3))
        @test_throws ChannelError synthetic_channel_model([equal[1],equal[1]],non_diagonal)
        @test_throws ChannelError synthetic_channel_model([merge(equal[1],(;two_j=7))],ones(1,1))
        @test_throws ChannelError synthetic_channel_model([channel_test_record(0,3,1)],ones(1,1))
        @test_throws ChannelError synthetic_channel_model([channel_test_record(4,9,1)],ones(1,1))
        @test_throws ChannelError synthetic_channel_model([merge(equal[1],(;r=zeros(41)))],ones(1,1))
        @test_throws ChannelError synthetic_channel_model([merge(equal[1],(;beta_raw=fill(NaN,41)))],ones(1,1))
        @test_throws ChannelError synthetic_channel_model([merge(equal[1],(;cutoff_index=99))],ones(1,1))
        @test_throws ChannelError synthetic_channel_model([merge(equal[1],(;cutoff_index=20))],ones(1,1))
        @test_throws ChannelError synthetic_channel_model(equal,non_diagonal;unit_convention=:divide_both_by_two)

        for bad_j in (NaN,Inf,0.7,1.5)
            bad=deepcopy(mg); r=bad.spin_orb.relbetas[1]
            bad.spin_orb.relbetas[1]=channel_test_replace(r;jjj=bad_j)
            @test_throws ChannelError fr_channels(bad)
        end
        near=deepcopy(mg);r=near.spin_orb.relbetas[1]
        near.spin_orb.relbetas[1]=channel_test_replace(r;jjj=r.jjj+0.5e-10)
        @test fr_channels(near).channels[1].two_j==1
        far=deepcopy(mg);r=far.spin_orb.relbetas[1]
        far.spin_orb.relbetas[1]=channel_test_replace(r;jjj=r.jjj+2e-10)
        @test_throws ChannelError fr_channels(far)
        for action in (:duplicate_beta,:missing_beta,:duplicate_relbeta,:missing_relbeta,:wrong_l,:missing_index)
            bad=deepcopy(mg)
            if action==:duplicate_beta
                bad.nonlocal.betas[2]=channel_test_replace(bad.nonlocal.betas[2];index=bad.nonlocal.betas[1].index)
            elseif action==:missing_beta
                pop!(bad.nonlocal.betas)
            elseif action==:duplicate_relbeta
                bad.spin_orb.relbetas[2]=channel_test_replace(bad.spin_orb.relbetas[2];index=bad.spin_orb.relbetas[1].index)
            elseif action==:missing_relbeta
                pop!(bad.spin_orb.relbetas)
            elseif action==:wrong_l
                bad.spin_orb.relbetas[1]=channel_test_replace(bad.spin_orb.relbetas[1];lll=3)
            else
                bad.spin_orb.relbetas[1]=channel_test_replace(bad.spin_orb.relbetas[1];index=nothing)
            end
            @test_throws ChannelError fr_channels(bad)
        end
        pruned=deepcopy(mg);pop!(pruned.nonlocal.betas)
        @test try fr_channels(pruned);false catch e;e isa ChannelError && e.status=="UNSUPPORTED" end
        @test_throws ChannelError scalar_degenerate_channels(mg)
        deg=scalar_degenerate_channels(si)
        @test deg.provenance.synthetic
        @test all(isnothing(c.relbeta_source_index) for c in deg.channels)
        @test sum(c.two_j+1 for c in deg.channels)==2sum(2b.angular_momentum+1 for b in si.nonlocal.betas)
        for l in unique(c.l for c in deg.channels)
            plus=findall(c->c.l==l && c.two_j==2l+1,deg.channels)
            minus=findall(c->c.l==l && c.two_j==2l-1,deg.channels)
            if l>0
                @test deg.D[plus,plus]==deg.D[minus,minus]
                @test all(a.beta_internal==b.beta_internal for (a,b) in zip(deg.channels[plus],deg.channels[minus]))
            else
                @test isempty(minus)
            end
        end
    end

    @testset "Stable radial transform versus analytic Gaussian (synthetic)" begin
        cfg=settings["gaussian"];a=cfg["a_bohr_minus2"]
        for count in cfg["points"],l in 0:3
            r=collect(range(0,cfg["rmax_bohr"];length=count))
            # Raw fixture is twice r*beta, so the default paired convention has
            # b_internal=r^(l+1)*exp(-a*r²) exactly; no physical UPF is generated.
            record=merge(channel_test_record(l,2l+1,1;r), (;beta_raw=2 .* r.^(l+1).*exp.(-a.*r.^2)))
            model=synthetic_channel_model([record],ones(1,1))
            for q in cfg["q_bohr_minus1"]
                expected_modified=4π*sqrt(π)/(2.0^(l+2)*a^(l+1.5))*exp(-q^2/(4a))
                expected=q^l*expected_modified
                modified=radial_modified(model,1,q);full=radial_factor(model,1,q)
                e=channel_test_error(full,expected);em=channel_test_error(modified,expected_modified)
                @test isfinite(full) && isfinite(modified)
                @test e<=settings["tolerances"]["gaussian_radial"]
                @test em<=settings["tolerances"]["gaussian_radial"]
                q==0 && l>0 && (@test full==0)
                q>0 && (@test channel_test_error(full/q^l,modified)<=1e-14)
                push!(gaussian_diagnostics,(;grid_points=count,l,q,actual_F=full,analytic_F=expected,
                    normalized_error=e,modified_normalized_error=em))
            end
            @test_throws ChannelError radial_factor(model,1,-1.0)
            @test_throws ChannelError radial_factor(model,1,NaN)
        end
    end

    @testset "Real Mg radial samples and independent quadrature sensitivity" begin
        model=fr_channels(mg)
        for (i,c) in enumerate(model.channels),q in settings["mg_probe"]["radial_q_bohr_minus1"]
            actual=radial_factor(model,i,q); reference=independent_radial_trapz(model,i,q)
            @test isfinite(actual) && isfinite(reference)
            q==0 && c.l>0 && (@test actual==reference==0)
            push!(real_diagnostics,(;channel_position=i,source_beta_index=c.source_beta_index,
                parsed_beta_position=c.parsed_beta_position,l=c.l,two_j=c.two_j,q,
                production_F=actual,independent_trapezoidal_F=reference,
                quadrature_normalized_difference=channel_test_error(actual,reference),
                comparison="Independent BigFloat Bessel/physical-grid trapezoidal sensitivity; no machine-precision equality gate"))
        end
    end
    (;gaussian=gaussian_diagnostics,mg_radial=real_diagnostics)
end
