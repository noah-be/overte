#!/usr/bin/env python3
"""Produce selector-free reliability trends without allowing quarantine to turn red green."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return round(ordered[index], 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", action="append", required=True, type=Path)
    parser.add_argument("--quarantine", action="append", default=[],
                        help="platform:suite annotation; failures remain failures")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    groups: dict[str, list[tuple[dict, dict]]] = {}
    for directory in args.result:
        manifest = json.loads((directory / "run-manifest.json").read_text(encoding="utf-8"))
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        if manifest.get("schemaVersion") != 1 or summary.get("schemaVersion") != 1:
            raise ValueError("unsupported history input contract")
        key = f"{manifest['platform']}:{manifest['suite']}"
        groups.setdefault(key, []).append((manifest, summary))
    quarantine = set(args.quarantine)
    unknown_quarantine = sorted(quarantine - set(groups))
    if unknown_quarantine:
        raise ValueError("quarantine references unknown history gates: "
                         + ", ".join(unknown_quarantine))
    cells = []
    for key in sorted(groups):
        runs = groups[key]
        passed = sum(manifest["status"] == "passed" for manifest, _ in runs)
        product_failed = sum(any(item["status"] == "failed" for item in summary["results"])
                             for _, summary in runs)
        infra_failed = sum(any(item["status"] == "error" for item in summary["results"])
                           for _, summary in runs)
        cells.append({
            "gate": key, "runs": len(runs), "passed": passed,
            "productFailures": product_failed, "infrastructureErrors": infra_failed,
            "passRate": round(passed / len(runs), 4),
            "infrastructureErrorRate": round(infra_failed / len(runs), 4),
            "durationP50Seconds": percentile([m["durationSeconds"] for m, _ in runs], 0.5),
            "durationP95Seconds": percentile([m["durationSeconds"] for m, _ in runs], 0.95),
            "flaky": passed > 0 and product_failed > 0,
            "quarantined": key in quarantine,
        })
    status = ("failed" if any(cell["productFailures"] for cell in cells) else
              "error" if any(cell["infrastructureErrors"] for cell in cells) else "passed")
    payload = {"schemaVersion": 1, "status": status,
               "cells": cells}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"History: {len(cells)} gate(s); status {payload['status']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=__import__("sys").stderr)
        raise SystemExit(2)
