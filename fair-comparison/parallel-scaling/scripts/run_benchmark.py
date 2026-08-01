#!/usr/bin/env python3
"""Run one parallel-scaling cell with deterministic shards and CPU affinity."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAIR = ROOT.parent
sys.path.insert(0, str(FAIR / "scripts"))
import generate_inputs as circuit  # noqa: E402

METHODS = ("hspice_independent", "hspice_alter", "ngspice_official_independent", "ngspice_optimized_independent", "ngspice_optimized_reuse")
OBSERVED = circuit.OBSERVED
VECTOR_LOCK = threading.Lock()
BASE_LOGIC_VECTORS = circuit.logic_vectors


def read_points(path: Path) -> list[dict[str, float | str]]:
    with path.open(encoding="utf-8") as handle:
        return [{key: (value if key == "point_id" else float(value)) for key, value in row.items()} for row in csv.DictReader(handle)]


def split(points: list[dict[str, float | str]], workers: int) -> list[list[dict[str, float | str]]]:
    return [points[index::workers] for index in range(workers)]


def dc_line(count: int) -> str:
    if count < 2: raise ValueError("DC points must be at least two")
    step = (1.8 - 0.8) / (count - 1)
    return f".dc VDD 0.8 1.8 {step:.17g}", f"dc vdd 0.8 1.8 {step:.17g}"


def vectors(count: int) -> list[tuple[int, int, int]]:
    base = BASE_LOGIC_VECTORS()
    if count <= len(base): return base[:count]
    result = list(base)
    state = 717
    while len(result) < count:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        a = state & 0xFFFF; state = (1103515245 * state + 12345) & 0x7FFFFFFF
        b = state & 0xFFFF; result.append((a, b, state & 1))
    return result


def patched_deck(point: dict[str, float | str], analysis: str, output: bool, complexity: int, simulator: str) -> str:
    if analysis == "dc":
        text = circuit.hspice_deck(point, analysis, output) if simulator == "hspice" else circuit.ng_deck(point, analysis, output)
        h_line, n_line = dc_line(complexity)
        return text.replace(circuit.analysis_line("dc"), h_line if simulator == "hspice" else n_line)
    original = circuit.logic_vectors
    with VECTOR_LOCK:
        try:
            circuit.logic_vectors = lambda: vectors(complexity)
            return circuit.hspice_deck(point, analysis, output) if simulator == "hspice" else circuit.ng_deck(point, analysis, output)
        finally:
            circuit.logic_vectors = original


def altered(points: list[dict[str, float | str]], analysis: str, output: bool, complexity: int) -> str:
    if analysis == "dc":
        h_line, _ = dc_line(complexity)
        return circuit.hspice_alter(points, analysis, output).replace(circuit.analysis_line("dc"), h_line)
    original = circuit.logic_vectors
    with VECTOR_LOCK:
        try:
            circuit.logic_vectors = lambda: vectors(complexity)
            return circuit.hspice_alter(points, analysis, output)
        finally:
            circuit.logic_vectors = original


def commands(points: list[dict[str, float | str]], analysis: str, output: bool, complexity: int) -> tuple[str, str]:
    if analysis == "dc":
        _, n_line = dc_line(complexity)
        commands_text = circuit.ng_commands(points, analysis, output).replace("dc vdd 0.8 1.8 0.05", n_line)
        batch = circuit.ng_batch(points[0], analysis, "COMMANDS", output).replace("dc vdd 0.8 1.8 0.05", n_line)
        return commands_text, batch
    original = circuit.logic_vectors
    with VECTOR_LOCK:
        try:
            circuit.logic_vectors = lambda: vectors(complexity)
            return circuit.ng_commands(points, analysis, output), circuit.ng_batch(points[0], analysis, "COMMANDS", output)
        finally:
            circuit.logic_vectors = original


def parse_time(path: Path) -> dict[str, float | int]:
    values: dict[str, float | int] = {}
    if not path.exists(): return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line: continue
        key, value = line.rsplit(":", 1); value = value.strip()
        try:
            if key.startswith("Elapsed (wall clock)"):
                fields = value.split(":"); values["wall_s"] = float(fields[-1]) + (60 * float(fields[-2]) if len(fields) > 1 else 0) + (3600 * float(fields[-3]) if len(fields) > 2 else 0)
            elif key.strip() == "User time (seconds)": values["user_s"] = float(value)
            elif key.strip() == "System time (seconds)": values["system_s"] = float(value)
            elif key.strip() == "Maximum resident set size (kbytes)": values["max_rss_kb"] = int(value)
        except ValueError: pass
    return values


def execute(command: list[str], work: Path, label: str, env: dict[str, str]) -> tuple[int, dict[str, float | int], Path]:
    stdout, timing = work / f"{label}.stdout", work / f"{label}.time"
    with stdout.open("w", encoding="utf-8") as handle:
        code = subprocess.run(["/usr/bin/time", "-v", "-o", str(timing), *command], stdout=handle, stderr=subprocess.STDOUT, env=env, check=False).returncode
    return code, parse_time(timing), stdout


def worker_task(index: int, points: list[dict[str, float | str]], args: argparse.Namespace, work_parent: Path) -> dict[str, object]:
    work = Path(tempfile.mkdtemp(prefix=f"w{index:03d}_", dir=work_parent))
    env = dict(os.environ); env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "LC_ALL": "C", "LANG": "C"})
    cpu = str(index)
    binary = {"hspice_independent": args.hspice, "hspice_alter": args.hspice, "ngspice_official_independent": args.ngspice_official, "ngspice_optimized_independent": args.ngspice_optimized, "ngspice_optimized_reuse": args.ngspice_optimized}[args.method]
    output = args.layer == "end_to_end"; outputs: list[Path] = []; stats: list[dict[str, float | int]] = []; codes: list[int] = []
    if args.method.endswith("independent"):
        simulator = "hspice" if args.method.startswith("hspice") else "ngspice"
        for point in points:
            suffix = ".sp" if simulator == "hspice" else ".cir"; deck = work / f"{point['point_id']}{suffix}"
            deck.write_text(patched_deck(point, args.analysis, output, args.complexity, simulator), encoding="ascii")
            if simulator == "hspice": command = ["taskset", "-c", cpu, binary, "-mt", "1", "-i", str(deck), "-o", str(work / str(point["point_id"]))]
            else: command = ["taskset", "-c", cpu, binary, "-b", str(deck)]
            code, stat, stdout = execute(command, work, f"{point['point_id']}_process", env); codes.append(code); stats.append(stat); outputs.append(stdout)
            listing = work / f"{point['point_id']}.lis"
            if code and listing.exists(): outputs.append(listing)
            deck.unlink(missing_ok=True)
            if not code: listing.unlink(missing_ok=True)
            if code: break
    elif args.method == "hspice_alter":
        deck = work / "alter.sp"; deck.write_text(altered(points, args.analysis, output, args.complexity), encoding="ascii")
        code, stat, stdout = execute(["taskset", "-c", cpu, binary, "-mt", "1", "-i", str(deck), "-o", str(work / "alter")], work, "alter_process", env)
        codes.append(code); stats.append(stat); outputs.extend([stdout, work / "alter.lis"])
    else:
        command_file = work / "commands.txt"; commands_text, batch = commands(points, args.analysis, output, args.complexity)
        command_file.write_text(commands_text, encoding="ascii")
        relative_commands = command_file.relative_to(ROOT)
        deck = work / "batch.cir"; deck.write_text(batch.replace("COMMANDS", str(relative_commands)), encoding="ascii")
        code, stat, stdout = execute(["taskset", "-c", cpu, binary, "-b", str(deck)], work, "batch_process", env)
        profile = stdout.read_text(encoding="utf-8", errors="replace") if stdout.exists() else ""
        setup = re.search(r'"setup_calls"\s*:\s*(\d+)', profile)
        reused = re.search(r'"setup_reuse"\s*:\s*(\d+)', profile)
        if code == 0 and (setup is None or reused is None or int(setup.group(1)) != len(points) or int(reused.group(1)) < len(points) - 1):
            code = 97
        codes.append(code); stats.append(stat); outputs.append(stdout)
    archive_dir = ROOT / "data" / "raw" / "logs"; archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f"{args.tag}_{args.scaling}_{args.analysis}_{args.layer}_{args.method}_w{args.workers}_c{args.complexity}_r{args.rep}_shard{index:03d}.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for path in outputs:
            if path.exists(): handle.add(path, arcname=path.name)
    result = {"worker": index, "cpu": index, "points": [str(point["point_id"]) for point in points], "returncodes": codes, "stats": stats, "archive": str(archive.relative_to(ROOT)), "ok": all(code == 0 for code in codes)}
    shutil.rmtree(work, ignore_errors=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scaling", choices=("strong", "weak"), required=True); parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--total-points", type=int, default=1000)
    parser.add_argument("--method", choices=METHODS, required=True); parser.add_argument("--analysis", choices=("dc", "tran"), required=True)
    parser.add_argument("--layer", choices=("solver_only", "end_to_end"), required=True); parser.add_argument("--complexity", type=int, required=True)
    parser.add_argument("--rep", type=int, required=True); parser.add_argument("--tag", required=True); parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--hspice", default=os.environ.get("HSPICE_BIN", "/home/LaiXinran/.local/eda/hspice/bin/hspice")); parser.add_argument("--ngspice-official", default=os.environ.get("NGSPICE_OFFICIAL_BIN", "/home/LaiXinran/ngspice_official_fair/build/src/ngspice")); parser.add_argument("--ngspice-optimized", default=os.environ.get("NGSPICE_OPTIMIZED_BIN", "/home/LaiXinran/ngspice_for_sizing/build/src/ngspice")); parser.add_argument("--hspice-concurrency-cap", type=int, default=int(os.environ.get("HSPICE_CONCURRENCY_CAP", "128")))
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 256: raise ValueError("workers must be in 1..256")
    output = ROOT / "data" / "raw" / args.tag; output.mkdir(parents=True, exist_ok=True)
    expected = output / f"{args.scaling}_{args.analysis}_{args.layer}_{args.method}_n{args.total_points}_w{args.workers}_c{args.complexity}_r{args.rep}.json"
    if args.skip_existing and expected.exists():
        print(expected); return
    manifest = json.loads((ROOT / "params" / "manifest.json").read_text(encoding="utf-8"))
    if args.scaling == "strong": points = read_points(ROOT / "params" / "strong_points_1000.csv")[:args.total_points]
    else:
        if args.total_points != args.workers * 1000: raise ValueError("weak scaling requires 1000 points per worker")
        points = []
        for seed in manifest["weak_worker_block_seeds"][str(args.workers)]: points.extend(circuit.latin_hypercube(int(seed), 1000))
        for block, point in enumerate(points): point["point_id"] = f"w{block // 1000:03d}_{block % 1000:04d}"
    active_workers = min(args.workers, len(points))
    shards = split(points, active_workers)
    work_parent = ROOT / "data" / "work"; work_parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    scheduled_concurrency = min(active_workers, args.hspice_concurrency_cap) if args.method.startswith("hspice") else active_workers
    with ThreadPoolExecutor(max_workers=scheduled_concurrency) as pool:
        futures = [pool.submit(worker_task, index, shard, args, work_parent) for index, shard in enumerate(shards)]
        worker_rows = [future.result() for future in as_completed(futures)]
    wall = time.perf_counter() - started
    total_cpu = sum(float(stat.get("user_s", 0)) + float(stat.get("system_s", 0)) for row in worker_rows for stat in row["stats"])
    payload = {"scaling": args.scaling, "workers": args.workers, "effective_workers": active_workers, "scheduled_concurrency": scheduled_concurrency, "hspice_license_concurrency_cap": args.hspice_concurrency_cap if args.method.startswith("hspice") else None, "method": args.method, "analysis": args.analysis, "layer": args.layer, "complexity": args.complexity, "rep": args.rep, "total_points": len(points), "observed_wall_s": wall, "total_cpu_s": total_cpu, "aggregate_max_rss_kb": sum(max([int(stat.get("max_rss_kb", 0)) for stat in row["stats"]], default=0) for row in worker_rows), "workers_started": len(worker_rows), "workers_ok": sum(bool(row["ok"]) for row in worker_rows), "worker_rows": sorted(worker_rows, key=lambda row: int(row["worker"]))}
    path = output / f"{args.scaling}_{args.analysis}_{args.layer}_{args.method}_n{len(points)}_w{args.workers}_c{args.complexity}_r{args.rep}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__": main()
