#!/usr/bin/env python3
"""Validate stable test-documentation facts against executable sources."""
from __future__ import annotations
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def source_facts(root: Path = ROOT) -> dict[str, object]:
    catalog = json.loads((root / "tests/suite/catalog.json").read_text())
    tiers = {tier for suite in catalog["suites"] for tier in suite["tiers"]}
    qml_text = "\n".join(p.read_text() for p in (root / "tests/qml").glob("*.qml"))
    qml_tests = len(re.findall(r"(?m)^\s*function\s+test_\w+\s*\(", qml_text))
    qml_cases = len(re.findall(r"\bTestCase\s*\{", qml_text))
    build = (root / "tests/robolectric/build.gradle").read_text()
    included = re.findall(r"include '([^']+RobolectricTest\.java)'", build)
    robo_methods = robo_executions = 0
    robo_matrices = {}
    matrix_labels = {
        "org/overte/phone/": "Phone",
        "io/highfidelity/hifiinterface/": "legacy Interface",
        "org/overte/pico/": "Pico",
        "io/highfidelity/questInterface/": "legacy Quest",
    }
    for relative in included:
        candidates = list((root / "apps").glob(f"*/src/test/java/{relative}"))
        if len(candidates) != 1:
            raise ValueError(f"Robolectric include must resolve exactly once: {relative}")
        text = candidates[0].read_text()
        methods = len(re.findall(r"(?m)^\s*@Test\b", text))
        sdk = re.search(r"@Config\s*\(\s*sdk\s*=\s*\{([^}]+)\}", text)
        sdks = tuple(int(value) for value in re.findall(r"\d+", sdk.group(1))) if sdk else ()
        if not sdks:
            raise ValueError(f"Robolectric test lacks an explicit SDK matrix: {relative}")
        labels = [label for prefix, label in matrix_labels.items() if relative.startswith(prefix)]
        if len(labels) != 1:
            raise ValueError(f"Robolectric test lacks one application matrix label: {relative}")
        previous = robo_matrices.setdefault(labels[0], sdks)
        if previous != sdks:
            raise ValueError(f"inconsistent Robolectric SDK matrix for {labels[0]}")
        robo_methods += methods
        robo_executions += methods * len(sdks)
    all_test_includes = re.findall(r"include '([^']+Test\.java)'", build)
    harness_executions = robo_executions
    for relative in set(all_test_includes) - set(included):
        candidates = list((root / "apps").glob(f"*/src/test/java/{relative}"))
        if len(candidates) != 1:
            raise ValueError(f"JUnit include must resolve exactly once: {relative}")
        harness_executions += len(re.findall(
            r"(?m)^\s*@Test\b", candidates[0].read_text(encoding="utf-8")))
    tree = ast.parse((root / "tests/mutation/run_mutations.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "Mutant"]
    def is_extended(call: ast.Call) -> bool:
        positional = (len(call.args) >= 6 and isinstance(call.args[5], ast.Constant)
                      and call.args[5].value is True)
        keyword = any(item.arg == "extended" and isinstance(item.value, ast.Constant)
                      and item.value.value is True for item in call.keywords)
        return positional or keyword
    extended = sum(is_extended(call) for call in calls)
    package = json.loads((root / "tests/javascript/package.json").read_text())
    js_thresholds = {}
    for name in ("places-main", "portal", "action-bar", "phone-emote", "tablet-apps", "quick-goto"):
        command = package["scripts"][f"coverage:{name}"]
        js_thresholds[name] = tuple(int(re.search(rf"--test-coverage-{metric}=(\d+)", command).group(1))
                                    for metric in ("lines", "branches", "functions"))
    return {"tiers": tiers, "qml_tests": qml_tests, "qml_rows": qml_tests + 2*qml_cases,
            "robo_methods": robo_methods, "robo_executions": robo_executions,
            "robo_matrices": robo_matrices,
            "harness_executions": harness_executions,
            "mutation_quick": len(calls)-extended, "mutation_extended": len(calls),
            "js_thresholds": js_thresholds}

def validate(testing: str, coverage: str, facts: dict[str, object]) -> list[str]:
    errors = []
    for tier in sorted(facts["tiers"]):
        command = f"tests/run-tests.sh {tier}"
        if command not in testing:
            errors.append(f"ANDROID_TESTING.md lacks catalog tier command: {command}")
    claims = [(coverage, rf"{facts['qml_tests']} explicit `test_\*` functions.*?{facts['qml_rows']} QtTest result rows", "QML count"),
              (testing+"\n"+coverage, rf"{facts['robo_methods']} Robolectric\s+source behaviors.*?\({facts['robo_executions']} executions\)", "Robolectric count"),
              (testing+"\n"+coverage, rf"{facts['harness_executions']} granular JUnit cases", "Robolectric harness JUnit count"),
              (coverage, rf"kills {facts['mutation_quick']}/{facts['mutation_quick']} curated mutants", "quick mutation count"),
              (coverage, rf"kills\s+{facts['mutation_extended']}/{facts['mutation_extended']}", "extended mutation count")]
    for text, pattern, label in claims:
        if not re.search(pattern, text, re.DOTALL):
            errors.append(f"stale or missing {label} documentation")
    combined_docs = testing + "\n" + coverage
    for application, sdks in facts.get("robo_matrices", {}).items():
        matrix = "/".join(str(sdk) for sdk in sdks)
        if f"{application} (API {matrix})" not in combined_docs:
            errors.append(f"stale or missing Robolectric SDK matrix for {application}")
    names = {"places-main":"places.js", "portal":"portal.js", "action-bar":"mobileActionBar.js",
             "phone-emote":"phoneEmote.js"}
    for key, filename in names.items():
        if key not in facts.get("js_thresholds", {}):
            continue
        line, branch, function = facts["js_thresholds"][key]
        pattern = rf"`?{re.escape(filename)}`?.{{0,40}}{line}%\s*(?:lines|/)\s*/?\s*{branch}%\s*(?:branches|/)\s*/?\s*{function}%"
        if not re.search(pattern, testing, re.DOTALL):
            errors.append(f"stale JavaScript coverage thresholds for {filename}")
    if "tablet-apps" in facts.get("js_thresholds", {}):
        if facts["js_thresholds"]["tablet-apps"] != (100,100,100) or facts["js_thresholds"]["quick-goto"] != (100,100,100):
            errors.append("documentation assumes obsolete all-100 tablet/quick coverage thresholds")
        elif not re.search(r"`mobileTabletApps\.js` plus\s+`quickGoto\.js` each require 100%", testing):
            errors.append("stale JavaScript coverage thresholds for tablet/quick scripts")
    return errors

def main() -> int:
    testing = (ROOT / "docs/ANDROID_TESTING.md").read_text()
    coverage = (ROOT / "docs/ANDROID_TEST_COVERAGE.md").read_text()
    errors = validate(testing, coverage, source_facts())
    if errors:
        print("Test documentation contract failed:\n" + "\n".join(f"- {e}" for e in errors), file=sys.stderr)
        return 1
    print("Test documentation contract passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
