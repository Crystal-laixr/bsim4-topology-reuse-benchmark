#!/usr/bin/env python3
"""Move failed matrix records out of the release-analysis input set."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "data" / "raw" / "matrix"
INVALID = ROOT / "data" / "raw" / "invalid"


def main() -> None:
    INVALID.mkdir(parents=True, exist_ok=True)
    excluded = []
    for path in sorted(MATRIX.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if int(row["workers_ok"]) == int(row["effective_workers"]):
            continue
        target = INVALID / path.name
        path.replace(target)
        excluded.append({"file": path.name, "reason": "workers_ok does not match effective_workers"})
    (INVALID / "exclusion_manifest.json").write_text(
        json.dumps({"excluded": excluded}, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"excluded_count": len(excluded)}))


if __name__ == "__main__":
    main()
