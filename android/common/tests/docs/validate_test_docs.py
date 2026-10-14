#!/usr/bin/env python3
"""Validate stable test-documentation facts against executable sources."""
from __future__ import annotations
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROFILE_START = "<!-- android-test-profile:start -->"
PROFILE_END = "<!-- android-test-profile:end -->"

def expected_profile(facts: dict[str, object], scope: str) -> dict[str, object]:
    return {"scope": scope, "qmlFunctions": facts["qml_tests"],
            "qmlRows": facts["qml_rows"], "robolectricBehaviors": facts["robo_methods"],
            "robolectricExecutions": facts["robo_executions"],
            "junitCases": facts["harness_executions"],
            "sdkMatrices": {key: list(value) for key, value in facts["robo_matrices"].items()},
            "robolectricClasses": facts["robo_classes"]}

def validate_profile(parent: str, phone: str, facts: dict[str, object]) -> list[str]:
    # A product declaration is authoritative when present. Never let an old
    # parent paragraph or coincidentally matching numbers mask a stale override.
    own = PROFILE_START in phone or PROFILE_END in phone
    text, scope = (phone, "android-phone") if own else (parent, "android-parent")
    if (text.count(PROFILE_START) != 1 or text.count(PROFILE_END) != 1
            or text.find(PROFILE_START) >= text.find(PROFILE_END)):
        return ["missing or duplicate authoritative Android test profile"]
    fragment = text.split(PROFILE_START, 1)[1].split(PROFILE_END, 1)[0].strip()
    match = re.fullmatch(r"```json\s*\n(.*?)\n```", fragment, re.DOTALL)
    if not match:
        return ["malformed authoritative Android test profile"]
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate profile key")
            result[key] = value
        return result
    try:
        actual = json.loads(match.group(1), object_pairs_hook=unique)
    except (ValueError, TypeError):
        return ["invalid authoritative Android test profile JSON"]
    expected = expected_profile(facts, scope)
    if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
        return ["authoritative Android test profile differs from actual checkout classes, SDK matrix or counts"]
    return []

def resolve_test_includes(root: Path, patterns: list[str]) -> list[Path]:
    """Expand actual Gradle include patterns without hiding missing or duplicate classes."""
    result = set()
    for pattern in patterns:
        candidates = sorted(root.glob(f"**/apps/*/src/test/java/{pattern}"))
        if not candidates:
            raise ValueError(f"JUnit include must resolve at least once: {pattern}")
        identities = set()
        for path in candidates:
            identity = path.as_posix().split('/src/test/java/', 1)[1]
            if identity in identities:
                raise ValueError(f"JUnit include resolves a duplicate class: {identity}")
            identities.add(identity)
            result.add(path)
    return sorted(result)

def source_facts(root: Path = ROOT) -> dict[str, object]:
    catalog = json.loads((root / "common/tests/suite/catalog.json").read_text())
    tiers = {tier for suite in catalog["suites"] for tier in suite["tiers"]}
    qml_text = "\n".join(p.read_text() for p in (root / "common/tests/qml").glob("*.qml"))
    qml_tests = len(re.findall(r"(?m)^\s*function\s+test_\w+\s*\(", qml_text))
    qml_cases = len(re.findall(r"\bTestCase\s*\{", qml_text))
    build = (root / "common/tests/robolectric/build.gradle").read_text()
    included = re.findall(r"include '([^']+RobolectricTest\.java)'", build)
    robo_methods = robo_executions = 0
    robo_matrices = {}
    robo_classes = {}
    matrix_labels = {
        "org/overte/phone/": "Phone",
        "io/highfidelity/hifiinterface/": "legacy Interface",
        "org/overte/pico/": "Pico",
        "io/highfidelity/questInterface/": "legacy Quest",
    }
    for candidate in resolve_test_includes(root, included):
        relative = candidate.as_posix().split('/src/test/java/', 1)[1]
        text = candidate.read_text()
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
        robo_classes[relative] = {"behaviors": methods, "sdks": list(sdks)}
    all_test_includes = re.findall(r"include '([^']+Test\.java)'", build)
    harness_executions = robo_executions
    for candidate in resolve_test_includes(root, sorted(set(all_test_includes) - set(included))):
        harness_executions += len(re.findall(
            r"(?m)^\s*@Test\b", candidate.read_text(encoding="utf-8")))
    tree = ast.parse((root / "common/tests/mutation/run_mutations.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "Mutant"]
    def is_extended(call: ast.Call) -> bool:
        positional = (len(call.args) >= 6 and isinstance(call.args[5], ast.Constant)
                      and call.args[5].value is True)
        keyword = any(item.arg == "extended" and isinstance(item.value, ast.Constant)
                      and item.value.value is True for item in call.keywords)
        return positional or keyword
    extended = sum(is_extended(call) for call in calls)
    package = json.loads((root / "common/tests/javascript/package.json").read_text())
    js_thresholds = {}
    for name in ("places-main", "portal", "action-bar", "phone-emote", "tablet-apps", "quick-goto"):
        command = package["scripts"][f"coverage:{name}"]
        js_thresholds[name] = tuple(int(re.search(rf"--test-coverage-{metric}=(\d+)", command).group(1))
                                    for metric in ("lines", "branches", "functions"))
    return {"tiers": tiers, "qml_tests": qml_tests, "qml_rows": qml_tests + 2*qml_cases,
            "robo_methods": robo_methods, "robo_executions": robo_executions,
            "robo_matrices": robo_matrices,
            "robo_classes": robo_classes,
            "harness_executions": harness_executions,
            "mutation_quick": len(calls)-extended, "mutation_extended": len(calls),
            "js_thresholds": js_thresholds}

def validate(testing: str, coverage: str, facts: dict[str, object], phone: str = "") -> list[str]:
    errors = validate_profile(testing, phone, facts)
    for tier in sorted(facts["tiers"]):
        command = f"common/tests/run-tests.sh {tier}"
        if command not in testing:
            errors.append(f"ANDROID_TESTING.md lacks catalog tier command: {command}")
    claims = [(coverage, rf"kills {facts['mutation_quick']}/{facts['mutation_quick']} curated mutants", "quick mutation count"),
              (coverage, rf"kills\s+{facts['mutation_extended']}/{facts['mutation_extended']}", "extended mutation count")]
    for text, pattern, label in claims:
        if not re.search(pattern, text, re.DOTALL):
            errors.append(f"stale or missing {label} documentation")
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
    testing = (ROOT / "common/docs/ANDROID_TESTING.md").read_text()
    coverage = (ROOT / "common/docs/ANDROID_TEST_COVERAGE.md").read_text()
    phone = ROOT / "phone/docs/BUILD.md"
    errors = validate(testing, coverage, source_facts(), phone.read_text() if phone.exists() else "")
    if errors:
        print("Test documentation contract failed:\n" + "\n".join(f"- {e}" for e in errors), file=sys.stderr)
        return 1
    print("Test documentation contract passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
