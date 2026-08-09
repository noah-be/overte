#!/usr/bin/env python3
"""Aggregate GCC gcov JSON into dependency-free Overte coverage reports."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import gzip
import html
import json
import re
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
            "line_hits": {str(number): count for number, count in sorted(lines.items())},
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
    components = []
    component_names = sorted({"/".join(item["path"].split("/")[:2]) for item in files})
    for component in component_names:
        members = [item for item in files if item["path"].startswith(component + "/")]
        metrics = {}
        for metric in ("lines", "functions", "branches"):
            covered = sum(item[metric]["covered"] for item in members)
            total = sum(item[metric]["total"] for item in members)
            metrics[metric] = {"covered": covered, "total": total,
                               "percent": round(covered * 100.0 / total, 2) if total else 0.0}
        components.append({"path": component, **metrics})
    return {"schema": 2, "summary": summary, "components": components, "files": files}


def parse_changed_lines(diff: str) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = defaultdict(set)
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif current and line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                start = int(match.group(1))
                count = int(match.group(2) or 1)
                changed[current].update(range(start, start + count))
    return changed


def diff_summary(report: dict, changed: dict[str, set[int]]) -> dict:
    covered = total = 0
    by_path = {item["path"]: item for item in report["files"]}
    for path, lines in changed.items():
        hits = by_path.get(path, {}).get("line_hits", {})
        instrumented = [str(number) for number in lines if str(number) in hits]
        total += len(instrumented)
        covered += sum(hits[number] > 0 for number in instrumented)
    return {"covered": covered, "total": total,
            "percent": round(covered * 100.0 / total, 2) if total else 0.0}


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
    component_rows = []
    for item in report.get("components", []):
        component_rows.append("<tr><td>" + html.escape(item["path"]) + "</td>" +
                              "".join(f"<td>{percentage(item[metric])}</td>"
                                      for metric in ("lines", "functions", "branches")) + "</tr>")
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
<h2>Components</h2>
<table><thead><tr><th>Component</th><th>Lines</th><th>Functions</th><th>Branches</th></tr></thead><tbody>%s</tbody></table>
<h2>Files</h2>
<table><thead><tr><th>Source</th><th>Lines</th><th>Functions</th><th>Branches</th></tr></thead><tbody>%s</tbody></table>
""" % (percentage(summary["lines"]), percentage(summary["functions"]),
       percentage(summary["branches"]), "\n".join(component_rows), "\n".join(rows)), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline", type=Path,
                        help="fail if any overall percentage regresses below this JSON report")
    parser.add_argument("--changed-since",
                        help="include line coverage for production lines changed since this git revision")
    args = parser.parse_args()
    build_dir = args.build_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = merge_documents(collect(build_dir))
    if args.changed_since:
        diff = subprocess.run(
            ["git", "diff", "--unified=0", args.changed_since, "--", *sorted(SOURCE_ROOTS)],
            cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE,
        ).stdout
        report["diff"] = {"base": args.changed_since,
                          "lines": diff_summary(report, parse_changed_lines(diff))}
    json_path = args.output_dir / "coverage.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_html(report, html_path)
    for metric in ("lines", "functions", "branches"):
        print(f"{metric.capitalize()}: {percentage(report['summary'][metric])}")
    if "diff" in report:
        print(f"Changed lines: {percentage(report['diff']['lines'])}")
    print(f"JSON: {json_path}\nHTML: {html_path}")
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        regressions = [metric for metric in ("lines", "functions", "branches")
                       if report["summary"][metric]["percent"] < baseline["summary"][metric]["percent"]]
        if regressions:
            print("Coverage regression: " + ", ".join(regressions))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
