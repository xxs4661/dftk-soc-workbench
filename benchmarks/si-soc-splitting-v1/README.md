# Si SOC splitting: prescribed finite functional case

Preparation only; no result is claimed. Two-atom diamond Si uses one byte-bound
PseudoDojo FR NC-PBE source with real d channels and NLCC. The fixed 30 Ha,
48 cubed FFT, eight-k grid and tau=0.001 Ha are not a convergence study.

- [Source and acquisition identities](source.json)
- [Exact case and solver settings](case.json)
- [Five-slot plan, formulas, gates and publication scope](plan.json)

Download only the three source URLs in source.json into its ignored local
directory; verify the UPF byte count and Git blob before SHA-256. No UPF or
radial arrays are redistributed. Companion djrepo describes psp8 and is not
convergence evidence for this calculation. Runtime must recheck the source.

The main statistic is Gamma mean(states5:8)-mean(states3:4), after isolation
and multiplicity checks. The spin-trace null is a fixed-density operator
diagnostic using the same FR input and common potential, not a scalar-UPF SCF.
