#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export GIT_TERMINAL_PROMPT=0
exec julia --startup-file=no "$SCRIPT_DIR/setup_workbench.jl" fetch "$@"
