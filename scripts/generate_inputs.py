#!/usr/bin/env python3
"""Generate one deterministic 550-MOS benchmark for HSPICE and NGSPICE."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path


LANES = 25
STAGES = 11
SELECTED_LANES = (1, 7, 13, 19, 25)
VDD = 1.8
PARAMETERS = (
    ("vthn", 0.42, 0.48),
    ("vthp", -0.48, -0.42),
    ("u0n", 0.045, 0.055),
    ("u0p", 0.018, 0.022),
    ("rdswn", 90.0, 110.0),
    ("rdswp", 108.0, 132.0),
    ("vsatn", 72000.0, 88000.0),
    ("vsatp", 72000.0, 88000.0),
    ("eta0n", 0.072, 0.088),
    ("eta0p", 0.072, 0.088),
    ("ws0", 0.90, 1.10),
    ("ws1", 0.90, 1.10),
    ("ws2", 0.90, 1.10),
    ("ws3", 0.90, 1.10),
)
BASE_WN = (2.0e-6, 3.0e-6, 4.5e-6, 6.75e-6)


def latin_hypercube(seed: int, count: int) -> list[dict[str, float]]:
    rng = random.Random(seed)
    columns: list[list[float]] = []
    for _name, low, high in PARAMETERS:
        strata = [(index + rng.random()) / count for index in range(count)]
        rng.shuffle(strata)
        columns.append([low + value * (high - low) for value in strata])
    points = []
    for index in range(count):
        point = {name: columns[column][index] for column, (name, _low, _high) in enumerate(PARAMETERS)}
        point["point_id"] = f"p{index:06d}"
        points.append(point)
    return points


def lane_factor(lane: int) -> float:
    return 0.76 + 0.02 * (lane - 1)


def width_group(stage: int) -> int:
    return (stage - 1) % 4


def transistor_lines(width_mode: str, point: dict[str, float] | None = None) -> list[str]:
    lines: list[str] = []
    for lane in range(1, LANES + 1):
        previous = "in"
        fixed_lane_factor = lane_factor(lane)
        for stage in range(1, STAGES + 1):
            output = f"l{lane:02d}_n{stage:02d}"
            group = width_group(stage)
            base_wn = BASE_WN[group] * fixed_lane_factor
            base_wp = 2.0 * base_wn
            if width_mode == "hspice_param":
                wn = f"'{base_wn:.17g}*WS{group}'"
                wp = f"'{base_wp:.17g}*WS{group}'"
            elif width_mode == "literal":
                if point is None:
                    raise ValueError("literal widths require a point")
                wn = f"{base_wn * float(point[f'ws{group}']):.17g}"
                wp = f"{base_wp * float(point[f'ws{group}']):.17g}"
            else:
                raise ValueError(width_mode)
            lines.append(f"MN_L{lane:02d}_S{stage:02d} {output} {previous} 0 0 NM W={wn} L=0.18u")
            lines.append(f"MP_L{lane:02d}_S{stage:02d} {output} {previous} vdd vdd PM W={wp} L=0.18u")
            previous = output
        lines.append(f"RLEAK_L{lane:02d} {previous} 0 1g")
    return lines


def hspice_param_lines(point: dict[str, float]) -> list[str]:
    names = [name.upper() for name, _low, _high in PARAMETERS]
    return [".param " + " ".join(f"{name}={float(point[name.lower()]):.17g}" for name in names)]


def hspice_models() -> list[str]:
    return [
        ".model NM NMOS LEVEL=54 VERSION=4.7.0 TOXE=1.5n XJ=0.1u NDEP=1.7e17 "
        "VTH0='VTHN' U0='U0N' RDSW='RDSWN' VSAT='VSATN' ETA0='ETA0N'",
        ".model PM PMOS LEVEL=54 VERSION=4.7.0 TOXE=1.5n XJ=0.1u NDEP=1.2e17 "
        "VTH0='VTHP' U0='U0P' RDSW='RDSWP' VSAT='VSATP' ETA0='ETA0P'",
    ]


def hspice_measures() -> list[str]:
    lines = []
    for lane in SELECTED_LANES:
        output = f"l{lane:02d}_n{STAGES:02d}"
        lines.extend(
            [
                f".measure dc l{lane:02d}_lo find v({output}) at=0",
                f".measure dc l{lane:02d}_hi find v({output}) at=1.8",
                f".measure dc l{lane:02d}_th find v(in) when v(l{lane:02d}_n01)=0.9 cross=1",
            ]
        )
    lines.append(".measure dc peak_pwr max par('-v(vdd)*i(vdd)')")
    return lines


def hspice_deck(point: dict[str, float], title: str) -> str:
    lines = [
        f"* {title}",
        ".option nomod reltol=1e-6 vntol=1e-9 abstol=1e-15",
        ".temp 25",
        *hspice_param_lines(point),
        *hspice_models(),
        "VDD vdd 0 1.8",
        "VIN in 0 0",
        *transistor_lines("hspice_param"),
        ".dc VIN 0 1.8 0.1",
        *hspice_measures(),
        ".end",
    ]
    return "\n".join(lines) + "\n"


def hspice_alter_deck(points: list[dict[str, float]]) -> str:
    first = points[0]
    lines = [
        "* 550-MOS BSIM4 HSPICE alter benchmark",
        ".option nomod reltol=1e-6 vntol=1e-9 abstol=1e-15",
        ".temp 25",
        *hspice_param_lines(first),
        *hspice_models(),
        "VDD vdd 0 1.8",
        "VIN in 0 0",
        *transistor_lines("hspice_param"),
        ".dc VIN 0 1.8 0.1",
        *hspice_measures(),
    ]
    for point in points[1:]:
        lines.extend([f".alter {point['point_id']}", *hspice_param_lines(point)])
    lines.append(".end")
    return "\n".join(lines) + "\n"


def ngspice_models(point: dict[str, float]) -> list[str]:
    return [
        ".model NM NMOS (LEVEL=54 VERSION=4.7.0 TOXE=1.5e-9 XJ=1e-7 NDEP=1.7e17 "
        f"VTH0={point['vthn']:.17g} U0={point['u0n']:.17g} RDSW={point['rdswn']:.17g} "
        f"VSAT={point['vsatn']:.17g} ETA0={point['eta0n']:.17g})",
        ".model PM PMOS (LEVEL=54 VERSION=4.7.0 TOXE=1.5e-9 XJ=1e-7 NDEP=1.2e17 "
        f"VTH0={point['vthp']:.17g} U0={point['u0p']:.17g} RDSW={point['rdswp']:.17g} "
        f"VSAT={point['vsatp']:.17g} ETA0={point['eta0p']:.17g})",
    ]


def batchlogic_lines(point_id: str) -> list[str]:
    lines = []
    for lane in SELECTED_LANES:
        lines.append(f"batchlogic {point_id}_l{lane:02d} v(in) v(l{lane:02d}_n{STAGES:02d}) i(VDD) 1.8")
        lines.append(f"batchlogic {point_id}_l{lane:02d}t v(in) v(l{lane:02d}_n01) i(VDD) 1.8")
    return lines


def ngspice_deck(point: dict[str, float], title: str) -> str:
    lines = [
        f"* {title}",
        *ngspice_models(point),
        "VDD vdd 0 1.8",
        "VIN in 0 0",
        *transistor_lines("literal", point),
        ".control",
        "set noaskquit",
        "set nopage",
        "set numdgt=15",
        "set num_threads=1",
        "option klu",
        "option reltol=1e-6 vntol=1e-9 abstol=1e-15",
        "dc vin 0 1.8 0.1",
        *batchlogic_lines(str(point["point_id"])),
        "quit",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def ngspice_bindings() -> list[str]:
    lines = [
        "batchparambind vthn model NM VTH0",
        "batchparambind vthp model PM VTH0",
        "batchparambind u0n model NM U0",
        "batchparambind u0p model PM U0",
        "batchparambind rdswn model NM RDSW",
        "batchparambind rdswp model PM RDSW",
        "batchparambind vsatn model NM VSAT",
        "batchparambind vsatp model PM VSAT",
        "batchparambind eta0n model NM ETA0",
        "batchparambind eta0p model PM ETA0",
    ]
    for lane in range(1, LANES + 1):
        fixed_lane_factor = lane_factor(lane)
        for stage in range(1, STAGES + 1):
            group = width_group(stage)
            base_wn = BASE_WN[group] * fixed_lane_factor
            base_wp = 2.0 * base_wn
            lines.append(f"batchparambind ws{group} instance MN_L{lane:02d}_S{stage:02d} W {base_wn:.17g}")
            lines.append(f"batchparambind ws{group} instance MP_L{lane:02d}_S{stage:02d} W {base_wp:.17g}")
    return lines


def ngspice_commands(points: list[dict[str, float]]) -> str:
    lines = ngspice_bindings()
    for point in points:
        for name, _low, _high in PARAMETERS:
            lines.append(f"batchparam {name} {float(point[name]):.17g}")
        lines.append("dc vin 0 1.8 0.1")
        lines.extend(batchlogic_lines(str(point["point_id"])))
        lines.append("destroy $curplot")
    return "\n".join(lines) + "\n"


def ngspice_batch_deck(first: dict[str, float], command_path: str) -> str:
    lines = [
        "* 550-MOS BSIM4 persistent topology-reuse benchmark",
        *ngspice_models(first),
        "VDD vdd 0 1.8",
        "VIN in 0 0",
        *transistor_lines("literal", first),
        ".control",
        "set noaskquit",
        "set nopage",
        "set numdgt=15",
        "set num_threads=1",
        "option klu",
        "option reltol=1e-6 vntol=1e-9 abstol=1e-15",
        "batchstats reset",
        f"batchrun {command_path}",
        "batchstats json",
        "quit",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def assert_design(points: list[dict[str, float]]) -> None:
    lines = transistor_lines("literal", points[0])
    mos_count = sum(line.startswith(("MN_", "MP_")) for line in lines)
    if mos_count != 550:
        raise RuntimeError(f"expected 550 MOSFETs, found {mos_count}")
    if len(PARAMETERS) != 14:
        raise RuntimeError("expected exactly 14 varying parameters")
    for point in points:
        for name, low, high in PARAMETERS:
            if not low <= float(point[name]) <= high:
                raise RuntimeError(f"{point['point_id']}:{name} outside bounds")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=int, default=500)
    parser.add_argument("--seed", type=int, default=717)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    points = latin_hypercube(args.seed, args.points)
    assert_design(points)

    params_dir = root / "params"
    h_independent = root / "netlists" / "hspice" / "independent"
    h_alter = root / "netlists" / "hspice" / "alter"
    n_independent = root / "netlists" / "ngspice" / "independent"
    n_batch = root / "netlists" / "ngspice" / "batch"
    for directory in (params_dir, h_independent, h_alter, n_independent, n_batch):
        directory.mkdir(parents=True, exist_ok=True)

    fieldnames = ["point_id", *[name for name, _low, _high in PARAMETERS]]
    with (params_dir / "points.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(points)
    (params_dir / "design.json").write_text(
        json.dumps(
            {
                "seed": args.seed,
                "points": args.points,
                "lanes": LANES,
                "stages_per_lane": STAGES,
                "mosfet_count": 2 * LANES * STAGES,
                "varying_parameters": len(PARAMETERS),
                "selected_lanes": SELECTED_LANES,
                "dc_sweep": {"start_v": 0.0, "stop_v": 1.8, "step_v": 0.1},
                "parameters": [{"name": name, "low": low, "high": high} for name, low, high in PARAMETERS],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    for point in points:
        point_id = str(point["point_id"])
        (h_independent / f"{point_id}.sp").write_text(hspice_deck(point, point_id), encoding="ascii")
        (n_independent / f"{point_id}.cir").write_text(ngspice_deck(point, point_id), encoding="ascii")

    for size in (1, 3, 10, 50, 100, 200, 500):
        subset = points[: min(size, len(points))]
        (h_alter / f"alter_{size}.sp").write_text(hspice_alter_deck(subset), encoding="ascii")
        command_rel = f"netlists/ngspice/batch/commands_{size}.txt"
        (n_batch / f"commands_{size}.txt").write_text(ngspice_commands(subset), encoding="ascii")
        (n_batch / f"batch_{size}.cir").write_text(
            ngspice_batch_deck(subset[0], command_rel), encoding="ascii"
        )

    print(f"generated {len(points)} points, 550 MOSFETs, and 14 varying parameters under {root}")


if __name__ == "__main__":
    main()
