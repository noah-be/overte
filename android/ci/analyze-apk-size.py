#!/usr/bin/env python3
"""Produce a deterministic Markdown size report for an APK."""

import argparse
from collections import defaultdict
from pathlib import Path
import sys
import zipfile


def mib(value):
    return f"{value / 1024 / 1024:.1f} MiB"


def category(name):
    if name.startswith("lib/"):
        return "Native libraries"
    if name.startswith("assets/scripts/"):
        return "Scripts"
    if name.startswith("assets/resources"):
        return "Resources"
    if name.startswith("assets/"):
        return "Other assets"
    if name.endswith(".dex"):
        return "DEX"
    return "Other"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--budget-mib", type=float, default=550.0)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()
    if not args.apk.is_file():
        parser.error(f"APK does not exist: {args.apk}")
    totals = defaultdict(lambda: [0, 0])
    with zipfile.ZipFile(args.apk) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
    for entry in entries:
        values = totals[category(entry.filename)]
        values[0] += entry.compress_size
        values[1] += entry.file_size
    lines = [f"# APK size report: {args.apk.name}", "",
             f"Total: **{mib(args.apk.stat().st_size)}** (budget: {args.budget_mib:.1f} MiB)", "",
             "## Categories", "", "| Category | Compressed | Uncompressed |", "|---|---:|---:|"]
    for name, values in sorted(totals.items(), key=lambda item: item[1][0], reverse=True):
        lines.append(f"| {name} | {mib(values[0])} | {mib(values[1])} |")
    lines += ["", "## Largest entries", "", "| Entry | Compressed | Uncompressed |",
              "|---|---:|---:|"]
    for entry in sorted(entries, key=lambda item: item.compress_size, reverse=True)[:args.top]:
        lines.append(f"| `{entry.filename}` | {mib(entry.compress_size)} | {mib(entry.file_size)} |")
    rendered = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if args.apk.stat().st_size > args.budget_mib * 1024 * 1024:
        print(f"error: APK exceeds {args.budget_mib:.1f} MiB size budget", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
