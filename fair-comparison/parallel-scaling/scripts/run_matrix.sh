#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
PYTHON_BIN=${PYTHON_BIN:-/usr/local/python312/bin/python3.12}
HSPICE_BIN=${HSPICE_BIN:-/home/LaiXinran/.local/eda/hspice/bin/hspice}
NGSPICE_OFFICIAL_BIN=${NGSPICE_OFFICIAL_BIN:-/home/LaiXinran/ngspice_official_fair/build/src/ngspice}
NGSPICE_OPTIMIZED_BIN=${NGSPICE_OPTIMIZED_BIN:-/home/LaiXinran/ngspice_for_sizing/build/src/ngspice}
export PYTHON_BIN HSPICE_BIN NGSPICE_OFFICIAL_BIN NGSPICE_OPTIMIZED_BIN OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 LC_ALL=C LANG=C HSPICE_CONCURRENCY_CAP=${HSPICE_CONCURRENCY_CAP:-128}
[[ -f /home/LaiXinran/.hspice_env ]] && source /home/LaiXinran/.hspice_env
mkdir -p data/raw/{system,smoke,matrix,logs} data/summary figures
"$PYTHON_BIN" scripts/generate_inputs.py --points 1000 --seed 717
{ date -Is; uname -a; lscpu; grep Swap /proc/meminfo; echo HSPICE_CONCURRENCY_CAP=$HSPICE_CONCURRENCY_CAP; "$HSPICE_BIN" -v; "$NGSPICE_OFFICIAL_BIN" -v; "$NGSPICE_OPTIMIZED_BIN" -v; } > data/raw/system/environment.txt 2>&1

run() {
    if [[ ${RESUME:-0} == 1 ]]; then "$PYTHON_BIN" scripts/run_benchmark.py --skip-existing "$@"; else "$PYTHON_BIN" scripts/run_benchmark.py "$@"; fi
}

methods=(hspice_independent hspice_alter ngspice_official_independent ngspice_optimized_independent ngspice_optimized_reuse)
if [[ ${1:-} == "--smoke" ]]; then
    for workers in 1 8; do
        points=$(( workers > 3 ? workers : 3 ))
        for method in "${methods[@]}"; do run --scaling strong --total-points "$points" --workers "$workers" --method "$method" --analysis dc --layer end_to_end --complexity 21 --rep 0 --tag smoke; done
    done
    "$PYTHON_BIN" scripts/check_results.py --tag smoke
    exit 0
fi

workers=(1 2 4 8 16 32 64 128 192 256)
for complexity in 5 21 101; do
  for layer in solver_only end_to_end; do
    for rep in 1 2 3; do
      for worker in "${workers[@]}"; do
        for method in "${methods[@]}"; do run --scaling strong --total-points 1000 --workers "$worker" --method "$method" --analysis dc --layer "$layer" --complexity "$complexity" --rep "$rep" --tag matrix; done
      done
    done
  done
done
for layer in solver_only end_to_end; do
  for rep in 1 2 3; do
    for worker in "${workers[@]}"; do
      for method in "${methods[@]}"; do run --scaling weak --total-points $((1000 * worker)) --workers "$worker" --method "$method" --analysis dc --layer "$layer" --complexity 21 --rep "$rep" --tag matrix; done
    done
  done
done
tran_methods=(hspice_independent hspice_alter ngspice_official_independent ngspice_optimized_independent)
for complexity in 4 16; do
  for layer in solver_only end_to_end; do
    for rep in 1 2 3; do
      for worker in 1 8 32 128; do
        for method in "${tran_methods[@]}"; do run --scaling strong --total-points 20 --workers "$worker" --method "$method" --analysis tran --layer "$layer" --complexity "$complexity" --rep "$rep" --tag matrix; done
      done
    done
  done
done
"$PYTHON_BIN" scripts/check_results.py --tag matrix
"$PYTHON_BIN" scripts/analyze.py
