#!/usr/bin/env python3
"""Extract HSPICE phase timings from .st0 files, then remove those sensitive logs."""

from __future__ import annotations

import argparse
import csv
import re
import tarfile
from pathlib import Path


ARCHIVE_RE = re.compile(r"matrix_(hspice_independent|hspice_alter)_n(\d+)_r(\d+)\.tar\.gz$")
CLOCK = r"([0-9.]+(?:E[+-][0-9]+)?)"
PHASES = {
    "read_s": (re.compile(r"init: begin read circuit files, cpu clock=\s*" + CLOCK), re.compile(r"init: end read circuit files, cpu clock=\s*" + CLOCK)),
    "check_s": (re.compile(r"init: begin check errors, cpu clock=\s*" + CLOCK), re.compile(r"init: end check errors, cpu clock=\s*" + CLOCK)),
    "setup_s": (re.compile(r"init: begin setup matrix.*cpu clock=\s*" + CLOCK), re.compile(r"init: end setup matrix, cpu clock=\s*" + CLOCK)),
    "analysis_s": (re.compile(r"sweep: dc .* begin.*cpu clock=\s*" + CLOCK), re.compile(r"sweep: dc .* end, cpu clock=\s*" + CLOCK)),
}


def parse_st0(text: str) -> dict[str, float | int]:
    totals: dict[str, float | int] = {key: 0.0 for key in PHASES}
    totals["jobs"] = 0
    for key, (begin_re, end_re) in PHASES.items():
        begin = None
        for line in text.splitlines():
            begin_match = begin_re.search(line)
            if begin_match:
                begin = float(begin_match.group(1))
                if key == "read_s":
                    totals["jobs"] = int(totals["jobs"]) + 1
                continue
            end_match = end_re.search(line)
            if end_match and begin is not None:
                totals[key] = float(totals[key]) + max(0.0, float(end_match.group(1)) - begin)
                begin = None
    return totals


def sanitize_archive(path: Path) -> dict[str, float | int]:
    totals: dict[str, float | int] = {key: 0.0 for key in PHASES}
    totals["jobs"] = 0
    totals["st0_files"] = 0
    temporary = path.with_suffix(path.suffix + ".tmp")
    with tarfile.open(path, "r:gz") as source, tarfile.open(temporary, "w:gz", compresslevel=6) as target:
        for member in source.getmembers():
            extracted = source.extractfile(member) if member.isfile() else None
            if member.name.endswith(".st0"):
                totals["st0_files"] = int(totals["st0_files"]) + 1
                if extracted is not None:
                    parsed = parse_st0(extracted.read().decode("utf-8", errors="replace"))
                    for key, value in parsed.items():
                        totals[key] = float(totals[key]) + float(value)
                continue
            if member.name.endswith(".lis"):
                continue
            lowered = member.name.lower()
            if "license" in lowered or "synopsys.dat" in lowered or "lmgrd" in lowered:
                continue
            target.addfile(member, extracted)
    temporary.replace(path)
    totals["jobs"] = int(totals["jobs"])
    totals["st0_files"] = int(totals["st0_files"])
    return totals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    rows = []
    for archive in sorted((root / "data/raw/logs").glob("*hspice*.tar.gz")):
        match = ARCHIVE_RE.match(archive.name)
        totals = sanitize_archive(archive)
        if match and int(totals["st0_files"]) > 0:
            method, size, rep = match.groups()
            totals.pop("st0_files", None)
            rows.append({"method": method, "size": int(size), "rep": int(rep), **totals})
    output = root / "data/summary/hspice_phases.csv"
    if rows:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {len(rows)} phase rows and sanitized their source archives")
    elif output.exists():
        print("archives already sanitized; retained existing phase summary")
    else:
        raise RuntimeError("no HSPICE phase data found")


if __name__ == "__main__":
    main()
