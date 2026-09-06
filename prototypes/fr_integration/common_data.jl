# Restricted common-only adapter. No existing DFTK method is replaced.
import Serialization

mutable struct CommonPspData <: DFTK.NormConservingPsp
    _token::Base.RefValue{Nothing}
    identifier::String
    description::String
    sha256::String
    source::String
    header_text::String
    element::Symbol
    z_valence::Int
    functional::String
    relativistic::String
    has_so::Bool
    has_nlcc::Bool
    r::Vector{Float64}
    rab::Vector{Float64}
    local_raw_ry::Vector{Float64}
    local_ha::Vector{Float64}
    rhoatom_raw::Vector{Float64}
    nlcc_raw::Union{Nothing,Vector{Float64}}
    r2_valence::Vector{Float64}
    r2_core::Vector{Float64}
    cutoffs::NamedTuple
end

mutable struct BoundPspBundle
    _token::Base.RefValue{Nothing}
    common::CommonPspData
    channels::RelativisticProjectors.ChannelModel
    parsed::PseudoPotentialIO.UpfFile
    mode::Symbol
    xc_identifiers::Vector{Symbol}
    sha256::String
end

# A loader-issued capability binds actual object identities, not caller-supplied
# matching strings. Full snapshots also detect subsequent array/header mutation.
const _BOUND_PSP_SOURCES = IdDict{Any,Any}()
function _source_snapshot(x)
    io=IOBuffer(); Serialization.serialize(io,x)
    bytes2hex(sha256(take!(io)))
end

function validate_common_data(c::CommonPspData,parsed)
    h=parsed.header; nr=length(parsed.mesh.r)
    c.element==Symbol(strip(h.element)) && c.z_valence==h.z_valence ||
        throw(ArgumentError("Common element or valence charge differs from parsed source"))
    (c.functional,c.relativistic,c.has_so)==(h.functional,h.relativistic,h.has_so) ||
        throw(ArgumentError("Common XC/relativistic header differs from parsed source"))
    c.r==parsed.mesh.r && c.rab==parsed.mesh.rab || throw(ArgumentError("Common radial mesh changed"))
    nr>=5 && length(c.rab)==nr && all(isfinite,c.r) && first(c.r)>=0 && all(>(0),diff(c.r)) &&
        all(x->isfinite(x)&&x>0,c.rab) || throw(ArgumentError("Invalid common radial mesh or PP_RAB"))
    c.local_raw_ry==parsed.local_ && c.rhoatom_raw==parsed.rhoatom && c.nlcc_raw==parsed.nlcc ||
        throw(ArgumentError("Common raw arrays differ from parsed source"))
    length(c.local_raw_ry)==nr && length(c.rhoatom_raw)==nr &&
        (isnothing(c.nlcc_raw)||length(c.nlcc_raw)==nr) ||
        throw(ArgumentError("Only full-mesh common quantities are supported for these locked inputs"))
    all(isfinite,c.local_raw_ry) && all(isfinite,c.rhoatom_raw) &&
        (isnothing(c.nlcc_raw)||all(isfinite,c.nlcc_raw)) || throw(ArgumentError("Nonfinite common arrays"))
    c.has_nlcc==h.core_correction==!isnothing(parsed.nlcc) ||
        throw(ArgumentError("NLCC presence disagrees with actual header/data"))
    c.local_ha==c.local_raw_ry./2 || throw(ArgumentError("PP_LOCAL must be converted Ry to Ha exactly once"))
    c.r2_valence==c.rhoatom_raw./(4π) || throw(ArgumentError("PP_RHOATOM is 4π r² n_valence"))
    expected_core=isnothing(c.nlcc_raw) ? zeros(nr) : c.r.^2 .* c.nlcc_raw
    c.r2_core==expected_core || throw(ArgumentError("PP_NLCC is core density, not PP_RHOATOM"))
    c.cutoffs==(;local_potential=nr,valence=nr,core=nr,correction=nr) ||
        throw(ArgumentError("Common quantities retain their full source ranges; beta cutoff cannot replace them"))
    nothing
end

function assert_bound_identity(bundle::BoundPspBundle;common=bundle.common,channels=bundle.channels)
    entry=get(_BOUND_PSP_SOURCES,bundle._token,nothing)
    isnothing(entry) && throw(ArgumentError("Pseudopotential bundle was not issued by the controlled loader"))
    bundle===entry.bundle && common===entry.common && channels===entry.channels &&
        bundle.parsed===entry.parsed && common._token===bundle._token ||
        throw(ArgumentError("Common data and FR channels are not the same loader-bound objects"))
    nothing
end

function assert_bound_sources(bundle::BoundPspBundle;common=bundle.common,channels=bundle.channels)
    assert_bound_identity(bundle;common,channels)
    entry=_BOUND_PSP_SOURCES[bundle._token]
    _source_snapshot(common)==entry.common_snapshot && _source_snapshot(channels)==entry.channel_snapshot &&
        _source_snapshot(bundle.parsed)==entry.parsed_snapshot &&
        (bundle.mode,bundle.xc_identifiers,bundle.sha256)==entry.metadata ||
        throw(ArgumentError("Loader-bound common/channel/source data changed after construction"))
    validate_common_data(common,bundle.parsed)
    nothing
end

function validate_common_request(bundle::BoundPspBundle;mode=bundle.mode,element=bundle.common.element,
                                 z_valence=bundle.common.z_valence,xc_identifiers=bundle.xc_identifiers)
    assert_bound_sources(bundle)
    mode==bundle.mode || throw(ArgumentError("Real FR and synthetic scalar-limit modes cannot be interchanged"))
    Symbol(element)==bundle.common.element || throw(ArgumentError("Requested element differs from input"))
    z_valence==bundle.common.z_valence || throw(ArgumentError("Requested valence charge differs from input"))
    Symbol.(xc_identifiers)==bundle.xc_identifiers || throw(ArgumentError("Requested XC differs from input family"))
    nothing
end

"""Hash bytes, parse once, and bind both common data and channels to that object."""
function load_bound_psp(root;mode::Symbol=:real_fr)
    if mode==:real_fr
        source=TOML.parsefile(joinpath(root,"config/sources.lock"))["pseudopotentials"]
        path=joinpath(root,source["local_path"]); expected=source["file_sha256"]
        element=:Mg; functional="PBESOL"; relativity="full"; has_so=true
        xc=[:gga_x_pbe_sol,:gga_c_pbe_sol]; origin=source["source_url"]
        expected=="19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256" ||
            throw(ArgumentError("Phase 6B Mg source lock identity changed"))
    elseif mode==:synthetic_scalar_limit
        case=JSON3.read(read(joinpath(root,"benchmarks/si-sr-lda/case.json"),String),Dict{String,Any})
        source=case["pseudo"]; path=joinpath(root,source["local_path"]); expected=source["sha256"]
        # PPIO upf2.jl:149,167 joins functional whitespace/hyphen tokens.
        element=:Si; functional="SLA PW NOGX NOGC"; relativity="scalar"; has_so=false
        xc=Symbol.(case["xc"]["dftk_identifiers"]); origin=source["source_url"]
        xc==[:lda_x,:lda_c_pw] && isnothing(source["dftk_rcut_bohr"]) ||
            throw(ArgumentError("Frozen Si common XC or full-grid cutoff changed"))
        expected=="686dd9f7d58fe63bdb1e595f0aeecf7d70d2857f06ffb00b8273950d6431e805" ||
            throw(ArgumentError("Phase 6B Si source identity changed"))
    else
        throw(ArgumentError("Supported modes: real_fr and synthetic_scalar_limit"))
    end
    isfile(path) || throw(ArgumentError("BLOCKED: locked pseudopotential is missing"))
    bytes=read(path); digest=bytes2hex(sha256(bytes))
    digest==expected || throw(ArgumentError("Locked UPF SHA-256 mismatch"))
    # Retain the exact source tag as provenance only, without a second UPF parse
    # or changing PPIO's normalized header. Both locked files use this XML tag.
    header_match=match(r"<PP_HEADER\b[^>]*>"s,String(copy(bytes)))
    isnothing(header_match) && throw(ArgumentError("Expected locked XML PP_HEADER tag"))
    parsed=PseudoPotentialIO.UpfFile(IOBuffer(bytes);identifier=basename(path))
    h=parsed.header
    (Symbol(strip(h.element)),h.functional,h.relativistic,h.has_so,h.pseudo_type)==
        (element,functional,relativity,has_so,"NC") || throw(ArgumentError("Actual UPF header does not match selected mode/family"))
    isfinite(h.z_valence) && isinteger(h.z_valence) && h.z_valence>0 ||
        throw(ArgumentError("Positive integral header valence charge required"))
    # The actual source header, including its original has_so, remains untouched.
    channels=mode==:real_fr ? RelativisticProjectors.fr_channels(parsed) :
                            RelativisticProjectors.scalar_degenerate_channels(parsed)
    token=Ref{Nothing}(nothing); r=copy(parsed.mesh.r); nr=length(r)
    core=isnothing(parsed.nlcc) ? nothing : copy(parsed.nlcc)
    common=CommonPspData(token,basename(path),"Common-only $(mode) adapter",digest,origin,header_match.match,element,
        Int(h.z_valence),h.functional,h.relativistic,h.has_so,!isnothing(core),r,copy(parsed.mesh.rab),
        copy(parsed.local_),parsed.local_./2,copy(parsed.rhoatom),core,parsed.rhoatom./(4π),
        isnothing(core) ? zeros(nr) : r.^2 .* core,(;local_potential=nr,valence=nr,core=nr,correction=nr))
    validate_common_data(common,parsed)
    bundle=BoundPspBundle(token,common,channels,parsed,mode,xc,digest)
    _BOUND_PSP_SOURCES[token]=(;bundle,common,channels,parsed,
        common_snapshot=_source_snapshot(common),channel_snapshot=_source_snapshot(channels),
        parsed_snapshot=_source_snapshot(parsed),metadata=(mode,copy(xc),digest))
    assert_bound_sources(bundle)
    bundle
end

DFTK.charge_ionic(c::CommonPspData)=c.z_valence
DFTK.has_valence_density(c::CommonPspData)=!all(iszero,c.r2_valence)
DFTK.has_core_density(c::CommonPspData)=c.has_nlcc
DFTK.has_core_kinetic_energy_density(::CommonPspData)=false

function DFTK.eval_psp_local_fourier(c::CommonPspData,p::Real)
    isfinite(p)&&p>=0 || throw(ArgumentError("Finite nonnegative Fourier magnitude required"))
    r=@view c.r[1:c.cutoffs.local_potential]; v=@view c.local_ha[1:c.cutoffs.local_potential]
    DFTK._eval_psp_local_fourier(DFTK.default_psp_quadrature(c.r),r,v,c.z_valence,Float64(p))
end
function DFTK.eval_psp_valence_density_fourier(c::CommonPspData,p::Real)
    isfinite(p)&&p>=0 || throw(ArgumentError("Finite nonnegative Fourier magnitude required"))
    DFTK.hankel(@view(c.r[1:c.cutoffs.valence]),@view(c.r2_valence[1:c.cutoffs.valence]),0,Float64(p))
end
function DFTK.eval_psp_core_density_fourier(c::CommonPspData,p::Real)
    isfinite(p)&&p>=0 || throw(ArgumentError("Finite nonnegative Fourier magnitude required"))
    DFTK.hankel(@view(c.r[1:c.cutoffs.core]),@view(c.r2_core[1:c.cutoffs.core]),0,Float64(p))
end
function DFTK.eval_psp_energy_correction(T,c::CommonPspData)
    r=@view c.r[1:c.cutoffs.correction]
    T(4π*DFTK.simpson((i,ri)->ri*(ri*c.local_ha[i]+c.z_valence),r))
end

# Linear interpolation of actual local/core values needs no r=0 division.
function _common_linear(r,values,x::Real)
    isfinite(x)&&first(r)<=x<=last(r) || throw(ArgumentError("Radius outside source data range"))
    i=min(searchsortedlast(r,x),length(r)-1)
    t=(x-r[i])/(r[i+1]-r[i]); (1-t)*values[i]+t*values[i+1]
end
DFTK.eval_psp_local_real(c::CommonPspData,r::Real)=_common_linear(c.r,c.local_ha,r)
DFTK.eval_psp_core_density_real(c::CommonPspData,r::Real)=
    isnothing(c.nlcc_raw) ? (isfinite(r)&&0<=r<=last(c.r) ? 0.0 : throw(ArgumentError("Invalid radius"))) :
                          _common_linear(c.r,c.nlcc_raw,r)
DFTK.eval_psp_valence_density_real(::CommonPspData,::Real)=
    throw(ArgumentError("Common adapter supplies valence Fourier density only; no undefined origin division"))
DFTK.count_n_proj(::CommonPspData)=throw(ArgumentError("Common-only data has no native scalar projectors; use bound FR channels"))
DFTK.count_n_proj(::CommonPspData,::Integer)=throw(ArgumentError("Common-only data has no native scalar projectors"))
DFTK.count_n_proj_radial(::CommonPspData)=throw(ArgumentError("Common-only data cannot enter AtomicNonlocal"))
DFTK.count_n_proj_radial(::CommonPspData,::Integer)=throw(ArgumentError("Common-only data cannot enter AtomicNonlocal"))
for fn in (:eval_psp_projector_fourier,:eval_psp_projector_real)
    @eval DFTK.$fn(::CommonPspData,i,l,p::Real)=throw(ArgumentError("Common-only data cannot evaluate scalar projectors"))
    @eval DFTK.$fn(::CommonPspData,i,l,p::AbstractVector{<:Real})=throw(ArgumentError("Common-only data cannot evaluate scalar projectors"))
end

function common_data_summary(bundle::BoundPspBundle)
    assert_bound_sources(bundle); c=bundle.common
    (;mode=string(bundle.mode),sha256=bundle.sha256,source=c.source,element=string(c.element),
      z_valence=c.z_valence,functional=c.functional,xc_identifiers=string.(bundle.xc_identifiers),
      relativistic=c.relativistic,has_so=c.has_so,nlcc_present=c.has_nlcc,
      radial_points=length(c.r),r_first_bohr=first(c.r),r_last_bohr=last(c.r),cutoff_indices=c.cutoffs,
      beta_cutoff_indices=[ch.cutoff_radius_index for ch in bundle.channels.channels],
      local_unit="PP_LOCAL / 2, Ry to Ha",valence_semantics="PP_RHOATOM / (4pi) = r² n_valence",
      core_semantics="PP_NLCC = n_core; Fourier integrand stores r² n_core",g0_local=0.0,
      valence_fourier_zero=DFTK.eval_psp_valence_density_fourier(c,0.0),
      core_fourier_zero=DFTK.eval_psp_core_density_fourier(c,0.0),
      correction_per_electron_volume=DFTK.eval_psp_energy_correction(Float64,c),
      quadrature=string(nameof(DFTK.default_psp_quadrature(c.r))),
      header_note="Exact PP_HEADER text retained; reported functional follows frozen PPIO whitespace normalization",
      binding="Loader-issued object capability plus unchanged full source/common/channel snapshots; one parse")
end

"""Same-rule common adapter comparison on real scalar Si, without a model or SCF."""
function compare_native_common_si(bundle::BoundPspBundle,qs)
    validate_common_request(bundle;mode=:synthetic_scalar_limit,element=:Si,xc_identifiers=[:lda_x,:lda_c_pw])
    c=bundle.common; native=DFTK.PspUpf(bundle.parsed;identifier="Frozen scalar Si common reference",rcut=nothing)
    err(a,b)=norm(a-b)/max(norm(a),norm(b),1)
    rows=[(;q,local_ha=DFTK.eval_psp_local_fourier(c,q),native_local_ha=DFTK.eval_psp_local_fourier(native,q),
        valence=DFTK.eval_psp_valence_density_fourier(c,q),native_valence=DFTK.eval_psp_valence_density_fourier(native,q),
        core=DFTK.eval_psp_core_density_fourier(c,q),native_core=DFTK.eval_psp_core_density_fourier(native,q)) for q in qs]
    # Native core real evaluation has 0/0 at r=0. Compare its stored r²n arrays,
    # physical nonzero grid samples, and the UPF's actual finite origin separately.
    core_native=DFTK.eval_psp_core_density_real.(Ref(native),c.r[2:end])
    checks=(;charge=abs(DFTK.charge_ionic(c)-DFTK.charge_ionic(native)),
        local_fourier=maximum(err(x.local_ha,x.native_local_ha) for x in rows),
        valence_fourier=maximum(err(x.valence,x.native_valence) for x in rows),
        core_fourier=maximum(err(x.core,x.native_core) for x in rows),
        correction=err(DFTK.eval_psp_energy_correction(Float64,c),DFTK.eval_psp_energy_correction(Float64,native)),
        local_samples=err(c.local_ha,native.vloc),valence_r2_samples=err(c.r2_valence,native.r2_ρion),
        core_r2_samples=err(c.r2_core,native.r2_ρcore),core_nonzero_grid_samples=err(c.nlcc_raw[2:end],core_native))
    (;scope="Real scalar Si same-rule common-only adapter comparison; no SCF",rows,checks,
      max_error=maximum(values(checks)),common=common_data_summary(bundle),
      local_g0=DFTK.eval_psp_local_fourier(c,0.0),core_origin=DFTK.eval_psp_core_density_real(c,0.0),
      core_origin_source=bundle.parsed.nlcc[1])
end
