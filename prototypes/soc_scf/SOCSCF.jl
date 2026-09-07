"""Restricted Phase 6C charge-only ensemble/SCF; not an upstream spinor API."""
module SOCSCF
using LinearAlgebra, Random, SHA, TOML, JSON3
import DFTK
using ..SpinorPrototype
import ..FRIntegration
import ..SpinorSCFPrototype
const FI=FRIntegration
const Controller=SpinorSCFPrototype
export EnsembleError, fermi_logistic, fermi_occupations, ensemble_free_energy, occupation_stationarity, band_completeness
include("ensemble.jl")
include("solver.jl")
include("scf.jl")
end
