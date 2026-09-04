# Sanitized logs

This directory may contain small text logs that are necessary to audit a reported benchmark. Temporary `*.tmp` and raw `*.raw` logs are ignored.

Before committing a log:

- remove usernames, absolute home-directory paths, hostnames when sensitive, credentials, scheduler identifiers, and unrelated environment data;
- retain executable versions, convergence parameters, iteration summaries, warnings, exit status, and numerical quantities needed by the report;
- link the log to its exact input and environment record; and
- verify that it contains no pseudopotential payload or large binary-derived dump.

Prefer a concise Markdown result table when a full log is not needed.
