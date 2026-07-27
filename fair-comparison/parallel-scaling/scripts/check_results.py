#!/usr/bin/env python3
"""Structural acceptance checks for parallel-scaling result records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--tag", required=True); args = parser.parse_args()
    paths = sorted((ROOT / "data" / "raw" / args.tag).glob("*.json"))
    if not paths: raise RuntimeError("no result records")
    checked = []
    for path in paths:
        row = json.loads(path.read_text(encoding="utf-8"))
        if int(row["workers_started"]) != int(row["effective_workers"]): raise RuntimeError(f"worker launch mismatch: {path}")
        if int(row["workers_ok"]) != int(row["effective_workers"]): raise RuntimeError(f"failed worker: {path}")
        points = [point for worker in row["worker_rows"] for point in worker["points"]]
        if len(points) != int(row["total_points"]) or len(set(points)) != len(points): raise RuntimeError(f"shard overlap/gap: {path}")
        if float(row["observed_wall_s"]) <= 0 or float(row["total_cpu_s"]) < 0: raise RuntimeError(f"invalid timing: {path}")
        checked.append(path.name)
    output = ROOT / "data" / "summary" / f"{args.tag}_gate.json"; output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"status": "pass", "files_checked": len(checked)}, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__": main()
