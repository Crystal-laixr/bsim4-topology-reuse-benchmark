#!/usr/bin/env python3
"""Structural gates for a completed benchmark tag."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import tarfile
from pathlib import Path

METHODS = ("hspice_independent", "hspice_alter", "ngspice_official_independent", "ngspice_optimized_independent", "ngspice_optimized_reuse")
OBSERVED = ("sum00", "sum05", "sum10", "sum15", "c04", "c08", "c12", "cout")

def canonical(root: Path, payload: dict[str, object]) -> list[dict[str, list[list[float]]]]:
    archive = root / str(payload["logs_archive"])
    with tarfile.open(archive, "r:gz") as handle:
        member = handle.getmember("canonical_outputs.json")
        stream = handle.extractfile(member)
        if stream is None: raise RuntimeError(f"missing canonical output in {archive}")
        return json.loads(stream.read().decode("utf-8"))

def compare(left: list[dict[str, list[list[float]]]], right: list[dict[str, list[list[float]]]]) -> dict[str, float | int]:
    if len(left) != len(right): raise RuntimeError("canonical point count differs")
    errors = []
    for lp, rp in zip(left, right):
        for name in OBSERVED:
            if len(lp[name]) != len(rp[name]): raise RuntimeError(f"sample count differs for {name}")
            for (lx, ly), (rx, ry) in zip(lp[name], rp[name]):
                if abs(lx - rx) > 1e-15: raise RuntimeError(f"axis differs for {name}: {lx} {rx}")
                errors.append(abs(ly - ry))
    ordered = sorted(errors)
    return {"comparisons": len(errors), "max_abs_v": max(errors, default=0.0), "median_abs_v": statistics.median(errors) if errors else 0.0, "p95_abs_v": ordered[min(len(ordered) - 1, math.floor(0.95 * len(ordered)))] if ordered else 0.0}

def vectors() -> list[tuple[int, int, int]]:
    import random
    rng = random.Random(717)
    fixed = [(0, 0, 0), (0xFFFF, 1, 0), (0xAAAA, 0x5555, 1), (0xFFFF, 0xFFFF, 1)]
    return fixed

def logic_gate(points: list[dict[str, list[list[float]]]]) -> dict[str, int]:
    checked = 0
    for point in points:
        by_axis = {name: {round(axis, 14): value for axis, value in point[name]} for name in OBSERVED}
        for index, (a, b, cin) in enumerate(vectors()):
            axis = round(((index + 1) * 10.0 - 0.5) * 1e-9, 14); total = a + b + cin
            expected = {"sum00": (total >> 0) & 1, "sum05": (total >> 5) & 1, "sum10": (total >> 10) & 1, "sum15": (total >> 15) & 1, "c04": ((a & 0xF) + (b & 0xF) + cin) >> 4, "c08": ((a & 0xFF) + (b & 0xFF) + cin) >> 8, "c12": ((a & 0xFFF) + (b & 0xFFF) + cin) >> 12, "cout": (total >> 16) & 1}
            for name, bit in expected.items():
                value = by_axis[name].get(axis)
                if value is None: raise RuntimeError(f"missing stable sample {axis} for {name}")
                observed = 1 if value >= 0.9 else 0
                if observed != bit: raise RuntimeError(f"logic mismatch vector={index} signal={name} expected={bit} voltage={value}")
                checked += 1
    return {"logic_samples_checked": checked}

def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--tag", required=True); parser.add_argument("--size", type=int, required=True); parser.add_argument("--tran-size", type=int)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1]); args = parser.parse_args()
    directory = args.root / "data" / "raw" / args.tag
    checked = 0; selected: dict[tuple[str, str], tuple[dict[str, object], list[dict[str, list[list[float]]]]]] = {}
    layers = ("solver_only", "end_to_end") if any(directory.glob("solver_only_*.json")) else ("end_to_end",)
    for analysis in ("dc", "tran"):
        target_size = args.tran_size if analysis == "tran" and args.tran_size is not None else args.size
        for layer in layers:
            required = METHODS if analysis == "dc" else tuple(method for method in METHODS if method != "ngspice_optimized_reuse")
            for method in required:
                matches = sorted(directory.glob(f"{layer}_{analysis}_{method}_n{target_size}_r*.json"))
                if not matches: raise RuntimeError(f"missing {layer}/{analysis}/{method}/n={target_size}")
                for path in matches:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if any(int(item.get("returncode", 1)) != 0 for item in payload["child_stats"]):
                        raise RuntimeError(f"nonzero child status: {path}")
                    if layer == "end_to_end" and (analysis, method) not in selected:
                        selected[(analysis, method)] = (payload, canonical(args.root, payload))
                    checked += 1
    comparisons = []
    for analysis in ("dc", "tran"):
        for left, right in (("hspice_independent", "hspice_alter"), ("ngspice_official_independent", "ngspice_optimized_independent"), ("ngspice_optimized_independent", "ngspice_optimized_reuse"), ("hspice_independent", "ngspice_official_independent")):
            if (analysis, left) in selected and (analysis, right) in selected:
                metric = compare(selected[(analysis, left)][1], selected[(analysis, right)][1]); metric.update({"analysis": analysis, "left": left, "right": right}); comparisons.append(metric)
    logic = logic_gate(selected[("tran", "hspice_independent")][1]) if ("tran", "hspice_independent") in selected else {}
    exclusions = []
    for metric in comparisons:
        if metric["left"] == "hspice_independent" and metric["right"] == "hspice_alter" and float(metric["max_abs_v"]) > 1e-6: raise RuntimeError(metric)
        if metric["left"] == "ngspice_optimized_independent" and metric["right"] == "ngspice_optimized_reuse":
            limit = 1e-6 if metric["analysis"] == "dc" else 1e-5
            if float(metric["max_abs_v"]) > limit:
                exclusions.append({"method": "ngspice_optimized_reuse", "analysis": metric["analysis"], "reason": "same-simulator waveform gate exceeded", "limit_v": limit, "observed_v": metric["max_abs_v"]})
    output = args.root / "data" / "summary" / f"{args.tag}_gate.json"; output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"status": "pass_with_exclusions" if exclusions else "pass", "files_checked": checked, "dc_size": args.size, "tran_size": args.tran_size or args.size, "comparisons": comparisons, "exclusions": exclusions, **logic}, indent=2) + "\n", encoding="utf-8")
    print(output)

if __name__ == "__main__": main()
