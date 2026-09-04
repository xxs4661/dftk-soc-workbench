#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
WORK_DIR="$REPOSITORY_ROOT/.work"
STATE_FILE="$WORK_DIR/source-state.env"

DFTK_FORK_URL="https://github.com/xxs4661/DFTK.jl.git"
DFTK_UPSTREAM_URL="https://github.com/JuliaMolSim/DFTK.jl.git"
DFTK_REFERENCE="refs/heads/master"
DFTK_LOCKED_COMMIT="2f51b91213e26726fb9c6a17e5fae235a1412d01"

PSEUDOPOTENTIALIO_URL="https://github.com/JuliaMolSim/PseudoPotentialIO.jl.git"
PSEUDOPOTENTIALIO_REFERENCE="refs/heads/main"
PSEUDOPOTENTIALIO_LOCKED_COMMIT="fec942781560c391f20214ba4cd85fb2431deb84"

export GIT_TERMINAL_PROMPT=0
mkdir -p "$WORK_DIR"

cleanup_directory=""
cleanup() {
    if [[ -n "$cleanup_directory" && "$cleanup_directory" == "$WORK_DIR"/.clone.* ]]; then
        rm -rf -- "$cleanup_directory"
    fi
}
trap cleanup EXIT

remote_has_reference() {
    local repository_url=$1
    local reference=$2
    git ls-remote --exit-code "$repository_url" "$reference" >/dev/null 2>&1
}

require_clean_checkout() {
    local label=$1
    local target=$2
    local status_output

    status_output=$(git -C "$target" status --porcelain --untracked-files=all)
    if [[ -n "$status_output" ]]; then
        echo "$label checkout has local changes; refusing to update it." >&2
        echo "$status_output" >&2
        return 1
    fi
}

prepare_checkout() {
    local label=$1
    local repository_url=$2
    local target=$3
    local reference=$4
    local locked_commit=$5

    if [[ -e "$target" && ! -d "$target/.git" ]]; then
        echo "$label target exists but is not a Git checkout: $target" >&2
        return 1
    fi

    if [[ ! -d "$target/.git" ]]; then
        cleanup_directory=$(mktemp -d "$WORK_DIR/.clone.XXXXXX")
        git clone --quiet --no-checkout "$repository_url" "$cleanup_directory/repository"
        mv "$cleanup_directory/repository" "$target"
        rmdir "$cleanup_directory"
        cleanup_directory=""
    else
        require_clean_checkout "$label" "$target"
        git -C "$target" remote set-url origin "$repository_url"
    fi

    git -C "$target" fetch --quiet --prune origin
    if ! git -C "$target" cat-file -e "$locked_commit^{commit}" 2>/dev/null; then
        git -C "$target" fetch --quiet origin "$locked_commit"
    fi
    git -C "$target" checkout --quiet --detach "$locked_commit"

    local actual_commit
    actual_commit=$(git -C "$target" rev-parse HEAD)
    if [[ "$actual_commit" != "$locked_commit" ]]; then
        echo "$label checkout did not resolve to the locked commit." >&2
        return 1
    fi
    require_clean_checkout "$label" "$target"

    printf '%s\n' "$actual_commit"
}

if remote_has_reference "$DFTK_FORK_URL" "$DFTK_REFERENCE"; then
    dftk_repository=$DFTK_FORK_URL
    dftk_source="user fork"
elif remote_has_reference "$DFTK_UPSTREAM_URL" "$DFTK_REFERENCE"; then
    dftk_repository=$DFTK_UPSTREAM_URL
    dftk_source="upstream fallback"
else
    echo "Neither the user DFTK fork nor the upstream repository is accessible." >&2
    exit 1
fi

if ! remote_has_reference "$PSEUDOPOTENTIALIO_URL" "$PSEUDOPOTENTIALIO_REFERENCE"; then
    echo "PseudoPotentialIO.jl is not accessible." >&2
    exit 1
fi

dftk_commit=$(prepare_checkout \
    "DFTK" "$dftk_repository" "$WORK_DIR/DFTK.jl" \
    "$DFTK_REFERENCE" "$DFTK_LOCKED_COMMIT")

if [[ "$dftk_source" == "user fork" ]]; then
    if git -C "$WORK_DIR/DFTK.jl" remote get-url upstream >/dev/null 2>&1; then
        git -C "$WORK_DIR/DFTK.jl" remote set-url upstream "$DFTK_UPSTREAM_URL"
    else
        git -C "$WORK_DIR/DFTK.jl" remote add upstream "$DFTK_UPSTREAM_URL"
    fi
fi

pseudopotentialio_commit=$(prepare_checkout \
    "PseudoPotentialIO" "$PSEUDOPOTENTIALIO_URL" "$WORK_DIR/PseudoPotentialIO.jl" \
    "$PSEUDOPOTENTIALIO_REFERENCE" "$PSEUDOPOTENTIALIO_LOCKED_COMMIT")

retrieved_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
state_temporary=$(mktemp "$WORK_DIR/.source-state.XXXXXX")
cat >"$state_temporary" <<EOF
DFTK_REPOSITORY='$dftk_repository'
DFTK_REFERENCE='$DFTK_REFERENCE'
DFTK_COMMIT='$dftk_commit'
PSEUDOPOTENTIALIO_REPOSITORY='$PSEUDOPOTENTIALIO_URL'
PSEUDOPOTENTIALIO_REFERENCE='$PSEUDOPOTENTIALIO_REFERENCE'
PSEUDOPOTENTIALIO_COMMIT='$pseudopotentialio_commit'
RETRIEVED_AT_UTC='$retrieved_at_utc'
EOF
mv "$state_temporary" "$STATE_FILE"

echo "DFTK source: $dftk_source"
echo "DFTK repository: $dftk_repository"
echo "DFTK reference: $DFTK_REFERENCE"
echo "DFTK commit: $dftk_commit"
echo "PseudoPotentialIO repository: $PSEUDOPOTENTIALIO_URL"
echo "PseudoPotentialIO reference: $PSEUDOPOTENTIALIO_REFERENCE"
echo "PseudoPotentialIO commit: $pseudopotentialio_commit"
echo "Retrieved at UTC: $retrieved_at_utc"
