#!/usr/bin/env bash
set -euo pipefail

OFFICIAL_ROOT=${OFFICIAL_ROOT:-/home/LaiXinran/ngspice_official_fair}
OPTIMIZED_ROOT=${OPTIMIZED_ROOT:-/home/LaiXinran/ngspice_for_sizing}
OFFICIAL_COMMIT=eb68de42d0ca8c97efd92f8d7528e7e7841f5fc9
OPTIMIZED_COMMIT=7a76e17d46ba49aa74f417151f8b8311c488760a
export PATH=/opt/rh/devtoolset-9/root/usr/bin:/usr/local/bin:/usr/bin:/bin

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
    make -C "$source_root/build" -j8
done

test -x "$OFFICIAL_ROOT/build/src/ngspice"
test -x "$OPTIMIZED_ROOT/build/src/ngspice"
