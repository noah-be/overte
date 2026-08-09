#!/usr/bin/env python3
"""Aggregate GCC gcov JSON into dependency-free Overte coverage reports."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import gzip
import html
import json
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = {
    "assignment-client", "domain-server", "ice-server", "interface", "libraries",
    "plugins", "server-console", "tools",
}


def merge_documents(documents: list[dict], root: Path = ROOT) -> dict:
    line_counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    function_counts: dict[str, dict[tuple[str, int], int]] = defaultdict(lambda: defaultdict(int))
    branch_counts: dict[str, dict[tuple[int, int, int], int]] = defaultdict(lambda: defaultdict(int))
    resolved_root = root.resolve()
    for document in documents:
        for source in document.get("files", []):
            path = Path(source["file"])
            try:
                relative = path.resolve().relative_to(resolved_root)
            except ValueError:
                continue
            if not relative.parts or relative.parts[0] not in SOURCE_ROOTS:
                continue
            name = relative.as_posix()
            for line in source.get("lines", []):
                number = int(line["line_number"])
                line_counts[name][number] += int(line.get("count", 0))
                for index, branch in enumerate(line.get("branches", [])):
                    key = (number, int(branch.get("source_block_id", 0)), index)
                    branch_counts[name][key] += int(branch.get("count", 0))
            for function in source.get("functions", []):
                key = (function.get("demangled_name") or function.get("name", "<unknown>"),
                       int(function.get("start_line", 0)))
                function_counts[name][key] += int(function.get("execution_count", 0))

    files = []
    for name in sorted(line_counts):
        lines = line_counts[name]
        functions = function_counts[name]
        branches = branch_counts[name]
        files.append({
            "path": name,
            "lines": {"covered": sum(count > 0 for count in lines.values()), "total": len(lines)},
            "functions": {"covered": sum(count > 0 for count in functions.values()), "total": len(functions)},
            "branches": {"covered": sum(count > 0 for count in branches.values()), "total": len(branches)},
        })
    summary = {}
    for metric in ("lines", "functions", "branches"):
        covered = sum(item[metric]["covered"] for item in files)
        total = sum(item[metric]["total"] for item in files)
        summary[metric] = {
            "covered": covered,
            "total": total,
            "percent": round(covered * 100.0 / total, 2) if total else 0.0,
        }
    return {"schema": 1, "summary": summary, "files": files}


def collect(build_dir: Path) -> list[dict]:
    data_files = sorted(build_dir.rglob("*.gcda"))
    if not data_files:
        raise RuntimeError(f"no .gcda files found below {build_dir}")
    documents = []
    with tempfile.TemporaryDirectory(prefix="overte-gcov-") as temporary:
        output_dir = Path(temporary)
        for data_file in data_files:
            for old in output_dir.glob("*.gcov.json.gz"):
                old.unlink()
            result = subprocess.run(
                ["gcov", "--json-format", "--branch-probabilities", "--branch-counts",
                 str(data_file.resolve())],
                cwd=output_dir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            if result.returncode:
                raise RuntimeError(f"gcov failed for {data_file}: {result.stderr.strip()}")
            generated = list(output_dir.glob("*.gcov.json.gz"))
            if len(generated) != 1:
                raise RuntimeError(f"gcov produced {len(generated)} reports for {data_file}")
            with gzip.open(generated[0], "rt", encoding="utf-8") as stream:
                documents.append(json.load(stream))
    return documents


def percentage(metric: dict) -> str:
    return f"{metric['percent']:.2f}% ({metric['covered']}/{metric['total']})"


def write_html(report: dict, path: Path) -> None:
    rows = []
    for item in sorted(report["files"], key=lambda value: value["lines"]["percent"] if "percent" in value["lines"] else (value["lines"]["covered"] / max(value["lines"]["total"], 1))):
        cells = []
        for metric in ("lines", "functions", "branches"):
            value = item[metric]
            percent = value["covered"] * 100.0 / value["total"] if value["total"] else 0.0
            cells.append(f"{percent:.2f}% ({value['covered']}/{value['total']})")
        rows.append("<tr><td>" + html.escape(item["path"]) + "</td>" +
                    "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    summary = report["summary"]
    path.write_text("""<!doctype html><meta charset=\"utf-8\"><title>Overte native coverage</title>
<style>body{font-family:sans-serif;margin:2rem}table{border-collapse:collapse;width:100%%}th,td{border:1px solid #ccc;padding:.35rem;text-align:right}th:first-child,td:first-child{text-align:left}</style>
<h1>Overte native coverage</h1>
<p>Lines: %s &nbsp; Functions: %s &nbsp; Branches: %s</p>
<table><thead><tr><th>Source</th><th>Lines</th><th>Functions</th><th>Branches</th></tr></thead><tbody>%s</tbody></table>
""" % (percentage(summary["lines"]), percentage(summary["functions"]),
       percentage(summary["branches"]), "\n".join(rows)), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    build_dir = args.build_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = merge_documents(collect(build_dir))
    json_path = args.output_dir / "coverage.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_html(report, html_path)
    for metric in ("lines", "functions", "branches"):
        print(f"{metric.capitalize()}: {percentage(report['summary'][metric])}")
    print(f"JSON: {json_path}\nHTML: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
