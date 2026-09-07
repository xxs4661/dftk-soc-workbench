# Synthetic mathematical identities only; no material or SOC-SCF claim.
angular_test_error(a,b) = norm(a-b)/max(norm(a),norm(b),1)

function run_angular_tests(settings)
    tol = settings["tolerances"]["angular"]
    diagnostics = Dict{String,Any}("scope"=>"Independent synthetic angular mathematics",
        "tolerance"=>tol,"normalization"=>settings["normalization"],
        "max_harmonic_error"=>0.0,"max_cg_ladder_error"=>0.0,
        "max_cg_orthogonality_error"=>0.0,"max_l_dot_s_projector_error"=>0.0,
        "max_jz_label_error"=>0.0,"max_j2_label_error"=>0.0)
    record(key,value) = (diagnostics[key]=max(diagnostics[key],value))
    directions = [[1.0,0,0],[0.0,1,0],[0.0,0,1],[0.0,0,-1],
                  [0.37,-0.51,0.83],[-0.72,0.23,-0.41],[0.1,0.2,1.4]]

    @testset "Complex CS harmonics versus associated-Legendre point reference" begin
        q = [0.37,-0.51,0.83]
        radius = norm(q)
        @test angular_test_error(RelativisticProjectors.complex_solid_harmonic(0,0,q),1/sqrt(4π)) <= tol
        @test angular_test_error(RelativisticProjectors.complex_solid_harmonic(1,0,q),sqrt(3/(4π))*q[3]) <= tol
        @test angular_test_error(RelativisticProjectors.complex_solid_harmonic(1,1,q),-sqrt(3/(8π))*(q[1]+im*q[2])) <= tol
        @test angular_test_error(independent_Ylm(1,0,q),sqrt(3/(4π))*q[3]/radius) <= tol
        @test angular_test_error(independent_Ylm(1,1,q),-sqrt(3/(8π))*(q[1]+im*q[2])/radius) <= tol
        for l in 0:3
            transform = RelativisticProjectors.real_to_complex_transform(l)
            @test angular_test_error(transform*transform',Matrix{ComplexF64}(I,2l+1,2l+1)) <= tol
            for q in directions
                actual = [RelativisticProjectors.complex_solid_harmonic(l,m,q) for m in -l:l]
                reference = [independent_solid_harmonic(l,m,q) for m in -l:l]
                real_values = [DFTK.solid_harmonic_real(l,m,q) for m in -l:l]
                error = angular_test_error(actual,reference)
                @test error <= tol
                record("max_harmonic_error",error)
                @test angular_test_error(transform*real_values,reference) <= tol
                @test abs(sum(abs2,reference)/norm(q)^(2l)-(2l+1)/(4π)) <= tol
                for m in 1:l
                    @test angular_test_error(actual[l-m+1],(isodd(m) ? -1 : 1)*conj(actual[l+m+1])) <= tol
                end
                for scale in (0.31,1.7,1e-8)
                    scaled = [RelativisticProjectors.complex_solid_harmonic(l,m,scale*q) for m in -l:l]
                    @test angular_test_error(scaled,scale^l*reference) <= tol
                end
            end
            origin = [RelativisticProjectors.complex_solid_harmonic(l,m,zeros(3)) for m in -l:l]
            @test all(isfinite,origin)
            @test l==0 ? origin==ComplexF64[1/sqrt(4π)] : iszero(norm(origin))
        end
        # An ordinary harmonic substituted for a solid harmonic must be detected.
        q = [0.2,-0.7,1.6]
        @test angular_test_error(independent_Ylm(2,1,q),
                                 RelativisticProjectors.complex_solid_harmonic(2,1,q)) > 1e-2
    end

    @testset "Independent ladder L.S projectors and labeled coupled states" begin
        for l in 0:3
            reference = independent_angular_matrices(l)
            Id = Matrix{ComplexF64}(I,2(2l+1),2(2l+1))
            plus,minus = reference.Pi_plus,reference.Pi_minus
            @test norm(plus-plus') <= tol
            @test norm(minus-minus') <= tol
            @test angular_test_error(plus*plus,plus) <= tol
            @test angular_test_error(minus*minus,minus) <= tol
            @test norm(plus*minus) <= tol
            @test angular_test_error(plus+minus,Id) <= tol
            @test abs(real(tr(plus))-(2l+2)) <= tol
            @test abs(real(tr(minus))-2l) <= tol
            @test count(>(0.5),eigvals(Hermitian(plus))) == 2l+2
            @test count(>(0.5),eigvals(Hermitian(minus))) == 2l
            coupled = Matrix{ComplexF64}[]
            for two_j in (l==0 ? (1,) : (2l-1,2l+1))
                U = RelativisticProjectors.cg_matrix(l,two_j)
                ladder_U = independent_cg_ladder(l,two_j)
                Pi = two_j==2l+1 ? plus : minus
                j = two_j/2
                M = collect(-two_j:2:two_j)./2
                @test size(U) == (2(2l+1),two_j+1)
                error = angular_test_error(U,ladder_U)
                @test error <= tol
                record("max_cg_ladder_error",error)
                error = angular_test_error(U'U,Matrix{ComplexF64}(I,two_j+1,two_j+1))
                @test error <= tol
                record("max_cg_orthogonality_error",error)
                error = angular_test_error(U*U',Pi)
                @test error <= tol
                record("max_l_dot_s_projector_error",error)
                error = angular_test_error(reference.Jz*U,U*Diagonal(M))
                @test error <= tol
                record("max_jz_label_error",error)
                error = angular_test_error(reference.J2*U,j*(j+1)*U)
                @test error <= tol
                record("max_j2_label_error",error)
                ls_value = two_j==2l+1 ? l/2 : -(l+1)/2
                @test angular_test_error(reference.LdotS*U,ls_value*U) <= tol
                for (column,two_mj) in enumerate(-two_j:2:two_j),m in -l:l,spin in 1:2
                    two_mj==2m+(spin==1 ? 1 : -1) || @test U[spin+2(m+l),column]==0
                end
                for q in directions
                    W = zeros(ComplexF64,2,2(2l+1))
                    for m in -l:l,spin in 1:2
                        W[spin,spin+2(m+l)] = independent_solid_harmonic(l,m,q)
                    end
                    actual = hcat([RelativisticProjectors.spin_angular_solid(l,two_j,two_mj,q)
                                   for two_mj in -two_j:2:two_j]...)
                    @test angular_test_error(actual,W*ladder_U) <= tol
                    ordinary = hcat([RelativisticProjectors.spin_angular(l,two_j,two_mj,q)
                                     for two_mj in -two_j:2:two_j]...)
                    @test angular_test_error(ordinary,(W*ladder_U)/norm(q)^l) <= tol
                end
                push!(coupled,U)
            end
            all_U = hcat(coupled...)
            @test angular_test_error(all_U*all_U',Id) <= tol
        end
        # A wrong relative sign can still give a Hermitian P*D*P': require the
        # independent angular-momentum projector, not Hermiticity alone.
        bad = copy(RelativisticProjectors.cg_matrix(1,1))
        row = findfirst(!iszero,bad[:,1])
        bad[row,1] *= -1
        wrong_kernel = bad*bad'
        @test norm(wrong_kernel-wrong_kernel') <= tol
        @test angular_test_error(wrong_kernel,independent_angular_matrices(1).Pi_minus) > 0.1
        # Conjugating Y changes non-axis point values; this is not a real-only test.
        value = independent_Ylm(1,1,[0.37,-0.51,0.83])
        @test abs(value-conj(value)) > 0.1
    end

    @testset "Strict angular labels and safe origin" begin
        @test RelativisticProjectors.cg_matrix(0,1) == ComplexF64[0 1;1 0]
        @test RelativisticProjectors.spin_angular(0,1,1,zeros(3)) == ComplexF64[1/sqrt(4π),0]
        for l in (1,2,3),two_j in (2l-1,2l+1),two_mj in -two_j:2:two_j
            @test iszero(norm(RelativisticProjectors.spin_angular_solid(l,two_j,two_mj,zeros(3))))
            @test_throws DomainError RelativisticProjectors.spin_angular(l,two_j,two_mj,zeros(3))
        end
        for l in (-1,4,1.0,true)
            @test_throws ArgumentError RelativisticProjectors.cg_matrix(l,1)
        end
        for two_j in (0,2,5,1.0,true)
            @test_throws ArgumentError RelativisticProjectors.cg_matrix(1,two_j)
        end
        @test_throws ArgumentError RelativisticProjectors.cg_matrix(0,-1)
        for two_mj in (-4,0,4,1.0,true)
            @test_throws ArgumentError RelativisticProjectors.spin_angular_solid(1,3,two_mj,ones(3))
        end
        @test_throws ArgumentError RelativisticProjectors.complex_solid_harmonic(1,2,ones(3))
        @test_throws ArgumentError RelativisticProjectors.complex_solid_harmonic(1,0,[NaN,0,0])
        @test_throws ArgumentError RelativisticProjectors.complex_solid_harmonic(1,0,ComplexF64[1,0,0])
        @test_throws DimensionMismatch RelativisticProjectors.complex_solid_harmonic(1,0,ones(2))
    end
    diagnostics
end
