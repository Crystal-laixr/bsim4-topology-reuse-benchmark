# BSIM4 topology-reuse benchmark

第一次接触本项目，请先阅读中文的 [`QUICKSTART.md`](QUICKSTART.md)。其中说明了任务目标、三轮实验的关系、优化 NGSPICE 源码构建、本地环境配置、smoke test、完整复现、输出检查和禁止公开的私有内容。

This repository compares four execution modes on the same 550-MOS BSIM4 circuit and parameter set:

1. HSPICE, one process per parameter point.
2. HSPICE, one process with `.alter` blocks.
3. NGSPICE, one process per parameter point.
4. Optimized NGSPICE, one persistent `batchrun` process with topology reuse.

The circuit contains 25 independent 11-stage CMOS inverter chains, for exactly 550 MOSFETs. Every parameter point changes 14 values while preserving topology.

## Reproduction

```bash
python3 scripts/generate_inputs.py --points 500 --seed 717
bash scripts/run_matrix.sh
python3 scripts/analyze.py
```

Copy `.benchmark-env.example` to `.benchmark-env` and set the executable paths for the local machine. The runners use that file instead of author-specific server paths. GNU `time`, `taskset`, and Python 3 are required on Linux.

No HSPICE binary, license file, license log, or credential is stored here.

## Fair NGSPICE/HSPICE comparison

The second-round experiment is under [`fair-comparison/`](fair-comparison/). It replaces the repeated inverter chains with an exactly 580-MOS static-CMOS 16-bit ripple-carry adder and adds:

- an official NGSPICE independent baseline;
- matched official/optimized NGSPICE build settings and binary hashes;
- a canonical 56-parameter-per-polarity BSIM4 model audit;
- matched DC and transient workloads, tolerances, output grids, and output volume;
- separate solver-only and end-to-end rankings;
- strict-reference calibration, numerical gates, linear fits, speedups, and release auditing.

Reproduce the second round with:

```bash
python3 fair-comparison/scripts/generate_inputs.py --points 500 --seed 717
bash fair-comparison/scripts/run_matrix.sh
python3 fair-comparison/scripts/analyze.py
```

See [`fair-comparison/REPORT.md`](fair-comparison/REPORT.md) for the methodology and conclusions. In the largest measured cases, NGSPICE is substantially faster for DC, while HSPICE is substantially faster for the strict transient workload; the report keeps solver-only and end-to-end conclusions separate.

## Parallel scaling

The third-round worker-scaling experiment is under [`fair-comparison/parallel-scaling/`](fair-comparison/parallel-scaling/). It adds strong/weak scaling, process-level throughput, analysis complexity, and the measured effect of the HSPICE license-concurrency cap. Start with a small validation:

```bash
bash fair-comparison/parallel-scaling/scripts/run_matrix.sh --smoke
```

The published matrix intentionally uses the reduced scope documented in [`REDUCED_SCOPE.md`](fair-comparison/parallel-scaling/REDUCED_SCOPE.md). Read [`REPORT.md`](fair-comparison/parallel-scaling/REPORT.md) before interpreting high-worker HSPICE end-to-end results as solver performance.
