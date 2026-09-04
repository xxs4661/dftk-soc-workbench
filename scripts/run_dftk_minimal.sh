#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
WORK_DIR="$REPOSITORY_ROOT/.work"
DFTK_DIR="$WORK_DIR/DFTK.jl"
RESULTS_DIR="$REPOSITORY_ROOT/results"
LOGS_DIR="$RESULTS_DIR/logs"
BOOTSTRAP_STATUS_FILE="$WORK_DIR/bootstrap-status.env"

mkdir -p "$LOGS_DIR"

timestamp=$(date -u '+%Y%m%dT%H%M%SZ')
started_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
log_name="dftk-minimal-$timestamp.log"
log_file="$LOGS_DIR/$log_name"
raw_log_file="$LOGS_DIR/$log_name.raw"
summary_file="$RESULTS_DIR/minimal-test-summary.md"

write_summary() {
    local status=$1
    local exit_code=$2
    local ended_at_utc=$3
    local detail=$4
    local summary_temporary
    summary_temporary=$(mktemp "$RESULTS_DIR/.minimal-test-summary.XXXXXX")
    cat >"$summary_temporary" <<EOF
# DFTK minimal-test summary

**Status:** $status

| Field | Value |
| --- | --- |
| Command | \`JULIA_DEPOT_PATH=.work/julia-depot julia --startup-file=no --color=no --project=.work/DFTK.jl -e 'import Pkg; Pkg.test("DFTK"; test_args=["minimal"])'\` |
| Exit code | \`$exit_code\` |
| Started at UTC | \`$started_at_utc\` |
| Ended at UTC | \`$ended_at_utc\` |
| DFTK commit | \`$dftk_commit\` |
| Test selection | Upstream test items tagged \`:minimal\`; not the full suite |
| Sanitized log | [\`results/logs/$log_name\`](logs/$log_name) |

$detail
EOF
    mv "$summary_temporary" "$summary_file"
}

dftk_commit="not available"
if [[ -d "$DFTK_DIR/.git" ]]; then
    dftk_commit=$(git -C "$DFTK_DIR" rev-parse HEAD)
fi

bootstrap_status=""
if [[ -f "$BOOTSTRAP_STATUS_FILE" ]]; then
    bootstrap_status=$(sed -n "s/^STATUS='\([^']*\)'/\1/p" "$BOOTSTRAP_STATUS_FILE")
fi

if [[ ! -d "$DFTK_DIR/.git" || "$bootstrap_status" != "PASS" ]]; then
    blocked_exit=3
    echo "BLOCKED: a successful bootstrap is required before the minimal test." | tee "$log_file"
    write_summary "BLOCKED" "$blocked_exit" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
        "The test command was not executed because its source or bootstrap prerequisite was absent."
    exit "$blocked_exit"
fi

if ! command -v julia >/dev/null 2>&1; then
    blocked_exit=3
    echo "BLOCKED: Julia is not available; the test command was not executed." | tee "$log_file"
    write_summary "BLOCKED" "$blocked_exit" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
        "Julia was absent, so no test execution was fabricated."
    exit "$blocked_exit"
fi

sanitize_stream() {
    local repository_tilde="~${REPOSITORY_ROOT#"$HOME"}"
    sed -E -e "s|$REPOSITORY_ROOT|<workbench>|g" \
        -e "s|$repository_tilde|<workbench>|g" \
        -e "s|$HOME|<home>|g" \
        -e 's|/private/var/folders/[^[:space:]`]+|<temporary>|g' \
        -e 's|/var/folders/[^[:space:]`]+|<temporary>|g' \
        -e 's|[[:space:]]+$||'
}

write_concise_log() {
    local line_count
    local log_temporary
    line_count=$(wc -l <"$raw_log_file" | tr -d ' ')
    log_temporary=$(mktemp "$LOGS_DIR/.dftk-minimal.XXXXXX")

    if [[ $line_count -le 240 ]]; then
        cp "$raw_log_file" "$log_temporary"
    else
        {
            echo "Sanitized concise test log; full transient output contained $line_count lines."
            echo "The omitted middle consisted primarily of dependency setup and SCF iteration output."
            echo
            sed -n '1,20p' "$raw_log_file"
            echo
            echo "[... middle of raw output omitted from the committed log ...]"
            echo
            tail -n 200 "$raw_log_file"
        } >"$log_temporary"
    fi
    mv "$log_temporary" "$log_file"
}

echo "Running the upstream DFTK :minimal test selection at $dftk_commit."
echo "Initial test-only dependency setup and Julia compilation may be quiet for several minutes."

set +e
JULIA_DEPOT_PATH="$WORK_DIR/julia-depot" \
    julia --startup-file=no --color=no --project="$DFTK_DIR" \
    -e 'import Pkg; Pkg.test("DFTK"; test_args=["minimal"])' \
    2>&1 | sanitize_stream | tee "$raw_log_file"
test_exit=${PIPESTATUS[0]}
set -e

write_concise_log

ended_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
if [[ $test_exit -eq 0 ]]; then
    test_status="PASS"
    detail="The documented minimal test command executed and exited successfully. This does not represent a full-suite result."
else
    test_status="FAIL"
    detail="The documented minimal test command executed and returned a nonzero exit code. The failure is retained in the sanitized log."
fi

write_summary "$test_status" "$test_exit" "$ended_at_utc" "$detail"
echo "$test_status: DFTK minimal test exited with $test_exit."
exit "$test_exit"
