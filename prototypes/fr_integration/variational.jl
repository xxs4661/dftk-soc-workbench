# Finite, predeclared energy/operator probes. These functions never solve an
# eigenproblem, update an input reference density or search for a direction.
integration_density_hash(n) = bytes2hex(sha256(reinterpret(UInt8,vec(n))))

function rotate_orbital_pair(X,ik,a,b,angle)
    angle isa Real && isfinite(angle) || throw(ArgumentError("Finite rotation angle required"))
    1<=ik<=length(X) && 1<=a<=size(X[ik],2) && 1<=b<=size(X[ik],2) && a!=b ||
        throw(ArgumentError("Invalid orbital rotation indices"))
    result=deepcopy(X)
    ca,cb=copy(X[ik][:,a]),copy(X[ik][:,b])
    result[ik][:,a]=cos(angle)*ca+sin(angle)*cb
    result[ik][:,b]=-sin(angle)*ca+cos(angle)*cb
    result
end

"""Prescribed occupied/empty rotation; fresh n and full XC/Hartree at every point."""
function variational_checks(ctx,X,f;k_index=1,occupied_state=1,
        empty_state=Int(ctx.basis.model.n_electrons)+1,center_angle=0.13,
        steps=[1e-3,3e-4,1e-4],total_derivative_min_abs=1e-5,
        nl_derivative_min_abs=1e-10,total_derivative_tol=1e-6,
        nl_derivative_atol=1e-9,nl_derivative_rtol=1e-6)
    steps==[1e-3,3e-4,1e-4] && center_angle==0.13 ||
        throw(ArgumentError("Phase6B variational probe uses its three fixed steps and center angle"))
    all(v->v isa Real && isfinite(v) && v>0,
        (total_derivative_min_abs,nl_derivative_min_abs,total_derivative_tol,nl_derivative_atol,nl_derivative_rtol)) ||
        throw(ArgumentError("Finite positive variational thresholds required"))
    check_energy_orbitals(ctx.basis,X,f)
    1<=k_index<=length(X) && 1<=occupied_state<=size(X[k_index],2) &&
        1<=empty_state<=size(X[k_index],2) || throw(ArgumentError("Variational state index out of range"))
    f[k_index][occupied_state]==1 && f[k_index][empty_state]==0 ||
        throw(ArgumentError("Prescribed direction must mix an occupied and an empty spinor"))
    centerX=rotate_orbital_pair(X,k_index,occupied_state,empty_state,center_angle)
    center=energy_snapshot(ctx,centerX,f)
    a=centerX[k_index][:,occupied_state];b=centerX[k_index][:,empty_state]
    multiplier=2ctx.basis.kweights[k_index]*(f[k_index][occupied_state]-f[k_index][empty_state])
    analytic_total=multiplier*real(dot(b,center.ham[k_index]*a))
    analytic_nl=multiplier*real(dot(b,ctx.fr_blocks[k_index]*a))
    total_identifiable=abs(analytic_total)>=total_derivative_min_abs
    nl_identifiable=abs(analytic_nl)>=nl_derivative_min_abs
    samples=NamedTuple[]
    for h in steps
        plusX=rotate_orbital_pair(centerX,k_index,occupied_state,empty_state,h)
        minusX=rotate_orbital_pair(centerX,k_index,occupied_state,empty_state,-h)
        plus=energy_snapshot(ctx,plusX,f);minus=energy_snapshot(ctx,minusX,f)
        numeric_total=(plus.total-minus.total)/(2h)
        numeric_nl=(plus.terms["AtomicNonlocalFR"]-minus.terms["AtomicNonlocalFR"])/(2h)
        push!(samples,(;h_rad=h,plus_total_ha=plus.total,minus_total_ha=minus.total,
            plus_nonlocal_ha=plus.terms["AtomicNonlocalFR"],minus_nonlocal_ha=minus.terms["AtomicNonlocalFR"],
            plus_hartree_ha=plus.terms["Hartree"],minus_hartree_ha=minus.terms["Hartree"],
            plus_xc_ha=plus.terms["Xc"],minus_xc_ha=minus.terms["Xc"],
            plus_density_sha256=integration_density_hash(plus.density.n),
            minus_density_sha256=integration_density_hash(minus.density.n),
            plus_center_density_norm=norm(plus.density.n-center.density.n),
            minus_center_density_norm=norm(minus.density.n-center.density.n),
            numeric_total_ha_per_rad=numeric_total,numeric_nonlocal_ha_per_rad=numeric_nl,
            total_normalized_error=abs(numeric_total-analytic_total)/max(1,abs(analytic_total)),
            nonlocal_absolute_error=abs(numeric_nl-analytic_nl)))
    end
    last_sample=last(samples)
    total_pass=last_sample.total_normalized_error<=total_derivative_tol
    nl_bound=nl_derivative_atol+nl_derivative_rtol*abs(analytic_nl)
    nl_pass=last_sample.nonlocal_absolute_error<=nl_bound
    total_status=total_identifiable ? (total_pass ? "PASS" : "FAIL") : "INCONCLUSIVE"
    nl_status=nl_identifiable ? (nl_pass ? "PASS" : "FAIL") : "INCONCLUSIVE"
    status="FAIL" in (total_status,nl_status) ? "FAIL" :
        "INCONCLUSIVE" in (total_status,nl_status) ? "INCONCLUSIVE" : "PASS"
    (;status,total_status,nonlocal_status=nl_status,k_index,occupied_state,empty_state,
      center_angle_rad=center_angle,center_total_ha=center.total,
      center_density_sha256=integration_density_hash(center.density.n),
      analytic_total_ha_per_rad=analytic_total,analytic_nonlocal_ha_per_rad=analytic_nl,
      total_derivative_min_abs,nl_derivative_min_abs,total_derivative_tol,
      nonlocal_error_bound=nl_bound,samples,
      scope="Fixed 0.13-rad nonstationary orbital trial center; fresh n_X at each point, no SCF/direction search")
end

function rotate_global_spin(X,U)
    U isa AbstractMatrix && size(U)==(2,2) && all(isfinite,U) || throw(ArgumentError("Finite 2x2 spin rotation required"))
    norm(U'*U-Matrix{ComplexF64}(I,2,2))<=1e-12 && abs(det(U)-1)<=1e-12 ||
        throw(ArgumentError("Global spin rotation must belong to SU(2)"))
    result=deepcopy(X)
    for (source,target) in zip(X,result)
        target[1:2:end,:]=U[1,1]*source[1:2:end,:]+U[1,2]*source[2:2:end,:]
        target[2:2:end,:]=U[2,1]*source[1:2:end,:]+U[2,2]*source[2:2:end,:]
    end
    result
end

"""Spin-only SU(2): common terms/n invariant, SOC nonlocal need not be invariant."""
function spin_rotation_diagnostic(ctx,X,f,U;signal_min_abs=1e-12,
                                  density_tol=1e-10,energy_atol=1e-8)
    before=energy_snapshot(ctx,X,f)
    after=energy_snapshot(ctx,rotate_global_spin(X,U),f)
    common_differences=Dict(name=>after.terms[name]-before.terms[name] for name in COMMON_ENERGY_NAMES)
    total_change=after.total-before.total
    nonlocal_change=after.terms["AtomicNonlocalFR"]-before.terms["AtomicNonlocalFR"]
    density_error=integration_error(before.density.n,after.density.n)
    change_error=abs(total_change-nonlocal_change)
    invariants_pass=density_error<=density_tol && maximum(abs,values(common_differences))<=energy_atol &&
        change_error<=energy_atol
    observable=abs(nonlocal_change)>=signal_min_abs
    (;status=invariants_pass ? (observable ? "PASS" : "INCONCLUSIVE") : "FAIL",
      common_invariance_status=invariants_pass ? "PASS" : "FAIL",
      nonlocal_noninvariance_status=observable ? "RESOLVED" : "INCONCLUSIVE",
      density_normalized_error=density_error,common_term_changes_ha=common_differences,
      total_change_ha=total_change,nonlocal_change_ha=nonlocal_change,
      total_minus_nonlocal_change_error_ha=change_error,signal_min_abs,
      before_nonlocal=before.nonlocal_decomposition,after_nonlocal=after.nonlocal_decomposition,
      scope="General complex operator/energy fixture; spatial shape and lattice unchanged; no SOC spin-only invariance assumed")
end
