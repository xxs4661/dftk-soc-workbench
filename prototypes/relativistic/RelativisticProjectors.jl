module RelativisticProjectors

using LinearAlgebra, SHA
import DFTK, PseudoPotentialIO
using ..UpfValidation
using ..UpfRuntime

include("channels.jl")
include("radial.jl")
include("angular.jl")
include("operator.jl")

export ChannelModel, RadialChannel, ChannelError, fr_channels,
       scalar_degenerate_channels, synthetic_channel_model,
       radial_modified, radial_factor, channel_summary,
       complex_solid_harmonic, cg_matrix, spin_angular_solid, spin_angular,
       projector_labels, expanded_coupling, build_projectors,
       build_nonlocal_operator, FRNonlocalOperator,
       nonlocal_energy, projected_nonlocal_energy

end
