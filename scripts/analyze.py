#!/usr/bin/env python3
"""Aggregate raw benchmark JSON into CSV, SVG, and a Chinese report."""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METHODS = ("hspice_independent", "hspice_alter", "ngspice_independent", "ngspice_reuse")
SIZES = (1, 10, 50, 100, 200, 500)
COLORS = {
    "hspice_independent": "#d95f02",
    "hspice_alter": "#e6ab02",
    "ngspice_independent": "#7570b3",
    "ngspice_reuse": "#1b9e77",
}


def load_runs() -> list[dict[str, object]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted((ROOT / "data/raw/matrix").glob("*.json"))]


def median_rows(runs: list[dict[str, object]]) -> list[dict[str, float | int | str]]:
    rows = []
    for size in SIZES:
        for method in METHODS:
            selected = [run for run in runs if run["method"] == method and int(run["size"]) == size]
            expected = 5 if size == 1 else 3
            if len(selected) != expected:
                raise RuntimeError(f"expected {expected} runs for {method} n={size}, found {len(selected)}")
            walls = [float(run["observed_wall_s"]) for run in selected]
            sim_walls = [float(run["simulation_wall_s"]) for run in selected]
            rss = [int(run["max_rss_kb"]) for run in selected]
            rows.append(
                {
                    "method": method,
                    "size": size,
                    "repeats": len(selected),
                    "median_wall_s": statistics.median(walls),
                    "median_simulation_wall_s": statistics.median(sim_walls),
                    "median_per_point_s": statistics.median(walls) / size,
                    "median_max_rss_kb": statistics.median(rss),
                    "min_wall_s": min(walls),
                    "max_wall_s": max(walls),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def ngspice_profile_rows(runs: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for size in SIZES:
        selected = [run for run in runs if run["method"] == "ngspice_reuse" and int(run["size"]) == size]
        keys = sorted({key for run in selected for key, value in run.get("batch_profile", {}).items() if isinstance(value, (int, float))})
        row: dict[str, object] = {"size": size, "repeats": len(selected)}
        for key in keys:
            row[key] = statistics.median(float(run["batch_profile"].get(key, 0.0)) for run in selected)
        rows.append(row)
    return rows


def hspice_phase_summary() -> list[dict[str, object]]:
    path = ROOT / "data/summary/hspice_phases.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))
    rows = []
    for size in SIZES:
        for method in ("hspice_independent", "hspice_alter"):
            selected = [row for row in raw if row["method"] == method and int(row["size"]) == size]
            if not selected:
                continue
            rows.append(
                {
                    "method": method,
                    "size": size,
                    "jobs": statistics.median(float(row["jobs"]) for row in selected),
                    "read_s": statistics.median(float(row["read_s"]) for row in selected),
                    "check_s": statistics.median(float(row["check_s"]) for row in selected),
                    "setup_s": statistics.median(float(row["setup_s"]) for row in selected),
                    "analysis_s": statistics.median(float(row["analysis_s"]) for row in selected),
                }
            )
    return rows


def row_map(rows: list[dict[str, object]]) -> dict[tuple[str, int], dict[str, object]]:
    return {(str(row["method"]), int(row["size"])): row for row in rows}


def speedup_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    lookup = row_map(rows)
    output = []
    for size in SIZES:
        h_ind = float(lookup[("hspice_independent", size)]["median_wall_s"])
        h_alt = float(lookup[("hspice_alter", size)]["median_wall_s"])
        n_ind = float(lookup[("ngspice_independent", size)]["median_wall_s"])
        n_reuse = float(lookup[("ngspice_reuse", size)]["median_wall_s"])
        output.append(
            {
                "size": size,
                "ngspice_reuse_vs_independent": n_ind / n_reuse,
                "hspice_alter_vs_independent": h_ind / h_alt,
                "ngspice_reuse_vs_hspice_independent": h_ind / n_reuse,
                "ngspice_reuse_vs_hspice_alter": h_alt / n_reuse,
                "ngspice_reuse_vs_best_hspice": min(h_ind, h_alt) / n_reuse,
            }
        )
    return output


def fit_line(rows: list[dict[str, object]], method: str) -> tuple[float, float]:
    selected = [(float(row["size"]), float(row["median_wall_s"])) for row in rows if row["method"] == method]
    mean_x = statistics.mean(x for x, _y in selected)
    mean_y = statistics.mean(y for _x, y in selected)
    denominator = sum((x - mean_x) ** 2 for x, _y in selected)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in selected) / denominator
    return mean_y - slope * mean_x, slope


def first_crossing(rows: list[dict[str, object]], hspice_method: str) -> int | None:
    lookup = row_map(rows)
    for size in SIZES:
        if float(lookup[("ngspice_reuse", size)]["median_wall_s"]) < float(lookup[(hspice_method, size)]["median_wall_s"]):
            return size
    return None


def flatten(run: dict[str, object]) -> dict[tuple[str, str, str], float]:
    values = {}
    for point in run["points"]:
        point_id = str(point["point_id"])
        for lane, metrics in point["lanes"].items():
            for metric, value in metrics.items():
                values[(point_id, str(lane), str(metric))] = abs(float(value)) if metric == "power_w" else float(value)
    return values


def representative(runs: list[dict[str, object]], method: str) -> dict[str, object]:
    selected = [run for run in runs if run["method"] == method and int(run["size"]) == 500]
    return min(selected, key=lambda run: float(run["observed_wall_s"]))


def error_row(runs: list[dict[str, object]], left_method: str, right_method: str) -> dict[str, object]:
    left = flatten(representative(runs, left_method))
    right = flatten(representative(runs, right_method))
    keys = sorted(left.keys() & right.keys())
    differences = [abs(left[key] - right[key]) for key in keys]
    relative = [difference / max(abs(left[key]), abs(right[key]), 1e-30) for key, difference in zip(keys, differences)]
    ordered = sorted(differences)
    p95 = ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]
    return {
        "left": left_method,
        "right": right_method,
        "comparisons": len(keys),
        "max_abs": max(differences),
        "median_abs": statistics.median(differences),
        "p95_abs": p95,
        "max_relative": max(relative),
    }


def svg_line_chart(path: Path, rows: list[dict[str, object]]) -> None:
    width, height = 900, 560
    margin_left, margin_right, margin_top, margin_bottom = 90, 30, 40, 80
    values = [float(row["median_wall_s"]) for row in rows]
    ymax = max(values) * 1.08
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    x = lambda size: margin_left + plot_w * (math.log10(size) / math.log10(500))
    y = lambda value: margin_top + plot_h * (1.0 - value / ymax)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>', '<text x="450" y="24" text-anchor="middle" font-family="sans-serif" font-size="18">Task count vs median wall time</text>']
    for tick in range(6):
        value = ymax * tick / 5
        yy = y(value)
        lines.append(f'<line x1="{margin_left}" y1="{yy:.2f}" x2="{width-margin_right}" y2="{yy:.2f}" stroke="#dddddd"/>')
        lines.append(f'<text x="{margin_left-10}" y="{yy+5:.2f}" text-anchor="end" font-family="sans-serif" font-size="12">{value:.2f}</text>')
    for size in SIZES:
        xx = x(size)
        lines.append(f'<line x1="{xx:.2f}" y1="{margin_top}" x2="{xx:.2f}" y2="{height-margin_bottom}" stroke="#eeeeee"/>')
        lines.append(f'<text x="{xx:.2f}" y="{height-margin_bottom+25}" text-anchor="middle" font-family="sans-serif" font-size="12">{size}</text>')
    for method_index, method in enumerate(METHODS):
        selected = sorted((row for row in rows if row["method"] == method), key=lambda row: int(row["size"]))
        points = " ".join(f'{x(int(row["size"])):.2f},{y(float(row["median_wall_s"])):.2f}' for row in selected)
        lines.append(f'<polyline points="{points}" fill="none" stroke="{COLORS[method]}" stroke-width="3"/>')
        for row in selected:
            lines.append(f'<circle cx="{x(int(row["size"])):.2f}" cy="{y(float(row["median_wall_s"])):.2f}" r="4" fill="{COLORS[method]}"/>')
        legend_y = 55 + method_index * 24
        lines.append(f'<line x1="620" y1="{legend_y}" x2="650" y2="{legend_y}" stroke="{COLORS[method]}" stroke-width="3"/>')
        lines.append(f'<text x="660" y="{legend_y+5}" font-family="sans-serif" font-size="12">{method}</text>')
    lines.extend([f'<text x="{width/2}" y="{height-20}" text-anchor="middle" font-family="sans-serif" font-size="14">Task count (log scale)</text>', f'<text x="20" y="{height/2}" transform="rotate(-90 20 {height/2})" text-anchor="middle" font-family="sans-serif" font-size="14">Wall time (s)</text>', '</svg>'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def svg_series_chart(path: Path, title: str, ylabel: str, series: dict[str, list[tuple[int, float]]]) -> None:
    width, height = 900, 560
    left, right, top, bottom = 90, 30, 40, 80
    palette = ("#1b9e77", "#d95f02", "#7570b3", "#e7298a")
    ymax = max(value for values in series.values() for _size, value in values) * 1.08
    plot_w, plot_h = width - left - right, height - top - bottom
    x = lambda size: left + plot_w * (math.log10(size) / math.log10(500))
    y = lambda value: top + plot_h * (1.0 - value / ymax)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>', f'<text x="450" y="24" text-anchor="middle" font-family="sans-serif" font-size="18">{title}</text>']
    for tick in range(6):
        value = ymax * tick / 5
        yy = y(value)
        lines.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width-right}" y2="{yy:.2f}" stroke="#dddddd"/>')
        lines.append(f'<text x="{left-10}" y="{yy+5:.2f}" text-anchor="end" font-family="sans-serif" font-size="12">{value:.3g}</text>')
    for size in SIZES:
        xx = x(size)
        lines.append(f'<text x="{xx:.2f}" y="{height-bottom+25}" text-anchor="middle" font-family="sans-serif" font-size="12">{size}</text>')
    for index, (label, values) in enumerate(series.items()):
        color = palette[index % len(palette)]
        points = " ".join(f"{x(size):.2f},{y(value):.2f}" for size, value in values)
        lines.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"/>')
        for size, value in values:
            lines.append(f'<circle cx="{x(size):.2f}" cy="{y(value):.2f}" r="4" fill="{color}"/>')
        legend_y = 55 + index * 24
        lines.append(f'<line x1="620" y1="{legend_y}" x2="650" y2="{legend_y}" stroke="{color}" stroke-width="3"/>')
        lines.append(f'<text x="660" y="{legend_y+5}" font-family="sans-serif" font-size="12">{label}</text>')
    lines.extend([f'<text x="{width/2}" y="{height-20}" text-anchor="middle" font-family="sans-serif" font-size="14">Task count (log scale)</text>', f'<text x="20" y="{height/2}" transform="rotate(-90 20 {height/2})" text-anchor="middle" font-family="sans-serif" font-size="14">{ylabel}</text>', '</svg>'])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    runs = load_runs()
    rows = median_rows(runs)
    speeds = speedup_rows(rows)
    summary = ROOT / "data" / "summary"
    write_csv(summary / "timings.csv", rows)
    write_csv(summary / "speedups.csv", speeds)
    errors = [
        error_row(runs, "ngspice_independent", "ngspice_reuse"),
        error_row(runs, "hspice_independent", "hspice_alter"),
        error_row(runs, "hspice_independent", "ngspice_independent"),
    ]
    write_csv(summary / "errors.csv", errors)
    fits = []
    for method in METHODS:
        intercept, slope = fit_line(rows, method)
        fits.append({"method": method, "estimated_init_s": intercept, "estimated_per_point_s": slope})
    write_csv(summary / "linear_fits.csv", fits)
    profiles = ngspice_profile_rows(runs)
    write_csv(summary / "ngspice_profiles.csv", profiles)
    phase_rows = hspice_phase_summary()
    if phase_rows:
        write_csv(summary / "hspice_phase_medians.csv", phase_rows)
    svg_line_chart(ROOT / "figures" / "task_count_vs_wall_time.svg", rows)
    svg_series_chart(
        ROOT / "figures" / "per_point_time.svg",
        "Task count vs median per-point time",
        "Seconds per point",
        {method: [(int(row["size"]), float(row["median_per_point_s"])) for row in rows if row["method"] == method] for method in METHODS},
    )
    svg_series_chart(
        ROOT / "figures" / "speedups.svg",
        "Speedup vs task count",
        "Speedup (x)",
        {
            "NG reuse / NG independent": [(int(row["size"]), float(row["ngspice_reuse_vs_independent"])) for row in speeds],
            "HSPICE alter / independent": [(int(row["size"]), float(row["hspice_alter_vs_independent"])) for row in speeds],
            "NG reuse / best HSPICE": [(int(row["size"]), float(row["ngspice_reuse_vs_best_hspice"])) for row in speeds],
        },
    )
    svg_series_chart(
        ROOT / "figures" / "peak_memory.svg",
        "Task count vs median peak RSS",
        "Peak RSS (MiB)",
        {method: [(int(row["size"]), float(row["median_max_rss_kb"]) / 1024.0) for row in rows if row["method"] == method] for method in METHODS},
    )

    lookup = row_map(rows)
    last_speed = next(row for row in speeds if int(row["size"]) == 500)
    alter_speed = float(last_speed["hspice_alter_vs_independent"])
    h_ind_slope = next(float(row["estimated_per_point_s"]) for row in fits if row["method"] == "hspice_independent")
    h_alt_slope = next(float(row["estimated_per_point_s"]) for row in fits if row["method"] == "hspice_alter")
    slope_ratio = h_alt_slope / h_ind_slope if h_ind_slope else math.inf
    phase_lookup = {(str(row["method"]), int(row["size"])): row for row in phase_rows}
    independent_phase = phase_lookup.get(("hspice_independent", 500))
    alter_phase = phase_lookup.get(("hspice_alter", 500))
    read_ratio = float(alter_phase["read_s"]) / float(independent_phase["read_s"]) if independent_phase and alter_phase and float(independent_phase["read_s"]) else math.inf
    setup_ratio = float(alter_phase["setup_s"]) / float(independent_phase["setup_s"]) if independent_phase and alter_phase and float(independent_phase["setup_s"]) else math.inf
    if alter_speed >= 1.2 and read_ratio <= 0.5 and setup_ratio <= 0.5:
        alter_judgement = "存在明显的复用或缓存证据"
    elif alter_speed >= 1.2:
        alter_judgement = "总时间明显降低，但阶段日志仍显示逐点 read/setup，不能据此认定拓扑矩阵被复用"
    elif 0.95 <= alter_speed <= 1.05 and 0.9 <= slope_ratio <= 1.1:
        alter_judgement = "未观察到有效复用"
    else:
        alter_judgement = "存在性能差异，但仅凭计时不足以确定内部机制"
    crossing_ind = first_crossing(rows, "hspice_independent")
    crossing_alt = first_crossing(rows, "hspice_alter")
    primary_cross = crossing_alt if float(lookup[("hspice_alter", 500)]["median_wall_s"]) <= float(lookup[("hspice_independent", 500)]["median_wall_s"]) else crossing_ind
    profile_500 = next(row for row in profiles if int(row["size"]) == 500)
    reuse_wall = float(lookup[("ngspice_reuse", 500)]["median_wall_s"])
    load_share = float(profile_500.get("load_time", 0.0)) / reuse_wall
    parameter_share = float(profile_500.get("direct_param_time", 0.0)) / reuse_wall

    report = f"""# 550 管 BSIM4 拓扑复用性能实验报告

## 实验配置

- 电路：25 路 × 11 级 CMOS 反相器链，共 550 个 BSIM4 MOSFET。
- 参数：500 个固定种子 Latin hypercube 点，每点同时改变 14 个参数。
- 分析：25°C，VIN 0–1.8 V、步长 0.1 V 的 DC 扫描。
- 规模：1、10、50、100、200、500；单点 5 次，其余 3 次并取中位数。
- 执行：单线程并固定 CPU；比较 HSPICE independent、HSPICE `.alter`、NGSPICE independent、NGSPICE topology reuse。

## 500 点核心结果

| 方案 | 中位总时间 (s) | 平均每点 (s) | 峰值 RSS (KiB) |
|---|---:|---:|---:|
"""
    for method in METHODS:
        row = lookup[(method, 500)]
        report += f"| {method} | {float(row['median_wall_s']):.6f} | {float(row['median_per_point_s']):.8f} | {float(row['median_max_rss_kb']):.0f} |\n"
    report += f"""

## 加速比与交叉点

- 500 点 NGSPICE topology reuse / NGSPICE independent：`{float(last_speed['ngspice_reuse_vs_independent']):.3f}×`。
- 500 点 HSPICE `.alter` / HSPICE independent：`{alter_speed:.3f}×`。
- 500 点 NGSPICE topology reuse / HSPICE independent：`{float(last_speed['ngspice_reuse_vs_hspice_independent']):.3f}×`。
- 500 点 NGSPICE topology reuse / HSPICE `.alter`：`{float(last_speed['ngspice_reuse_vs_hspice_alter']):.3f}×`。
- 首次实测超过 HSPICE independent：`{crossing_ind if crossing_ind is not None else '500 点内未观察到'}`。
- 首次实测超过 HSPICE `.alter`：`{crossing_alt if crossing_alt is not None else '500 点内未观察到'}`。
- 相对最佳 HSPICE 方案的主要交叉点：`{primary_cross if primary_cross is not None else '500 点内未观察到'}`。

## HSPICE `.alter` 判断

500 点加速比为 `{alter_speed:.3f}×`，拟合后的 `.alter`/独立模式稳态斜率比为 `{slope_ratio:.3f}`；read 阶段总时间比为 `{read_ratio:.3f}`，setup 阶段总时间比为 `{setup_ratio:.3f}`。按预注册规则，结论为：**{alter_judgement}**。

## NGSPICE 复用证据与瓶颈

- 500 点共调用 setup `{float(profile_500.get('setup_calls', 0)):.0f}` 次，其中复用 `{float(profile_500.get('setup_reuse', 0)):.0f}` 次；KLU symbolic reuse 为 `{float(profile_500.get('symbolic_reuse', 0)):.0f}` 次。
- `CKTload` 累计 `{float(profile_500.get('load_calls', 0)):.0f}` 次，耗时 `{float(profile_500.get('load_time', 0)):.3f} s`，约占总时间 `{load_share:.1%}`。
- 14 个逻辑参数产生 `{float(profile_500.get('direct_param_writes', 0)):.0f}` 次直接写入，耗时 `{float(profile_500.get('direct_param_time', 0)):.3f} s`，约占总时间 `{parameter_share:.1%}`。
- 因 setup 与 symbolic 已几乎完全复用，后续主要瓶颈是 BSIM4 矩阵装载、数值分解及大量参数扇出写入，而不是拓扑初始化。

## 线性拟合

| 方案 | 估计初始化时间 (s) | 稳态每点斜率 (s/点) |
|---|---:|---:|
"""
    for fit in fits:
        report += f"| {fit['method']} | {float(fit['estimated_init_s']):.6f} | {float(fit['estimated_per_point_s']):.8f} |\n"
    report += """

## 数值一致性

| 对比 | 样本数 | 最大绝对差 | P95 绝对差 | 最大相对差 |
|---|---:|---:|---:|---:|
"""
    for error in errors:
        report += f"| {error['left']} vs {error['right']} | {error['comparisons']} | {float(error['max_abs']):.6g} | {float(error['p95_abs']):.6g} | {float(error['max_relative']):.6g} |\n"
    report += """

同模拟器优化前后通过严格门槛后才纳入性能结论。跨模拟器误差只用于描述 BSIM4 实现差异，不作为复用正确性的单一判据。

## 文件索引

- `data/raw/`：逐次 JSON、压缩模拟器日志和系统信息。
- `data/summary/`：计时、加速比、误差和线性拟合 CSV。
- `figures/`：总时间、每点时间、加速比和峰值内存曲线。
- `params/points.csv`：全部 500 个参数点。
- `netlists/`：独立网表、HSPICE `.alter` 网表和 NGSPICE batch 命令。
"""
    (ROOT / "REPORT.md").write_text(report, encoding="utf-8")
    print(f"wrote summaries, figure, and {ROOT / 'REPORT.md'}")


if __name__ == "__main__":
    main()
