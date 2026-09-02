#!/usr/bin/env python3
"""Validate reproducibility-critical Android CI declarations without PyYAML."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


ACTION = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
EXPECTED_GRADLE_SHA = "20f1b1176237254a6fc204d8434196fa11a4cfb387567519c61556e8710aed78"

REQUIRED_QT_PACKAGES = {
    "qtdeclarative5-dev-tools", "qml-module-qttest", "qml-module-qtquick2",
    "qml-module-qtquick-controls", "qml-module-qtquick-controls2",
    "qml-module-qtquick-layouts", "qml-module-qtquick-window2",
}
REQUIRED_TIER_COMMANDS = {
    "common/tests/run-tests.sh fast",
    "common/tests/run-tests.sh contracts",
    "common/tests/run-tests.sh regression",
    "common/tests/run-tests.sh mutation",
    "common/tests/run-tests.sh mutation-extended",
    "common/tests/run-tests.sh stability",
    "common/tests/run-tests.sh endurance",
}
REQUIRED_JUNIT_PATHS = {
    "android/build/test-results/suite/",
    "android/build/test-results/suite/TEST-android-mutation.xml",
    "android/build/test-results/suite/TEST-android-mutation-extended.xml",
    "android/common/tests/robolectric/build/test-results/test/",
    "android/build/test-results/native/",
    "android/build/test-results/javascript/",
    "android/build/test-results/qml/",
    "android/build/test-results/suite/TEST-android-stability.xml",
    "android/build/test-results/suite/TEST-android-endurance.xml",
    "android/build/test-results/qml-endurance/TEST-qml-endurance.xml",
    "android/build/reports/mutation/critical-policies-extended.json",
}

DIAGNOSTIC_CONDITION_PARTS = (
    "github.event_name == 'workflow_dispatch'",
    "github.event_name == 'pull_request'",
    "contains(github.event.pull_request.labels.*.name, 'android-long-diagnostics')",
)
REGRESSION_CONDITION_PARTS = (
    "github.event_name == 'workflow_dispatch' && inputs.run_regression",
)
SCRIPT_REFERENCE = re.compile(r"(?<![\w./-])((?:[\w.+-]+/)+[\w.+-]+\.(?:py|sh))(?![\w./-])")


def job_body(workflow: str, job: str) -> str | None:
    match = re.search(rf"^  {re.escape(job)}:\s*$\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)",
                      workflow, re.MULTILINE | re.DOTALL)
    return match.group("body") if match else None


def validate_actions(workflow: str) -> list[str]:
    errors = []
    actions = ACTION.findall(workflow)
    if not actions:
        return ["workflow declares no actions"]
    for declaration in actions:
        action, separator, revision = declaration.rpartition("@")
        if not separator or not action or not FULL_SHA.fullmatch(revision):
            errors.append(f"action {action or declaration} must use a full 40-character commit SHA")
    return errors


def validate_workflow(workflow: str) -> list[str]:
    errors = validate_actions(workflow)
    install_match = re.search(
        r"- name: Install Qt Quick test runtime\s+run:\s*\|(?P<body>.*?)(?=\n\s+- name:)",
        workflow, re.DOTALL,
    )
    install_body = install_match.group("body") if install_match else ""
    for package in sorted(REQUIRED_QT_PACKAGES):
        if not re.search(rf"(?<![\w-]){re.escape(package)}(?![\w-])", install_body):
            errors.append(f"Qt install step is missing {package}")
    for command in sorted(REQUIRED_TIER_COMMANDS):
        if not re.search(rf"^\s*(?:-\s*)?run:\s*{re.escape(command)}\s*$",
                         workflow, re.MULTILINE):
            errors.append(f"workflow is missing tier command: {command}")
    for path in sorted(REQUIRED_JUNIT_PATHS):
        if path not in workflow:
            errors.append(f"workflow is missing JUnit artifact path: {path}")
    if len(re.findall(r"^\s*(?:path:\s*)?android/build/test-results/suite/\s*$",
                      workflow, re.MULTILINE)) < 3:
        errors.append("fast, contracts and regression must each upload their JUnit directory")
    if "if-no-files-found: error" not in workflow:
        errors.append("JUnit uploads must fail when their artifacts are absent")
    return errors


def validate_script_references(workflow: str, android_root: Path) -> list[str]:
    """Ensure every repository script named by the workflow exists statically."""
    errors = []
    root = android_root.resolve()
    for relative in sorted(set(SCRIPT_REFERENCE.findall(workflow))):
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            errors.append(f"workflow script does not exist below Android root: {relative}")
    return errors


def validate_wrapper(properties: str) -> list[str]:
    match = re.search(r"^distributionSha256Sum=(\S+)\s*$", properties, re.MULTILINE)
    if not match or not SHA256.fullmatch(match.group(1)):
        return ["Gradle wrapper requires a 64-character distributionSha256Sum"]
    if match.group(1) != EXPECTED_GRADLE_SHA:
        return ["Gradle 8.13 wrapper checksum differs from the verified distribution checksum"]
    return []


def validate_periodic_jobs(workflow: str) -> list[str]:
    errors = []
    for job, command in (("mutation-extended", "common/tests/run-tests.sh mutation-extended"),
                         ("stability", "common/tests/run-tests.sh stability"),
                         ("endurance", "common/tests/run-tests.sh endurance")):
        body = job_body(workflow, job)
        if body is None:
            errors.append(f"workflow is missing long diagnostic {job} job")
            continue
        if not all(part in body for part in DIAGNOSTIC_CONDITION_PARTS):
            errors.append(f"{job} must run only for manual or labeled diagnostics")
        if "github.event_name == 'schedule'" in body:
            errors.append(f"{job} must not run on the contract-only schedule")
        if command not in body:
            errors.append(f"{job} job is missing its tier command")
        if "if: always()" not in body or "continue-on-error: true" not in body:
            errors.append(f"{job} summary must always run without masking failures")
    endurance = job_body(workflow, "endurance")
    if endurance:
        body = endurance
        for declaration in ("OVERTE_JS_ENDURANCE_CYCLES: 100",
                            "OVERTE_NATIVE_ENDURANCE_CYCLES: 1000",
                            "OVERTE_REQUIRE_QML_TESTS: 1"):
            if declaration not in body:
                errors.append(f"endurance job is missing scale/runtime declaration: {declaration}")
        if "common/tests/qml/run-qml-tests.sh" in body:
            errors.append("endurance job must not rerun the complete fast QML suite")
    return errors


def workflow_event_matrix(workflow: str, event: str, run_regression: bool = True,
                          run_diagnostics: bool = False) -> set[str]:
    jobs = {"contracts"} if job_body(workflow, "contracts") is not None else set()
    if event != "schedule":
        jobs.update(job for job in ("fast", "coverage") if job_body(workflow, job) is not None)
    if event == "workflow_dispatch" and run_regression:
        jobs.add("regression")
    if event == "workflow_dispatch" or (event == "pull_request" and run_diagnostics):
        jobs.update({"mutation-extended", "stability", "endurance"})
    return jobs


def quick_mutation_runs(event: str) -> bool:
    return event != "workflow_dispatch"


def validate_workflow_topology(workflow: str) -> list[str]:
    errors = []
    for job in ("fast", "coverage"):
        body = job_body(workflow, job)
        if body is None:
            errors.append(f"workflow is missing required {job} job")
        elif "if: github.event_name != 'schedule'" not in body:
            errors.append(f"{job} must skip the contract-only schedule")
    contracts = job_body(workflow, "contracts")
    if contracts is None:
        errors.append("workflow is missing required contracts job")
    elif re.search(r"^    if:", contracts, re.MULTILINE):
        errors.append("contracts must run for every workflow event")
    for job in ("regression", "mutation-extended", "stability", "endurance"):
        body = job_body(workflow, job)
        if body is None:
            continue
        if "needs: [fast, contracts, coverage]" not in body:
            errors.append(f"{job} must depend only on the three required gates")
    regression = job_body(workflow, "regression") or ""
    if not all(part in regression for part in REGRESSION_CONDITION_PARTS):
        errors.append("regression event condition is incomplete")
    if "github.event_name == 'push'" in regression:
        errors.append("regression must not run automatically on push")
    if "github.event_name == 'schedule'" in regression:
        errors.append("regression must not run on the contract-only schedule")
    coverage = job_body(workflow, "coverage") or ""
    if "if: github.event_name != 'workflow_dispatch'" not in coverage:
        errors.append("quick mutation condition must complement periodic extended mutation")
    java_jobs = ("fast", "contracts", "coverage", "mutation-extended", "stability",
                 "endurance", "regression")
    node_jobs = ("fast", "contracts", "coverage", "mutation-extended", "stability",
                 "endurance", "regression")
    for job in java_jobs:
        body = job_body(workflow, job) or ""
        if "uses: actions/setup-java@" not in body or "java-version: 21" not in body:
            errors.append(f"{job} must provide pinned Java 21 (including JNI headers)")
    for job in node_jobs:
        body = job_body(workflow, job) or ""
        if "uses: actions/setup-node@" not in body or "node-version: 22" not in body:
            errors.append(f"{job} must provide pinned Node 22")
    artifact_names = re.findall(
        r"uses:\s*actions/upload-artifact@[0-9a-f]{40}.*?\n\s+with:\s*\n\s+name:\s*([^\s]+)",
        workflow, re.DOTALL)
    if len(artifact_names) != len(set(artifact_names)):
        errors.append("artifact names must be unique")
    if "permissions:\n  contents: read" not in workflow:
        errors.append("workflow permissions must remain contents: read")
    if "group: android-tests-${{ github.workflow }}-${{ github.ref }}" not in workflow:
        errors.append("workflow concurrency group is missing")
    if "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" not in workflow:
        errors.append("only pull-request runs may cancel in progress")
    timeout_pairs = {"fast": (15, 8), "contracts": (15, 8), "coverage": (30, 8),
                     "mutation-extended": (40, 35), "stability": (45, 40),
                     "endurance": (20, 15), "regression": (30, 8)}
    for job, (outer, inner) in timeout_pairs.items():
        body = job_body(workflow, job) or ""
        if f"timeout-minutes: {outer}" not in body or outer <= inner:
            errors.append(f"{job} timeout hierarchy must leave report-finalization margin")
    return errors


def validate_robolectric(build: str, lockfile: str) -> list[str]:
    errors = []
    if not re.search(r"dependencyLocking\s*\{.*?lockAllConfigurations\(\).*?"
                     r"lockMode\s*=\s*LockMode\.STRICT.*?\}", build, re.DOTALL):
        errors.append("Robolectric must lock every configuration in STRICT mode")
    dependencies = [line for line in lockfile.splitlines()
                    if line and not line.startswith("#") and not line.startswith("empty=")]
    if not dependencies or not any(line.startswith("org.robolectric:robolectric:")
                                   for line in dependencies):
        errors.append("Robolectric dependency lockfile is absent or incomplete")
    return errors


def validate_files(workflow: Path, wrapper: Path, build: Path, lockfile: Path) -> list[str]:
    errors = []
    for path, validator in ((workflow, validate_workflow), (wrapper, validate_wrapper)):
        try:
            errors.extend(validator(path.read_text(encoding="utf-8")))
        except OSError as error:
            errors.append(f"cannot read {path}: {error}")
    try:
        errors.extend(validate_robolectric(build.read_text(encoding="utf-8"),
                                           lockfile.read_text(encoding="utf-8")))
    except OSError as error:
        errors.append(f"cannot read Robolectric locking inputs: {error}")
    try:
        source = workflow.read_text(encoding="utf-8")
        errors.extend(validate_periodic_jobs(source))
        errors.extend(validate_workflow_topology(source))
        errors.extend(validate_script_references(source, workflow.parents[2] / "android"))
    except OSError:
        pass
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=Path, default=root / ".github/workflows/android-tests.yml")
    parser.add_argument("--wrapper", type=Path, default=root / "android/common/gradle/wrapper/gradle-wrapper.properties")
    parser.add_argument("--robolectric-build", type=Path, default=root / "android/common/tests/robolectric/build.gradle")
    parser.add_argument("--robolectric-lock", type=Path, default=root / "android/common/tests/robolectric/gradle.lockfile")
    args = parser.parse_args()
    errors = validate_files(args.workflow, args.wrapper, args.robolectric_build,
                            args.robolectric_lock)
    for error in errors:
        print(f"error: {error}")
    if errors:
        return 1
    print("Android CI reproducibility contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
