#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
WORK_DIR="$REPOSITORY_ROOT/.work"
DFTK_DIR="$WORK_DIR/DFTK.jl"
PPIO_DIR="$WORK_DIR/PseudoPotentialIO.jl"
RESULTS_DIR="$REPOSITORY_ROOT/results"
LOGS_DIR="$RESULTS_DIR/logs"
DEFAULT_INPUT="$WORK_DIR/pseudos/Mg.upf"
EXPECTED_DFTK_COMMIT="2f51b91213e26726fb9c6a17e5fae235a1412d01"
EXPECTED_PPIO_COMMIT="fec942781560c391f20214ba4cd85fb2431deb84"

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
    echo "Usage: scripts/run_upf_inspection.sh [UPF_PATH]"
    echo "With no argument, inspect .work/pseudos/Mg.upf from the selected catalog family."
    exit 0
fi
if [[ $# -gt 1 ]]; then
    echo "Expected zero or one UPF path." >&2
    exit 2
fi
if ! command -v julia >/dev/null 2>&1; then
    echo "BLOCKED: Julia is unavailable." >&2
    exit 3
fi
if [[ ! -d "$DFTK_DIR/.git" || ! -d "$PPIO_DIR/.git" ]]; then
    echo "BLOCKED: locked source checkouts are unavailable; run scripts/fetch_sources.sh." >&2
    exit 3
fi
if [[ $(git -C "$DFTK_DIR" rev-parse HEAD) != "$EXPECTED_DFTK_COMMIT" ]]; then
    echo "BLOCKED: DFTK checkout does not match config/sources.lock." >&2
    exit 3
fi
if [[ $(git -C "$PPIO_DIR" rev-parse HEAD) != "$EXPECTED_PPIO_COMMIT" ]]; then
    echo "BLOCKED: PseudoPotentialIO checkout does not match config/sources.lock." >&2
    exit 3
fi
if [[ -n $(git -C "$DFTK_DIR" status --porcelain=v1) ||
      -n $(git -C "$PPIO_DIR" status --porcelain=v1) ]]; then
    echo "BLOCKED: a locked source checkout has local changes." >&2
    exit 3
fi

mkdir -p "$LOGS_DIR"
input_path=${1:-$DEFAULT_INPUT}
if [[ ! -f "$input_path" ]]; then
    echo "BLOCKED: UPF input is unavailable: ${1:-.work/pseudos/Mg.upf}" >&2
    exit 3
fi

if [[ "$input_path" == "$REPOSITORY_ROOT/"* ]]; then
    display_path=${input_path#"$REPOSITORY_ROOT/"}
else
    display_path="<external-input>/$(basename -- "$input_path")"
fi

family_args=()
if [[ $# -eq 0 ]]; then
    family_args=(
        --family-id "dojo.nc.fr.pbesol.v0_4.stringent.upf"
        --source-id "PseudoPotentialData v0.3.2 / PseudoLibrary v0.2.1 artifact"
        --redistribution "not verified; inspected locally and not redistributed"
    )
else
    family_args=(
        --source-id "user-supplied UPF"
        --redistribution "not verified; inspected locally and not redistributed"
    )
fi

timestamp=$(date -u '+%Y%m%dT%H%M%SZ')
log_file="$LOGS_DIR/upf-inspection-$timestamp.log"
json_file="$RESULTS_DIR/upf-inspection.json"
json_temporary=$(mktemp "$RESULTS_DIR/.upf-inspection.XXXXXX")
cleanup() {
    rm -f -- "$json_temporary"
}
trap cleanup EXIT

sanitize_stream() {
    local repository_tilde="~${REPOSITORY_ROOT#"$HOME"}"
    sed -E -e "s|$REPOSITORY_ROOT|<workbench>|g" \
        -e "s|$repository_tilde|<workbench>|g" \
        -e "s|$HOME|<home>|g" \
        -e 's|/private/var/folders/[^[:space:]`]+|<temporary>|g' \
        -e 's|/var/folders/[^[:space:]`]+|<temporary>|g' \
        -e 's|[[:space:]]+$||'
}

echo "Inspecting: $display_path" | tee "$log_file"
echo "Raw UPF parsing and DFTK construction are separate recorded stages." | tee -a "$log_file"

set +e
JULIA_DEPOT_PATH="$WORK_DIR/julia-depot" \
    julia --startup-file=no --color=no --project="$DFTK_DIR" \
    "$SCRIPT_DIR/inspect_relativistic_upf.jl" \
    --json "$json_temporary" \
    --display-path "$display_path" \
    "${family_args[@]}" \
    "$input_path" \
    2>&1 | sanitize_stream | tee -a "$log_file"
inspection_exit=${PIPESTATUS[0]}
set -e

if [[ -s "$json_temporary" ]]; then
    mv "$json_temporary" "$json_file"
fi

echo "Inspection exit code: $inspection_exit" | tee -a "$log_file"
exit "$inspection_exit"
