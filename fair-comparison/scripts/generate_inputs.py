#!/usr/bin/env python3
"""Generate the fair 580-MOS BSIM4 HSPICE/NGSPICE benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path


BITS = 16
VDD = 1.8
SIZES = (1, 3, 5, 10, 20, 50, 100, 200, 500)
PARAMETERS = (
    ("vthn", 0.42, 0.48), ("vthp", -0.48, -0.42),
    ("u0n", 0.045, 0.055), ("u0p", 0.018, 0.022),
    ("rdswn", 90.0, 110.0), ("rdswp", 108.0, 132.0),
    ("vsatn", 72000.0, 88000.0), ("vsatp", 72000.0, 88000.0),
    ("eta0n", 0.072, 0.088), ("eta0p", 0.072, 0.088),
    ("ws0", 0.90, 1.10), ("ws1", 0.90, 1.10),
    ("ws2", 0.90, 1.10), ("ws3", 0.90, 1.10),
)
BASE_WN = (1.2e-6, 1.8e-6, 2.4e-6, 8.0e-6)
OBSERVED = ("sum00", "sum05", "sum10", "sum15", "c04", "c08", "c12", "cout")
TRAN_PERIOD_NS = 10.0
TRAN_STOP_NS = 40.0
TRAN_STEP_NS = 0.50

COMMON_MODEL = {
    "LEVEL": 54, "VERSION": "4.7.0", "TNOM": 25.0,
    "TOXE": 1.5e-9, "DTOX": 0.0, "EPSROX": 3.9, "XJ": 1.0e-7,
    "NSD": 1.0e20, "NGATE": 0.0, "PHIN": 0.0,
    "K1": 0.53, "K2": -0.0186, "K3": 0.0, "K3B": 0.0,
    "W0": 2.5e-6,
    "DVT0": 2.2, "DVT1": 0.53, "DVT2": -0.032,
    "DVT0W": 0.0, "DVT1W": 5.3e6, "DVT2W": -0.032,
    "UA": 1.0e-9, "UB": 1.0e-18, "UC": -4.65e-11,
    "A0": 1.0, "AGS": 0.0, "B0": 0.0, "B1": 0.0,
    "KETA": -0.047, "A1": 0.0, "A2": 1.0,
    "PRWG": 0.0, "PRWB": 0.0, "WR": 1.0, "DWG": 0.0, "DWB": 0.0,
    "VOFF": -0.08, "NFACTOR": 1.0, "ETAB": -0.07,
    "PCLM": 1.3, "PDIBLC1": 0.39, "PDIBLC2": 0.0086,
    "PDIBLCB": 0.0, "DROUT": 0.56, "PVAG": 0.0, "DELTA": 0.01,
    "MOBMOD": 0, "CAPMOD": 2, "RDSMOD": 0, "RGATEMOD": 0,
}


@dataclass(frozen=True)
class Mos:
    name: str
    drain: str
    gate: str
    source: str
    bulk: str
    model: str
    group: int


def latin_hypercube(seed: int, count: int) -> list[dict[str, float | str]]:
    rng = random.Random(seed)
    columns: list[list[float]] = []
    for _name, low, high in PARAMETERS:
        values = [(index + rng.random()) / count for index in range(count)]
        rng.shuffle(values)
        columns.append([low + value * (high - low) for value in values])
    return [
        {"point_id": f"p{index:06d}", **{name: columns[col][index] for col, (name, _lo, _hi) in enumerate(PARAMETERS)}}
        for index in range(count)
    ]


def add_inverter(devices: list[Mos], prefix: str, inp: str, out: str, group: int) -> None:
    devices.extend([
        Mos(f"MN_{prefix}", out, inp, "0", "0", "NM", group),
        Mos(f"MP_{prefix}", out, inp, "vdd", "vdd", "PM", group),
    ])


def add_xor12(devices: list[Mos], prefix: str, a: str, b: str, out: str) -> None:
    abar, bbar = f"{prefix}_ab", f"{prefix}_bb"
    n00, n11, p01, p10 = (f"{prefix}_{name}" for name in ("n00", "n11", "p01", "p10"))
    add_inverter(devices, f"{prefix}_IA", a, abar, 0)
    add_inverter(devices, f"{prefix}_IB", b, bbar, 0)
    devices.extend([
        Mos(f"MN_{prefix}_00A", out, abar, n00, "0", "NM", 1), Mos(f"MN_{prefix}_00B", n00, bbar, "0", "0", "NM", 1),
        Mos(f"MN_{prefix}_11A", out, a, n11, "0", "NM", 1), Mos(f"MN_{prefix}_11B", n11, b, "0", "0", "NM", 1),
        Mos(f"MP_{prefix}_01A", out, a, p01, "vdd", "PM", 1), Mos(f"MP_{prefix}_01B", p01, bbar, "vdd", "vdd", "PM", 1),
        Mos(f"MP_{prefix}_10A", out, abar, p10, "vdd", "PM", 1), Mos(f"MP_{prefix}_10B", p10, b, "vdd", "vdd", "PM", 1),
    ])


def add_nand2(devices: list[Mos], prefix: str, a: str, b: str, out: str, group: int = 2) -> None:
    middle = f"{prefix}_mid"
    devices.extend([
        Mos(f"MN_{prefix}_A", out, a, middle, "0", "NM", group), Mos(f"MN_{prefix}_B", middle, b, "0", "0", "NM", group),
        Mos(f"MP_{prefix}_A", out, a, "vdd", "vdd", "PM", group), Mos(f"MP_{prefix}_B", out, b, "vdd", "vdd", "PM", group),
    ])


def circuit() -> list[Mos]:
    devices: list[Mos] = []
    carry = "cin"
    for bit in range(BITS):
        prefix = f"FA{bit:02d}"
        propagate = f"p{bit:02d}"
        nab, npc = f"nab{bit:02d}", f"npc{bit:02d}"
        add_xor12(devices, f"{prefix}_X0", f"a{bit:02d}", f"b{bit:02d}", propagate)
        add_xor12(devices, f"{prefix}_X1", propagate, carry, f"sum{bit:02d}")
        add_nand2(devices, f"{prefix}_NAB", f"a{bit:02d}", f"b{bit:02d}", nab)
        add_nand2(devices, f"{prefix}_NPC", propagate, carry, npc)
        add_nand2(devices, f"{prefix}_COUT", nab, npc, f"c{bit + 1:02d}", 3)
        carry = f"c{bit + 1:02d}"
    add_inverter(devices, "COUT_BUF0", carry, "cout_b", 3)
    add_inverter(devices, "COUT_BUF1", "cout_b", "cout", 3)
    if len(devices) != 580:
        raise RuntimeError(f"expected 580 MOSFETs, got {len(devices)}")
    return devices


def width(device: Mos, point: dict[str, float | str]) -> float:
    base = BASE_WN[device.group]
    if device.model == "PM":
        base *= 2.0
    return base * float(point[f"ws{device.group}"])


def model_values(point: dict[str, float | str], model: str) -> dict[str, object]:
    values = dict(COMMON_MODEL)
    if model == "NM":
        values.update(NDEP=1.7e17, VTH0=point["vthn"], U0=point["u0n"], RDSW=point["rdswn"], VSAT=point["vsatn"], ETA0=point["eta0n"])
    else:
        values.update(NDEP=1.2e17, VTH0=point["vthp"], U0=point["u0p"], RDSW=point["rdswp"], VSAT=point["vsatp"], ETA0=point["eta0p"])
    return values


def model_line(point: dict[str, float | str], model: str, parameterized: bool = False) -> str:
    values = model_values(point, model)
    varying = {
        "NM": {"VTH0": "VTHN", "U0": "U0N", "RDSW": "RDSWN", "VSAT": "VSATN", "ETA0": "ETA0N"},
        "PM": {"VTH0": "VTHP", "U0": "U0P", "RDSW": "RDSWP", "VSAT": "VSATP", "ETA0": "ETA0P"},
    }[model]
    rendered = []
    for name, value in values.items():
        if parameterized and name in varying:
            rendered.append(f"{name}='{varying[name]}'")
        elif isinstance(value, str):
            rendered.append(f"{name}={value}")
        else:
            rendered.append(f"{name}={float(value):.17g}")
    kind = "NMOS" if model == "NM" else "PMOS"
    return f".model {model} {kind} (" + " ".join(rendered) + ")"


def mos_lines(point: dict[str, float | str], parameterized: bool = False) -> list[str]:
    lines = []
    for device in circuit():
        if parameterized:
            base = BASE_WN[device.group] * (2.0 if device.model == "PM" else 1.0)
            w = f"'{base:.17g}*WS{device.group}'"
        else:
            w = f"{width(device, point):.17g}"
        lines.append(f"{device.name} {device.drain} {device.gate} {device.source} {device.bulk} {device.model} W={w} L=1.8e-7")
    return lines


def logic_vectors() -> list[tuple[int, int, int]]:
    rng = random.Random(717)
    fixed = [(0, 0, 0), (0xFFFF, 1, 0), (0xAAAA, 0x5555, 1), (0xFFFF, 0xFFFF, 1)]
    return fixed


def dc_sources() -> list[str]:
    a, b, cin = 0xA5A5, 0x5A3C, 1
    lines = []
    for prefix, value in (("a", a), ("b", b)):
        for bit in range(BITS):
            if (value >> bit) & 1:
                lines.append(f"E{prefix.upper()}{bit:02d} {prefix}{bit:02d} 0 vdd 0 1")
            else:
                lines.append(f"V{prefix.upper()}{bit:02d} {prefix}{bit:02d} 0 0")
    lines.append("ECIN cin 0 vdd 0 1" if cin else "VCIN cin 0 0")
    return lines


def pwl(value_index: int, bit: int, period_ns: float = TRAN_PERIOD_NS, edge_ns: float = 0.10) -> str:
    vectors = logic_vectors()
    samples = []
    previous = (vectors[0][value_index] >> bit) & 1 if value_index < 2 else vectors[0][2]
    samples.append((0.0, previous * VDD))
    for index, vector in enumerate(vectors[1:], 1):
        current = (vector[value_index] >> bit) & 1 if value_index < 2 else vector[2]
        time_ns = index * period_ns
        samples.extend([(time_ns - edge_ns, previous * VDD), (time_ns, current * VDD)])
        previous = current
    samples.append((len(vectors) * period_ns, previous * VDD))
    return "PWL(" + " ".join(f"{time:.6g}n {voltage:.17g}" for time, voltage in samples) + ")"


def tran_sources() -> list[str]:
    lines = []
    for prefix, index in (("a", 0), ("b", 1)):
        for bit in range(BITS):
            lines.append(f"V{prefix.upper()}{bit:02d} {prefix}{bit:02d}_src 0 {pwl(index, bit)}")
            lines.append(f"RIN_{prefix.upper()}{bit:02d} {prefix}{bit:02d}_src {prefix}{bit:02d} 10")
    lines.append(f"VCIN cin_src 0 {pwl(2, 0)}")
    lines.append("RIN_CIN cin_src cin 10")
    return lines


def common_header(point: dict[str, float | str], analysis: str, parameterized: bool = False) -> list[str]:
    sources = dc_sources() if analysis == "dc" else tran_sources()
    return [
        f"* fair-comparison {point['point_id']} {analysis}",
        ".temp 25", model_line(point, "NM", parameterized), model_line(point, "PM", parameterized),
        "VDD vdd 0 1.8", *sources, *mos_lines(point, parameterized),
        *[f"CLOAD_{node} {node} 0 2e-14" for node in OBSERVED],
    ]


def hspice_options(tight: bool = False) -> str:
    return ".option nomod method=gear reltol={} vntol={} abstol={} gmin=1e-12 itl1=200".format(
        "1e-6", "1e-9", "1e-13")


def analysis_line(analysis: str) -> str:
    return ".dc VDD 0.8 1.8 0.05" if analysis == "dc" else f".tran {TRAN_STEP_NS}n {TRAN_STOP_NS}n 0 {TRAN_STEP_NS}n"


def hspice_deck(point: dict[str, float | str], analysis: str, output: bool, tight: bool = False) -> str:
    lines = [common_header(point, analysis)[0], hspice_options(tight), *common_header(point, analysis)[1:], analysis_line(analysis)]
    if output:
        lines.append(f".print {analysis} " + " ".join(f"v({node})" for node in OBSERVED) + " i(VDD)")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def hspice_params(point: dict[str, float | str]) -> str:
    return ".param " + " ".join(f"{name.upper()}={float(point[name]):.17g}" for name, _lo, _hi in PARAMETERS)


def hspice_alter(points: list[dict[str, float | str]], analysis: str, output: bool) -> str:
    first = points[0]
    header = common_header(first, analysis, parameterized=True)
    lines = [header[0], hspice_options(), hspice_params(first), *header[1:], analysis_line(analysis)]
    if output:
        lines.append(f".print {analysis} " + " ".join(f"v({node})" for node in OBSERVED) + " i(VDD)")
    for point in points[1:]:
        lines.extend([f".alter {point['point_id']}", hspice_params(point)])
    lines.append(".end")
    return "\n".join(lines) + "\n"


def ng_deck(point: dict[str, float | str], analysis: str, output: bool, tight: bool = False) -> str:
    reltol, vntol, abstol = ("1e-6", "1e-9", "1e-13")
    command = "dc vdd 0.8 1.8 0.05" if analysis == "dc" else f"tran {TRAN_STEP_NS}n {TRAN_STOP_NS}n 0 {TRAN_STEP_NS}n"
    lines = [*common_header(point, analysis), ".control", "set noaskquit", "set nopage", "set num_threads=1", "option klu", f"option method=gear reltol={reltol} vntol={vntol} abstol={abstol} gmin=1e-12 itl1=200"]
    if output and analysis == "tran":
        lines.append("option interp")
    lines.append(command)
    if output:
        lines.append("print " + " ".join(f"v({node})" for node in OBSERVED) + " i(VDD)")
    lines.extend(["quit", ".endc", ".end"])
    return "\n".join(lines) + "\n"


def ng_bindings() -> list[str]:
    lines = []
    for name, model, parameter in (("vthn", "NM", "VTH0"), ("vthp", "PM", "VTH0"), ("u0n", "NM", "U0"), ("u0p", "PM", "U0"), ("rdswn", "NM", "RDSW"), ("rdswp", "PM", "RDSW"), ("vsatn", "NM", "VSAT"), ("vsatp", "PM", "VSAT"), ("eta0n", "NM", "ETA0"), ("eta0p", "PM", "ETA0")):
        lines.append(f"batchparambind {name} model {model} {parameter}")
    for device in circuit():
        base = BASE_WN[device.group] * (2.0 if device.model == "PM" else 1.0)
        lines.append(f"batchparambind ws{device.group} instance {device.name} W {base:.17g}")
    return lines


def ng_commands(points: list[dict[str, float | str]], analysis: str, output: bool) -> str:
    command = "dc vdd 0.8 1.8 0.05" if analysis == "dc" else f"tran {TRAN_STEP_NS}n {TRAN_STOP_NS}n 0 {TRAN_STEP_NS}n"
    lines = ng_bindings()
    for point in points:
        for name, _lo, _hi in PARAMETERS:
            lines.append(f"batchparam {name} {float(point[name]):.17g}")
        lines.append(command)
        if output:
            lines.append(f"echo @POINT {point['point_id']}")
            lines.append("print " + " ".join(f"v({node})" for node in OBSERVED) + " i(VDD)")
        lines.append("destroy $curplot")
    return "\n".join(lines) + "\n"


def ng_batch(first: dict[str, float | str], analysis: str, command_path: str, output: bool) -> str:
    lines = [*common_header(first, analysis), ".control", "set noaskquit", "set nopage", "set num_threads=1", "option klu", "option method=gear reltol=1e-6 vntol=1e-9 abstol=1e-13 gmin=1e-12 itl1=200"]
    if output and analysis == "tran":
        lines.append("option interp")
    lines.extend(["batchstats reset", f"batchrun {command_path}", "batchstats json", "quit", ".endc", ".end"])
    return "\n".join(lines) + "\n"


def write_model_audit(root: Path, first: dict[str, float | str]) -> None:
    model_dir = root / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for model in ("NM", "PM"):
        for name, value in model_values(first, model).items():
            rows.append({"model": model, "parameter": name, "value": value})
    with (model_dir / "canonical_model.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("model", "parameter", "value"))
        writer.writeheader(); writer.writerows(rows)
    h_text = "\n".join(model_line(first, model) for model in ("NM", "PM")) + "\n"
    n_text = h_text
    (model_dir / "hspice_bsim4.mod").write_text(h_text, encoding="ascii")
    (model_dir / "ngspice_bsim4.mod").write_text(n_text, encoding="ascii")
    audit = {"parameter_rows": len(rows), "hspice_sha256": hashlib.sha256(h_text.encode()).hexdigest(), "ngspice_sha256": hashlib.sha256(n_text.encode()).hexdigest(), "identical_text": h_text == n_text}
    (model_dir / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=int, default=500)
    parser.add_argument("--seed", type=int, default=717)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve(); points = latin_hypercube(args.seed, args.points); devices = circuit()
    for name, low, high in PARAMETERS:
        if any(not low <= float(point[name]) <= high for point in points):
            raise RuntimeError(f"parameter out of range: {name}")
    params = root / "params"; params.mkdir(parents=True, exist_ok=True)
    fields = ["point_id", *[item[0] for item in PARAMETERS]]
    with (params / "points.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(points)
    design = {"seed": args.seed, "points": args.points, "bits": BITS, "mosfet_count": len(devices), "full_adder_mos": 36, "final_output_buffer_mos": 4, "logic_style": "fully complementary static CMOS", "varying_parameters": len(PARAMETERS), "observed_nodes": OBSERVED, "analyses": ["dc", "tran"], "parameters": [{"name": n, "low": lo, "high": hi} for n, lo, hi in PARAMETERS]}
    (params / "design.json").write_text(json.dumps(design, indent=2) + "\n", encoding="utf-8")
    write_model_audit(root, points[0])
    for analysis in ("dc", "tran"):
        h_tight = root / "netlists" / "tight_reference" / analysis / "hspice_independent"
        n_tight = root / "netlists" / "tight_reference" / analysis / "ngspice_independent"
        h_tight.mkdir(parents=True, exist_ok=True); n_tight.mkdir(parents=True, exist_ok=True)
        for point in points:
            pid = str(point["point_id"])
            (h_tight / f"{pid}.sp").write_text(hspice_deck(point, analysis, True, tight=True), encoding="ascii")
            (n_tight / f"{pid}.cir").write_text(ng_deck(point, analysis, True, tight=True), encoding="ascii")
    for analysis in ("dc", "tran"):
        for output in (False, True):
            layer = "end_to_end" if output else "solver_only"
            h_ind = root / "netlists" / layer / analysis / "hspice_independent"
            n_ind = root / "netlists" / layer / analysis / "ngspice_independent"
            h_alt = root / "netlists" / layer / analysis / "hspice_alter"
            n_batch = root / "netlists" / layer / analysis / "ngspice_reuse"
            for directory in (h_ind, n_ind, h_alt, n_batch): directory.mkdir(parents=True, exist_ok=True)
            for point in points:
                pid = str(point["point_id"])
                (h_ind / f"{pid}.sp").write_text(hspice_deck(point, analysis, output), encoding="ascii")
                (n_ind / f"{pid}.cir").write_text(ng_deck(point, analysis, output), encoding="ascii")
            for size in SIZES:
                subset = points[: min(size, len(points))]
                (h_alt / f"alter_{size}.sp").write_text(hspice_alter(subset, analysis, output), encoding="ascii")
                rel = f"netlists/{layer}/{analysis}/ngspice_reuse/commands_{size}.txt"
                (n_batch / f"commands_{size}.txt").write_text(ng_commands(subset, analysis, output), encoding="ascii")
                (n_batch / f"batch_{size}.cir").write_text(ng_batch(subset[0], analysis, rel, output), encoding="ascii")
    print(json.dumps({"points": len(points), "mosfet_count": len(devices), "model_parameters_per_polarity": len(model_values(points[0], "NM"))}, sort_keys=True))


if __name__ == "__main__":
    main()
