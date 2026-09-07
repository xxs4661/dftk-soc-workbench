# Repository maintenance

Follow [CONTRIBUTING.md](CONTRIBUTING.md) and the [evidence policy](docs/evidence-policy.md).

- Update affected commands, navigation and `docs/status.md` in the same change;
  do not refresh unrelated dates or invent validation claims.
- Bind results to input, execution code, evidence and limits; preserve NOT_RUN
  and scientific failures. Never weaken tests to accommodate a migration.
- Keep frozen dependencies and historical numerical results unchanged unless a
  separately authorized scientific task explicitly requires a new version.
- Finish with affected tests, link/evidence checks and `git diff --check`.
- Keep raw runs ignored; publish through reviewed file/field whitelists. Do not
  copy a whole run into results or stage the whole repository without review.
- Do not merge/push main or contact upstream without separate authorization.
