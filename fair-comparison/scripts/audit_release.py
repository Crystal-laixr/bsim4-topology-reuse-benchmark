#!/usr/bin/env python3
"""Release audit for the fair comparison subtree."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (b"License/Maintenance for hspice", b"SERVER this_host", b"synopsys.dat", b"BEGIN OPENSSH PRIVATE KEY")
FORBIDDEN_NAMES = ("lmgrd", "synopsys.dat")

def main() -> None:
    design = json.loads((ROOT / "params" / "design.json").read_text(encoding="utf-8"))
    if design["mosfet_count"] != 580 or design["varying_parameters"] != 14 or design["points"] != 500:
        raise RuntimeError("design audit failed")
    large = []; forbidden = []
    for path in ROOT.rglob("*"):
        if not path.is_file(): continue
        relative = path.relative_to(ROOT)
        if (
            path == Path(__file__).resolve()
            or "__pycache__" in relative.parts
            or relative == Path("data/summary/release_audit.json")
            or (relative.parent == Path("data/raw/system") and relative.name.startswith("full_matrix") and relative.suffix == ".stdout")
        ):
            continue
        if path.stat().st_size >= 95 * 1024 * 1024: large.append(str(path.relative_to(ROOT)))
        lowered_name = path.name.lower()
        for marker in FORBIDDEN_NAMES:
            if marker in lowered_name: forbidden.append({"file": str(relative), "marker": f"filename:{marker}"})
        if path.suffix.lower() not in (".gz", ".png", ".pdf"):
            data = path.read_bytes()
            for marker in FORBIDDEN:
                if marker in data: forbidden.append({"file": str(path.relative_to(ROOT)), "marker": marker.decode(errors="replace")})
    result = {"status": "pass" if not large and not forbidden else "fail", "mosfet_count": 580, "points": 500, "large_files": large, "forbidden_hits": forbidden}
    output = ROOT / "data" / "summary" / "release_audit.json"; output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["status"] != "pass": raise RuntimeError(result)
    print(output)

if __name__ == "__main__": main()
