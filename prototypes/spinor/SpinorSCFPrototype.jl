"""Restricted charge-only LDA workbench prototype, not upstream spinor/SOC support."""
module SpinorSCFPrototype
using LinearAlgebra, Random, SHA
import DFTK, PseudoPotentialIO, TOML, JSON3
using ..SpinorPrototype
using ..WorkbenchEnvironment

export build_b0, initial_densities, energy_snapshot, spinor_factors, density_from_orbitals
export check_supported_basis, spinor_scf, iterate_density_map
export density_summary, DensityMapFailure
export finite_difference_check, compare_references, scalar_reference

include("energy.jl")
include("scf.jl")
include("b0_support.jl")
include("checks.jl")
end
