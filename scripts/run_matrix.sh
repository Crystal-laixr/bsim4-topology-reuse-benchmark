#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

NGSPICE_BIN=${NGSPICE_BIN:-/home/LaiXinran/ngspice_for_sizing/build/src/ngspice}
HSPICE_BIN=${HSPICE_BIN:-/home/LaiXinran/.local/eda/hspice/bin/hspice}
PYTHON_BIN=${PYTHON_BIN:-/usr/local/python312/bin/python3.12}
export NGSPICE_BIN HSPICE_BIN PYTHON_BIN OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 LC_ALL=C LANG=C

if [ -f /home/LaiXinran/.hspice_env ]; then
    source /home/LaiXinran/.hspice_env
fi

if ! pgrep -f '/home/LaiXinran/.local/eda/new/lmgrd' >/dev/null 2>&1; then
    nohup /home/LaiXinran/.local/eda/new/lmgrd \
        -c /home/LaiXinran/.local/eda/new/synopsys.dat \
        -l /home/LaiXinran/.local/eda/new/license.log \
        >/home/LaiXinran/.local/eda/new/lmgrd.stdout 2>&1 &
    sleep 3
fi

test -x "$NGSPICE_BIN"
test -x "$HSPICE_BIN"
test -x "$PYTHON_BIN"
test -x /usr/bin/time
command -v taskset >/dev/null

mkdir -p data/raw/system data/raw/smoke data/raw/gate data/raw/matrix data/raw/logs data/summary figures
"$PYTHON_BIN" scripts/generate_inputs.py --points 500 --seed 717

{
    date -Is
    uname -a
    cat /etc/os-release
    lscpu
    free -h
    git -C /home/LaiXinran/ngspice_for_sizing rev-parse HEAD
    "$NGSPICE_BIN" -v
    "$HSPICE_BIN" -v
} > data/raw/system/environment.txt 2>&1

methods=(hspice_independent hspice_alter ngspice_independent ngspice_reuse)

for method in "${methods[@]}"; do
    "$PYTHON_BIN" scripts/run_benchmark.py --method "$method" --size 1 --rep 0 --tag warmup
done

for method in "${methods[@]}"; do
    "$PYTHON_BIN" scripts/run_benchmark.py --method "$method" --size 3 --rep 0 --tag smoke
done
"$PYTHON_BIN" scripts/check_gate.py --dir data/raw/smoke --size 3 --output data/raw/smoke/gate.json

for method in "${methods[@]}"; do
    "$PYTHON_BIN" scripts/run_benchmark.py --method "$method" --size 10 --rep 0 --tag gate
done
"$PYTHON_BIN" scripts/check_gate.py --dir data/raw/gate --size 10 --output data/raw/gate/gate.json

sizes=(1 10 50 100 200 500)
for size_index in "${!sizes[@]}"; do
    size=${sizes[$size_index]}
    repeats=3
    if [ "$size" -eq 1 ]; then repeats=5; fi
    for rep in $(seq 1 "$repeats"); do
        offset=$(( (rep + size_index) % 4 ))
        for method_index in 0 1 2 3; do
            index=$(( (method_index + offset) % 4 ))
            method=${methods[$index]}
            "$PYTHON_BIN" scripts/run_benchmark.py --method "$method" --size "$size" --rep "$rep" --tag matrix
        done
    done
done

"$PYTHON_BIN" scripts/extract_hspice_phases.py
"$PYTHON_BIN" scripts/analyze.py
"$PYTHON_BIN" scripts/check_gate.py --dir data/raw/matrix --size 500 --output data/summary/gate_500.json
"$PYTHON_BIN" scripts/audit_release.py
