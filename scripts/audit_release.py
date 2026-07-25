#!/usr/bin/env python3
"""Audit completeness, size limits, and absence of credentials/license metadata."""

from __future__ import annotations

import csv
import json
import re
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_CONTENT = (
    b"BEGIN OPENSSH PRIVATE KEY",
    b"github_pat_",
    b"ghp_",
    b"License/Maintenance for hspice",
    b"HOSTID:",
    b"27099@localhost",
)
FORBIDDEN_ARCHIVE_NAMES = (".st0", "synopsys.dat", "license.log", "lmgrd", "snpslmd")


def main() -> None:
    design = json.loads((ROOT / "params/design.json").read_text(encoding="utf-8"))
    with (ROOT / "params/points.csv").open(newline="", encoding="utf-8") as handle:
        points = list(csv.DictReader(handle))
    matrix_files = list((ROOT / "data/raw/matrix").glob("*.json"))
    gate = json.loads((ROOT / "data/summary/gate_500.json").read_text(encoding="utf-8"))
    failures = []
    if design.get("mosfet_count") != 550:
        failures.append("design does not contain exactly 550 MOSFETs")
    if design.get("varying_parameters") != 14:
        failures.append("design does not contain exactly 14 varying parameters")
    if len(points) != 500:
        failures.append(f"expected 500 points, found {len(points)}")
    if len(matrix_files) != 80:
        failures.append(f"expected 80 matrix JSON files, found {len(matrix_files)}")
    if gate.get("status") != "pass":
        failures.append("500-point numerical gate did not pass")

    large_files = []
    for path in ROOT.rglob("*"):
        if path.is_file() and path.stat().st_size >= 95 * 1024 * 1024:
            large_files.append(str(path.relative_to(ROOT)))
    if large_files:
        failures.append("files at or above 95 MiB: " + ", ".join(large_files))

    scanned_archives = 0
    for archive in (ROOT / "data/raw/logs").glob("*.tar.gz"):
        scanned_archives += 1
        with tarfile.open(archive, "r:gz") as handle:
            for member in handle.getmembers():
                lowered = member.name.lower()
                if any(token in lowered for token in FORBIDDEN_ARCHIVE_NAMES):
                    failures.append(f"forbidden archive member {archive.name}:{member.name}")
                    continue
                if not member.isfile():
                    continue
                source = handle.extractfile(member)
                if source is None:
                    continue
                content = source.read()
                for token in FORBIDDEN_CONTENT:
                    if token in content:
                        failures.append(f"forbidden content {token!r} in {archive.name}:{member.name}")

    audit = {
        "status": "pass" if not failures else "fail",
        "mosfet_count": design.get("mosfet_count"),
        "varying_parameters": design.get("varying_parameters"),
        "parameter_points": len(points),
        "matrix_json_files": len(matrix_files),
        "archives_scanned": scanned_archives,
        "large_files": large_files,
        "failures": failures,
    }
    output = ROOT / "data/summary/release_audit.json"
    output.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

