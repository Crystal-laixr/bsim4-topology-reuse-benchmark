#!/usr/bin/env python3
"""Create the immutable point-set and shard manifests for parallel scaling."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAIR = ROOT.parent
sys.path.insert(0, str(FAIR / "scripts"))
import generate_inputs as circuit  # noqa: E402

WORKERS = (1, 2, 4, 8, 16, 32, 64, 128, 192, 256)
FIELDS = ("point_id", *[item[0] for item in circuit.PARAMETERS])


def write_csv(path: Path, points: list[dict[str, float | str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(points)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=717)
    args = parser.parse_args()
    if args.points != 1000:
        raise ValueError("this protocol fixes strong and weak worker blocks at 1000 points")
    params = ROOT / "params"; params.mkdir(parents=True, exist_ok=True)
    strong = circuit.latin_hypercube(args.seed, args.points)
    write_csv(params / "strong_points_1000.csv", strong)
    blocks = {str(worker): [args.seed + 100003 * index for index in range(worker)] for worker in WORKERS}
    manifest = {
        "seed": args.seed,
        "strong_points": args.points,
        "weak_points_per_worker": args.points,
        "workers": WORKERS,
        "weak_worker_block_seeds": blocks,
        "mosfet_count": len(circuit.circuit()),
        "varying_parameters": len(circuit.PARAMETERS),
        "precision": {"reltol": 1e-6, "vntol": 1e-9, "abstol": 1e-13, "gmin": 1e-12, "method": "gear"},
    }
    (params / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    circuit.write_model_audit(ROOT, strong[0])
    print(json.dumps({"strong_points": len(strong), "workers": len(WORKERS), "mosfet_count": len(circuit.circuit())}, sort_keys=True))


if __name__ == "__main__":
    main()
