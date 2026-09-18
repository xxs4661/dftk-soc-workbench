# Purely synthetic providers for the REAL adapter validation functions below.
# No UPF is read/generated, no physical basis/context is constructed, and no
# eigensolve, occupation solve, FFT, energy evaluation or SCF is performed.
# Test registries are deliberately populated in isolated modules; this is not
# evidence that the production loader accepts these artificial objects.
using Test, LinearAlgebra, Random, SHA

const BOUNDARY_ROOT=normpath(joinpath(@__DIR__,"../.."))
const BOUNDARY_REFERENCE="d9e19af3557c923a1e4f7e64510092d47975cc7c"
include(joinpath(BOUNDARY_ROOT,"src/SOCKernels.jl"))
include(joinpath(BOUNDARY_ROOT,"prototypes/diagnostics.jl"))

module BoundaryDFTK
using LinearAlgebra
abstract type NormConservingPsp end
module Smearing
struct None end
struct FermiDirac end
end
for name in (:Kinetic,:AtomicLocal,:Ewald,:PspCorrection,:Hartree,:TermAtomicNonlocal,:NonlocalOperator)
    @eval struct $name end
end
mutable struct Xc
    functionals; use_nlcc; nlcc_from_vw; scaling_factor; potential_threshold
end
mutable struct TermKinetic; kinetic_energies; scaling_factor; end
mutable struct TermAtomicLocal; potential_values; end
mutable struct TermHartree; poisson_green_coeffs; scaling_factor; end
mutable struct TermXc; functionals; scaling_factor; potential_threshold; ρcore; τcore; end
mutable struct TermEwald; energy; end
mutable struct TermPspCorrection; energy; end
mutable struct RealSpaceMultiplication; potential; end
mutable struct FourierMultiplication; multiplier; end
mutable struct HamiltonianBlock
    basis; kpoint; operators; optimized_operators; local_op; fourier_op; nonlocal_op
end
mutable struct Hamiltonian; basis; blocks; end
Base.size(h::HamiltonianBlock)=(length(h.kpoint.G_vectors),length(h.kpoint.G_vectors))
Base.size(h::HamiltonianBlock,i::Integer)=size(h)[i]
Base.eltype(::HamiltonianBlock)=ComplexF64
# A declared artificial diagonal matrix, only for small alias/output checks.
LinearAlgebra.mul!(Y,h::HamiltonianBlock,X)=(Y .= 2 .* X;Y)
identifier(x)=x
for name in (:charge_ionic,:has_valence_density,:has_core_density,:has_core_kinetic_energy_density,
             :eval_psp_local_fourier,:eval_psp_valence_density_fourier,:eval_psp_core_density_fourier,
             :eval_psp_energy_correction,:eval_psp_local_real,:eval_psp_core_density_real,
             :eval_psp_valence_density_real,:count_n_proj,:count_n_proj_radial,
             :eval_psp_projector_fourier,:eval_psp_projector_real)
    @eval function $name end
end
end

module BoundaryPPIO
mutable struct UpfFile; header;mesh;local_;rhoatom;nlcc;end
end
module BoundaryChannels
mutable struct ChannelModel; channels;end
function projected_nonlocal_energy end
end
module BoundarySpinor
using LinearAlgebra
const SOCKernels=Main.SOCKernels
const DFTK=Main.BoundaryDFTK
# Reuse the existing small workspace/alias implementations; their FFT and
# orbital-density functions are defined but never evaluated by these tests.
include(joinpath(Main.BOUNDARY_ROOT,"prototypes/spinor/operators.jl"))
include(joinpath(Main.BOUNDARY_ROOT,"prototypes/spinor/fft.jl"))
end

module BoundaryCandidate
using LinearAlgebra, SHA, Random
const DFTK=Main.BoundaryDFTK
const PseudoPotentialIO=Main.BoundaryPPIO
const RelativisticProjectors=Main.BoundaryChannels
const SpinorPrototype=Main.BoundarySpinor
include(joinpath(Main.BOUNDARY_ROOT,"prototypes/fr_integration/common_data.jl"))
include(joinpath(Main.BOUNDARY_ROOT,"prototypes/fr_integration/hamiltonian.jl"))
include(joinpath(Main.BOUNDARY_ROOT,"prototypes/fr_integration/runtime.jl"))
end
module BoundaryReference
using LinearAlgebra, SHA, Random
const DFTK=Main.BoundaryDFTK
const PseudoPotentialIO=Main.BoundaryPPIO
const RelativisticProjectors=Main.BoundaryChannels
const SpinorPrototype=Main.BoundarySpinor
for relative in ("common_data.jl","hamiltonian.jl","runtime.jl")
    path="prototypes/fr_integration/"*relative
    source=read(`git -C $(Main.BOUNDARY_ROOT) show $(Main.BOUNDARY_REFERENCE*":"*path)`,String)
    include_string(@__MODULE__,source,"frozen-reference/"*path)
end
end
module BoundarySOC
using LinearAlgebra, Random
const FI=Main.BoundaryCandidate
const DFTK=Main.BoundaryDFTK
const RunDiagnostics=Main.WorkbenchDiagnostics
include(joinpath(Main.BOUNDARY_ROOT,"prototypes/soc_scf/scf.jl"))
end
module ReferenceSOC
using LinearAlgebra, Random
const FI=Main.BoundaryReference
const DFTK=Main.BoundaryDFTK
const RunDiagnostics=Main.WorkbenchDiagnostics
const path="prototypes/soc_scf/scf.jl"
include_string(@__MODULE__,read(`git -C $(Main.BOUNDARY_ROOT) show $(Main.BOUNDARY_REFERENCE*":"*path)`,String),
               "frozen-reference/"*path)
end

mutable struct SyntheticBasis
    model; kpoints; kweights; fft_size; Ecut; terms
end
mutable struct SyntheticModel
    lattice;positions;atoms;n_electrons;temperature;smearing;term_types;spin_polarization;n_spin_components
end
mutable struct SyntheticKpoint
    coordinate;G_vectors;mapping;mapping_inv;mapping_device
end
struct SyntheticFR
    P::Matrix{ComplexF64};D::Matrix{ComplexF64};labels::Vector{NamedTuple}
end

function synthetic_bundle(FI)
    token=Ref{Nothing}(nothing);r=collect(0.0:0.25:1.0);rab=fill(0.25,5)
    raw=[-2.,-1.5,-1.,-0.5,0.];valence=ones(5);core=fill(0.1,5)
    header=(;element="X",z_valence=2,functional="SYNTHETIC",relativistic="full",has_so=true,core_correction=true)
    parsed=BoundaryPPIO.UpfFile(header,(;r=copy(r),rab=copy(rab)),copy(raw),copy(valence),copy(core))
    common=FI.CommonPspData(token,"synthetic","not a pseudopotential","synthetic-digest","memory-only",
        "synthetic header",:X,2,"SYNTHETIC","full",true,true,r,rab,raw,raw./2,valence,core,
        valence./(4π),r.^2 .*core,(;local_potential=5,valence=5,core=5,correction=5))
    channels=BoundaryChannels.ChannelModel([(;l=0,j=0.5,radial=[1.,2.])])
    bundle=FI.BoundPspBundle(token,common,channels,parsed,:real_fr,[:synthetic_xc],"synthetic-digest")
    FI._BOUND_PSP_SOURCES[token]=(;bundle,common,channels,parsed,
        common_snapshot=FI._source_snapshot(common),channel_snapshot=FI._source_snapshot(channels),
        parsed_snapshot=FI._source_snapshot(parsed),metadata=(bundle.mode,copy(bundle.xc_identifiers),bundle.sha256))
    bundle
end

function synthetic_context(FI;shared_sources=true)
    T=BoundaryDFTK;b=synthetic_bundle(FI);b2=shared_sources ? b : synthetic_bundle(FI)
    termtypes=Any[T.Kinetic(),T.AtomicLocal(),T.Ewald(),T.PspCorrection(),T.Hartree(),
        T.Xc([:synthetic_xc],true,false,1,0)]
    model=SyntheticModel(Matrix{Float64}(I,3,3),[[0.,0.,0.],[0.25,0.25,0.25]],
        Any[(;psp=b.common),(;psp=b2.common)],4,0.,T.Smearing.None(),termtypes,:none,1)
    ks=Any[SyntheticKpoint(copy(k),[(0,0,0),(1,0,0)],[1,2],[1,2],[1,2])
        for k in ([0.,0.,0.],[0.5,0.,0.])]
    local_values=[0.3,0.4]
    terms=Any[T.TermKinetic([[0.,1.],[0.25,2.25]],1.),T.TermAtomicLocal(local_values),
        T.TermEwald(1.),T.TermPspCorrection(2.),T.TermHartree([0.,1.],1.),
        T.TermXc([:synthetic_xc],1.,0.,[0.1,0.2],nothing)]
    basis=SyntheticBasis(model,ks,[0.5,0.5],(2,1,1),2.,terms)
    # Same canonical P/D bytes are legitimately reachable through two distinct
    # issued block objects, exposing intra-validation digest reuse.
    P=ComplexF64[1 0;0 1;0.5 0;0 0.5];D=ComplexF64[1 0;0 2]
    ops=[SyntheticFR(P,D,NamedTuple[(;atom=1,l=0),(;atom=2,l=0)]) for _ in ks]
    ctx=FI.FRHamiltonianContext(basis,[b,b2],ops,:real_fr,[:synthetic_xc])
    FI._FR_CONTEXT_CERTIFICATES[ctx]=(;basis,bundles=copy(ctx.bundles),fr_blocks=copy(ops),mode=ctx.mode,
        xc_identifiers=copy(ctx.xc_identifiers),snapshot=FI._basis_snapshot(basis),
        projector_hashes=[FI._fr_array_hash(op.P) for op in ops],
        coupling_hashes=[FI._fr_array_hash(op.D) for op in ops],labels=[deepcopy(op.labels) for op in ops])
    ctx
end

function synthetic_runtime(FI=BoundaryCandidate;policy=:strict,shared_sources=true,default=false)
    ctx=synthetic_context(FI;shared_sources)
    rt=default || FI===BoundaryReference ? FI.owned_runtime(ctx;max_rhs=3) :
        FI.owned_runtime(ctx;max_rhs=3,validation_policy=policy)
    # Independent current scalar potential: content mutation must be detected
    # by current-storage validation, not only by a derived atomic-local alias.
    T=BoundaryDFTK;local_values=copy(ctx.basis.terms[2].potential_values)
    blocks=[begin
        localop=T.RealSpaceMultiplication(local_values)
        fourierop=T.FourierMultiplication(ctx.basis.terms[1].kinetic_energies[ik])
        T.HamiltonianBlock(ctx.basis,k,Any[localop,fourierop],Any[localop,fourierop],localop,fourierop,nothing)
    end for (ik,k) in enumerate(ctx.basis.kpoints)]
    common=T.Hamiltonian(ctx.basis,blocks)
    full=FI.compose_full_hamiltonian(rt,common)
    (;FI,ctx,rt,common,full)
end

function clean_fixture(f)
    try f.FI.close_runtime!(f.rt) catch err
        f.FI.runtime_summary(f.rt).closed || rethrow(err)
    end
end
captured(f)=try f();nothing catch err;err end
flatten_errors(err)=err isa CompositeException ? reduce(vcat,flatten_errors.(err.exceptions);init=Any[]) : Any[err]
