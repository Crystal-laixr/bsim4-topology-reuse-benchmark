#!/usr/bin/env python3
"""Enforce same-simulator completeness and numerical-equivalence gates."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


PAIRS = (
    ("hspice_independent", "hspice_alter"),
    ("ngspice_independent", "ngspice_reuse"),
)


def load_run(directory: Path, method: str, size: int) -> dict[str, object]:
    matches = sorted(directory.glob(f"{method}_n{size}_r*.json"))
    if not matches:
        raise RuntimeError(f"missing {method} size {size} in {directory}")
    return json.loads(matches[0].read_text(encoding="utf-8"))


def indexed(run: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(point["point_id"]): point for point in run["points"]}


def compare(reference: dict[str, object], candidate: dict[str, object], label: str) -> dict[str, float | int | str]:
    left = indexed(reference)
    right = indexed(candidate)
    if left.keys() != right.keys():
        raise RuntimeError(f"{label}: point IDs differ")
    max_voltage = 0.0
    max_power_abs = 0.0
    max_power_rel = 0.0
    comparisons = 0
    for point_id in sorted(left):
        left_lanes = left[point_id]["lanes"]
        right_lanes = right[point_id]["lanes"]
        if left_lanes.keys() != right_lanes.keys():
            raise RuntimeError(f"{label}:{point_id}: lane IDs differ")
        for lane in left_lanes:
            for metric in ("low_v", "high_v", "threshold_v"):
                a = float(left_lanes[lane][metric])
                b = float(right_lanes[lane][metric])
                if not math.isfinite(a) or not math.isfinite(b):
                    raise RuntimeError(f"{label}:{point_id}:{lane}:{metric} is not finite")
                max_voltage = max(max_voltage, abs(a - b))
                comparisons += 1
            a = abs(float(left_lanes[lane]["power_w"]))
            b = abs(float(right_lanes[lane]["power_w"]))
            if not math.isfinite(a) or not math.isfinite(b):
                raise RuntimeError(f"{label}:{point_id}:{lane}:power_w is not finite")
            difference = abs(a - b)
            relative = difference / max(a, b, 1e-30)
            max_power_abs = max(max_power_abs, difference)
            max_power_rel = max(max_power_rel, relative)
            comparisons += 1
    voltage_ok = max_voltage <= 1e-5
    power_ok = max_power_abs <= 1e-12 or max_power_rel <= 1e-4
    if not voltage_ok or not power_ok:
        raise RuntimeError(
            f"{label} failed: max_voltage={max_voltage:.6g}, "
            f"max_power_abs={max_power_abs:.6g}, max_power_rel={max_power_rel:.6g}"
        )
    return {
        "pair": label,
        "comparisons": comparisons,
        "max_voltage_abs_v": max_voltage,
        "max_power_abs_w": max_power_abs,
        "max_power_relative": max_power_rel,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = []
    for reference, candidate in PAIRS:
        records.append(
            compare(
                load_run(args.dir, reference, args.size),
                load_run(args.dir, candidate, args.size),
                f"{reference}_vs_{candidate}",
            )
        )
    text = json.dumps({"size": args.size, "status": "pass", "pairs": records}, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()

