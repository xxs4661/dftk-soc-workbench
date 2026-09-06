# Physical spinor occupations: capacity one, one global mu, spatial weights.
# Frozen DFTK occupation.jl / terms/entropy.jl multiply filled_occupation(model),
# which is two for the charge-only scalar model. Those paths are not called here.
struct EnsembleError <: Exception
    status::String
    reason::String
end
Base.showerror(io::IO,e::EnsembleError)=print(io,e.status,": ",e.reason)
ensemble_fail(status,reason)=throw(EnsembleError(status,reason))

function _ensemble_tau(tau)
    tau isa Real && isfinite(tau) && tau>0 && isfinite(Float64(tau)) && Float64(tau)>0 ||
        ensemble_fail("INVALID_ENSEMBLE","tau must be a positive finite energy in Ha")
    Float64(tau)
end
function _ensemble_weights(weights,nk)
    weights isa AbstractVector && length(weights)==nk && nk>0 &&
        all(w->w isa Real && isfinite(w) && w>=0,weights) ||
        ensemble_fail("INVALID_ENSEMBLE","One finite nonnegative spatial weight per k point required")
    w=Float64.(weights)
    all(isfinite,w) && abs(sum(w)-1)<=1e-12 ||
        ensemble_fail("INVALID_ENSEMBLE","Spatial weights must sum to one without renormalization")
    w
end
function _ensemble_levels(eigenvalues)
    eigenvalues isa AbstractVector && !isempty(eigenvalues) &&
        all(e->e isa AbstractVector && !isempty(e) && all(x->x isa Real && isfinite(x),e),eigenvalues) ||
        ensemble_fail("INVALID_ENSEMBLE","Finite nonempty energy vectors required")
    energies=[Float64.(e) for e in eigenvalues]
    all(e->all(isfinite,e),energies) ||
        ensemble_fail("INVALID_ENSEMBLE","Energies must be finite Float64 values")
    # Global FD does not require ordering. Preserve orbital correspondence when
    # own-density Rayleigh quotients split/reorder a nearly degenerate subspace.
    energies
end
function _ensemble_occupations(f)
    f isa AbstractVector && !isempty(f) &&
        all(v->v isa AbstractVector && !isempty(v) &&
            all(x->x isa Real && isfinite(x) && 0<=x<=1,v),f) ||
        ensemble_fail("INVALID_ENSEMBLE","Finite capacity-one occupation vectors required")
    nothing
end

"""Stable logistic; ±Inf represent saturated exponents, NaN is rejected."""
function fermi_logistic(x::Real)
    isnan(x) && ensemble_fail("INVALID_ENSEMBLE","NaN Fermi exponent")
    if x>=0
        y=exp(-Float64(x)); y/(1+y)
    else
        1/(1+exp(Float64(x)))
    end
end
_fermi_at_mu(energies,mu,tau)=[[fermi_logistic((e-mu)/tau) for e in ek] for ek in energies]
_ensemble_count(f,w)=sum(w[k]*sum(f[k]) for k in eachindex(w))

# A Float64 count plateau is diagnosed on the middle half of an actual global
# spectral gap whose integer-capacity weighted filling equals Ne. All three
# counts must be exactly equal, with the usual electron residual still checked.
# Select the gap midpoint deterministically; do not adjust or truncate any f.
function _fermi_gap_plateau(energies,w,ne,tau,tol)
    states=sort([(e,w[k]) for (k,ek) in enumerate(energies) for e in ek];by=first)
    cumulative=0.0; i=1
    while i<=length(states)
        lower=states[i][1]
        while i<=length(states) && states[i][1]==lower
            cumulative+=states[i][2]; i+=1
        end
        i>length(states) && break
        upper=states[i][1]
        if abs(cumulative-ne)<=tol
            left=.75lower+.25upper; midpoint=.5lower+.5upper; right=.25lower+.75upper
            counts=[_ensemble_count(_fermi_at_mu(energies,mu,tau),w) for mu in (left,midpoint,right)]
            if left<midpoint<right && counts[1]==counts[2]==counts[3] && abs(counts[2]-ne)<=tol
                return (;mu=midpoint,interval=(left,right),gap=(lower,upper))
            end
        end
    end
    nothing
end

"""
Global capacity-one Fermi–Dirac root. No scalar filling factor, occupation
rescaling, small-f cutoff, or independent per-k electron constraint is used.
The bounded bracket extends the finite spectrum by a stated thermal margin;
at most 256 bisection iterations are allowed and failure is explicit.
"""
function fermi_occupations(eigenvalues,weights,n_electrons,tau;
                           electron_tol=1e-12,maxiter=256)
    energies=_ensemble_levels(eigenvalues);w=_ensemble_weights(weights,length(energies));t=_ensemble_tau(tau)
    n_electrons isa Real && isfinite(n_electrons) && n_electrons>0 ||
        ensemble_fail("INVALID_ENSEMBLE","Positive finite valence electron count required")
    ne=Float64(n_electrons)
    electron_tol isa Real && isfinite(electron_tol) && 0<electron_tol<=1e-12 ||
        ensemble_fail("INVALID_ENSEMBLE","Electron tolerance must be positive and no larger than 1e-12")
    maxiter isa Integer && !(maxiter isa Bool) && 1<=maxiter<=256 ||
        ensemble_fail("INVALID_ENSEMBLE","Root iteration budget must be between 1 and 256")
    capacity=sum(w[k]*length(energies[k]) for k in eachindex(w))
    ne<capacity || ensemble_fail("INSUFFICIENT_BANDS","Target states lack empty capacity at finite temperature")
    margin=t*max(64.0,log(capacity)-log(Float64(electron_tol))+4)
    lower=minimum(minimum,energies)-margin; upper=maximum(maximum,energies)+margin
    isfinite(lower)&&isfinite(upper)&&lower<upper ||
        ensemble_fail("ROOT_NOT_BRACKETED","Spectrum/temperature cannot form a finite Float64 bracket")
    initial_bracket=(lower,upper)
    count_lower=_ensemble_count(_fermi_at_mu(energies,lower,t),w)
    count_upper=_ensemble_count(_fermi_at_mu(energies,upper,t),w)
    count_lower<=ne<=count_upper ||
        ensemble_fail("ROOT_NOT_BRACKETED","Bounded thermal bracket does not enclose the requested electron count")
    plateau=_fermi_gap_plateau(energies,w,ne,t,Float64(electron_tol))
    iterations=0;mu=0.0;f=Vector{Vector{Float64}}()
    if !isnothing(plateau)
        mu=plateau.mu;f=_fermi_at_mu(energies,mu,t)
        lower,upper=plateau.interval
    else
        converged=false
        for iteration in 1:maxiter
            iterations=iteration
            mu=lower/2+upper/2;f=_fermi_at_mu(energies,mu,t)
            residual=_ensemble_count(f,w)-ne
            if abs(residual)<=electron_tol
                converged=true;break
            end
            if mu==lower || mu==upper
                break
            end
            residual<0 ? (lower=mu) : (upper=mu)
        end
        converged || ensemble_fail("ROOT_NOT_CONVERGED","Bounded bisection could not achieve the electron tolerance")
    end
    _ensemble_occupations(f)
    per_k=sum.(f);shares=w.*per_k;count=sum(shares);residual=count-ne
    abs(residual)<=electron_tol || ensemble_fail("ROOT_NOT_CONVERGED","Final occupations violate electron tolerance")
    report=(;status="PASS",capacity_per_state=1,tau_ha=t,smearing="FermiDirac",mu_ha=mu,
        electron_count=count,target_electrons=ne,electron_residual=residual,iterations,maxiter,
        spatial_weights=w,electrons_per_k_unweighted=per_k,electrons_per_k_weighted=shares,
        occupation_minimum=minimum(minimum,f),occupation_maximum=maximum(maximum,f),
        highest_two=[f[k][sortperm(energies[k])[max(1,end-1):end]] for k in eachindex(f)],
        initial_bracket_ha=initial_bracket,final_bracket_ha=(lower,upper),
        numerical_plateau=!isnothing(plateau),
        plateau_interval_ha=isnothing(plateau) ? nothing : plateau.interval,
        plateau_gap_ha=isnothing(plateau) ? nothing : plateau.gap,
        mu_selection_rule=isnothing(plateau) ? "First bounded-bisection midpoint satisfying the global count tolerance" :
            "Midpoint of the global spectral gap; Float64 counts equal at its 1/4,1/2,3/4 points")
    (;f,mu,report)
end

function _binary_entropy(f::Real)
    f==0 || f==1 ? 0.0 : -f*log(f)-(1-f)*log1p(-f)
end

"""Seven-term internal E plus physical-spinor entropy once; never use fchi=[f;f]."""
function ensemble_free_energy(internal_energy,f,weights,tau)
    _ensemble_occupations(f);w=_ensemble_weights(weights,length(f));t=_ensemble_tau(tau)
    internal_energy isa Real && isfinite(internal_energy) || ensemble_fail("INVALID_ENSEMBLE","Internal energy must be finite")
    E=Float64(internal_energy)
    S=sum(w[k]*sum(_binary_entropy,Float64.(f[k])) for k in eachindex(w))
    entropy_energy=-t*S;F=E+entropy_energy
    all(isfinite,(E,S,entropy_energy,F)) && S>=0 && entropy_energy<=0 ||
        ensemble_fail("INVALID_ENSEMBLE","Nonfinite or incorrectly signed entropy/free energy")
    arithmetic_error=F-E-entropy_energy
    abs(arithmetic_error)<=1e-12*max(1,abs(F),abs(E)) ||
        ensemble_fail("INVALID_ENSEMBLE","Free-energy arithmetic identity failed")
    (;internal_energy_ha=E,entropy_dimensionless=S,entropy_energy_ha=entropy_energy,free_energy_ha=F,
      arithmetic_error_ha=arithmetic_error,tau_ha=t,entropy_capacity_per_state=1,
      entropy_scope="Physical spinor f only, spatial weights; S/k_B; no core or component multiplicity")
end

"""Local FD stationarity only for numerically resolvable partial occupations."""
function occupation_stationarity(eigenvalues,f,mu,tau;endpoint_margin=1e-8)
    energies=_ensemble_levels(eigenvalues);_ensemble_occupations(f);t=_ensemble_tau(tau)
    length(energies)==length(f) && all(length(e)==length(o) for (e,o) in zip(energies,f)) ||
        ensemble_fail("INVALID_ENSEMBLE","Stationarity energy/occupation shapes differ")
    mu isa Real && isfinite(mu) && 0<endpoint_margin<.5 ||
        ensemble_fail("INVALID_ENSEMBLE","Invalid chemical potential or endpoint margin")
    values=NamedTuple[];excluded=0
    for k in eachindex(f),n in eachindex(f[k])
        o=f[k][n]
        if endpoint_margin<=o<=1-endpoint_margin
            residual=energies[k][n]+t*(log(o)-log1p(-o))-mu
            isfinite(residual) || ensemble_fail("INVALID_ENSEMBLE","Nonfinite occupation stationarity residual")
            push!(values,(;k_index=k,band_index=n,occupation=o,residual_ha=residual))
        else
            excluded+=1
        end
    end
    (;status=isempty(values) ? "NO_RESOLVABLE_PARTIAL_OCCUPATIONS" : "EVALUATED",
      values,checked_states=length(values),excluded_states=excluded,endpoint_margin,
      max_abs_residual_ha=isempty(values) ? 0.0 : maximum(abs(v.residual_ha) for v in values))
end

"""Finite target-band diagnostic, not a bound on the uncomputed infinite tail."""
function band_completeness(f;threshold=1e-10)
    _ensemble_occupations(f)
    threshold isa Real && isfinite(threshold) && 0<=threshold<=1e-10 ||
        ensemble_fail("INVALID_ENSEMBLE","Boundary occupation threshold must not exceed 1e-10")
    target=length(first(f))
    all(length(o)==target for o in f) && target in (24,32,40,48) ||
        ensemble_fail("INVALID_ENSEMBLE","All physical k points require the same target count from 24,32,40,48")
    all(o->issorted(o;rev=true),f) || ensemble_fail("INVALID_ENSEMBLE","Band diagnostic requires energy-ordered FD occupations")
    top=[copy(o[end-1:end]) for o in f]
    maximum_top=maximum(maximum,top)
    enough=maximum_top<=threshold
    status=enough ? "PASS" : target==48 ? "INSUFFICIENT_BANDS" : "EXPAND"
    (;status,target,next_target=status=="EXPAND" ? target+8 : nothing,top_two=top,
      maximum_top_occupation=maximum_top,threshold,
      scope="Highest two converged physical target states per k; auxiliary states excluded; finite-tail diagnostic")
end
