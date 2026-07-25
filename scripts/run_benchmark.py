#!/usr/bin/env python3
"""Execute one benchmark method/size/repetition and emit normalized JSON."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path


METHODS = ("hspice_independent", "hspice_alter", "ngspice_independent", "ngspice_reuse")
SELECTED_LANES = (1, 7, 13, 19, 25)


def elapsed_seconds(value: str) -> float:
    fields = value.strip().split(":")
    if len(fields) == 3:
        return float(fields[0]) * 3600.0 + float(fields[1]) * 60.0 + float(fields[2])
    if len(fields) == 2:
        return float(fields[0]) * 60.0 + float(fields[1])
    return float(fields[0])


def parse_time_file(path: Path) -> dict[str, float | int]:
    result: dict[str, float | int] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.rsplit(":", 1)
        key = key.strip()
        value = value.strip()
        try:
            if key.startswith("Elapsed (wall clock)"):
                result["wall_s"] = elapsed_seconds(value)
            elif key == "User time (seconds)":
                result["user_s"] = float(value)
            elif key == "System time (seconds)":
                result["system_s"] = float(value)
            elif key == "Maximum resident set size (kbytes)":
                result["max_rss_kb"] = int(value)
            elif key == "Exit status":
                result["exit_status"] = int(value)
        except ValueError:
            continue
    return result


def run_timed(command: list[str], cwd: Path, prefix: Path, env: dict[str, str]) -> tuple[int, dict[str, float | int]]:
    stdout_path = prefix.with_suffix(".stdout")
    time_path = prefix.with_suffix(".time")
    full_command = ["/usr/bin/time", "-v", "-o", str(time_path), *command]
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = subprocess.run(
            full_command,
            cwd=str(cwd),
            env=env,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            check=False,
        )
    stats = parse_time_file(time_path)
    stats["returncode"] = process.returncode
    return process.returncode, stats


def numeric_suffix(path: Path) -> int:
    match = re.search(r"(\d+)$", path.suffix)
    return int(match.group(1)) if match else -1


def parse_hspice_measure(path: Path) -> dict[str, float]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    title_index = next((index for index, line in enumerate(lines) if line.startswith(".TITLE")), None)
    if title_index is not None:
        headers: list[str] = []
        values: list[str] = []
        reading_values = False
        for line in lines[title_index + 1 :]:
            tokens = line.split()
            if not tokens:
                continue
            if not reading_values:
                try:
                    float(tokens[0])
                    reading_values = True
                except ValueError:
                    headers.extend(token.lower() for token in tokens)
                    continue
            values.extend(tokens)
            if headers and len(values) >= len(headers):
                parsed: dict[str, float] = {}
                for key, value in zip(headers, values):
                    try:
                        parsed[key] = float(value)
                    except ValueError:
                        parsed[key] = math.nan
                return parsed
    raise RuntimeError(f"unable to parse HSPICE measurement file {path}")


def normalize_hspice(point_id: str, measured: dict[str, float]) -> dict[str, object]:
    lanes: dict[str, dict[str, float]] = {}
    power = measured.get("peak_pwr", math.nan)
    for lane in SELECTED_LANES:
        lanes[f"l{lane:02d}"] = {
            "low_v": measured.get(f"l{lane:02d}_lo", math.nan),
            "high_v": measured.get(f"l{lane:02d}_hi", math.nan),
            "threshold_v": measured.get(f"l{lane:02d}_th", math.nan),
            "power_w": power,
        }
    return {"point_id": point_id, "lanes": lanes}


def parse_ngspice_output(path: Path) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    points: dict[str, dict[str, object]] = {}
    profile: dict[str, object] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("@batchlogic\t"):
            fields = line.split("\t")
            if len(fields) < 6:
                continue
            marker = fields[1]
            match = re.fullmatch(r"(p\d{6})_(l\d{2})(t?)", marker)
            if not match:
                continue
            point_id, lane, threshold_only = match.groups()
            try:
                values = [float(value) for value in fields[2:6]]
            except ValueError:
                values = [math.nan] * 4
            point = points.setdefault(point_id, {"point_id": point_id, "lanes": {}})
            if threshold_only:
                lane_metrics = point["lanes"].setdefault(lane, {})
                lane_metrics["threshold_v"] = values[3]
            else:
                lane_metrics = point["lanes"].setdefault(lane, {})
                lane_metrics.update({"low_v": values[0], "high_v": values[1], "power_w": values[2]})
        elif line.startswith('{"setup_calls"'):
            try:
                profile = json.loads(line)
            except json.JSONDecodeError:
                pass
    return points, profile


def archive_work(work_dir: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz", compresslevel=6) as handle:
        for path in sorted(work_dir.rglob("*")):
            if path.is_file():
                lowered = path.name.lower()
                if path.suffix in (".st0", ".lis") or "license" in lowered or "synopsys.dat" in lowered or "lmgrd" in lowered:
                    continue
                handle.add(path, arcname=path.relative_to(work_dir))


def run_hspice_independent(args: argparse.Namespace, root: Path, work: Path, env: dict[str, str]) -> dict[str, object]:
    results = []
    child_stats = []
    start = time.perf_counter()
    for index in range(args.size):
        point_id = f"p{index:06d}"
        deck = root / "netlists" / "hspice" / "independent" / f"{point_id}.sp"
        prefix = work / point_id
        command = ["taskset", "-c", str(args.cpu), args.hspice, "-mt", "1", "-i", str(deck), "-o", str(prefix)]
        returncode, stats = run_timed(command, root, prefix.with_name(prefix.name + "_process"), env)
        child_stats.append(stats)
        measure = prefix.with_suffix(".ms0")
        if returncode != 0 or not measure.exists():
            raise RuntimeError(f"HSPICE independent failed at {point_id}; see {prefix}.lis")
        results.append(normalize_hspice(point_id, parse_hspice_measure(measure)))
    observed = time.perf_counter() - start
    return {
        "observed_wall_s": observed,
        "simulation_wall_s": sum(float(item.get("wall_s", 0.0)) for item in child_stats),
        "max_rss_kb": max(int(item.get("max_rss_kb", 0)) for item in child_stats),
        "child_stats": child_stats,
        "points": results,
        "batch_profile": {},
    }


def run_hspice_alter(args: argparse.Namespace, root: Path, work: Path, env: dict[str, str]) -> dict[str, object]:
    deck = root / "netlists" / "hspice" / "alter" / f"alter_{args.size}.sp"
    prefix = work / f"alter_{args.size}"
    command = ["taskset", "-c", str(args.cpu), args.hspice, "-mt", "1", "-i", str(deck), "-o", str(prefix)]
    start = time.perf_counter()
    returncode, stats = run_timed(command, root, work / "alter_process", env)
    observed = time.perf_counter() - start
    measures = sorted(work.glob(f"alter_{args.size}.ms*"), key=numeric_suffix)
    if returncode != 0 or len(measures) != args.size:
        raise RuntimeError(f"HSPICE alter returned {returncode} and {len(measures)}/{args.size} measurement files")
    results = [normalize_hspice(f"p{index:06d}", parse_hspice_measure(path)) for index, path in enumerate(measures)]
    return {
        "observed_wall_s": observed,
        "simulation_wall_s": float(stats.get("wall_s", observed)),
        "max_rss_kb": int(stats.get("max_rss_kb", 0)),
        "child_stats": [stats],
        "points": results,
        "batch_profile": {},
    }


def run_ngspice_independent(args: argparse.Namespace, root: Path, work: Path, env: dict[str, str]) -> dict[str, object]:
    results = []
    child_stats = []
    start = time.perf_counter()
    for index in range(args.size):
        point_id = f"p{index:06d}"
        deck = root / "netlists" / "ngspice" / "independent" / f"{point_id}.cir"
        prefix = work / point_id
        command = ["taskset", "-c", str(args.cpu), args.ngspice, "-b", str(deck)]
        returncode, stats = run_timed(command, root, prefix, env)
        child_stats.append(stats)
        stdout_path = prefix.with_suffix(".stdout")
        parsed, _profile = parse_ngspice_output(stdout_path)
        if returncode != 0 or point_id not in parsed:
            raise RuntimeError(f"NGSPICE independent failed at {point_id}; see {stdout_path}")
        results.append(parsed[point_id])
    observed = time.perf_counter() - start
    return {
        "observed_wall_s": observed,
        "simulation_wall_s": sum(float(item.get("wall_s", 0.0)) for item in child_stats),
        "max_rss_kb": max(int(item.get("max_rss_kb", 0)) for item in child_stats),
        "child_stats": child_stats,
        "points": results,
        "batch_profile": {},
    }


def run_ngspice_reuse(args: argparse.Namespace, root: Path, work: Path, env: dict[str, str]) -> dict[str, object]:
    deck = root / "netlists" / "ngspice" / "batch" / f"batch_{args.size}.cir"
    prefix = work / f"batch_{args.size}"
    command = ["taskset", "-c", str(args.cpu), args.ngspice, "-b", str(deck)]
    start = time.perf_counter()
    returncode, stats = run_timed(command, root, prefix, env)
    observed = time.perf_counter() - start
    stdout_path = prefix.with_suffix(".stdout")
    parsed, profile = parse_ngspice_output(stdout_path)
    if returncode != 0 or len(parsed) != args.size:
        raise RuntimeError(f"NGSPICE reuse returned {returncode} and {len(parsed)}/{args.size} points; see {stdout_path}")
    return {
        "observed_wall_s": observed,
        "simulation_wall_s": float(stats.get("wall_s", observed)),
        "max_rss_kb": int(stats.get("max_rss_kb", 0)),
        "child_stats": [stats],
        "points": [parsed[f"p{index:06d}"] for index in range(args.size)],
        "batch_profile": profile,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--rep", type=int, required=True)
    parser.add_argument("--tag", default="matrix")
    parser.add_argument("--cpu", type=int, default=0)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ngspice", default=os.environ.get("NGSPICE_BIN", "/home/LaiXinran/ngspice_for_sizing/build/src/ngspice"))
    parser.add_argument("--hspice", default=os.environ.get("HSPICE_BIN", "/home/LaiXinran/.local/eda/hspice/bin/hspice"))
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = root / "data" / "raw" / args.tag
    log_dir = root / "data" / "raw" / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    work_parent = root / "data" / "work"
    work_parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.update({"LC_ALL": "C", "LANG": "C", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"})
    runner = {
        "hspice_independent": run_hspice_independent,
        "hspice_alter": run_hspice_alter,
        "ngspice_independent": run_ngspice_independent,
        "ngspice_reuse": run_ngspice_reuse,
    }[args.method]

    with tempfile.TemporaryDirectory(prefix=f"{args.method}_n{args.size}_r{args.rep}_", dir=work_parent) as temporary:
        work = Path(temporary)
        started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        payload = runner(args, root, work, env)
        payload.update(
            {
                "schema_version": 1,
                "method": args.method,
                "size": args.size,
                "rep": args.rep,
                "tag": args.tag,
                "cpu": args.cpu,
                "started_at": started_at,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
        )
        archive = log_dir / f"{args.tag}_{args.method}_n{args.size}_r{args.rep}.tar.gz"
        archive_work(work, archive)
        payload["logs_archive"] = str(archive.relative_to(root))

    output = output_dir / f"{args.method}_n{args.size}_r{args.rep}.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "method": args.method, "size": args.size, "rep": args.rep, "wall_s": payload["observed_wall_s"], "points": len(payload["points"])}, sort_keys=True))


if __name__ == "__main__":
    main()
