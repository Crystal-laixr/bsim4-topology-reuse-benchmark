#!/usr/bin/env bash

benchmark_load_env() {
    local repo_root=$1
    local env_file=${BENCHMARK_ENV_FILE:-"$repo_root/.benchmark-env"}

    if [[ -f $env_file ]]; then
        # shellcheck disable=SC1090
        source "$env_file"
    fi
    if [[ -n ${HSPICE_ENV_FILE:-} ]]; then
        if [[ ! -f $HSPICE_ENV_FILE ]]; then
            echo "HSPICE_ENV_FILE does not exist: $HSPICE_ENV_FILE" >&2
            return 2
        fi
        # shellcheck disable=SC1090
        source "$HSPICE_ENV_FILE"
    fi

    PYTHON_BIN=${PYTHON_BIN:-$(command -v python3 2>/dev/null || true)}
    HSPICE_BIN=${HSPICE_BIN:-$(command -v hspice 2>/dev/null || true)}
    NGSPICE_OFFICIAL_BIN=${NGSPICE_OFFICIAL_BIN:-$(command -v ngspice 2>/dev/null || true)}
    NGSPICE_OPTIMIZED_SOURCE=${NGSPICE_OPTIMIZED_SOURCE:-"$repo_root/upstream/ngspice_for_sizing"}
    NGSPICE_OPTIMIZED_BIN=${NGSPICE_OPTIMIZED_BIN:-"$NGSPICE_OPTIMIZED_SOURCE/build/src/ngspice"}
    NGSPICE_OFFICIAL_SOURCE=${NGSPICE_OFFICIAL_SOURCE:-}
    NGSPICE_BIN=${NGSPICE_BIN:-$NGSPICE_OPTIMIZED_BIN}
    HSPICE_CONCURRENCY_CAP=${HSPICE_CONCURRENCY_CAP:-1}

    export PYTHON_BIN HSPICE_BIN NGSPICE_BIN NGSPICE_OFFICIAL_BIN
    export NGSPICE_OPTIMIZED_BIN NGSPICE_OFFICIAL_SOURCE NGSPICE_OPTIMIZED_SOURCE
    export HSPICE_CONCURRENCY_CAP OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 LC_ALL=C LANG=C
}

benchmark_require_executable() {
    local variable_name=$1
    local executable_path=$2
    if [[ -z $executable_path || ! -x $executable_path ]]; then
        echo "$variable_name is not executable: ${executable_path:-<unset>}" >&2
        echo "Copy .benchmark-env.example to .benchmark-env and set the local path." >&2
        return 2
    fi
}

benchmark_git_revision() {
    local source_dir=$1
    local label=$2
    if [[ -n $source_dir && -d $source_dir ]]; then
        printf '%s source commit: ' "$label"
        git -C "$source_dir" rev-parse HEAD 2>/dev/null || echo unavailable
    else
        echo "$label source commit: unavailable"
    fi
}
