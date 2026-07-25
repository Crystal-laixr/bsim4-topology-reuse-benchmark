# BSIM4 topology-reuse benchmark

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

The server runner expects:

- optimized NGSPICE at `/home/LaiXinran/ngspice_for_sizing/build/src/ngspice`;
- HSPICE environment at `/home/LaiXinran/.hspice_env`;
- GNU `time` and `taskset`.
- Python 3.12 at `/usr/local/python312/bin/python3.12` (override with `PYTHON_BIN`).

No HSPICE binary, license file, license log, or credential is stored here.
