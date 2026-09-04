#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
WORK_DIR="$REPOSITORY_ROOT/.work"
RESULTS_DIR="$REPOSITORY_ROOT/results"
DFTK_DIR="$WORK_DIR/DFTK.jl"
PSEUDOPOTENTIALIO_DIR="$WORK_DIR/PseudoPotentialIO.jl"

mkdir -p "$RESULTS_DIR"

one_line() {
    tr '\n|' ' /' | sed 's/[[:space:]][[:space:]]*/ /g; s/^ //; s/ $//'
}

if [[ "$(uname -s)" == "Darwin" ]]; then
    execution_type="local macOS workspace"
    product_name=$(sw_vers -productName 2>/dev/null || printf 'unavailable')
    product_version=$(sw_vers -productVersion 2>/dev/null || printf 'unavailable')
    product_build=$(sw_vers -buildVersion 2>/dev/null || printf 'unavailable')
    operating_system="$product_name $product_version, build $product_build"
else
    execution_type="Codex execution environment; not identified as the user's Mac"
    operating_system=$(uname -s 2>/dev/null || printf 'unavailable')
fi

architecture=$(uname -m 2>/dev/null || printf 'unavailable')
kernel=$(uname -srv 2>/dev/null | one_line)

cpu_description=""
if command -v sysctl >/dev/null 2>&1; then
    cpu_description=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || true)
    if [[ -z "$cpu_description" ]]; then
        cpu_description=$(sysctl -n hw.model 2>/dev/null || true)
    fi
fi
if [[ -z "$cpu_description" && -r /proc/cpuinfo ]]; then
    cpu_description=$(awk -F: '/model name/ {sub(/^[[:space:]]+/, "", $2); print $2; exit}' /proc/cpuinfo)
fi
if [[ -z "$cpu_description" ]]; then
    cpu_description="unavailable from permitted queries"
fi

memory_description=""
if command -v sysctl >/dev/null 2>&1; then
    memory_bytes=$(sysctl -n hw.memsize 2>/dev/null || true)
    if [[ "$memory_bytes" =~ ^[0-9]+$ ]]; then
        memory_description="$memory_bytes bytes"
    fi
fi
if [[ -z "$memory_description" && -r /proc/meminfo ]]; then
    memory_description=$(awk '/MemTotal/ {print $2 " kB"; exit}' /proc/meminfo)
fi
if [[ -z "$memory_description" ]]; then
    memory_description="unavailable from permitted queries"
fi

if command -v julia >/dev/null 2>&1; then
    julia_version=$(julia --startup-file=no --version 2>&1 | one_line)

    set +e
    julia_threads=$(julia --startup-file=no -e 'using Base.Threads; print(nthreads())' 2>/dev/null)
    threads_exit=$?
    blas_information=$(julia --startup-file=no -e 'using LinearAlgebra; print(BLAS.get_config())' 2>/dev/null | one_line)
    blas_exit=$?
    set -e

    if [[ $threads_exit -ne 0 || -z "$julia_threads" ]]; then
        julia_threads="query failed with exit $threads_exit"
    fi
    if [[ $blas_exit -ne 0 || -z "$blas_information" ]]; then
        blas_information="query failed with exit $blas_exit"
    fi
else
    julia_version="not available"
    julia_threads="not available"
    blas_information="not available because Julia is absent"
fi

git_version=$(git --version 2>/dev/null | one_line)

if [[ -d "$DFTK_DIR/.git" ]]; then
    dftk_commit=$(git -C "$DFTK_DIR" rev-parse HEAD)
else
    dftk_commit="not available; source checkout is absent"
fi

if [[ -d "$PSEUDOPOTENTIALIO_DIR/.git" ]]; then
    pseudopotentialio_commit=$(git -C "$PSEUDOPOTENTIALIO_DIR" rev-parse HEAD)
else
    pseudopotentialio_commit="not available; source checkout is absent"
fi

if command -v pw.x >/dev/null 2>&1; then
    qe_output_file=$(mktemp "$WORK_DIR/.qe-version.XXXXXX")
    set +e
    pw.x -version >"$qe_output_file" 2>&1
    qe_exit=$?
    set -e
    if [[ $qe_exit -eq 0 ]]; then
        qe_version=$(sed -n '1,3p' "$qe_output_file" | one_line)
        if [[ -z "$qe_version" ]]; then
            qe_version="version command exited 0 without output"
        fi
    else
        qe_version="pw.x is available, but its version query failed with exit $qe_exit"
    fi
    rm -f -- "$qe_output_file"
else
    qe_version="pw.x not available"
fi

captured_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
temporary_summary=$(mktemp "$RESULTS_DIR/.environment-summary.XXXXXX")
cat >"$temporary_summary" <<EOF
# Environment summary

**Collection status:** PASS — the environment collection command completed successfully.

This records the host observed by the Phase 2 command. It does not infer specifications from a product name and does not contain a dump of environment variables.

| Field | Observed value |
| --- | --- |
| UTC date | \`$captured_at_utc\` |
| Environment type | $execution_type |
| Operating system | $operating_system |
| Architecture | $architecture |
| Kernel | $kernel |
| CPU description | $cpu_description |
| Memory | $memory_description |
| Julia version | $julia_version |
| Git version | $git_version |
| DFTK commit | \`$dftk_commit\` |
| PseudoPotentialIO commit | \`$pseudopotentialio_commit\` |
| Julia threads | $julia_threads |
| BLAS information | $blas_information |
| Quantum ESPRESSO | $qe_version |

The script queried only the listed facts. It did not print authentication-related variables or the full process environment.
EOF
mv "$temporary_summary" "$RESULTS_DIR/environment-summary.md"
cat "$RESULTS_DIR/environment-summary.md"
