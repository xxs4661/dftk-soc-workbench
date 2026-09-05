# Charge-only Phase 5B controller. This file never calls scalar SCF.
# The enclosing module imports DFTK, LinearAlgebra, Random, SHA, SpinorPrototype,
# and includes energy.jl first.

struct DensityMapFailure <: Exception
    reason::String
    history::Vector{Any}
end
Base.showerror(io::IO, err::DensityMapFailure) = print(io, err.reason)

_scf_hash(a) = bytes2hex(SHA.sha256(reinterpret(UInt8, vec(copy(a)))))

"""Validate a Float64 valence density without clipping or renormalizing it."""
function density_summary(n, dvol; electron_tol=1e-8)
    n isa AbstractArray{Float64} && !isempty(n) ||
        throw(ArgumentError("Density must be a nonempty Float64 array"))
    isfinite(dvol) && dvol > 0 || throw(ArgumentError("Invalid real-grid volume element"))
    isfinite(electron_tol) && electron_tol > 0 || throw(ArgumentError("Invalid electron-count tolerance"))
    all(isfinite, n) || throw(ArgumentError("Nonfinite valence density"))
    negative_bound = 64eps(Float64) * max(1.0, maximum(abs, n))
    minimum(n) >= -negative_bound || throw(ArgumentError("Negative density exceeds rounding bound"))
    count = dvol * sum(n)
    abs(count-8) <= electron_tol || throw(ArgumentError("Valence electron count drift: $count"))
    (; sha256=_scf_hash(n), electron_count=count, l2=sqrt(dvol)*norm(n),
       minimum=minimum(n), negative_roundoff_bound=negative_bound)
end

"""
    iterate_density_map(map_density, n0; dvol, ...)

Small controller shared by the real loop and synthetic fault tests. A map takes
`(n_in, map_index, is_closure)` and returns `n_out`, `raw`, `closure_ok`, and
`diagnostics` containing `consumed_input_sha256` and `orbital_density_sha256`.
The latter is derived independently from the actual returned orbitals.

Only the unmixed output-input norm triggers a candidate. Every candidate needs
an extra map from its output density. Failed closure outputs enter the next
linear mixing step. All maps, including closure, count against the same limit.
The callback receives every completed map and a safe failure record on errors.
"""
function iterate_density_map(map_density, n0; dvol, alpha=0.3, max_maps=200,
                             density_tol=1e-9, electron_tol=1e-8,
                             callback=(record, raw)->nothing)
    isfinite(alpha) && 0 < alpha <= 1 || throw(ArgumentError("Mixing alpha must lie in (0,1]"))
    max_maps isa Integer && max_maps > 0 || throw(ArgumentError("Positive map budget required"))
    isfinite(density_tol) && density_tol > 0 || throw(ArgumentError("Positive density tolerance required"))
    history = Any[]
    n_in = copy(vec(n0))
    closing = false
    for imap in 1:max_maps
        record = Dict{String,Any}("map_index"=>imap,
            "map_role"=>closing ? "closure" : "iteration", "status"=>"RUNNING")
        raw = nothing
        try
            sin = density_summary(n_in, dvol; electron_tol)
            record["n_in"] = sin
            mapped = map_density(copy(n_in), imap, closing)
            raw = mapped.raw
            n_out = copy(vec(mapped.n_out))
            size(n_out) == size(n_in) || throw(DimensionMismatch("Density map changed grid size"))
            sout = density_summary(n_out, dvol; electron_tol)
            diag = mapped.diagnostics
            diag.consumed_input_sha256 == sin.sha256 ||
                error("Hamiltonian consumed stale or mismatched input density")
            diag.orbital_density_sha256 == sout.sha256 ||
                error("Output density differs from the current orbital density")
            mapped.closure_ok isa Bool || error("Closure check must return a Boolean")
            residual = sqrt(dvol) * norm(n_out-n_in)
            n_mixed = (1-alpha).*n_in .+ alpha.*n_out
            smixed = density_summary(n_mixed, dvol; electron_tol)
            candidate = residual <= density_tol
            converged = closing && candidate && mapped.closure_ok
            # Closure uses the candidate OUTPUT, not its damped approximation.
            next_is_closure = !closing && candidate
            n_next = converged || next_is_closure ? copy(n_out) : n_mixed
            snext = density_summary(n_next, dvol; electron_tol)
            merge!(record, Dict("n_out"=>sout, "n_mixed"=>smixed, "n_next"=>snext,
                "unmixed_residual_l2"=>residual,
                "mixed_step_l2"=>sqrt(dvol)*norm(n_mixed-n_in),
                "actual_next_step_l2"=>sqrt(dvol)*norm(n_next-n_in),
                "alpha"=>alpha, "density_candidate"=>candidate,
                "closure_checks_passed"=>mapped.closure_ok, "diagnostics"=>diag,
                "next_density_source"=>converged ? "returned_orbital_output" :
                    next_is_closure ? "candidate_output_for_closure" : "linear_mixing",
                "status"=>converged ? "PASS" : next_is_closure ? "CANDIDATE" : "CONTINUE"))
            if imap == max_maps && !converged
                record["status"] = "FAIL"
                record["failure_reason"] = "Maximum density-map count reached without closure acceptance"
            end
            push!(history, record)
            callback(record, raw)
            converged && return (; raw, history, map_count=imap, converged=true,
                                  status="PASS", n_in=copy(n_in), n_out)
            imap == max_maps && throw(DensityMapFailure(record["failure_reason"], history))
            n_in = n_next
            closing = next_is_closure
        catch err
            err isa DensityMapFailure && rethrow()
            record["status"] = "FAIL"
            record["failure_reason"] = sprint(showerror, err)
            (isempty(history) || last(history) !== record) && push!(history, record)
            callback(record, raw)
            throw(DensityMapFailure(record["failure_reason"], history))
        end
    end
    error("Unreachable density-map controller state")
end

function _scf_energy_check(report, threshold)
    fields = (:energy_term_sum_difference_ha, :direct_kinetic_difference_ha,
        :direct_nonlocal_difference_ha, :local_integral_difference_ha,
        :hartree_half_integral_difference_ha, :ewald_once_difference_ha,
        :psp_correction_once_difference_ha, :double_counting_difference_ha)
    for name in fields
        value = getproperty(report, name)
        isfinite(value) && abs(value) <= threshold || error("Energy check $name failed: $value")
    end
    nothing
end

"""
    spinor_scf(basis, n0, settings; seed, callback, hooks=NamedTuple())

Actual charge-only spinor SCF on the frozen B0 scalar spatial terms. Every map
builds H[n_in], solves its lifted 16+6-state problem, and evaluates the energy
of those orbitals at their own n_out. No scalar reference enters this API.

Optional `ham`, `density`, `solve`, and `occupations` hooks are narrowly scoped
fault injection for tests. Their results undergo the same provenance, explicit
residual, electron-count and orbital-density checks as the ordinary path.
"""
function spinor_scf(basis, n0, settings; seed::Integer,
                    callback=(record, raw)->nothing, hooks=NamedTuple())
    scf, solver, accept = settings["scf"], settings["solver"], settings["acceptance"]
    scf["alpha"] == 0.3 && scf["max_maps"] == 200 || error("Real SCF settings must retain alpha=0.3 and 200-map limit")
    target, auxiliary = solver["target_states"], solver["auxiliary_states"]
    target == 16 && auxiliary == 6 && solver["tolerance_ha"] == 1e-10 &&
        solver["maxiter"] == 300 || error("Real spinor solver settings differ from declared 16+6 setup")
    nstates = target + auxiliary
    check_supported_basis(basis)
    length(basis.kpoints) == 8 && all(w->abs(w-0.125)<1e-14, basis.kweights) ||
        error("This spinor SCF is restricted to B0's eight spatial k points")
    length(n0) == prod(basis.fft_size) || throw(DimensionMismatch("Initial density grid mismatch"))
    kinetic = only(filter(t->t isa DFTK.TermKinetic, basis.terms)).kinetic_energies
    previous_X = nothing
    previous_potential = nothing
    previous_probe_action = nothing
    probe_ng = length(kinetic[1])
    probe = randn(MersenneTwister(59001), ComplexF64, 2probe_ng, 1)
    probe ./= norm(probe)

    function map_density(n_in, imap, is_closure)
        sin = density_summary(n_in, basis.dvol; electron_tol=accept["electron_count_abs"])
        # Orbital-dependent temporary energies can be Inf. They are neither used
        # as energies nor placed in a report: only the new Hamiltonian is kept.
        fresh = DFTK.energy_hamiltonian(basis, nothing, nothing;
                    ρ=valence_rho(basis, n_in)).ham
        fresh_potential_hashes = [_scf_hash(fresh[ik].local_op.potential) for ik in eachindex(basis.kpoints)]
        probe_operator = ComponentOperator(fresh[1], 2)
        fresh_probe = probe_operator * probe
        ham = hasproperty(hooks, :ham) ? hooks.ham(fresh, n_in, imap) : fresh
        potential = copy(ham[1].local_op.potential)
        probe_action = fresh_probe
        if hasproperty(hooks, :ham)
            probe_action = ComponentOperator(ham[1], 2) * probe
            all(_scf_hash(ham[ik].local_op.potential) == fresh_potential_hashes[ik]
                for ik in eachindex(basis.kpoints)) &&
                norm(probe_action-fresh_probe) <= 1e-13 ||
                error("Hamiltonian hook froze or changed H for the current input density")
        end
        potential_diagnostics = (; sha256=_scf_hash(potential), norm=norm(potential),
            change_norm=isnothing(previous_potential) ? nothing : norm(potential-previous_potential),
            probe_action_sha256=_scf_hash(probe_action), probe_action_norm=norm(probe_action),
            probe_action_change_norm=isnothing(previous_probe_action) ? nothing : norm(probe_action-previous_probe_action),
            probe_seed=59001, probe_operator_counters=operator_stats(probe_operator))
        previous_potential = potential
        previous_probe_action = probe_action
        X = Matrix{ComplexF64}[]
        lambdas = Vector{Float64}[]
        per_k = Any[]
        for ik in eachindex(basis.kpoints)
            ng = length(kinetic[ik])
            initial = isnothing(previous_X) ?
                DFTK.ortho_qr(randn(MersenneTwister(seed+ik-1), ComplexF64, 2ng, nstates)) :
                copy(previous_X[ik])
            initial_saved = copy(initial)
            initial_gram = norm(initial'initial-I)
            initial_gram <= accept["orthogonality_frobenius"] || error("Initial spinor subspace lost orthogonality")
            initial_norms = [[sum(abs2, initial[c:2:end,n]) for c in 1:2] for n in 1:nstates]
            initial_imag = norm(imag.(initial))
            if isnothing(previous_X)
                all(v->all(>(0),v), initial_norms) || error("First random state needs both components")
                initial_imag > 0 || error("First random subspace must be complex")
            end
            op = ComponentOperator(ham[ik], 2)
            prec = ComponentKineticPreconditioner(kinetic[ik], 2; shift=solver["preconditioner_shift_ha"])
            eig = hasproperty(hooks,:solve) ? hooks.solve(op,initial,prec,ik,imap) :
                DFTK.lobpcg_hyper(op, initial; prec, tol=solver["tolerance_ha"],
                    maxiter=solver["maxiter"], miniter=1, n_conv_check=target)
            solved_counts = operator_stats(op)
            initial == initial_saved || error("Eigensolver modified its supplied initial subspace")
            eig.converged && eig.n_iter > 0 || error("Spinor diagonalization failed or performed zero iterations")
            size(eig.X) == (2ng,nstates) && length(eig.λ) == nstates || error("Eigensolver changed state counts")
            all(isfinite,eig.X) && all(isfinite,eig.λ) || error("Nonfinite eigensolver result")
            xt = eig.X[:,1:target]
            hxt = op * xt
            residuals = [norm(hxt[:,n]-eig.λ[n]*xt[:,n]) for n in 1:target]
            gram = norm(xt'xt-I)
            maximum(residuals) <= accept["explicit_residual_ha"] || error("Explicit H[n_in] target residual failed")
            gram <= accept["orthogonality_frobenius"] || error("Target spinor orthogonality failed")
            push!(X, Matrix{ComplexF64}(eig.X)); push!(lambdas, Float64.(eig.λ))
            push!(per_k, (; index=ik, ng, dimension=2ng, target_states=target,
                auxiliary_states=auxiliary, initial_seed=seed+ik-1,
                initial_source=isnothing(previous_X) ? "independent_complex_random_QR" : "previous_spinor_map",
                initial_orthogonality_frobenius=initial_gram, initial_component_norms=initial_norms,
                initial_imaginary_norm=initial_imag, initial_array_unchanged=true,
                converged=eig.converged, iterations=eig.n_iter, solver_n_matvec=eig.n_matvec,
                solver_operator_counters=solved_counts, counters_after_residual=operator_stats(op),
                eigenvalues_ha=Float64.(eig.λ), explicit_residuals_ha=residuals,
                orthogonality_frobenius=gram))
        end
        fixed = fixed_gapped_occupations(lambdas, basis.kweights; representation=:spinor,
                                        atol=accept["electron_count_abs"])
        f = hasproperty(hooks,:occupations) ? hooks.occupations(fixed.occupations,imap) : fixed.occupations
        orbital_density = density_from_orbitals(basis,X,f)
        selected_density = hasproperty(hooks,:density) ? hooks.density(orbital_density,n_in,imap) : orbital_density
        _scf_hash(selected_density.n) == _scf_hash(orbital_density.n) ||
            error("Density hook reused or exchanged the actual orbital output density")
        snapshot = energy_snapshot(basis,X,f; expected_n=selected_density.n)
        _scf_energy_check(snapshot.report, accept["energy_identity_abs_ha_cell"])
        sout = density_summary(snapshot.density.n,basis.dvol; electron_tol=accept["electron_count_abs"])
        _scf_hash(orbital_density.n) == sout.sha256 || error("Energy and orbital density mismatch")
        self_residuals, rayleigh_residuals, rayleigh_values = Any[], Any[], Any[]
        self_counts = Any[]
        for ik in eachindex(X)
            xt = X[ik][:,1:target]
            op_self = ComponentOperator(snapshot.ham[ik],2)
            hx = op_self * xt
            rq = [real(dot(xt[:,n],hx[:,n]))/sum(abs2,xt[:,n]) for n in 1:target]
            push!(self_residuals,[norm(hx[:,n]-lambdas[ik][n]*xt[:,n]) for n in 1:target])
            push!(rayleigh_residuals,[norm(hx[:,n]-rq[n]*xt[:,n]) for n in 1:target])
            push!(rayleigh_values,rq); push!(self_counts,operator_stats(op_self))
        end
        pauli_ratio = norm(snapshot.density.m)/norm(snapshot.density.n)
        max_self = maximum(maximum,self_residuals)
        max_rq = maximum(maximum,rayleigh_residuals)
        all(isfinite,(pauli_ratio,max_self,max_rq)) || error("Nonfinite closure diagnostic")
        closure_ok = max_self <= accept["self_density_residual_ha"] &&
            max_rq <= accept["self_density_residual_ha"] && pauli_ratio <= accept["pauli_density_relative_l2"]
        previous_X = X
        diagnostics = (; consumed_input_sha256=sin.sha256, orbital_density_sha256=sout.sha256,
            potential=potential_diagnostics, per_k, occupations=fixed,
            max_input_h_residual_ha=maximum(maximum(k.explicit_residuals_ha) for k in per_k),
            max_orthogonality_frobenius=maximum(k.orthogonality_frobenius for k in per_k),
            self_density_h_old_lambda_residuals_ha=self_residuals,
            self_density_h_rayleigh_residuals_ha=rayleigh_residuals,
            self_density_h_rayleigh_values_ha=rayleigh_values,
            rayleigh_note="Diagnostic quotients of H[n_out]; not a new diagonalization",
            self_density_h_operator_counters=self_counts, max_self_density_h_residual_ha=max_self,
            pauli_density_relative_l2=pauli_ratio, energy_total_ha=snapshot.total,
            energy_terms_ha=snapshot.terms, energy_checks=snapshot.report,
            energy_density_source="Current returned spinor orbitals, n_out; no mixed-density terms")
        raw = (; X,f,lambda=lambdas,density=snapshot.density,energy=snapshot,
                n_in=copy(n_in),ham_input=ham,ham_output=snapshot.ham)
        (; n_out=snapshot.density.n,diagnostics,raw,closure_ok)
    end
    loop = iterate_density_map(map_density,n0; dvol=basis.dvol,alpha=scf["alpha"],max_maps=scf["max_maps"],
        density_tol=accept["density_fixedpoint_l2"],electron_tol=accept["electron_count_abs"],callback)
    merge(loop.raw,(;history=loop.history,map_count=loop.map_count,converged=loop.converged,status=loop.status))
end
