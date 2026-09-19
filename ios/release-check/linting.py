"""Structured, bounded lint diagnostics without executing product code."""
# SPDX-License-Identifier: Apache-2.0
import ast
import json
from pathlib import Path
import re

from common import HERE, ROOT


def deferred_annotation(text, line):
    """Missing names inside non-evaluated annotations are typing review, not runtime failure."""
    tree = ast.parse(text)
    future = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                 and any(a.name == "annotations" for a in n.names) for n in tree.body)
    annotations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
            annotations.append(node.returns)
        if isinstance(node, (ast.arg, ast.AnnAssign)) and node.annotation:
            annotations.append(node.annotation)
    return any(a.lineno <= line <= getattr(a, "end_lineno", a.lineno)
               and (future or isinstance(a, ast.Constant) and isinstance(a.value, str)) for a in annotations)


def report(ctx, scope, tool, rule, filename, line, status, description):
    path = Path(filename)
    if path.is_absolute() and path.is_relative_to(ROOT):
        filename = str(path.relative_to(ROOT))
    ctx.add(f"{tool}-{rule}", status, filename, line, description,
            "Inspect the private tool log; resolve the defect or record an exact reviewed exception.",
            critical=status == "FAIL", evidence=scope.hashes.get(filename, ""), suppressible=True)


def run_linters(ctx, scope):
    specifications = [
        ("shellcheck", ["shellcheck", "--severity=error", "--format=json"], [p for p in scope.paths if p.endswith(".sh")]),
        ("cmakelint", ["cmakelint", "--config=None", "--filter=-readability,-package,-whitespace,-linelength,-convention"],
         [p for p in scope.paths if p.endswith(".cmake") or Path(p).name == "CMakeLists.txt"]),
        ("ruff", ["ruff", "check", "--isolated", "--select", "E9,F63,F7,F82", "--output-format", "json"],
         [p for p in scope.paths if p.endswith(".py") and "/fixtures/" not in p]),
        ("eslint", ["eslint", "--no-config-lookup", "--no-inline-config", "--config", str(HERE / "eslint.config.mjs"),
                    "--no-ignore", "--format", "json"], [p for p in scope.paths if p.startswith("scripts/") and p.endswith(".js")]),
    ]
    for tool, command, files in specifications:
        for offset in range(0, len(files), 80):
            result = ctx.command(f"{tool}-{offset // 80}", [*command, *files[offset:offset + 80]], ok=(0, 1), timeout=1800)
            if result is None or result.returncode not in (0, 1):
                continue
            count = 0
            try:
                if tool == "cmakelint":
                    output = (result.stdout + result.stderr).decode()
                    for match in re.finditer(r"^(.+?):(\d+): (.*?) \[([^\]]+)\]$", output, re.MULTILINE):
                        filename, line, _, rule = match.groups()
                        # This lexer misreads escaped backslashes in valid shared CMake.
                        # Actual target configure/build remains a separate mandatory gate.
                        status = "FAIL" if rule == "syntax" and filename.startswith("ios/") else "WARNING"
                        report(ctx, scope, tool, rule, filename, int(line), status,
                               "CMake lexical diagnostic; confirm with actual iOS configuration.")
                        count += 1
                else:
                    payload = json.loads(result.stdout)
                    if not isinstance(payload, list):
                        raise ValueError("unexpected lint report")
                    for item in payload:
                        if tool == "shellcheck":
                            report(ctx, scope, tool, str(item["code"]), item["file"], item["line"], "FAIL", "Shell analysis reported an error.")
                            count += 1
                        elif tool == "ruff":
                            path = Path(item["filename"])
                            name = str(path.relative_to(ROOT)) if path.is_absolute() else str(path)
                            line, rule = item["location"]["row"], item["code"]
                            postponed = rule == "F821" and deferred_annotation(scope.texts[name], line)
                            report(ctx, scope, tool, rule, name, line, "WARNING" if postponed else "FAIL",
                                   "Unresolved type-only annotation; no runtime name evaluation here." if postponed else "Python analysis reported a runtime/syntax defect.")
                            count += 1
                        else:
                            for message in item["messages"]:
                                rule = message.get("ruleId") or "parse"
                                report(ctx, scope, tool, rule, item["filePath"], message.get("line", 0),
                                       "FAIL" if message["severity"] == 2 else "WARNING",
                                       "JavaScript analysis reported a syntax/control-flow/type comparison issue.")
                                count += 1
                ctx.need(result.returncode == 0 or count, "lint-output", f"{tool} failed without structured findings.")
            except (ValueError, KeyError, TypeError):
                ctx.add("lint-report-invalid", "FAIL", message=f"{tool} produced an unreadable diagnostic report; remaining linters will continue.", critical=True)
