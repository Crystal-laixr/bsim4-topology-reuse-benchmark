#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
MATRIX="$ROOT/data/raw/matrix"
SYSTEM="$ROOT/data/raw/system"
TARGET_SOLVER_RECORDS=1050

while (( $(find "$MATRIX" -maxdepth 1 -name '*.json' | wc -l) < TARGET_SOLVER_RECORDS )); do
    sleep 60
done

old_pid=$(cat "$SYSTEM/full_matrix.pid" 2>/dev/null || true)
if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    pkill -TERM -P "$old_pid" 2>/dev/null || true
    kill -TERM "$old_pid" 2>/dev/null || true
fi

sleep 5
cd "$ROOT"
nohup env RESUME=1 HSPICE_CONCURRENCY_CAP="${HSPICE_CONCURRENCY_CAP:-128}" bash scripts/run_matrix.sh >> "$SYSTEM/full_matrix.stdout" 2>&1 < /dev/null &
new_pid=$!
echo "$new_pid" > "$SYSTEM/full_matrix.pid"
printf '%s switched to reduced scope: old_pid=%s new_pid=%s\n' "$(date -Is)" "${old_pid:-none}" "$new_pid" >> "$SYSTEM/reduced_scope_switch.log"
