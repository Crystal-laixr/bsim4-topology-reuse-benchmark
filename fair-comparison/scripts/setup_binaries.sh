#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
source "$REPO_ROOT/scripts/runtime_env.sh"
benchmark_load_env "$REPO_ROOT"

OFFICIAL_ROOT=${OFFICIAL_ROOT:-${NGSPICE_OFFICIAL_SOURCE:-"$REPO_ROOT/upstream/ngspice_official"}}
OPTIMIZED_ROOT=${OPTIMIZED_ROOT:-$NGSPICE_OPTIMIZED_SOURCE}
BUILD_JOBS=${BUILD_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)}
OFFICIAL_COMMIT=eb68de42d0ca8c97efd92f8d7528e7e7841f5fc9
OPTIMIZED_COMMIT=828d455865fe1b530672de4be6519703826057be

if [[ ! -d "$OFFICIAL_ROOT/.git" ]]; then
    git clone https://github.com/imr/ngspice.git "$OFFICIAL_ROOT"
fi
git -C "$OFFICIAL_ROOT" fetch origin pre-master-47
git -C "$OFFICIAL_ROOT" checkout --detach "$OFFICIAL_COMMIT"

if [[ $(git -C "$OPTIMIZED_ROOT" rev-parse HEAD) != "$OPTIMIZED_COMMIT" ]]; then
    echo "optimized source is not pinned to $OPTIMIZED_COMMIT" >&2
    exit 1
fi

for source_root in "$OFFICIAL_ROOT" "$OPTIMIZED_ROOT"; do
    if [[ ! -x "$source_root/configure" || "$source_root/configure.ac" -nt "$source_root/configure" ]]; then
        (cd "$source_root" && ./autogen.sh)
    fi
    mkdir -p "$source_root/build"
    if [[ ! -f "$source_root/build/Makefile" ]]; then
        (cd "$source_root/build" && ../configure --with-x=no --disable-xspice --disable-cider CFLAGS="-O2")
    fi
    make -C "$source_root/build" -j"$BUILD_JOBS"
done

test -x "$OFFICIAL_ROOT/build/src/ngspice"
test -x "$OPTIMIZED_ROOT/build/src/ngspice"

echo "NGSPICE_OFFICIAL_BIN=$OFFICIAL_ROOT/build/src/ngspice"
echo "NGSPICE_OPTIMIZED_BIN=$OPTIMIZED_ROOT/build/src/ngspice"
