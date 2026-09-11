"""Opt-in ownership and validation adapter; the numerical kernels have no provenance I/O."""
const _CoreKernels = SpinorPrototype.SOCKernels

mutable struct _RuntimeWorkspace
    nonlocal
    component
    density
    common_action::Matrix{ComplexF64}
    fr_action::Matrix{ComplexF64}
end

function _runtime_workspace(ctx,max_rhs)
    maxng=maximum(length(k.G_vectors) for k in ctx.basis.kpoints)
    maxp=maximum(size(op.P,2) for op in ctx.fr_blocks)
    nr=prod(ctx.basis.fft_size)
    ws=_RuntimeWorkspace(_CoreKernels.NonlocalWorkspace(2maxng,maxp,max_rhs),
        _CoreKernels.ComponentWorkspace(maxng,max_rhs,2),
        SpinorPrototype.OrbitalDensityWorkspace(maxng,nr,ctx.basis.fft_size,2),
        Matrix{ComplexF64}(undef,2maxng,max_rhs),Matrix{ComplexF64}(undef,2maxng,max_rhs))
    ws,(;max_ng=maxng,max_projectors=maxp,max_rhs,n_real=nr,n_components=2)
end

"""
Own a newly issued context and its original certificates. This consumes the
legacy authority for that context; callers may not use its borrowed aliases
during a numerical session. Boundary checks detect sequential outside mutation.
Fields are private by API convention, not a security or concurrency sandbox.
"""
mutable struct OwnedRuntime
    _context::Union{Nothing,FRHamiltonianContext}
    _certificate
    _sources::IdDict{Any,Any}
    _workspace::Union{Nothing,_RuntimeWorkspace}
    _capacity::NamedTuple
    _generation::Int
    _current
    _current_storage::Vector
    _derived_storage::Vector
    _term_values
    _density_sha256::Union{Nothing,String}
    _busy::Bool
    _closed::Bool
    _boundaries::Dict{String,Int}
    _counts::Dict{String,Int}
    function OwnedRuntime(ctx::FRHamiltonianContext,max_rhs::Integer)
        !(max_rhs isa Bool) && 0<max_rhs<=30 || throw(ArgumentError("Runtime RHS capacity must be an integer in 1:30"))
        validate_context(ctx)
        cert=_context_certificate(ctx)
        sources=IdDict{Any,Any}()
        for bundle in ctx.bundles
            sources[bundle._token]=_BOUND_PSP_SOURCES[bundle._token]
        end
        # A transferred source cannot invalidate another live legacy context.
        for (other,_) in _FR_CONTEXT_CERTIFICATES
            other===ctx && continue
            any(b->haskey(sources,b._token),other.bundles) &&
                throw(ArgumentError("Cannot transfer a source shared by another legacy context"))
        end
        workspace,capacity=_runtime_workspace(ctx,Int(max_rhs))
        derived=_storage_certificate(_runtime_term_arrays(ctx))
        counts=Dict(name=>0 for name in ("fr_mul_calls","fr_columns","component_mul_calls",
            "component_columns","full_mul_calls","full_columns","density_calls"))
        rt=new(ctx,cert,sources,workspace,capacity,0,nothing,Any[],derived,
            _runtime_term_values(ctx),nothing,false,false,Dict{String,Int}(),counts)
        validate_context(rt)
        # All checks and allocations precede the ownership transfer. No global
        # registry receives this runtime or any new Hamiltonian/density object.
        delete!(_FR_CONTEXT_CERTIFICATES,ctx)
        for token in keys(sources)
            delete!(_BOUND_PSP_SOURCES,token)
        end
        rt._boundaries["conversion"]=1
        rt
    end
end

owned_runtime(ctx::FRHamiltonianContext;max_rhs=30)=OwnedRuntime(ctx,max_rhs)
FullHamiltonianBlock(rt::OwnedRuntime,ik::Integer,scalar,fr)=
    throw(ArgumentError("Owned runtimes require compose_full_hamiltonian; legacy full-H fallback is forbidden"))
runtime_enabled(ctx)=false
runtime_enabled(::OwnedRuntime)=true
runtime_boundary!(ctx,event;ham=nothing)=true
close_runtime!(ctx)=nothing
runtime_fr_blocks(ctx)=ctx.fr_blocks

function Base.getproperty(rt::OwnedRuntime,name::Symbol)
    if name in (:basis,:bundles,:fr_blocks,:mode,:xc_identifiers)
        ctx=getfield(rt,:_context)
        isnothing(ctx) && throw(ArgumentError("Owned runtime is closed"))
        return getproperty(ctx,name)
    end
    getfield(rt,name)
end
Base.propertynames(::OwnedRuntime,private=false)=(:basis,:bundles,:fr_blocks,:mode,:xc_identifiers,fieldnames(OwnedRuntime)...)

function _runtime_open(rt::OwnedRuntime)
    !rt._closed && !isnothing(rt._context) && !isnothing(rt._workspace) ||
        throw(ArgumentError("Owned runtime is closed"))
    rt
end
_context_certificate(rt::OwnedRuntime)=(_runtime_open(rt);rt._certificate)
function _context_assert_bound_identity(rt::OwnedRuntime,bundle)
    _assert_bound_identity(bundle,get(rt._sources,bundle._token,nothing))
end
function _context_assert_bound_sources(rt::OwnedRuntime,bundle)
    _assert_bound_sources(bundle,get(rt._sources,bundle._token,nothing))
end

function _runtime_term_arrays(ctx)
    b=ctx.basis
    kinetic=only(filter(t->t isa DFTK.TermKinetic,b.terms))
    localterm=only(filter(t->t isa DFTK.TermAtomicLocal,b.terms))
    hartree=only(filter(t->t isa DFTK.TermHartree,b.terms))
    xc=only(filter(t->t isa DFTK.TermXc,b.terms))
    arrays=Any[("kinetic/$i",array) for (i,array) in enumerate(kinetic.kinetic_energies)]
    append!(arrays,[("atomic_local",localterm.potential_values),("hartree",hartree.poisson_green_coeffs)])
    isnothing(xc.ρcore) || push!(arrays,("rho_core",xc.ρcore))
    isnothing(xc.τcore) || push!(arrays,("tau_core",xc.τcore))
    arrays
end
function _runtime_term_values(ctx)
    b=ctx.basis
    term(T)=only(filter(t->t isa T,b.terms))
    (;kinetic=term(DFTK.TermKinetic).scaling_factor,hartree=term(DFTK.TermHartree).scaling_factor,
      ewald=term(DFTK.TermEwald).energy,psp_correction=term(DFTK.TermPspCorrection).energy)
end
function _storage_certificate(arrays)
    hashes=IdDict{Any,String}()
    Any[(;label,array,shape=size(array),sha256=get!(()->_fr_array_hash(array),hashes,array)) for (label,array) in arrays]
end
function _check_storage(certificate,arrays)
    length(certificate)==length(arrays) || throw(ArgumentError("Runtime numerical storage count changed"))
    hashes=IdDict{Any,String}()
    for (saved,(label,array)) in zip(certificate,arrays)
        label==saved.label && array===saved.array && size(array)==saved.shape &&
            get!(()->_fr_array_hash(array),hashes,array)==saved.sha256 ||
            throw(ArgumentError("Runtime numerical storage changed: $label"))
    end
    true
end
function _ham_storage(common)
    arrays=Any[]
    for (ik,scalar) in enumerate(common.blocks)
        for listname in (:operators,:optimized_operators)
            hasproperty(scalar,listname) || continue
            for (j,op) in enumerate(getproperty(scalar,listname))
                op isa DFTK.RealSpaceMultiplication && push!(arrays,("$ik/$listname/$j/local",op.potential))
                op isa DFTK.FourierMultiplication && push!(arrays,("$ik/$listname/$j/fourier",op.multiplier))
            end
        end
        hasproperty(scalar,:local_op) && push!(arrays,("$ik/local_op",scalar.local_op.potential))
        hasproperty(scalar,:fourier_op) && push!(arrays,("$ik/fourier_op",scalar.fourier_op.multiplier))
    end
    arrays
end

function runtime_boundary!(rt::OwnedRuntime,event;ham=nothing)
    _runtime_open(rt)
    !rt._busy || throw(ArgumentError("Boundary entered during an active numerical action"))
    validate_context(rt)
    _check_storage(rt._derived_storage,_runtime_term_arrays(rt))
    _runtime_term_values(rt)==rt._term_values || throw(ArgumentError("Common energy/kinetic term values changed"))
    if !isnothing(rt._current)
        for (ik,scalar) in enumerate(rt._current.blocks)
            _check_common_block(rt,ik,scalar)
        end
        _check_storage(rt._current_storage,_ham_storage(rt._current))
    end
    if !isnothing(ham)
        blocks=hasproperty(ham,:full) ? ham.full : ham isa Union{AbstractVector,Tuple} ? ham : (ham,)
        for h in blocks
            h isa RuntimeFullHamiltonian || throw(ArgumentError("Boundary received a non-runtime Hamiltonian"))
            _runtime_hamiltonian_current(h)
            h.runtime===rt || throw(ArgumentError("Hamiltonian belongs to another runtime"))
        end
    end
    key=string(event);rt._boundaries[key]=get(rt._boundaries,key,0)+1
    true
end

function close_runtime!(rt::OwnedRuntime)
    rt._closed && return rt
    failure=nothing
    try
        runtime_boundary!(rt,:session_close)
    catch error
        failure=error
    finally
        # Even a failed final boundary releases every runtime-owned reference.
        rt._generation+=1;rt._closed=true;rt._busy=false
        rt._current=nothing;empty!(rt._current_storage);empty!(rt._derived_storage)
        rt._context=nothing;rt._certificate=nothing;empty!(rt._sources)
        rt._workspace=nothing;rt._density_sha256=nothing;rt._term_values=nothing
        rt._boundaries["close"]=get(rt._boundaries,"close",0)+1
    end
    isnothing(failure) || throw(failure)
    rt
end
function runtime_summary(rt::OwnedRuntime)
    counts=(;fr_mul_calls=rt._counts["fr_mul_calls"],fr_columns=rt._counts["fr_columns"],
        component_mul_calls=rt._counts["component_mul_calls"],component_columns=rt._counts["component_columns"],
        full_mul_calls=rt._counts["full_mul_calls"],full_columns=rt._counts["full_columns"],density_calls=rt._counts["density_calls"])
    (;backend="soc-core",closed=rt._closed,generation=rt._generation,max_rhs=rt._capacity.max_rhs,
      workspace_capacity=rt._capacity,workspace_released=isnothing(rt._workspace),
      owned_source_entries=length(rt._sources),owned_context_present=!isnothing(rt._context),
      counters=counts,boundary_counts=copy(rt._boundaries),
      density_sha256=rt._density_sha256,
      ownership="One consumed loader-issued context; original P/D only; private boundary certificates; serial scoped workspace")
end

struct RuntimeFRBlock
    runtime::OwnedRuntime
    ik::Int
end
function Base.getproperty(op::RuntimeFRBlock,name::Symbol)
    if name in (:P,:D,:labels)
        rt=getfield(op,:runtime);_runtime_open(rt)
        return getproperty(rt.fr_blocks[getfield(op,:ik)],name)
    end
    getfield(op,name)
end
Base.size(op::RuntimeFRBlock)=(size(op.P,1),size(op.P,1))
Base.size(op::RuntimeFRBlock,i::Integer)=i>0 ? (i<=2 ? size(op)[1] : 1) : throw(ArgumentError("Positive dimension required"))
Base.eltype(::RuntimeFRBlock)=ComplexF64
Base.eltype(::Type{RuntimeFRBlock})=ComplexF64
runtime_fr_blocks(rt::OwnedRuntime)=(_runtime_open(rt);[RuntimeFRBlock(rt,i) for i in eachindex(rt.fr_blocks)])
_context_nonlocal_operators(rt::OwnedRuntime)=runtime_fr_blocks(rt)

function _runtime_action_enter!(rt)
    _runtime_open(rt)
    !rt._busy || throw(ArgumentError("Runtime workspace is already in use; nested/concurrent actions are unsupported"))
    rt._busy=true
end
function _runtime_buffers(ws)
    (ws.common_action,ws.fr_action,ws.nonlocal.coefficients,ws.nonlocal.weighted,ws.nonlocal.candidate,
     ws.component.spatial_input,ws.component.spatial_output,ws.component.candidate,
     SpinorPrototype._orbital_workspace_buffers(ws.density)...)
end
function _runtime_protect_arrays(rt,Y,X;scalar=nothing,op=nothing)
    buffers=_runtime_buffers(rt._workspace)
    any(a->Base.mightalias(Y,a)||Base.mightalias(X,a),buffers) &&
        throw(ArgumentError("Caller arrays alias runtime workspace storage"))
    _CoreKernels._no_overlap(buffers)
    for a in buffers
        !isnothing(scalar) && _aliases_common_storage(a,scalar) &&
            throw(ArgumentError("Runtime scratch aliases the retained scalar operator"))
        !isnothing(op) && (Base.mightalias(a,op.P)||Base.mightalias(a,op.D)) &&
            throw(ArgumentError("Runtime scratch aliases retained FR data"))
    end
    nothing
end
function LinearAlgebra.mul!(Y::AbstractVecOrMat,op::RuntimeFRBlock,X::AbstractVecOrMat,a::Number,b::Number)
    rt=op.runtime;_runtime_open(rt);_runtime_protect_arrays(rt,Y,X;op);_runtime_action_enter!(rt)
    try
        _CoreKernels.nonlocal_action!(Y,op.P,op.D,X,rt._workspace.nonlocal,a,b)
        rt._counts["fr_mul_calls"]+=1;rt._counts["fr_columns"]+=size(X,2)
        Y
    finally
        rt._busy=false
    end
end
LinearAlgebra.mul!(Y::AbstractVecOrMat,op::RuntimeFRBlock,X::AbstractVecOrMat)=mul!(Y,op,X,1,0)
Base.:*(op::RuntimeFRBlock,X::AbstractVecOrMat)=mul!(similar(X,ComplexF64),op,X)

mutable struct RuntimeComponentBlock{S}
    runtime::OwnedRuntime
    ik::Int
    generation::Int
    scalar::S
    ncomp::Int
    ng::Int
    calls::Vector{Int}
end
struct RuntimeFullHamiltonian{C}
    runtime::OwnedRuntime
    ik::Int
    generation::Int
    common::C
    calls::Vector{Int}
end
function Base.getproperty(h::RuntimeFullHamiltonian,name::Symbol)
    name===:fr && return RuntimeFRBlock(getfield(h,:runtime),getfield(h,:ik))
    name===:context && return getfield(h,:runtime)
    name===:scalar_binding && return getfield(h,:common).scalar
    getfield(h,name)
end
Base.size(h::RuntimeFullHamiltonian)=(2h.common.ng,2h.common.ng)
Base.size(h::RuntimeFullHamiltonian,i::Integer)=i>0 ? (i<=2 ? size(h)[1] : 1) : throw(ArgumentError("Positive dimension required"))
Base.eltype(::RuntimeFullHamiltonian)=ComplexF64
Base.size(h::RuntimeComponentBlock)=(h.ncomp*h.ng,h.ncomp*h.ng)
Base.size(h::RuntimeComponentBlock,i::Integer)=i>0 ? (i<=2 ? size(h)[1] : 1) : throw(ArgumentError("Positive dimension required"))
Base.eltype(::RuntimeComponentBlock)=ComplexF64
function _runtime_hamiltonian_current(h)
    rt=h.runtime;_runtime_open(rt)
    h.generation==rt._generation && !isnothing(rt._current) &&
        1<=h.ik<=length(rt._current.blocks) || throw(ArgumentError("Stale Hamiltonian generation"))
    scalar=h isa RuntimeFullHamiltonian ? h.common.scalar : h.scalar
    scalar===rt._current.blocks[h.ik] || throw(ArgumentError("Stale or exchanged scalar Hamiltonian"))
    common=h isa RuntimeFullHamiltonian ? h.common : h
    common.runtime===rt && common.ik==h.ik && common.generation==rt._generation &&
        common.ncomp==2 && common.ng==size(scalar,1) || throw(ArgumentError("Runtime component binding changed"))
    true
end
function _component_action!(Y,h,X,a,b)
    _CoreKernels.component_action!(Y,(out,input)->mul!(out,h.scalar,input),X,h.ncomp,
        h.runtime._workspace.component,a,b)
    nrhs=size(X,2);h.calls[1]+=1;h.calls[2]+=nrhs;h.calls[3]+=h.ncomp;h.calls[4]+=h.ncomp*nrhs
    h.runtime._counts["component_mul_calls"]+=1;h.runtime._counts["component_columns"]+=nrhs
    Y
end
function LinearAlgebra.mul!(Y::AbstractVecOrMat,h::RuntimeComponentBlock,X::AbstractVecOrMat,a::Number,b::Number)
    _runtime_hamiltonian_current(h);rt=h.runtime
    _runtime_protect_arrays(rt,Y,X;scalar=h.scalar,op=rt.fr_blocks[h.ik]);_runtime_action_enter!(rt)
    try
        _aliases_common_storage(Y,h.scalar) && throw(ArgumentError("Component output aliases common operator storage"))
        _component_action!(Y,h,X,a,b)
    finally
        rt._busy=false
    end
end
LinearAlgebra.mul!(Y::AbstractVecOrMat,h::RuntimeComponentBlock,X::AbstractVecOrMat)=mul!(Y,h,X,1,0)
Base.:*(h::RuntimeComponentBlock,X::AbstractVecOrMat)=mul!(similar(X,ComplexF64),h,X)
SpinorPrototype.operator_stats(h::RuntimeComponentBlock)=(;operator_mul_calls=h.calls[1],operator_columns=h.calls[2],scalar_mul_calls=h.calls[3],scalar_columns=h.calls[4])
SpinorPrototype.reset_counters!(h::RuntimeComponentBlock)=(fill!(h.calls,0);h)

function LinearAlgebra.mul!(Y::AbstractVecOrMat,h::RuntimeFullHamiltonian,X::AbstractVecOrMat,alpha::Number,beta::Number)
    _runtime_hamiltonian_current(h)
    Base.require_one_based_indexing(Y,X)
    size(Y)==size(X) && size(X,1)==size(h,1) && size(X,2)>0 || throw(DimensionMismatch("Full-H input/output shape mismatch"))
    eltype(Y)===ComplexF64 && eltype(X) in (Float64,ComplexF64) || throw(ArgumentError("Full-H Float64/ComplexF64 storage required"))
    rt=h.runtime;op=rt.fr_blocks[h.ik];ws=rt._workspace
    _runtime_protect_arrays(rt,Y,X;scalar=h.common.scalar,op)
    size(X,2)<=rt._capacity.max_rhs || throw(DimensionMismatch("Runtime RHS capacity exceeded"))
    (any(a->Base.mightalias(Y,a),(X,op.P,op.D,ws.common_action,ws.fr_action)) ||
        any(a->Base.mightalias(X,a),(ws.common_action,ws.fr_action)) || _aliases_common_storage(Y,h.common.scalar)) &&
        throw(ArgumentError("Full-H arrays alias input, owned operator or workspace storage"))
    all(isfinite,X) && isfinite(alpha) && isfinite(beta) || throw(ArgumentError("Nonfinite full-H input or scale"))
    a,b=ComplexF64(alpha),ComplexF64(beta)
    isfinite(a) && isfinite(b) || throw(ArgumentError("Full-H scale overflows ComplexF64"))
    iszero(beta) || all(isfinite,Y) || throw(ArgumentError("Nonfinite beta-weighted full-H output"))
    _runtime_action_enter!(rt)
    try
        rows,cols=size(X,1),size(X,2)
        common=@view ws.common_action[1:rows,1:cols]
        fr=@view ws.fr_action[1:rows,1:cols]
        xm=reshape(X,rows,cols);ym=reshape(Y,rows,cols)
        _component_action!(common,h.common,xm,1,0)
        _CoreKernels.nonlocal_action!(fr,op.P,op.D,xm,ws.nonlocal,1,0)
        # Preserve the old alpha*(common+FR)+beta*Y order and failure atomicity.
        for i in eachindex(common,fr)
            common[i]=a*(common[i]+fr[i])
        end
        if !iszero(beta)
            for i in eachindex(common,ym)
                common[i]+=b*ym[i]
            end
        end
        all(isfinite,common) || throw(ArgumentError("Full-H action produced nonfinite values"))
        copyto!(ym,common)
        h.calls[1]+=1;h.calls[2]+=cols;h.calls[3]+=1;h.calls[4]+=cols
        rt._counts["full_mul_calls"]+=1;rt._counts["full_columns"]+=cols
        rt._counts["fr_mul_calls"]+=1;rt._counts["fr_columns"]+=cols
        Y
    finally
        rt._busy=false
    end
end
LinearAlgebra.mul!(Y::AbstractVecOrMat,h::RuntimeFullHamiltonian,X::AbstractVecOrMat)=mul!(Y,h,X,1,0)
Base.:*(h::RuntimeFullHamiltonian,X::AbstractVecOrMat)=mul!(similar(X,ComplexF64),h,X)
full_operator_stats(h::RuntimeFullHamiltonian)=(;full_mul_calls=h.calls[1],full_columns=h.calls[2],fr_mul_calls=h.calls[3],fr_columns=h.calls[4],common=SpinorPrototype.operator_stats(h.common),backend="soc-core")
reset_full_counters!(h::RuntimeFullHamiltonian)=(fill!(h.calls,0);SpinorPrototype.reset_counters!(h.common);h)

function compose_full_hamiltonian(rt::OwnedRuntime,common_ham;fr_blocks=rt.fr_blocks)
    runtime_boundary!(rt,:hamiltonian_replacement)
    common_ham isa DFTK.Hamiltonian && common_ham.basis===rt.basis || throw(ArgumentError("Common Hamiltonian belongs to another basis"))
    length(common_ham.blocks)==length(rt.fr_blocks)==length(fr_blocks) || throw(DimensionMismatch("Full-H block counts changed"))
    all(fr_blocks[i]===rt.fr_blocks[i] for i in eachindex(fr_blocks)) || throw(ArgumentError("FR block source/order changed"))
    for (ik,scalar) in enumerate(common_ham.blocks)
        _check_common_block(rt,ik,scalar)
    end
    storage=_storage_certificate(_ham_storage(common_ham))
    rt._generation+=1;rt._current=common_ham;rt._current_storage=storage;rt._density_sha256=nothing
    [RuntimeFullHamiltonian(rt,ik,rt._generation,
        RuntimeComponentBlock(rt,ik,rt._generation,scalar,2,size(scalar,1),zeros(Int,4)),zeros(Int,4))
        for (ik,scalar) in enumerate(common_ham.blocks)]
end
function _context_density_binding!(rt::OwnedRuntime,rho)
    _runtime_open(rt);rt._density_sha256=integration_density_hash(rho)
    nothing
end
function context_orbital_density(rt::OwnedRuntime,X,f;stream_k=false)
    stream_k isa Bool || throw(ArgumentError("stream_k must be boolean"))
    runtime_boundary!(rt,:density_entry)
    check_energy_orbitals(rt.basis,X,f)
    _runtime_action_enter!(rt)
    result=try
        borrowed=SpinorPrototype.orbital_density!(rt._workspace.density,rt.basis,X,rt.basis.kweights,f)
        # The FFT adapter deliberately lends its accumulator. Public/SCF
        # results own independent arrays, including the second energy recovery.
        (;R=copy(borrowed.R),n=copy(borrowed.n),m=isnothing(borrowed.m) ? nothing : copy(borrowed.m))
    finally
        rt._busy=false
    end
    rt._counts["density_calls"]+=1
    runtime_boundary!(rt,:density_return)
    result
end

function RelativisticProjectors.projected_nonlocal_energy(operators::AbstractVector{RuntimeFRBlock},X,weights,f)
    RelativisticProjectors._check_nonlocal_energy(operators,X,weights,f)
    total=0.0
    for (op,x,w,occ) in zip(operators,X,weights,f)
        rt=op.runtime;_runtime_action_enter!(rt)
        try
            total=_CoreKernels.projected_nonlocal_energy(op.P,op.D,x,occ,w,rt._workspace.nonlocal;initial_total=total)
        finally
            rt._busy=false
        end
    end
    isfinite(total) || throw(ArgumentError("Nonfinite runtime projected nonlocal energy"))
    total
end
