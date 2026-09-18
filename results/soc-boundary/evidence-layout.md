# Evidence layout

`data.json.gz` and `protection.json.gz` retain the original export bytes.
`runs.json` keeps acceptance fields, measured resource/counter summaries, fixed
thresholds, and both same-map comparison receipts. Its `evidence_bundles` map
binds the remaining material:

- `native-logs.json.gz`: all eight original public stdout/stderr streams.
- `checks.json.gz`: preparation and check artifacts, including failed checks.
- `identities.json.gz`: recorded worker, source, environment, control, and
  resource identities, plus per-run metadata moved out of `runs.json`.

Each bundle's `files` object is keyed by the **original expanded artifact path**.
Each entry contains its original raw/public/compressed descriptors and exact
UTF-8 `public_text`; original public bytes are `public_text.encode("utf-8")`.
The entry's old compressed hash identifies the expanded export, retained in
local staging. The containing bundle has a separate current compressed hash.
No private array is added or reread by packing.

References inside the unchanged protection package use these original path
keys. Per-run `identity_record.entry_key` selects `relocated_runs` in the
identity bundle. Derived `replay.json` is omitted; regenerate the result:

```sh
python3.12 -B benchmarks/soc-boundary-v1/replay.py
```

Packing does not rerun any material calculation or change acceptance criteria.
