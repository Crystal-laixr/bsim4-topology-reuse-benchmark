#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
PYTHON_BIN=${PYTHON_BIN:-/usr/local/python312/bin/python3.12}
HSPICE_BIN=${HSPICE_BIN:-/home/LaiXinran/.local/eda/hspice/bin/hspice}
NGSPICE_OFFICIAL_BIN=${NGSPICE_OFFICIAL_BIN:-/home/LaiXinran/ngspice_official_fair/build/src/ngspice}
NGSPICE_OPTIMIZED_BIN=${NGSPICE_OPTIMIZED_BIN:-/home/LaiXinran/ngspice_for_sizing/build/src/ngspice}
export PYTHON_BIN HSPICE_BIN NGSPICE_OFFICIAL_BIN NGSPICE_OPTIMIZED_BIN
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 LC_ALL=C LANG=C

run_case() {
    local method=$1 analysis=$2 layer=$3 size=$4 rep=$5 tag=$6
    local output="data/raw/${tag}/${layer}_${analysis}_${method}_n${size}_r${rep}.json"
    if [[ ${RESUME:-0} == 1 && -s $output ]]; then
        echo "skip existing $output"
        return
    fi
    "$PYTHON_BIN" scripts/run_benchmark.py --method "$method" --analysis "$analysis" --layer "$layer" --size "$size" --rep "$rep" --tag "$tag"
}

if [[ -f /home/LaiXinran/.hspice_env ]]; then source /home/LaiXinran/.hspice_env; fi
test -x "$PYTHON_BIN"; test -x "$HSPICE_BIN"; test -x "$NGSPICE_OFFICIAL_BIN"; test -x "$NGSPICE_OPTIMIZED_BIN"
mkdir -p data/raw/{system,warmup,smoke,accuracy,matrix,logs} data/summary figures
"$PYTHON_BIN" scripts/generate_inputs.py --points 500 --seed 717

sha256sum "$NGSPICE_OFFICIAL_BIN" "$NGSPICE_OPTIMIZED_BIN" > data/raw/system/binary_sha256.txt
{
    date -Is
    uname -a
    lscpu
    git -C /home/LaiXinran/ngspice_official_fair rev-parse HEAD
    git -C /home/LaiXinran/ngspice_for_sizing rev-parse HEAD
    "$NGSPICE_OFFICIAL_BIN" -v
    "$NGSPICE_OPTIMIZED_BIN" -v
    "$HSPICE_BIN" -v
} > data/raw/system/environment.txt 2>&1

dc_methods=(hspice_independent hspice_alter ngspice_official_independent ngspice_optimized_independent ngspice_optimized_reuse)
tran_methods=(hspice_independent hspice_alter ngspice_official_independent ngspice_optimized_independent)
for method in "${dc_methods[@]}"; do
    run_case "$method" startup solver_only 1 0 warmup
done
for analysis in dc tran; do
    if [[ $analysis == dc ]]; then methods=("${dc_methods[@]}"); else methods=("${tran_methods[@]}"); fi
    for layer in solver_only end_to_end; do
        for method in "${methods[@]}"; do
            run_case "$method" "$analysis" "$layer" 3 0 smoke
        done
    done
done
"$PYTHON_BIN" scripts/check_results.py --tag smoke --size 3

if [[ ${1:-} == "--smoke" ]]; then
    "$PYTHON_BIN" scripts/analyze.py
    exit 0
fi

dc_sizes=(1 10 50 100 200 500)
tran_sizes=(1 5 10 20)
for analysis in dc tran; do
    if [[ $analysis == dc ]]; then sizes=("${dc_sizes[@]}"); else sizes=("${tran_sizes[@]}"); fi
    if [[ $analysis == dc ]]; then methods=("${dc_methods[@]}"); else methods=("${tran_methods[@]}"); fi
    for layer in solver_only end_to_end; do
        for size_index in "${!sizes[@]}"; do
            size=${sizes[$size_index]}; repeats=3
            [[ $size -eq 1 ]] && repeats=5
            for rep in $(seq 1 "$repeats"); do
                offset=$(( (rep + size_index) % ${#methods[@]} ))
                for method_index in "${!methods[@]}"; do
                    method=${methods[$(( (method_index + offset) % ${#methods[@]} ))]}
                    run_case "$method" "$analysis" "$layer" "$size" "$rep" matrix
                done
            done
        done
    done
done
"$PYTHON_BIN" scripts/check_results.py --tag matrix --size 500 --tran-size 20
"$PYTHON_BIN" scripts/analyze.py
"$PYTHON_BIN" scripts/audit_release.py
