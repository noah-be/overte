#!/usr/bin/env python3
"""Unified catalog-driven runner for Overte's interface and project tests."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised by Windows CI once enabled there.
    fcntl = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "tests/catalog.json"
DEFAULT_TIMEOUT_SECONDS = 480
DEFAULT_REPORT_LOCK_TIMEOUT_SECONDS = 600.0
MAX_REPORT_OUTPUT_BYTES = 256 * 1024
TERMINATION_GRACE_SECONDS = 1.0


@dataclass(frozen=True)
class Suite:
    identifier: str
    kind: str
    interfaces: tuple[str, ...]
    tiers: tuple[str, ...]
    command: tuple[str, ...]
    description: str
    cwd: Path
    category: str = ""
    requirements: tuple[str, ...] = ()
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    optional_when_tool_missing: bool = False
    hardware: bool = False


def _strings(value: object, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{label} must be a {'possibly empty ' if allow_empty else 'non-empty '}list")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{label} must contain non-empty strings")
    return tuple(value)


def _suite(raw: dict, *, namespace: str, cwd: Path, interfaces: tuple[str, ...],
           tier_aliases: dict[str, str]) -> Suite:
    if not isinstance(raw, dict):
        raise ValueError("suite entries must be objects")
    local_id = raw.get("id")
    if not isinstance(local_id, str) or not local_id:
        raise ValueError("suite ids must be non-empty strings")
    identifier = f"{namespace}:{local_id}" if namespace else local_id
    kind = raw.get("kind")
    description = raw.get("description")
    if not isinstance(kind, str) or not kind:
        raise ValueError(f"suite {identifier} requires a non-empty kind")
    if not isinstance(description, str) or not description:
        raise ValueError(f"suite {identifier} requires a non-empty description")
    command = _strings(raw.get("command"), f"suite {identifier} command")
    raw_tiers = _strings(raw.get("tiers"), f"suite {identifier} tiers")
    tiers = tuple(tier_aliases.get(tier, tier) for tier in raw_tiers)
    suite_interfaces = raw.get("interfaces", list(interfaces))
    parsed_interfaces = _strings(
        suite_interfaces, f"suite {identifier} interfaces", allow_empty=False)
    requirements = _strings(
        raw.get("requirements", []), f"suite {identifier} requirements", allow_empty=True)
    timeout = raw.get("timeoutSeconds", DEFAULT_TIMEOUT_SECONDS)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise ValueError(f"suite {identifier} has invalid timeoutSeconds")
    optional = raw.get("optionalWhenToolMissing", False)
    hardware = raw.get("hardware", False)
    if not isinstance(optional, bool) or not isinstance(hardware, bool):
        raise ValueError(f"suite {identifier} has invalid execution flags")
    category = raw.get("category", "")
    if not isinstance(category, str):
        raise ValueError(f"suite {identifier} has an invalid category")
    return Suite(identifier, kind, parsed_interfaces, tiers, command, description,
                 cwd.resolve(), category, requirements, timeout, optional, hardware)


def load_catalog(path: Path = DEFAULT_CATALOG) -> list[Suite]:
    """Load the root catalog and its explicitly configured imports."""
    path = path.resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("suites"), list):
        raise ValueError(f"unsupported test catalog schema: {path}")
    suites = [
        _suite(raw, namespace="", cwd=ROOT, interfaces=("project",), tier_aliases={})
        for raw in payload["suites"]
    ]
    imports = payload.get("imports", [])
    if not isinstance(imports, list):
        raise ValueError("catalog imports must be a list")
    for item in imports:
        if not isinstance(item, dict):
            raise ValueError("catalog imports must be objects")
        namespace = item.get("namespace")
        relative = item.get("path")
        relative_cwd = item.get("cwd", ".")
        if not isinstance(namespace, str) or not namespace:
            raise ValueError("catalog imports require a namespace")
        if not isinstance(relative, str) or not relative:
            raise ValueError(f"catalog import {namespace} requires a path")
        imported_path = (ROOT / relative).resolve()
        try:
            imported_path.relative_to(ROOT)
        except ValueError as error:
            raise ValueError(f"catalog import escapes the repository: {relative}") from error
        imported = json.loads(imported_path.read_text(encoding="utf-8"))
        if imported.get("schemaVersion") != 1 or not isinstance(imported.get("suites"), list):
            raise ValueError(f"unsupported imported catalog schema: {relative}")
        interfaces = _strings(
            item.get("interfaces", [namespace]), f"catalog import {namespace} interfaces")
        aliases = item.get("tierAliases", {})
        if (not isinstance(aliases, dict)
                or any(not isinstance(key, str) or not isinstance(value, str)
                       or not key or not value for key, value in aliases.items())):
            raise ValueError(f"catalog import {namespace} has invalid tierAliases")
        cwd = (ROOT / relative_cwd).resolve()
        try:
            cwd.relative_to(ROOT)
        except ValueError as error:
            raise ValueError(f"catalog cwd escapes the repository: {relative_cwd}") from error
        if not cwd.is_dir():
            raise ValueError(f"catalog cwd does not exist: {relative_cwd}")
        all_tier = item.get("allTier")
        if all_tier is not None and (not isinstance(all_tier, str) or not all_tier):
            raise ValueError(f"catalog import {namespace} has invalid allTier")
        for raw in imported["suites"]:
            imported_suite = _suite(
                raw, namespace=namespace, cwd=cwd,
                interfaces=interfaces, tier_aliases=aliases)
            if all_tier is not None:
                imported_suite = Suite(
                    imported_suite.identifier, imported_suite.kind,
                    imported_suite.interfaces, imported_suite.tiers + (all_tier,),
                    imported_suite.command, imported_suite.description,
                    imported_suite.cwd, imported_suite.category,
                    imported_suite.requirements, imported_suite.timeout_seconds,
                    imported_suite.optional_when_tool_missing, imported_suite.hardware)
            suites.append(imported_suite)
    identifiers = [suite.identifier for suite in suites]
    duplicates = sorted({name for name in identifiers if identifiers.count(name) > 1})
    if duplicates:
        raise ValueError("duplicate suite ids: " + ", ".join(duplicates))
    return suites


def xml_safe(value: object) -> str:
    text = str(value)
    def allowed(character: str) -> bool:
        codepoint = ord(character)
        return (character in "\t\n\r" or 0x20 <= codepoint <= 0xD7FF
                or 0xE000 <= codepoint <= 0xFFFD
                or 0x10000 <= codepoint <= 0x10FFFF)
    return "".join(character if allowed(character) else "\ufffd" for character in text)


def bounded_output(value: object) -> str:
    safe = xml_safe(value)
    encoded = safe.encode("utf-8")
    if len(encoded) <= MAX_REPORT_OUTPUT_BYTES:
        return safe
    marker = b"\n... test output truncated by unified runner ...\n"
    available = MAX_REPORT_OUTPUT_BYTES - len(marker)
    head_size = available // 2
    head = encoded[:head_size].decode("utf-8", errors="ignore")
    tail = encoded[-(available - head_size):].decode("utf-8", errors="ignore")
    return head + marker.decode("ascii") + tail


def report_lock_timeout() -> float:
    value = os.environ.get(
        "OVERTE_SUITE_REPORT_LOCK_TIMEOUT_SECONDS", str(DEFAULT_REPORT_LOCK_TIMEOUT_SECONDS))
    try:
        timeout = float(value)
    except ValueError as error:
        raise ValueError("suite report lock timeout must be a non-negative number") from error
    if timeout < 0 or timeout == float("inf") or timeout != timeout:
        raise ValueError("suite report lock timeout must be a non-negative number")
    return timeout


@contextmanager
def report_lock(path: Path, timeout: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / f".{path.name}.lock"
    with lock_path.open("a+b") as lock:
        if fcntl is not None:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"timed out waiting for suite report lock after {timeout:g} seconds")
                    time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock, fcntl.LOCK_UN)


def write_junit(path: Path, results: list[dict[str, object]], profile: str) -> None:
    failures = sum(result["status"] == "failed" for result in results)
    skipped = sum(result["status"] == "skipped" for result in results)
    root = ET.Element("testsuite", {
        "name": f"overte-{profile}", "tests": str(len(results)),
        "failures": str(failures), "errors": "0", "skipped": str(skipped),
        "time": f"{sum(float(result['time']) for result in results):.3f}",
    })
    for result in results:
        case = ET.SubElement(root, "testcase", {
            "name": xml_safe(result["id"]),
            "classname": xml_safe(f"overte.{result['kind']}"),
            "time": f"{float(result['time']):.3f}",
        })
        if result["status"] == "failed":
            failure = ET.SubElement(case, "failure", {
                "message": xml_safe(result["message"]),
            })
            failure.text = bounded_output(result["output"])
        elif result["status"] == "skipped":
            ET.SubElement(case, "skipped", {"message": xml_safe(result["message"])})
        ET.SubElement(case, "system-out").text = bounded_output(result["output"])
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def select(suites: list[Suite], profile: str, names: list[str], interfaces: list[str],
           categories: list[str], allow_hardware: bool) -> list[Suite]:
    known_profiles = {tier for suite in suites for tier in suite.tiers}
    if profile not in known_profiles:
        raise ValueError(f"unknown profile: {profile}")
    known_names = {suite.identifier for suite in suites}
    requested_names = set(names)
    unknown_names = sorted(requested_names - known_names)
    if unknown_names:
        raise ValueError("unknown suites: " + ", ".join(unknown_names))
    known_interfaces = {name for suite in suites for name in suite.interfaces}
    unknown_interfaces = sorted(set(interfaces) - known_interfaces)
    if unknown_interfaces:
        raise ValueError("unknown interfaces: " + ", ".join(unknown_interfaces))
    known_categories = {suite.category for suite in suites if suite.category}
    unknown_categories = sorted(set(categories) - known_categories)
    if unknown_categories:
        raise ValueError("unknown categories: " + ", ".join(unknown_categories))
    selected = [suite for suite in suites if profile in suite.tiers]
    if requested_names:
        selected = [suite for suite in selected if suite.identifier in requested_names]
    if interfaces:
        selected = [suite for suite in selected if set(interfaces) & set(suite.interfaces)]
    if categories:
        selected = [suite for suite in selected if suite.category in categories]
    if not allow_hardware:
        selected = [suite for suite in selected if not suite.hardware]
    return selected


def _temporary_parent() -> Path:
    configured = os.environ.get("OVERTE_SUITE_TEMP_ROOT")
    candidates = ([Path(configured)] if configured else []) + [
        ROOT.parent / ".overte-test-tmp", ROOT / "build/test-tmp",
        Path(tempfile.gettempdir()),
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix="overte-probe-", dir=candidate) as probe:
                probe.write(b"test")
                probe.flush()
            return candidate
        except OSError:
            continue
    raise OSError("no writable temporary directory is available")


def _command(suite: Suite, native_build_dir: Path | None) -> list[str]:
    command = [sys.executable if part == "{python}" else part for part in suite.command]
    if suite.identifier == "native-ctest" and native_build_dir is not None:
        command.append(str(native_build_dir.resolve()))
    return command


def _run(command: list[str], cwd: Path, environment: dict[str, str], timeout: int) -> tuple[int, str]:
    options: dict[str, object] = {}
    if os.name == "posix":
        options["start_new_session"] = True
    process = subprocess.Popen(
        command, cwd=cwd, env=environment, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **options)
    try:
        output, _ = process.communicate(timeout=timeout)
        return process.returncode, output
    except subprocess.TimeoutExpired as error:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        else:  # pragma: no cover - exercised by Windows CI once enabled there.
            process.kill()
        remaining, _ = process.communicate()
        prefix = error.stdout if isinstance(error.stdout, str) else ""
        raise subprocess.TimeoutExpired(command, timeout, output=prefix + remaining)


def run(suites: list[Suite], profile: str, *, timeout_override: int | None,
        fail_fast: bool, skip_missing: bool, native_build_dir: Path | None,
        report: Path) -> int:
    results: list[dict[str, object]] = []
    temporary_parent = _temporary_parent()
    incomplete = {"id": "suite-run-incomplete", "kind": "infrastructure",
                  "status": "failed", "message": "suite run did not complete",
                  "output": "The unified runner stopped before all selected suites completed.\n",
                  "time": 0.0}
    write_junit(report, [incomplete], profile)
    for index, suite in enumerate(suites):
        missing = [tool for tool in suite.requirements if shutil.which(tool) is None]
        started = time.monotonic()
        if missing:
            status = "skipped" if skip_missing or suite.optional_when_tool_missing else "failed"
            message = "missing tools: " + ", ".join(missing)
            output = message + "\n"
        else:
            timeout = timeout_override or suite.timeout_seconds
            try:
                with tempfile.TemporaryDirectory(
                        prefix="overte-suite-", dir=temporary_parent) as temporary:
                    environment = os.environ.copy()
                    environment["TMPDIR"] = temporary
                    returncode, output = _run(
                        _command(suite, native_build_dir), suite.cwd, environment, timeout)
                if returncode == 77 and suite.optional_when_tool_missing:
                    status, message = "skipped", "required optional host tool is unavailable"
                else:
                    status = "passed" if returncode == 0 else "failed"
                    message = "" if returncode == 0 else f"exit code {returncode}"
            except subprocess.TimeoutExpired as error:
                status, message = "failed", f"timeout after {error.timeout}s"
                output = str(error.output or "") + f"\nSuite timed out after {error.timeout} seconds.\n"
            except OSError as error:
                status, message, output = "failed", "could not start suite", f"{error}\n"
        duration = time.monotonic() - started
        print(f"{status.upper():7} {suite.identifier:<40} {duration:8.3f}s", flush=True)
        if status == "failed" and output:
            print(output.rstrip(), file=sys.stderr)
        results.append({"id": suite.identifier, "kind": suite.kind, "status": status,
                        "message": message, "output": output, "time": duration})
        pending = [incomplete] if index + 1 < len(suites) and not (
            status == "failed" and fail_fast) else []
        write_junit(report, results + pending, profile)
        if status == "failed" and fail_fast:
            break
    passed = sum(result["status"] == "passed" for result in results)
    failed = sum(result["status"] == "failed" for result in results)
    skipped = sum(result["status"] == "skipped" for result in results)
    print(f"JUnit: {report}")
    print(f"Overte {profile}: {passed} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--profile", default="project-quick")
    parser.add_argument("--suite", action="append", default=[])
    parser.add_argument("--interface", action="append", default=[])
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--native-build-dir", type=Path)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--skip-missing", action="store_true")
    parser.add_argument("--allow-hardware", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout is not None and args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.junit and args.report_dir:
        parser.error("--junit and --report-dir are mutually exclusive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = arguments(argv)
    try:
        suites = load_catalog(args.catalog)
        selected = select(suites, args.profile, args.suite, args.interface,
                          args.category, args.allow_hardware)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if not selected:
        print("error: no suites selected", file=sys.stderr)
        return 2
    if args.list:
        for suite in selected:
            print(f"{suite.identifier:<42} {suite.kind:<16} {','.join(suite.interfaces)}")
        return 0
    report = args.junit
    if report is None:
        directory = args.report_dir or ROOT / "build/test-results/unified"
        report = directory / f"TEST-overte-{args.profile}.xml"
    report = report.resolve()
    try:
        with report_lock(report, report_lock_timeout()):
            return run(selected, args.profile, timeout_override=args.timeout,
                       fail_fast=args.fail_fast, skip_missing=args.skip_missing,
                       native_build_dir=args.native_build_dir, report=report)
    except (OSError, TimeoutError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
