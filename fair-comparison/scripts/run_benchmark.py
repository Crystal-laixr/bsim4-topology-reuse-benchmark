#!/usr/bin/env python3
"""Run one fair-comparison benchmark cell and emit machine-readable timing."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path


METHODS = (
    "hspice_independent", "hspice_alter", "ngspice_official_independent",
    "ngspice_optimized_independent", "ngspice_optimized_reuse",
)
OBSERVED = ("sum00", "sum05", "sum10", "sum15", "c04", "c08", "c12", "cout")


def spice_float(token: str) -> float:
    suffixes = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}
    match = re.fullmatch(r"([+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+\-]?\d+)?)([A-Za-z]+)?", token.strip())
    if not match:
        raise ValueError(token)
    value = float(match.group(1)); suffix = (match.group(2) or "").lower()
    return value * suffixes.get(suffix, 1.0)


def parse_hspice_tables(path: Path) -> list[dict[str, list[list[float]]]]:
    runs: list[dict[str, list[list[float]]]] = []
    current: dict[str, list[list[float]]] | None = None
    headers: list[str] | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        lowered = line.lower()
        if "****** dc transfer curves" in lowered or "****** transient analysis" in lowered:
            current = {}; runs.append(current); headers = None; continue
        names = [name for name in OBSERVED if re.search(rf"\b{name}\b", lowered)]
        if current is not None and names:
            headers = names
            for name in names: current.setdefault(name, [])
            continue
        if current is None or not headers:
            continue
        stripped = line.strip()
        if stripped == "y": headers = None; continue
        tokens = stripped.split()
        if len(tokens) == len(headers) + 1:
            try:
                axis = spice_float(tokens[0]); values = [spice_float(token) for token in tokens[1:]]
            except ValueError:
                continue
            for name, value in zip(headers, values): current[name].append([axis, value])
    return [run for run in runs if all(name in run for name in OBSERVED)]


def parse_ngspice_tables(path: Path) -> list[dict[str, list[list[float]]]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    chunks = re.split(r"(?=@POINT p\d{6})", text)
    if len(chunks) == 1: chunks = [text]
    runs = []
    for chunk in chunks:
        current: dict[str, list[list[float]]] = {}; headers: list[str] = []
        for line in chunk.splitlines():
            if line.startswith("Index"):
                headers = [match.group(1).lower() for match in re.finditer(r"v\(([^)]+)\)", line, re.I) if match.group(1).lower() in OBSERVED]
                for name in headers: current.setdefault(name, [])
                continue
            if not headers or not re.match(r"^\d+\s+", line): continue
            tokens = line.split()
            if len(tokens) >= len(headers) + 2:
                try:
                    axis = float(tokens[1]); values = [float(token) for token in tokens[2:2 + len(headers)]]
                except ValueError:
                    continue
                for name, value in zip(headers, values): current[name].append([axis, value])
        if all(name in current for name in OBSERVED): runs.append(current)
    return runs


def elapsed(value: str) -> float:
    fields = value.split(":")
    if len(fields) == 3:
        return float(fields[0]) * 3600 + float(fields[1]) * 60 + float(fields[2])
    if len(fields) == 2:
        return float(fields[0]) * 60 + float(fields[1])
    return float(fields[0])


def parse_time(path: Path) -> dict[str, float | int]:
    result: dict[str, float | int] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.rsplit(":", 1)
        try:
            if key.startswith("Elapsed (wall clock)"):
                result["wall_s"] = elapsed(value.strip())
            elif key.strip() == "User time (seconds)":
                result["user_s"] = float(value)
            elif key.strip() == "System time (seconds)":
                result["system_s"] = float(value)
            elif key.strip() == "Maximum resident set size (kbytes)":
                result["max_rss_kb"] = int(value)
            elif key.strip() == "Exit status":
                result["exit_status"] = int(value)
        except ValueError:
            pass
    return result


def run_process(command: list[str], root: Path, work: Path, name: str, env: dict[str, str]) -> tuple[int, dict[str, float | int], Path]:
    stdout = work / f"{name}.stdout"
    timing = work / f"{name}.time"
    full = ["/usr/bin/time", "-v", "-o", str(timing), *command]
    with stdout.open("w", encoding="utf-8") as handle:
        process = subprocess.run(full, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT, check=False)
    stats = parse_time(timing); stats["returncode"] = process.returncode
    return process.returncode, stats, stdout


def output_shape(paths: list[Path]) -> dict[str, int]:
    byte_count = 0; numeric_rows = 0; numeric_values = 0
    number = re.compile(r"^[\s\d.+\-Ee]+$")
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        byte_count += len(text.encode("utf-8"))
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and number.fullmatch(stripped):
                tokens = stripped.split()
                if len(tokens) >= 2:
                    numeric_rows += 1; numeric_values += len(tokens)
    return {"raw_text_bytes": byte_count, "numeric_rows": numeric_rows, "numeric_values": numeric_values}


def batch_profile(path: Path) -> dict[str, object]:
    profile: dict[str, object] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith('{"setup_calls"'):
            profile = json.loads(line)
    return profile


def archive(work: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz", compresslevel=6) as handle:
        for path in sorted(work.rglob("*")):
            if not path.is_file():
                continue
            lowered = path.name.lower()
            if path.suffix.lower() in (".lis", ".st0") or any(word in lowered for word in ("license", "lmgrd", "synopsys")):
                continue
            handle.add(path, arcname=path.relative_to(work))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--analysis", choices=("dc", "tran", "startup"), required=True)
    parser.add_argument("--layer", choices=("solver_only", "end_to_end", "tight_reference"), default="solver_only")
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--rep", type=int, required=True)
    parser.add_argument("--tag", default="matrix")
    parser.add_argument("--cpu", type=int, default=0)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--hspice", default=os.environ.get("HSPICE_BIN", "/home/LaiXinran/.local/eda/hspice/bin/hspice"))
    parser.add_argument("--ngspice-official", default=os.environ.get("NGSPICE_OFFICIAL_BIN", "/home/LaiXinran/ngspice_official_fair/build/src/ngspice"))
    parser.add_argument("--ngspice-optimized", default=os.environ.get("NGSPICE_OPTIMIZED_BIN", "/home/LaiXinran/ngspice_for_sizing/build/src/ngspice"))
    args = parser.parse_args()
    root = args.root.resolve(); env = dict(os.environ)
    env.update({"LC_ALL": "C", "LANG": "C", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"})
    output_dir = root / "data" / "raw" / args.tag; output_dir.mkdir(parents=True, exist_ok=True)
    work_parent = root / "data" / "work"; work_parent.mkdir(parents=True, exist_ok=True)
    log_dir = root / "data" / "raw" / "logs"; log_dir.mkdir(parents=True, exist_ok=True)
    binaries = {
        "hspice_independent": args.hspice, "hspice_alter": args.hspice,
        "ngspice_official_independent": args.ngspice_official,
        "ngspice_optimized_independent": args.ngspice_optimized,
        "ngspice_optimized_reuse": args.ngspice_optimized,
    }
    binary = binaries[args.method]
    with tempfile.TemporaryDirectory(prefix=f"{args.method}_{args.analysis}_", dir=work_parent) as temporary:
        work = Path(temporary); stats_list = []; output_paths: list[Path] = []
        started = time.perf_counter()
        if args.analysis == "startup":
            deck = work / ("startup.sp" if args.method.startswith("hspice") else "startup.cir")
            deck.write_text("* startup benchmark\nV1 in 0 1\nR1 in 0 1k\n.op\n.end\n", encoding="ascii")
            if args.method.startswith("hspice"):
                command = ["taskset", "-c", str(args.cpu), binary, "-mt", "1", "-i", str(deck), "-o", str(work / "startup")]
            else:
                command = ["taskset", "-c", str(args.cpu), binary, "-b", str(deck)]
            code, stats, stdout = run_process(command, root, work, "startup_process", env)
            stats_list.append(stats); output_paths.append(stdout)
            if code != 0: raise RuntimeError(f"startup failed: {stdout}")
        elif args.method in ("hspice_independent", "ngspice_official_independent", "ngspice_optimized_independent"):
            family = "hspice_independent" if args.method == "hspice_independent" else "ngspice_independent"
            suffix = ".sp" if family.startswith("hspice") else ".cir"
            for index in range(args.size):
                deck = root / "netlists" / args.layer / args.analysis / family / f"p{index:06d}{suffix}"
                if args.method.startswith("hspice"):
                    prefix = work / f"p{index:06d}"
                    command = ["taskset", "-c", str(args.cpu), binary, "-mt", "1", "-i", str(deck), "-o", str(prefix)]
                else:
                    command = ["taskset", "-c", str(args.cpu), binary, "-b", str(deck)]
                code, stats, stdout = run_process(command, root, work, f"p{index:06d}_process", env)
                stats_list.append(stats); output_paths.append(stdout)
                if args.method.startswith("hspice"):
                    output_paths.append(work / f"p{index:06d}.lis")
                if code != 0: raise RuntimeError(f"{args.method} failed at point {index}: {stdout}")
        elif args.method == "hspice_alter":
            deck = root / "netlists" / args.layer / args.analysis / "hspice_alter" / f"alter_{args.size}.sp"
            prefix = work / f"alter_{args.size}"
            command = ["taskset", "-c", str(args.cpu), binary, "-mt", "1", "-i", str(deck), "-o", str(prefix)]
            code, stats, stdout = run_process(command, root, work, "alter_process", env)
            stats_list.append(stats); output_paths.extend([stdout, prefix.with_suffix(".lis")])
            if code != 0: raise RuntimeError(f"hspice alter failed: {stdout}")
        else:
            deck = root / "netlists" / args.layer / args.analysis / "ngspice_reuse" / f"batch_{args.size}.cir"
            command = ["taskset", "-c", str(args.cpu), binary, "-b", str(deck)]
            code, stats, stdout = run_process(command, root, work, "batch_process", env)
            stats_list.append(stats); output_paths.append(stdout)
            if code != 0: raise RuntimeError(f"ngspice reuse failed: {stdout}")
        observed = time.perf_counter() - started
        fatal_text = ("timestep too small", "simulation(s) aborted", "fatal error")
        for path in output_paths:
            if path.exists():
                lowered = path.read_text(encoding="utf-8", errors="replace").lower()
                hit = next((marker for marker in fatal_text if marker in lowered), None)
                if hit:
                    raise RuntimeError(f"simulator reported '{hit}' in {path}")
        canonical: list[dict[str, list[list[float]]]] = []
        if args.layer in ("end_to_end", "tight_reference") and args.analysis != "startup":
            if args.method.startswith("hspice"):
                lis_paths = [path for path in output_paths if path.suffix == ".lis"]
                for path in lis_paths: canonical.extend(parse_hspice_tables(path))
            else:
                for path in output_paths: canonical.extend(parse_ngspice_tables(path))
            expected_samples = 21 if args.analysis == "dc" else 81
            if len(canonical) != args.size:
                raise RuntimeError(f"parsed {len(canonical)}/{args.size} canonical point outputs")
            for point in canonical:
                if any(len(point[name]) != expected_samples for name in OBSERVED):
                    raise RuntimeError(f"unexpected canonical sample count: {[(name, len(point[name])) for name in OBSERVED]}")
            canonical_path = work / "canonical_outputs.json"
            canonical_path.write_text(json.dumps(canonical, separators=(",", ":")) + "\n", encoding="utf-8")
        profile = batch_profile(output_paths[0]) if args.method == "ngspice_optimized_reuse" and args.analysis != "startup" else {}
        if args.method == "ngspice_optimized_reuse" and args.analysis != "startup":
            if int(profile.get("setup_calls", 0)) != args.size:
                raise RuntimeError(f"batchrun did not execute all points: {profile}")
            if args.layer in ("end_to_end", "tight_reference"):
                markers = output_paths[0].read_text(encoding="utf-8", errors="replace").count("@POINT p")
                if markers != args.size:
                    raise RuntimeError(f"batchrun emitted {markers}/{args.size} point markers")
        payload = {
            "schema_version": 2, "method": args.method, "analysis": args.analysis, "layer": args.layer,
            "size": args.size, "rep": args.rep, "tag": args.tag, "cpu": args.cpu,
            "observed_wall_s": observed,
            "simulation_wall_s": sum(float(item.get("wall_s", 0.0)) for item in stats_list),
            "user_s": sum(float(item.get("user_s", 0.0)) for item in stats_list),
            "system_s": sum(float(item.get("system_s", 0.0)) for item in stats_list),
            "max_rss_kb": max(int(item.get("max_rss_kb", 0)) for item in stats_list),
            "output_shape": output_shape(output_paths), "canonical_points": len(canonical),
            "canonical_samples_per_signal": (21 if args.analysis == "dc" else 81) if canonical else 0,
            "child_stats": stats_list, "batch_profile": profile,
        }
        archive_path = log_dir / f"{args.tag}_{args.layer}_{args.analysis}_{args.method}_n{args.size}_r{args.rep}.tar.gz"
        archive(work, archive_path); payload["logs_archive"] = str(archive_path.relative_to(root))
    output = output_dir / f"{args.layer}_{args.analysis}_{args.method}_n{args.size}_r{args.rep}.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "wall_s": observed, "shape": payload["output_shape"]}, sort_keys=True))


if __name__ == "__main__":
    main()
