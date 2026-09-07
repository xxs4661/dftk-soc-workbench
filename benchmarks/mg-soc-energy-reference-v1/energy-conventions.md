# Historical energy ledger conventions

The ledger reads the existing A/B endpoint JSON and G40 SCF XML/stdout. It
performs no electronic-structure evaluation. Every number retains its original
token, unit, file hash and JSON pointer/XML path or stdout line. Derived rows
name their operands and cannot become independent operator measurements.

DFTK records seven-term internal energy E, entropy energy −TS, and F=E−TS.
Its band expectation uses the original spinors in H[n_out]; the solved
eigenvalues belong to H[n_in]. AtomicLocal excludes its zero Fourier component;
PspCorrection enters once. These definitions come from the frozen
[energy adapter](../../prototypes/fr_integration/energy.jl),
[ensemble](../../prototypes/soc_scf/ensemble.jl), and
[DFTK correction](https://github.com/JuliaMolSim/DFTK.jl/blob/2f51b91213e26726fb9c6a17e5fae235a1412d01/src/terms/psp_correction.jl#L24-L33).

QE definitions below are **qe-7.5 tag conventions**. The installed executable's
exact source commit and all build-time changes remain unknown.

- XML energy fields are Hartree: the writer divides internal Rydberg values by
  two. [Writer](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_restart_new.f90#L719-L727)
- `etot` is F, `demet` is −TS, so E=etot−demet. The converged stdout block
  prints `one-electron contribution` as eband+deband and XC as etxc−etxcc.
  deband uses the potential before the final output-density update. The final
  branch refreshes Hartree, XC and vtxc on unmixed output rho and sets descf=0.
  Therefore final XML 2H+vtxc cannot replace the earlier deband. Extra energy
  branches require separate applicability checks.
  [State and sum](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/electrons.f90#L843-L1203),
  [printing](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/electrons.f90#L1689-L1728)
- etxcc is initialized to zero and marked obsolete/unused in this tag; it is
  not the current NLCC n·vxc integral.
  [Declaration](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pwcom.f90#L353-L354)
- For noncollinear, nonmagnetic charge, vtxc integrates valence n against the
  scalar XC potential. The routine adds gradient corrections, including their
  contribution to vtxc. This establishes the final-density full-GGA meaning,
  without independently reproducing QE's evaluation.
  [XC](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/v_of_rho.f90#L507-L613),
  [GGA](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/gradcorr.f90)

The bound G40 input and native records establish neutral periodic NC/PBEsol,
no NLCC, no Hubbard/hybrid/dispersion/external-field request, FCP/RISM false,
and only the four ordinary stdout components. These are case conditions;
absence of a printed correction alone never proves a mathematical zero or
an unknown build's internal state.

Only the last successful SCF endpoint block is accepted. A printed decimal
token has half a last-place rounding interval, propagated through each sum
and Ry→Ha conversion, plus the declared 1e-12 Ha arithmetic allowance.
Printed zero retains this interval. JSON round-trip tokens are exact recorded
numbers, without a claim about physical error.

O_D=T+L+NL+Pc and O_Q=E−H−XC−Ewald are named combinations. The ledger keeps
signed ΔH/ΔXC/ΔEwald/ΔO and both residuals ΔE−ΔH and ΔE−ΔH−ΔXC−ΔEwald.
It does not identify separate QE T, L or NL, fit a constant, or alter energy
references. Native historical Hartree values remain the ledger authority;
Phase 7C coefficient recomputations are separate diagnostics.
