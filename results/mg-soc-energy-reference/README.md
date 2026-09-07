# Existing SOC endpoint energy/reference audit

The historical energy difference is now a complete **signed combination ledger**.
The fixed DFTK implementation restores its own local/XC/Pc/Ewald terms and measures
responses at the existing A/B densities and Q_rep. It does **not** independently
measure QE kinetic, local and nonlocal energies or finish residual attribution.
Numerical agreement/review remain **REVIEW_REQUIRED**; physical convergence is
**NOT_ESTABLISHED**. No historical E/F was corrected.

[Predeclared plan and conventions](../../benchmarks/mg-soc-energy-reference-v1/README.md) ·
[Energy dictionary/ledger](ledger.json) · [Common terms](common-terms.json) ·
[Signed response table](comparison.json) · [Finite G=0 diagnostic](local-g0.json) ·
[Evidence, hashes, commands and tests](evidence.json).

## Execution and historical sources

Base `45225ee1accabd0aae36acec072f0f6ba7dd1de8`; preparation `8e630af6028432d9c266eb3c97c5d91306560160`; first execution code `dfa51ee63ae4bbb0e2c88214cfdb04880049c223`; successful execution code `4e953e202e1ffff46a4dabc6e0df512304cd55ec`. New branch `codex/phase7d-energy-reference-audit`.

All previous SCFs are **HISTORICAL_REUSED**, bound to accepted commit
`45225ee1accabd0aae36acec072f0f6ba7dd1de8` and their original receipts:

| Source | Historical run_id | Scope |
| --- | --- | --- |
| [A](../mg-soc-scf/A/endpoint.json) | 20260906T151940Z-A-270110aa | Primary original n_out; checkpoint SHA 5b138d68662fc6451ffd8b78bbd71939454ca30f8ad014623cb1d8e6720f5451 |
| [B](../mg-soc-scf/B/endpoint.json) | 20260906T153016Z-B-62835d43 | Auxiliary original n_out; checkpoint SHA ff91020614a30d40a226194b95f041ee6120c1fb8398ad685712ca41ff4dddd9 |
| [G40](../mg-soc-qe-diagnostics/G40/qe.xml) | 20260907T112107073262Z-G40-3f9731a6 | Original successful SCF charge, SHA b93c254aa6972cf3c559fb8f85a630c0699e2eefe4382772a9203d11fcaa5359 |
| [Complete public Fourier packs](../mg-soc-density-hartree/README.md) | 20260907T132708175964Z-8d33b91c | Full A/B 64000 and QE 22119 saved modes; referenced, not copied |

Successful new run `20260907T144446657126Z-8fa3b4d2` executed exactly **five** full XC calls: original A/B/Q_rep plus the two A/B reconstruction checks. Worker and recorder exits are **0**. These are **NEW_POSTPROCESSING_OF_HISTORICAL_STATES**, with one process/thread and no electronic solve.

The actual new process loaded Julia 1.12.7, DFTK 0.8.0 at
`2f51b91213e26726fb9c6a17e5fae235a1412d01`, and PPIO 0.3.3 at
`fec942781560c391f20214ba4cd85fb2431deb84`, from the locked local checkouts,
verified by real paths before redaction, both clean. Active environment is
`environment/workbench`; Manifest SHA
`5b8ae036ac430219a95d61a5e3cd20074e9ecd252335253bf7ada81278b08c37`.
Actual backend: DFTK DispatchFunctional → Libxc GGA Float64 CPU; wrapper 0.3.26,
Libxc runtime 7.0.0, DftFunctionals 0.3.2. The functional identifiers, default
external parameters, library SHA, thresholds, methods and source lines are in
the common receipt. No setter/backend substitution was used. Full vxc includes
the gradient divergence; the synthetic bare-Vρ counterexample is rejected.

## Native energy fields and signed ledger

There are 42 machine-readable dictionary rows and eight successful token-specific
printed-interval checks. QE XML etot is F, demet is −TS, E=F−demet;
eband is the occupied H[n_in] eigenvalue sum. The final stdout one-electron
contribution is eband+deband, whereas final H/XC/vtxc use the unmixed output rho
under the qe-7.5 tagged call chain. Final vtxc cannot replace the earlier deband.
The selected successful final block is stdout lines 443–454 (not an earlier
iteration). Each decimal token retains its own rounding interval, including
printed zeros. etxcc is obsolete/unused and initialized zero in this tag;
this is not a generic statement about NLCC. The actual case has no NLCC or
requested extra corrections. Installed QE exact source commit remains unknown.

`O_D=T+L+NL+Pc`; `O_Q=E−H−XC−Ewald` is a **derived combination**, not a new
operator measurement. O_Q is −64.47924879196043 Ha; its difference from printed
one-electron energy is −1.96043e-9 Ha, inside its propagated 2.501016e-9 Ha bound.
The misleading final eband−2H−vtxc diagnostic is recorded separately and is not
used to claim an exact same-state identity.

| DFTK minus G40 | ΔE (Ha/cell) | ΔH | ΔXC | ΔEwald | ΔO |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | +2.294777767986e-05 | -5.967043431809e-06 | +2.647081800866e-06 | +1.840410490672e-08 | +2.624933520678e-05 |
| B | +2.294777768697e-05 | -5.967043659183e-06 | +2.647081777774e-06 | +1.840410490672e-08 | +2.624933546258e-05 |

| DFTK minus G40 | ΔE (meV/cell) | ΔH | ΔXC | ΔEwald | ΔO |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | +0.624440841934 | -0.162371523570 | +0.072030765308 | +0.000500801207 | +0.714280799012 |
| B | +0.624440842127 | -0.162371529757 | +0.072030764680 | +0.000500801207 | +0.714280805973 |

Signed closure errors are −8.88e-16 Ha (A) and +8.88e-16 Ha (B).
The main ledger uses **native historical Hartree**. The tiny Phase 7C
coefficient-reconstruction differences are separate in ledger.json, never mixed
into its closure. R_after_H is +0.786812365503 meV for A; after subtracting XC
and Ewald as well it is +0.714280799012 meV (ΔO). Negative Hartree partly cancels
the positive components. This is not a percentage attribution or a residual SOC
operator error. Historical entropy is unresolved at printed precision in QE;
DFTK −TS is approximately −1.24e-37 Ha, so displayed equal E/F is not proof of
mathematical zero entropy. Display conversion is 1 Ha = 27.211386245981 eV.

## Density representation and same-source recovery

Q_rep evaluates the **whole saved finite series** at the original zero-origin
40³ nodes, using sqrt(Omega)*nbar and a complex inverse FFT. Its Ne is
10.000000000000004, minimum 0.00011640201905994439 and maximum
2.4636263197587387 electron/bohr³; negative count is zero. Maximum imaginary
part is 2.92012e-16 electron/bohr³, relative imaginary L2 1.23656e-16;
Fourier roundtrip relative L2 is 3.61753e-16. All 17 phase-sensitive directional
checks passed. No clipping, mean subtraction, coefficient projection,
renormalization, spin factor or k weight was applied.

Original A/B versus complete public reconstructions have max difference
8.88179e-16 electron/bohr³ and relative L2 3.26106e-16 / 3.10949e-16.
A/B original local/XC/Pc/Ewald restore exactly at recorded Float64 values;
Ixc maximum error is 1.77636e-15 Ha. The largest error including reconstructed
A/B is 1.42109e-14 Ha. Their source hashes and reconstructed hashes remain
separate. Original arrays were authenticated before deserialization; no orbital
field was used for a new evaluation.

This confirms the stated finite representation. It does not independently
extract QE's native real-space array or establish unsaved physical modes as
zero, and does not overwrite Phase 7C's historical full-real-space NOT_ASSESSED.
The matched charge-only, no-NLCC, zero-origin reciprocal support and QE tagged
GGA call chain support this restricted comparison. Native gradient roundoff,
threshold behavior and all installed-source details are not independently
reproduced; native DFTK full-grid/Nyquist conventions remain unchanged.

## XC and local density response

All energies below are Ha/cell. DFTK's XC at Q_rep is
−7.1770574954758555; its Ixc is −9.371198187776406.

| Difference | A | B |
| --- | ---: | ---: |
| XC historical difference | +2.647081800866e-06 | +2.647081777774e-06 |
| XC density response in DFTK | +6.374752610228e-07 | +6.374752379301e-07 |
| XC evaluation residual at Q_rep | +2.009606539843e-06 | +2.009606539843e-06 |
| XC first-order at Q_rep | +6.374757765798e-07 | +6.374757511641e-07 |
| XC curvature diagnostic | -5.155570005699e-13 | -5.132339420907e-13 |
| Ixc historical difference | +3.396977231063e-06 | +3.396977195536e-06 |
| Ixc density response in DFTK | +8.331691869756e-07 | +8.331691532248e-07 |
| Ixc evaluation residual at Q_rep | +2.563808042311e-06 | +2.563808042311e-06 |

The table also retains same-source drift (A Ixc −1.77636e-15 Ha); subtracting
that drift recombines the exact historical difference. XC response ≈+0.01735 meV
and Q_rep residual ≈+0.05468 meV are different evidence. The residual includes
unseparated evaluator/representation/gradient/threshold details, not a proved
PBEsol bug. Ixc's corresponding endpoint full-GGA meaning is supported by the
qe-7.5 tagged v_of_rho/gradcorr chain, with the installed-source limitation.
The small curvature diagnostic is not a rigorous total-energy error bound.

Gradient maximum uses electron/bohr⁴, gradient L2 electron/bohr^(5/2),
and sigma electron²/bohr⁸ in the common receipt.

The native analytic DFTK local G=0 is exactly zero; the sampled spatial mean
is zero and its FFT-recovered zero coefficient is −4.44090e-18 Ha (roundoff). Local density responses are +7.862332579611e-6 Ha (A) and
+7.862333139412e-6 Ha (B), approximately +0.21394 meV. Real/Fourier inner-product
errors on all 64000 native bins, including zero and Nyquist, are 3.90e-20 and
1.02e-20 Ha. Actual ΔN is −6.74e-16 / +3.20e-15 electrons; none was removed.
These **new field integrals are RUNNER_REPORTED**: complete potentials and
gradients are local, not independently recomputable from the public scalar table.

## G=0, Pc and finite radial diagnostic

Lbar=L+Pc is an audit combination, not another total-energy term. DFTK Pc is
+0.09187494522099392 Ha and enters once; it has a no-op Hamiltonian contribution.
Its neutral atom/electron/volume identity closes within 1.39e-17 Ha. DFTK L+Pc
is −79.34115248268944 Ha (A) and −79.34115248268887 Ha (B). No missed or double
Pc is found in that native bookkeeping. QE uses a finite local G=0 under the
ordinary periodic tagged convention; its actual local-potential array remains
**NOT_EXTRACTED**, so no runtime cross-code local equality is claimed.

| Route | alpha (Ha bohr³/atom) | C (Ha) | N_e C (Ha/cell) |
| --- | ---: | ---: | ---: |
| Frozen DFTK full mesh | 9.18749452209939 | 0.00918749452209939 | 0.0918749452209939 |
| Independent full-mesh quadratic | 9.18749452200667 | 0.00918749452200667 | 0.0918749452200667 |
| Full-mesh trapezoid sensitivity | 9.18644732226481 | 0.00918644732226481 | 0.0918644732226481 |
| QE tagged range prediction | 9.18582744603758 | 0.00918582744603758 | 0.0918582744603758 |

The actual UPF has 1510 points, r=0..15.09 bohr, step and PP_RAB=0.01.
PP_LOCAL Ry→Ha is applied once. The independent rule integrates actual r-space
quadratics, with one final trapezoid; RAB is not additionally multiplied.
Independent versus native Pc differs by −9.27258e-13 Ha. Full quadratic versus
trapezoid Pc differs by +1.04720e-5 Ha; this is method sensitivity, not an error
bound. The finite integrand at the last node is still 1.47613e-5 Ha bohr²:
no tail patch or extrapolation was added, and a Coulomb tail beyond supplied
support is an assumption of the finite-part interpretation.

The qe-7.5 source/data rule selects msh=1001 (0..10.00 bohr); PP_RAB supplies
the Jacobian once in the standard odd-node Simpson prediction. This is a
**source-convention prediction**, not the extracted installed QE table value.
The screened short-range q→0 entry is a different object; no real screened
integral was added. The signed candidate N_e(C_D−C_Q_tagged) is
+1.667076061808e-5 Ha, approximately **+0.45363 meV/cell**. Its scale is suggestive,
but it is neither a causal proof nor an E/F correction. No constant comes from
energy residuals, HOMO, eigenvalues or a fit. The known nonzero-G interpolation
path is only a source clue; no table/interpolation scan was executed.

The remaining native O difference cannot be separated into measured QE T, L
and NL with current evidence. Existing DFTK T+NL and L+Pc are shown in the
ledger, but no mixed-reference quantity is promoted to measured QE T+NL.
The single highest-value future check is an independently authorized extraction
of the actual QE native local potential (including G=0) bound to G40, followed
by its local-energy integral on the same certified representation. That would
test the convention/interpolation candidate before attributing anything to
orbitals or NL. **It is NOT_RUN in this task.**

## Failures, tests, reproduction and limits

The first formal attempt `20260907T144202626001Z-e3d5ec63` returned worker 1 /
recorder 9: JSON3 decoded integer-valued volume as Int64, selecting an unsupported
Complex{Int64} FFT. It stopped with **0 XC calls** and retained its FAIL record.
The new boundary now explicitly selects Float64 without changing the value;
a regression follows the actual JSON3 request path. A separate ordinary fix
commit preceded the sole successful retry. Three earlier Julia synthetic
preflights had new-code parse/reflection errors; a radial wrapper synthetic
fixture had a resolved temporary-path mismatch. These failed logs remain local
and archived. A later public-protocol regression initially exposed four subtest failures
(wrong execution flags and UPF identity were not checked); the new public
comparator now rejects them, and the same assertions passed without numerical
re-evaluation. No old PASS was reused. No frozen helper or scientific kernel
needed a fix.

Actual command/exit/log identities and final test counts are recorded in
[evidence.json](evidence.json). New Python tests: 92/92; Julia synthetic tests: 67/67, exit 0.
The public-only combined replay passed, including unchanged earlier checkers. New tests distinguish synthetic fields and
protocol faults from this real fixed-input evaluation. The affected density,
charge parser and recorder regressions were rerun (100 tests, exit 0).
Historical upstream Julia suites, full SOC/SCF suites, all new SCF/eigensolves,
QE/pp.x numerical execution, wavefunction analysis, convergence scans and new
IEEE experiments are **NOT_RUN**. QE separate T/NL is **NOT_AVAILABLE**;
QE native local potential is **NOT_EXTRACTED**; IEEE cause is **NOT_LOCALIZED**.
There are no missing required sources or unresolved execution blockers. Residual
attribution remains partially quantified and open, not a scientific PASS.

Public-only replay in a normal clone retaining history:

```sh
python3.12 scripts/check_energy_reference.py --all --legacy-python python3.9
```

This chains the unchanged earlier checkers, using their existing Python split.
It reparses original tokens and recomputes saved signed tables/algebra; it does
not independently execute XC or reintegrate the unpublished radial/field arrays.
For physical static re-evaluation, first obtain the exact source-locked UPF and
restore the source-bound A/B checkpoint/receipts/maps and original G40 charge from
the recorded archive. Use the existing frozen environment and depot; install or
rebuild nothing. Then, in an authorized review reproduction:

```sh
JULIA_DEPOT_PATH=<existing-frozen-depot> JULIA_LOAD_PATH=@:@stdlib JULIA_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3.12 scripts/run_energy_reference_audit.py --julia julia
```

The current plan and execution code must be committed; the runner creates a new
run_id and directory. It binds all sources before evaluation and publishes a
successful result only after complete field/summary/algebra validation. Existing
run directories are refused.

The incremental archive `phase7d-20260907T142212Z` contains only new outputs
and process records; old scientific sources are referenced through the verified
Phase 7C archive, not recopied. The initial raw manifest verifies 29 files,
38,986,495 bytes; three restored samples total 23,604,877 bytes, including the
full new arrays. See evidence for manifest hashes, later process archive and
final clean-checkout replay. This is a same-machine repository-external backup,
**not offsite**. No UPF, checkpoint, potential/gradient array or source copy is
published. All 277 frozen predecessor files (excluding the five authorized
current navigation documents) are compared byte-for-byte to the accepted base.
Upstream checkouts, dependencies, locks, physical parameters, historical inputs
and reports stay unchanged. Only this development branch is pushed; no PR,
main update, merge or upstream communication is part of Phase 7D.
