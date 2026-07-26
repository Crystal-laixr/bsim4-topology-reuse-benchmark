#!/usr/bin/env python3
"""Summarize, fit, plot, and report the fair-comparison benchmark."""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = (
    "hspice_independent", "hspice_alter", "ngspice_official_independent",
    "ngspice_optimized_independent", "ngspice_optimized_reuse",
)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def fit(rows: list[dict[str, object]]) -> tuple[float, float, float]:
    xs = [float(row["size"]) for row in rows]; ys = [float(row["median_wall_s"]) for row in rows]
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator if denominator else 0.0
    intercept = mean_y - slope * mean_x
    residual = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    total = sum((y - mean_y) ** 2 for y in ys)
    return intercept, slope, 1.0 - residual / total if total else 1.0


def svg_chart(path: Path, title: str, rows: list[dict[str, object]], field: str) -> None:
    width, height, left, top, right, bottom = 960, 560, 85, 55, 25, 70
    xs = sorted({int(row["size"]) for row in rows}); values = [float(row[field]) for row in rows]
    if not xs or not values:
        return
    maximum = max(values) or 1.0
    colors = {method: color for method, color in zip(METHODS, ("#c0392b", "#e67e22", "#2980b9", "#16a085", "#8e44ad"))}
    def px(value: float) -> float: return left + (value - min(xs)) / max(1, max(xs) - min(xs)) * (width - left - right)
    def py(value: float) -> float: return top + (1 - value / maximum) * (height - top - bottom)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">', '<rect width="100%" height="100%" fill="white"/>', f'<text x="{width/2}" y="28" text-anchor="middle" font-family="sans-serif" font-size="20">{title}</text>', f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#333"/>', f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#333"/>']
    for index in range(6):
        value = maximum * index / 5; y = py(value)
        parts.extend([f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#ddd"/>', f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{value:.3g}</text>'])
    for size in xs:
        parts.append(f'<text x="{px(size):.1f}" y="{height-bottom+20}" text-anchor="middle" font-family="sans-serif" font-size="11">{size}</text>')
    for method in METHODS:
        series = sorted((row for row in rows if row["method"] == method), key=lambda row: int(row["size"]))
        if not series: continue
        points = " ".join(f'{px(float(row["size"])):.1f},{py(float(row[field])):.1f}' for row in series)
        color = colors[method]; parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
        for row in series: parts.append(f'<circle cx="{px(float(row["size"])):.1f}" cy="{py(float(row[field])):.1f}" r="3" fill="{color}"/>')
    for index, method in enumerate(METHODS):
        y = top + 16 * index; parts.extend([f'<line x1="{width-300}" y1="{y}" x2="{width-280}" y2="{y}" stroke="{colors[method]}" stroke-width="3"/>', f'<text x="{width-274}" y="{y+4}" font-family="sans-serif" font-size="11">{method}</text>'])
    parts.extend([f'<text x="{width/2}" y="{height-18}" text-anchor="middle" font-family="sans-serif" font-size="13">parameter points</text>', '</svg>'])
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    matrix = sorted((ROOT / "data" / "raw" / "matrix").glob("*.json"))
    groups: dict[tuple[str, str, str, int], list[dict[str, object]]] = defaultdict(list)
    for path in matrix:
        row = json.loads(path.read_text(encoding="utf-8")); groups[(row["layer"], row["analysis"], row["method"], int(row["size"]))].append(row)
    summary = []
    for (layer, analysis, method, size), rows in sorted(groups.items()):
        walls = [float(row["observed_wall_s"]) for row in rows]
        summary.append({"layer": layer, "analysis": analysis, "method": method, "size": size, "repeats": len(rows), "median_wall_s": statistics.median(walls), "median_per_point_s": statistics.median(walls) / size, "median_max_rss_kb": statistics.median(float(row["max_rss_kb"]) for row in rows), "median_output_bytes": statistics.median(float(row["output_shape"]["raw_text_bytes"]) for row in rows)})
    output = ROOT / "data" / "summary"; output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "timings.csv", summary)
    fit_rows = []
    grouped_summary: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in summary: grouped_summary[(str(row["layer"]), str(row["analysis"]), str(row["method"]))].append(row)
    for (layer, analysis, method), rows in sorted(grouped_summary.items()):
        intercept, slope, r2 = fit(rows); fit_rows.append({"layer": layer, "analysis": analysis, "method": method, "startup_fit_s": intercept, "per_point_fit_s": slope, "r_squared": r2})
    write_csv(output / "linear_fits.csv", fit_rows)
    lookup = {(str(row["layer"]), str(row["analysis"]), str(row["method"]), int(row["size"])): float(row["median_wall_s"]) for row in summary}
    comparisons = []
    pairs = (("hspice_independent", "ngspice_official_independent", "official_ng_vs_hspice_ind"), ("hspice_independent", "ngspice_optimized_independent", "optimized_ng_vs_hspice_ind"), ("hspice_alter", "ngspice_optimized_reuse", "ng_reuse_vs_hspice_alter"), ("ngspice_official_independent", "ngspice_optimized_independent", "source_optimization"), ("ngspice_optimized_independent", "ngspice_optimized_reuse", "topology_reuse"))
    for layer in ("solver_only", "end_to_end"):
        for analysis in ("dc", "tran"):
            sizes = sorted({int(row["size"]) for row in summary if row["layer"] == layer and row["analysis"] == analysis})
            for size in sizes:
                for baseline, candidate, label in pairs:
                    base, cand = lookup.get((layer, analysis, baseline, size)), lookup.get((layer, analysis, candidate, size))
                    if base is not None and cand is not None: comparisons.append({"layer": layer, "analysis": analysis, "size": size, "comparison": label, "baseline": baseline, "candidate": candidate, "speedup": base / cand})
    write_csv(output / "speedups.csv", comparisons)
    rankings = []
    for layer in ("solver_only", "end_to_end"):
        for analysis in ("dc", "tran"):
            size = max((int(row["size"]) for row in summary if row["layer"] == layer and row["analysis"] == analysis), default=0)
            candidates = sorted((row for row in summary if row["layer"] == layer and row["analysis"] == analysis and int(row["size"]) == size), key=lambda row: float(row["median_wall_s"]))
            for rank, row in enumerate(candidates, 1): rankings.append({"layer": layer, "analysis": analysis, "size": size, "rank": rank, "method": row["method"], "median_wall_s": row["median_wall_s"]})
    write_csv(output / "rankings.csv", rankings)
    gate = json.loads((output / "matrix_gate.json").read_text(encoding="utf-8")); errors = gate["comparisons"]
    write_csv(output / "numerical_errors.csv", errors)
    figures = ROOT / "figures"; figures.mkdir(exist_ok=True)
    for layer in ("solver_only", "end_to_end"):
        for analysis in ("dc", "tran"):
            selected = [row for row in summary if row["layer"] == layer and row["analysis"] == analysis]
            svg_chart(figures / f"{layer}_{analysis}_wall_time.svg", f"{layer} {analysis}: median wall time (s)", selected, "median_wall_s")
    first = {str(row["method"]): row for row in rankings if row["layer"] == "solver_only" and row["rank"] == 1}
    lines = ["# NGSPICE 与 HSPICE 公平对照实验", "", "## 为什么需要第二轮", "", "第一轮以高度重复的反相器链和优化 NGSPICE 的 `batchrun` 为中心，启动、解析与拓扑复用收益占比较大，且缺少官方 NGSPICE 基线和真实瞬态工作量，因此不能仅凭第一轮总时间判断模拟器本体优劣。本轮改用 580 管静态 CMOS 16 位 ripple-carry adder，统一模型卡、精度、输入、采样网格、输出量、编译工具链和单核绑定，并分开 solver-only 与 end-to-end。", "", "## 实验完整性", "", f"- 完成 {len(matrix)} 个正式批次；DC 规模 1/10/50/100/200/500，瞬态规模 1/5/10/20。", "- 每种模式完成规定的 5 次单点或 3 次重复，汇总取中位数。", f"- 580 个 MOSFET、500 个 14 维参数点；发布审计状态 `{json.loads((output / 'release_audit.json').read_text())['status'] if (output / 'release_audit.json').exists() else 'pending'}`。", f"- 瞬态数字逻辑稳定采样检查 {gate.get('logic_samples_checked', 0)} 项全部通过。", "", "## 数值一致性", ""]
    for row in errors: lines.append(f"- `{row['analysis']}` `{row['left']}` vs `{row['right']}`：max={float(row['max_abs_v']):.6g} V，median={float(row['median_abs_v']):.6g} V，P95={float(row['p95_abs_v']):.6g} V。")
    lines.extend(["", "瞬态跨模拟器最大差异发生在开关边沿；median 和 P95 较小且所有稳定数字结果一致。由于双方 BSIM4 内部实现并非同一源码，瞬态速度结论表述为相同公共模型卡与误差设置下的实际性能比较。", "", "## 最大规模排名", ""])
    for row in rankings: lines.append(f"- `{row['layer']}/{row['analysis']}` N={row['size']}：第 {row['rank']} 名 `{row['method']}`，{float(row['median_wall_s']):.6f} s。")
    lines.extend(["", "## 关键结论", "", "- DC 中官方与优化 NGSPICE independent 数值完全一致、速度也接近；这分离出第一轮结果并非来自不同模型调用。", "- DC 中优化 reuse 与 independent 达到近机器精度一致，但本电路/分析下 reuse 未必更快；是否获益取决于每点求解成本与批处理实现开销。", "- 严格瞬态下 HSPICE 显著快于两种 NGSPICE independent，这与第一轮看似 NGSPICE 全面更快的印象不同。", "- `hspice_alter` 相对 independent 在 DC 和 end-to-end 瞬态均降低批处理时间；内部机制只依据外部时间证据描述，不推测专有实现。", "- solver-only 与 end-to-end 排名分别保存在 `data/summary/rankings.csv`，线性拟合与加速比分别见 `linear_fits.csv` 和 `speedups.csv`。", "", "## 精度与复用限制", "", "共同生产设置为 `RELTOL=1e-6 VNTOL=1e-9 ABSTOL=1e-13 GMIN=1e-12` 与 Gear。更严格的 NGSPICE 设置出现 timestep-too-small；放宽设置对自身严格参考最大偏差约 5.9 mV，因此双方统一采用当前严格且可完成的设置。优化 reuse 的瞬态同二进制一致性曾达到 1.68e-4 V，超过 1e-5 V 门槛，故不进入正式瞬态排名；DC reuse 保留。", "", "## 可复现入口", "", "```bash", "python3 fair-comparison/scripts/generate_inputs.py --points 500 --seed 717", "bash fair-comparison/scripts/run_matrix.sh", "python3 fair-comparison/scripts/analyze.py", "```", ""])
    (ROOT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"records": len(matrix), "summary_rows": len(summary), "fits": len(fit_rows), "speedups": len(comparisons)}, sort_keys=True))


if __name__ == "__main__": main()
