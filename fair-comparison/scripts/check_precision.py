#!/usr/bin/env python3
"""Compare production outputs with the tighter per-simulator reference."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import tarfile
from pathlib import Path

OBSERVED = ("sum00", "sum05", "sum10", "sum15", "c04", "c08", "c12", "cout")

def load(root: Path, tag: str, layer: str, analysis: str, method: str, size: int):
    path = next((root / "data" / "raw" / tag).glob(f"{layer}_{analysis}_{method}_n{size}_r*.json"))
    payload = json.loads(path.read_text(encoding="utf-8")); archive = root / payload["logs_archive"]
    with tarfile.open(archive, "r:gz") as handle:
        return json.load(handle.extractfile("canonical_outputs.json"))

def metric(left, right):
    errors = []
    for lp, rp in zip(left, right):
        for name in OBSERVED:
            for (lx, ly), (rx, ry) in zip(lp[name], rp[name]):
                if abs(lx-rx) > 1e-15: raise RuntimeError("axis mismatch")
                errors.append(abs(ly-ry))
    ordered = sorted(errors)
    return {"comparisons": len(errors), "max_abs_v": max(errors), "median_abs_v": statistics.median(errors), "p95_abs_v": ordered[min(len(ordered)-1, math.floor(0.95*len(ordered)))]}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--production-tag", required=True); parser.add_argument("--tight-tag", required=True); parser.add_argument("--size", type=int, required=True); parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1]); args=parser.parse_args()
    rows=[]
    for analysis in ("dc","tran"):
        for method in ("hspice_independent","ngspice_official_independent"):
            row=metric(load(args.root,args.production_tag,"end_to_end",analysis,method,args.size),load(args.root,args.tight_tag,"tight_reference",analysis,method,args.size)); row.update({"analysis":analysis,"method":method}); rows.append(row)
    failed=[row for row in rows if float(row["max_abs_v"])>1e-5]
    output=args.root/"data"/"summary"/f"precision_gate_n{args.size}.json"; output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps({"status":"fail" if failed else "pass","rows":rows},indent=2)+"\n",encoding="utf-8")
    if failed: raise RuntimeError(failed)
    print(output)

if __name__=="__main__": main()
