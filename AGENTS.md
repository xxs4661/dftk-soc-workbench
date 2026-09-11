# Agent execution rules

Read the user's current task, [CONTRIBUTING.md](CONTRIBUTING.md) and the
[evidence policy](docs/evidence-policy.md). Human contribution guidance is not
permission to publish, run expensive calculations or contact other projects.

- Confirm the requested base, branch and worktree before editing. Preserve user
  changes and all existing commits; never automatically reset, stash or rewrite history.
- Stay within the task's file and computation boundaries. Keep numerical source,
  locked dependencies, physical inputs and historical evidence unchanged unless
  the user explicitly authorizes their modification.
- Do not start SCF, eigen/occupation solves, QE/pp, parameter scans, CI or another
  scientific stage without task-specific authorization. Read-only public replay
  and synthetic examples must be described by their actual scope.
- Never invent tests, PASS states, provenance, citations or human review. Preserve
  failures, warnings and unperformed work; do not relax checks to hide a problem.
- Update current explanations directly when authorized. Keep historical checkers
  at fixed snapshots; never refresh old hashes to accommodate new navigation.
- Publish only the evidence required to review the claimed result. Keep private
  paths, credentials, UPF payloads, raw large arrays and execution transcripts out
  of Git. Preserve existing evidence dependencies and verify backups before removal.
- Use ordinary commits and push only the branch authorized by the user. Do not
  push main, create/merge PRs, contact upstream, change repository settings or
  publish releases without explicit authorization. Stop at the requested review point.
