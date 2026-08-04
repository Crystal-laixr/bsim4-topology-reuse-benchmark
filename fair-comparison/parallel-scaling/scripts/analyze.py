#!/usr/bin/env python3
"""Summarize worker scaling, crossover, efficiency, and resource records."""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (("hspice_independent", "ngspice_official_independent", "official_ng_vs_hspice_ind"), ("hspice_alter", "ngspice_optimized_reuse", "ng_reuse_vs_hspice_alter"), ("ngspice_official_independent", "ngspice_optimized_independent", "optimized_vs_official"), ("ngspice_optimized_independent", "ngspice_optimized_reuse", "reuse_vs_optimized"))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows: return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def svg(path: Path, title: str, rows: list[dict[str, object]], value: str) -> None:
    if not rows: return
    methods = sorted({str(row["method"]) for row in rows}); workers = sorted({int(row["workers"]) for row in rows})
    maximum = max(float(row[value]) for row in rows) or 1.0; width, height, left, bottom = 960, 520, 80, 60
    colors = ("#c0392b", "#e67e22", "#2980b9", "#16a085", "#8e44ad")
    def x(worker: int) -> float: return left + (worker - min(workers)) / max(1, max(workers) - min(workers)) * (width - left - 30)
    def y(number: float) -> float: return 45 + (1 - number / maximum) * (height - 45 - bottom)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">', '<rect width="100%" height="100%" fill="white"/>', f'<text x="480" y="25" text-anchor="middle" font-family="sans-serif" font-size="19">{title}</text>', f'<line x1="{left}" y1="45" x2="{left}" y2="{height-bottom}" stroke="#222"/>', f'<line x1="{left}" y1="{height-bottom}" x2="930" y2="{height-bottom}" stroke="#222"/>']
    for index in range(6):
        amount = maximum * index / 5; yy = y(amount); parts.append(f'<line x1="{left}" y1="{yy:.1f}" x2="930" y2="{yy:.1f}" stroke="#ddd"/><text x="72" y="{yy+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="10">{amount:.3g}</text>')
    for worker in workers: parts.append(f'<text x="{x(worker):.1f}" y="{height-bottom+18}" text-anchor="middle" font-family="sans-serif" font-size="10">{worker}</text>')
    for index, method in enumerate(methods):
        series = sorted((row for row in rows if row["method"] == method), key=lambda row: int(row["workers"]))
        color = colors[index % len(colors)]; points = " ".join(f'{x(int(row["workers"])):.1f},{y(float(row[value])):.1f}' for row in series)
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<text x="{left+8}" y="{64 + 16*index}" font-family="sans-serif" font-size="11" fill="{color}">{method}</text>')
    parts.append('</svg>'); path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    paths = sorted((ROOT / "data" / "raw" / "matrix").glob("*.json"))
    if not paths: raise RuntimeError("matrix records not found")
    groups: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for path in paths:
        row = json.loads(path.read_text(encoding="utf-8")); key = tuple(row[name] for name in ("scaling", "analysis", "layer", "method", "workers", "complexity", "total_points")); groups[key].append(row)
    summary = []
    for key, rows in sorted(groups.items()):
        scaling, analysis, layer, method, workers, complexity, total_points = key
        wall = statistics.median(float(row["observed_wall_s"]) for row in rows)
        cpu = statistics.median(float(row["total_cpu_s"]) for row in rows)
        rss = statistics.median(float(row["aggregate_max_rss_kb"]) for row in rows)
        effective = int(rows[0]["effective_workers"])
        summary.append({"scaling": scaling, "analysis": analysis, "layer": layer, "method": method, "workers": workers, "effective_workers": effective, "complexity": complexity, "total_points": total_points, "repeats": len(rows), "median_wall_s": wall, "median_total_cpu_s": cpu, "median_aggregate_rss_kb": rss, "throughput_points_s": int(total_points) / wall, "effective_cpu": cpu / wall})
    output = ROOT / "data" / "summary"; output.mkdir(parents=True, exist_ok=True); write_csv(output / "timings.csv", summary)
    lookup = {(row["scaling"], row["analysis"], row["layer"], row["complexity"], row["workers"], row["method"]): row for row in summary}
    speeds = []
    for row in summary:
        if row["scaling"] != "strong": continue
        for base, candidate, label in PAIRS:
            left = lookup.get((row["scaling"], row["analysis"], row["layer"], row["complexity"], row["workers"], base)); right = lookup.get((row["scaling"], row["analysis"], row["layer"], row["complexity"], row["workers"], candidate))
            if left and right: speeds.append({"analysis": row["analysis"], "layer": row["layer"], "complexity": row["complexity"], "workers": row["workers"], "comparison": label, "speedup": float(left["median_wall_s"]) / float(right["median_wall_s"])})
    write_csv(output / "strong_speedups.csv", speeds)
    weak = []
    for row in summary:
        if row["scaling"] != "weak": continue
        baseline = lookup.get(("weak", row["analysis"], row["layer"], row["complexity"], 1, row["method"]))
        if baseline: weak.append({**row, "parallel_efficiency": float(row["throughput_points_s"]) / (float(baseline["throughput_points_s"]) * int(row["workers"]))})
    write_csv(output / "weak_scaling.csv", weak)
    crossings = []
    for analysis, layer, complexity, label in sorted({(row["analysis"], row["layer"], row["complexity"], row["comparison"]) for row in speeds}):
        series = sorted((row for row in speeds if (row["analysis"], row["layer"], row["complexity"], row["comparison"]) == (analysis, layer, complexity, label)), key=lambda row: int(row["workers"]))
        crossing = next((row for row in series if float(row["speedup"]) >= 1), None)
        crossings.append({"analysis": analysis, "layer": layer, "complexity": complexity, "comparison": label, "first_measured_worker": crossing["workers"] if crossing else "not_observed", "first_measured_speedup": crossing["speedup"] if crossing else ""})
    write_csv(output / "crossovers.csv", crossings)
    figures = ROOT / "figures"; figures.mkdir(exist_ok=True)
    for scaling, metric in (("strong", "median_wall_s"), ("weak", "throughput_points_s")):
        selected = [row for row in summary if row["scaling"] == scaling and row["analysis"] == "dc" and row["layer"] == "end_to_end" and int(row["complexity"]) == 21]
        svg(figures / f"{scaling}_dc21_{metric}.svg", f"{scaling} DC-21 {metric}", selected, metric)
    lines = ["# 第三轮：并行 worker、批长度与分析复杂度", "", f"完成正式记录 {len(paths)} 个，汇总单元 {len(summary)} 个。", "", "## 结果口径", "", "- 强扩展固定 1000 点，比较同一批任务的完成时间。", "- 弱扩展每 worker 固定 1000 点，比较整机总吞吐和并行效率。", "- `effective_workers` 小于请求 worker 时，表示任务数不足以让所有 worker 都有工作。", "- HSPICE 许可证排队属于端到端时间；共同 worker 上限内的记录用于严格公平比较。", "", "## 交叉点", ""]
    for row in crossings: lines.append(f"- `{row['analysis']}/{row['layer']}` complexity={row['complexity']} `{row['comparison']}`：首次实测 {row['first_measured_worker']}，speedup={row['first_measured_speedup']}。")
    (output / "generated_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(paths), "summary_rows": len(summary), "crossovers": len(crossings)}, sort_keys=True))


if __name__ == "__main__": main()
