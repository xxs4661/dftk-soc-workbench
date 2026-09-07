# UPF acceptance and recorder behavior

[evidence.json](evidence.json) binds the original runs to their immutable sources.
[strict-mg.json](strict-mg.json) is the historical strict FR-NC result for Mg run
`20260905T030611379883Z-0094f2da`: environment, parse and metadata PASS followed by
**EXPECTED_SOC_REJECTION** from the locked native DFTK constructor. The workbench
prototype uses a separate interface; the native protection is preserved.

Mg is `dojo.nc.fr.pbesol.v0_4.stringent.upf`, SHA-256
`19b117bfa920945bffaee91eefbcfbf9fd44e035f3708b965aae59aabf3be256`.
Its redistribution permission is unverified and bytes are not published. It was
originally used for metadata inspection and later for the explicitly prescribed
PBEsol prototypes, never as an LDA/LSDA numerical comparison fixture.

The original [Phase 3 inspection](phase3-inspection.json) remains byte-identical as
a regression fixture. Its legacy `status=PASS` means that inspection completed;
it predates strict acceptance and must not be interpreted as its equivalent.
[Source/format evidence](../../docs/upf-source-map.md) and the
[acceptance contract](../../scripts/README.md) explain source-index association,
legal repeated radial `(l,j)` channels and unsupported ambiguous variants.

Two corrected tool defects are retained as public errata: the legacy inspector
could mistake any `unsupported` exception for the native SOC guard; the early
recorder could accept contradictory worker statuses and publish PASS before a
summary failure. The strict validator and recorder now validate stage/action/mode
contracts and publish the authoritative result last. The unchanged
[legacy negative regression](../../tests/legacy_regression.jl),
[validator tests](../../tests/runtests.jl), and
[recorder contract tests](../../tests/test_recorder_contract.py) reproduce those
boundaries. Synthetic workers test the recorder protocol, not Julia or physics.

The [historical upstream minimal log](historical-minimal.log) reports 1387/1387
at the pinned DFTK commit on 2026-09-04. It is an excerpt (first 20 and final 200
lines of 4,022 sanitized lines), not a full-suite test or a curation rerun.
Fresh environment/CLI/UPF checks require the locked local prerequisites:

```sh
python3 scripts/run_recorded.py identity
python3 tests/test_cli.py
bash scripts/run_upf_inspection.sh
```

Curation reran the seven existing CLI checks, including information-only Mg
parsing; it did not produce a new strict-Mg acceptance or upstream minimal run.
Python recorder regressions and public evidence checks are separate from
historical upstream test counts.

The explicit historical export is reproducible from the fixed Git snapshot with
`python3.9 scripts/check_publication.py --export-upf`. It reads three immutable
blobs and replaces only the strict run’s identical environment body by its shared
reference. It does not run the worker.
