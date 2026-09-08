# Actual small Mg G sets and synthetic random coefficients only. No SCF,
# eigenproblem or Si XC evaluation. Owned Kpoint copies exercise ordering faults.
function boundary_test_kpoint(k,indices)
    mapping=k.mapping[indices]
    DFTK.Kpoint(k.spin,k.coordinate,k.G_vectors[indices],mapping,
        Dict(g=>i for (i,g) in enumerate(mapping)),k.mapping_device[indices])
end

function run_boundary_mapping_tests(root)
    FI=FRIntegration
    mg=FI.load_bound_psp(root)
    coords=[[x,y,z] for x in (0.,-.5) for y in (0.,-.5) for z in (0.,-.5)]
    ctx=FI.build_context([mg],10.0Matrix{Float64}(I,3,3),[[0.,0.,0.]],coords,fill(1/8,8);
        Ecut=1.,xc_identifiers=mg.xc_identifiers,mode=:real_fr,fft_size=(16,16,16))
    b=ctx.basis;savedG=[copy(k.G_vectors) for k in b.kpoints];rows=NamedTuple[]
    @testset "Eight boundary k points use q reversal with the integer shift" begin
        @test length(b.kpoints)==8
        @test [collect(k.coordinate) for k in b.kpoints]==coords
        @test b.kweights==fill(1/8,8)
        for (ik,k) in enumerate(b.kpoints)
            two_k=2 .* k.coordinate
            @test all(isinteger,two_k)
            t=Int.(two_k)
            @test k.coordinate == -k.coordinate+t
            G=k.G_vectors;n=length(G)
            actual=FI.time_reversal_map(b,k,k)
            lookup=Dict(Tuple(g)=>i for (i,g) in enumerate(G))
            expected=[get(lookup,Tuple(-g-t),0) for g in G]
            @test all(>(0),expected)
            @test actual==expected
            @test sort(actual)==collect(1:n)
            @test all(G[actual[i]]==-G[i]-t for i in 1:n)
            @test all(G[actual[i]]+k.coordinate==-(G[i]+k.coordinate) for i in 1:n)
            rng=MersenneTwister(80880+ik)
            x=randn(rng,ComplexF64,2n,2);x/=norm(x)
            reversed=FI.time_reverse_spinor(x,actual)
            @test norm(FI.time_reverse_spinor(reversed,actual)+x)<=1e-12

            # A valid row permutation cannot determine the physical mapping.
            permutation=randperm(rng,n)
            target=boundary_test_kpoint(k,permutation)
            reordered=FI.time_reversal_map(b,k,target)
            @test reordered==invperm(permutation)[actual]
            back=FI.time_reversal_map(b,target,k)
            @test norm(FI.time_reverse_spinor(FI.time_reverse_spinor(x,reordered),back)+x)<=1e-12
            @test all(target.G_vectors[reordered[i]]+target.coordinate==-(G[i]+k.coordinate) for i in 1:n)
            row_only=collect(1:n)
            physical_row_error=maximum(norm(G[i]+k.coordinate+target.G_vectors[row_only[i]]+target.coordinate) for i in 1:n)
            @test physical_row_error>1
            spin_only=FI.time_reverse_spinor(x,row_only)
            @test norm(spin_only-reversed)>1e-2
            @test maximum(norm(2 .* (g+k.coordinate)) for g in G)>1

            # Omitting t produces the wrong plane-wave list at every boundary k.
            naive=[get(lookup,Tuple(-g),0) for g in G]
            if iszero(norm(t))
                @test naive==actual
            else
                @test naive!=actual
                @test any(iszero,naive)
            end
            duplicate=collect(1:n);duplicate[1]=duplicate[2]
            @test_throws ArgumentError FI.time_reversal_map(b,k,boundary_test_kpoint(k,duplicate))
            @test_throws ArgumentError FI.time_reversal_map(b,k,boundary_test_kpoint(k,collect(1:n-1)))
            @test G==savedG[ik]
            push!(rows,(;k_index=ik,coordinate_fractional=collect(k.coordinate),integer_shift=collect(t),ng=n,
                physical_q_max_error=maximum(norm(G[actual[i]]+k.coordinate+G[i]+k.coordinate) for i in 1:n),
                reordered_target_row_only_error=physical_row_error,
                spin_only_vs_physical_time_reversal_error=norm(spin_only-reversed)))
        end
        @test_throws ArgumentError FI.time_reversal_map(b,b.kpoints[1],b.kpoints[2])
        @test FI.validate_context(ctx)
    end
    (;scope="Static small Mg basis plus synthetic random coefficients; G'=−G−t, k'=−k+t; no physical solve",rows)
end
