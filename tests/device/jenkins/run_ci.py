#!/usr/bin/env python3
"""Safe Jenkins glue for the platform-neutral Overte device runner.

The helper deliberately contains no device-specific test logic.  It starts the
controlled fixture when needed, invokes the universal runner, performs an
idempotent last-chance cleanup, and stages private-safe results for Jenkins.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit


SUITES = {"smoke", "e2e-core", "accessibility", "stability", "lifecycle-stability"}
IOS_ARTIFACT_SOURCES = {
    "personal-team-preinstalled", "local-personal-team", "protected-github",
}
PUBLIC_HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
STAGED_MARKER = ".overte-device-ci-staged"
PRIVATE_BUILD_MARKER = ".overte-ios-ci-private-build"
EMBEDDED_FIXTURE_URL = "overte-e2e://fixture/scene"
PUBLIC_RESULT_NAMES = {
    "accessibility-audit.json", "cycles.jsonl", "device.json", "junit.xml",
    "metrics.json", "module.log", "pipeline-error.txt", "summary.json",
    "telemetry.jsonl",
}
IOS_SESSION_PREWARM_TIMEOUT_SECONDS = 210
IOS_SIGNED_INSTALL_PREWARM_TIMEOUT_SECONDS = 20 * 60


def fail(message: str) -> "NoReturn":
    raise ValueError(message)


def environment(name: str, *, required: bool = True, default: str = "") -> str:
    value = os.environ.get(name, default)
    if required and not value:
        fail(f"{name} is required")
    return value


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def has_symlink_component(path: Path) -> bool:
    """Return true if any existing lexical component is a symlink."""
    absolute = Path(os.path.abspath(path.expanduser()))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            if current.is_symlink():
                return True
            current.lstat()
        except FileNotFoundError:
            break
    return False


def workspace() -> Path:
    value = (environment("OVERTE_CI_WORKSPACE", required=False)
             or environment("WORKSPACE", required=False) or str(Path.cwd()))
    root = Path(value).resolve()
    if not (root / "tests/device/run.py").is_file():
        fail("OVERTE_CI_WORKSPACE does not contain the Overte device runner")
    return root


def repository_file(root: Path, variable: str) -> Path:
    value = environment(variable)
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not is_within(path, root) or not path.is_file():
        fail(f"{variable} must name an existing file inside the workspace")
    return path


def external_directory(root: Path, variable: str) -> Path:
    raw_path = Path(environment(variable)).expanduser()
    if has_symlink_component(raw_path):
        fail(f"{variable} must not contain symbolic-link components")
    path = raw_path.resolve()
    if path == root or is_within(path, root):
        fail(f"{variable} must be outside the source workspace")
    return path


def checked_suite() -> str:
    suite = environment("OVERTE_CI_SUITE")
    if suite not in SUITES:
        fail(f"OVERTE_CI_SUITE must be one of: {', '.join(sorted(SUITES))}")
    return suite


def checked_public_host() -> str:
    host = environment("OVERTE_CI_FIXTURE_PUBLIC_HOST")
    if not PUBLIC_HOST.fullmatch(host) or ".." in host:
        fail("OVERTE_CI_FIXTURE_PUBLIC_HOST must be a DNS name or IPv4 address without a URL scheme")
    return host


def checked_fixture_port() -> int:
    value = environment("OVERTE_CI_FIXTURE_PORT", required=False, default="0")
    if not value.isdigit() or not 0 <= int(value) <= 65535:
        fail("OVERTE_CI_FIXTURE_PORT must be an integer from 0 through 65535")
    return int(value)


def checked_fixture_mode() -> str:
    value = environment("OVERTE_CI_FIXTURE_MODE", required=False, default="network")
    if value not in {"embedded", "network"}:
        fail("OVERTE_CI_FIXTURE_MODE must be embedded or network")
    return value


def normalized_fixture_origin(value: object) -> str:
    if not isinstance(value, str) or not value:
        fail("fixture ready metadata has no base URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        fail("fixture ready metadata has an invalid base URL")
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or port is None
            or not 1 <= port <= 65535 or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        fail("fixture ready metadata has an invalid base URL")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def is_ios_appium_manifest(manifest: Path) -> bool:
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("adapter manifest is unreadable")
    return isinstance(value, dict) and value.get("id") == "appium-ios"


def update_ios_fixture_origin(root: Path, selector: str, base_url: object) -> None:
    """Atomically update only the selected iOS target in the private job copy."""
    raw = Path(environment("OVERTE_IOS_JOB_TARGET_CONFIG")).expanduser()
    appium_raw = Path(environment("OVERTE_APPIUM_TARGETS")).expanduser()
    if (not raw.is_absolute() or not appium_raw.is_absolute()
            or has_symlink_component(raw) or has_symlink_component(appium_raw)):
        fail("job-private iOS target configuration must be absolute and symlink-free")
    path = raw.resolve()
    appium_path = appium_raw.resolve()
    if path != appium_path or path == root or is_within(path, root):
        fail("job-private iOS target configuration is outside its allowed scope")
    before = path.lstat()
    parent_before = path.parent.lstat()
    if (not stat.S_ISREG(before.st_mode) or not stat.S_ISDIR(parent_before.st_mode)
            or before.st_uid != os.geteuid() or parent_before.st_uid != os.geteuid()
            or before.st_mode & 0o077 or parent_before.st_mode & 0o077):
        fail("job-private iOS target configuration is not private")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            fail("job-private iOS target configuration changed during validation")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as source:
            config = json.load(source)
    finally:
        os.close(descriptor)
    targets = config.get("targets") if isinstance(config, dict) else None
    if (not isinstance(config, dict) or config.get("schemaVersion") != 1
            or not isinstance(targets, list)):
        fail("job-private iOS target configuration has an invalid shape")
    matches = [item for item in targets if isinstance(item, dict)
               and item.get("selector") == selector]
    if len(matches) != 1 or matches[0].get("platform") != "ios":
        fail("private selector does not identify exactly one iOS target")
    contract = matches[0].get("testBuild")
    if not isinstance(contract, dict) or contract.get("contract") != "overte-ios-e2e-v1":
        fail("selected iOS target has no supported test-build contract")
    contract["fixtureOrigin"] = normalized_fixture_origin(base_url)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as output:
            json.dump(config, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.close(descriptor)
        descriptor = -1
        current = path.lstat()
        parent_current = path.parent.lstat()
        if ((current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
                or (parent_current.st_dev, parent_current.st_ino)
                != (parent_before.st_dev, parent_before.st_ino)
                or temporary.is_symlink()):
            fail("job-private iOS target configuration changed before activation")
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def stop_process(process: subprocess.Popen | None, grace_seconds: int = 5) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10, check=False,
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=grace_seconds)


def wait_for_ready(process: subprocess.Popen, ready_file: Path, timeout_seconds: int = 10) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if ready_file.exists():
            value = json.loads(ready_file.read_text(encoding="utf-8"))
            if isinstance(value, dict) and isinstance(value.get("sceneUrl"), str):
                return value
            fail("fixture ready file has an invalid shape")
        if process.poll() is not None:
            fail("fixture server exited before becoming ready")
        time.sleep(0.05)
    fail("fixture server did not become ready within 10 seconds")


def subprocess_group_options() -> dict[str, object]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def prewarm_ios_appium_session(root: Path, manifest: Path, selector: str,
                               child_environment: dict[str, str],
                               active_processes: list[subprocess.Popen] | None = None) -> None:
    """Create the slow physical iOS session before the common module timeout.

    Appium may spend up to three minutes connecting a preinstalled WDA over
    RemoteXPC.  The common adapter client intentionally bounds ordinary module
    operations to 60 seconds.  This Jenkins-only prewarm gives session creation
    its own bounded window; launch-smoke then reuses the persisted session and
    verifies that the single controlled app launch is still alive.
    """
    command = load_adapter_command(manifest)
    timeout = IOS_SESSION_PREWARM_TIMEOUT_SECONDS
    if child_environment.get("OVERTE_IOS_ARTIFACT_SOURCE") in {
            "local-personal-team", "protected-github"}:
        timeout = IOS_SIGNED_INSTALL_PREWARM_TIMEOUT_SECONDS
    process = subprocess.Popen(
        [*command, "invoke", "--target", selector,
         "--operation", "app.launch", "--arguments", "{}"],
        cwd=root, env=child_environment, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, **subprocess_group_options(),
    )
    if active_processes is not None:
        active_processes.append(process)
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        stop_process(process, grace_seconds=2)
        raise RuntimeError(
            "iOS Appium session did not become ready within the bounded prewarm window"
        ) from error
    finally:
        if active_processes is not None and process in active_processes:
            active_processes.remove(process)
    if returncode:
        raise RuntimeError(
            "iOS Appium session prewarm failed; inspect the private Appium service log"
        )


def run_suite() -> int:
    root = workspace()
    manifest = repository_file(root, "OVERTE_CI_ADAPTER_MANIFEST")
    catalog = repository_file(root, "OVERTE_CI_CATALOG")
    output = external_directory(root, "OVERTE_CI_OUTPUT_DIR")
    suite = checked_suite()
    selector = environment("OVERTE_DEVICE_TARGET_SELECTOR")
    if output.exists():
        fail("OVERTE_CI_OUTPUT_DIR must not already exist")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    fixture = None
    runner = None
    fixture_log_handle = None
    fixture_metadata = output.parent / f".{output.name}-fixture"
    fixture_log = fixture_metadata / "fixture.log"
    fixture_ready = fixture_metadata / "ready.json"
    runner_environment = os.environ.copy()
    previous_handlers: dict[int, object] = {}
    active_adapter_processes: list[subprocess.Popen] = []

    def forward_signal(signum: int, _frame: object) -> None:
        # Jenkins sends TERM on a Pipeline timeout. Forward it promptly to all
        # active process groups, including a session prewarm still in flight.
        for process in tuple(active_adapter_processes):
            stop_process(process, grace_seconds=1)
        stop_process(runner, grace_seconds=1)
        stop_process(fixture, grace_seconds=1)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, forward_signal)

    try:
        if suite in {"e2e-core", "accessibility"} \
                and checked_fixture_mode() == "embedded":
            runner_environment["OVERTE_E2E_SCENE_URL"] = EMBEDDED_FIXTURE_URL
        elif suite in {"e2e-core", "accessibility"}:
            host = checked_public_host()
            bind = environment("OVERTE_CI_FIXTURE_BIND", required=False, default="0.0.0.0")
            port = checked_fixture_port()
            if fixture_metadata.exists():
                fail("fixture metadata directory already exists")
            fixture_metadata.mkdir(mode=0o700)
            fixture_log_handle = fixture_log.open("w", encoding="utf-8")
            fixture = subprocess.Popen([
                sys.executable, str(root / "tests/device/fixture/serve.py"),
                "--bind", bind, "--port", str(port), "--public-host", host,
                "--ready-file", str(fixture_ready),
            ], cwd=root, stdout=fixture_log_handle, stderr=subprocess.STDOUT,
               text=True, **subprocess_group_options())
            ready = wait_for_ready(fixture, fixture_ready)
            if is_ios_appium_manifest(manifest):
                update_ios_fixture_origin(root, selector, ready.get("baseUrl"))
            runner_environment["OVERTE_E2E_SCENE_URL"] = ready["sceneUrl"]

        if is_ios_appium_manifest(manifest) and suite in {"e2e-core", "accessibility"}:
            if fixture is None:
                fail("physical iOS fixture-backed suites require the network fixture")
            prewarm_ios_appium_session(
                root, manifest, selector, runner_environment, active_adapter_processes,
            )

        command = [
            sys.executable, str(root / "tests/device/run.py"),
            "--adapter-manifest", str(manifest), "--catalog", str(catalog),
            "--suite", suite, "--target", selector, "--output-dir", str(output),
            "--require-complete",
        ]
        if environment("OVERTE_CI_ALLOW_VIRTUAL", required=False, default="0") == "1":
            command.append("--allow-virtual")

        runner = subprocess.Popen(command, cwd=root, env=runner_environment,
                                  **subprocess_group_options())

        returncode = runner.wait()
        return returncode if returncode >= 0 else 128 + abs(returncode)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        stop_process(runner)
        stop_process(fixture)
        if fixture_log_handle is not None:
            fixture_log_handle.close()
        if fixture_metadata.exists():
            output.mkdir(parents=True, exist_ok=True, mode=0o700)
            if fixture_log.exists():
                shutil.copy2(fixture_log, output / "fixture.log")
            if fixture_ready.exists():
                shutil.copy2(fixture_ready, output / "fixture-ready.json")


def load_adapter_command(manifest: Path) -> list[str]:
    # All supported manifests are below tests/device/adapters. Importing from
    # the workspace keeps command resolution identical to the runner.
    root = workspace()
    sys.path.insert(0, str(root / "tests/device"))
    try:
        from adapter_client import load_command
        return load_command(manifest)
    finally:
        sys.path.pop(0)


def cleanup_target() -> int:
    root = workspace()
    manifest = repository_file(root, "OVERTE_CI_ADAPTER_MANIFEST")
    selector = environment("OVERTE_DEVICE_TARGET_SELECTOR")
    command = load_adapter_command(manifest)
    try:
        result = subprocess.run(
            [*command, "cleanup", "--target", selector], cwd=root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
        )
    except subprocess.TimeoutExpired:
        print("error: adapter cleanup timed out", file=sys.stderr)
        return 2
    if result.returncode != 0:
        detail = (result.stderr.strip() or "adapter cleanup failed").replace(selector, "<target>")
        print(f"error: {detail}", file=sys.stderr)
        return result.returncode
    print("Target cleanup completed.")
    return 0


def contains_secret(path: Path, secret: bytes) -> bool:
    if not secret:
        return False
    overlap = max(0, len(secret) - 1)
    previous = b""
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            value = previous + chunk
            if secret in value:
                return True
            previous = value[-overlap:] if overlap else b""
    return False


def inspect_publishable(source: Path, selector: str) -> str | None:
    secret = selector.encode("utf-8")
    if source.is_symlink() or not source.is_dir():
        return "result tree is not a safe ordinary directory"
    for path in source.rglob("*"):
        if path.is_symlink():
            return "result tree contains a symbolic link"
        relative = path.relative_to(source)
        if any(selector in component for component in relative.parts):
            return "a result path contained the private target selector"
        if not path.is_dir() and not path.is_file():
            return "result tree contains an unsupported file type"
        if path.is_file() and contains_secret(path, secret):
            return "a result file contained the private target selector"
    return None


def write_synthetic_junit(destination: Path, suite: str, message: str) -> None:
    root = ET.Element("testsuite", name=f"device-{suite}", tests="1", failures="0",
                      errors="1", skipped="0", time="0")
    case = ET.SubElement(root, "testcase", classname="overte.device.infrastructure",
                         name="jenkins-result-staging", time="0")
    error = ET.SubElement(case, "error", message="device-lab infrastructure failure")
    error.text = message
    ET.ElementTree(root).write(destination / "junit.xml", encoding="utf-8",
                               xml_declaration=True)


def prepare_destination(destination: Path) -> None:
    if has_symlink_component(destination):
        fail("result staging path must not contain symbolic-link components")
    if destination.exists():
        marker = destination / STAGED_MARKER
        if (destination.is_symlink() or marker.is_symlink() or not marker.is_file()):
            fail("refusing to replace an unrecognized staging directory")
        shutil.rmtree(destination)
    destination.mkdir(parents=True, mode=0o700)
    if has_symlink_component(destination):
        fail("result staging path became a symbolic link")
    (destination / STAGED_MARKER).write_text("Owned by Overte device CI.\n", encoding="utf-8")


def copy_publishable_results(source: Path, destination: Path) -> tuple[int, int]:
    """Copy only privacy-minimal evidence; never publish raw UI/probe captures."""
    copied = 0
    private = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if path.name not in PUBLIC_RESULT_NAMES:
            private += 1
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(path, target)
        copied += 1
    policy = {"schemaVersion": 1, "copiedFiles": copied,
              "privateFilesWithheld": private,
              "rawScreenshotsPublished": False,
              "rawAccessibilityPublished": False,
              "rawProbePublished": False}
    (destination / "diagnostics-policy.json").write_text(
        json.dumps(policy, sort_keys=True) + "\n", encoding="utf-8")
    return copied, private


def stage_results() -> int:
    root = workspace()
    raw_source = Path(environment("OVERTE_CI_OUTPUT_DIR")).expanduser()
    source_path_unsafe = has_symlink_component(raw_source)
    source = raw_source.resolve()
    if source == root or is_within(source, root):
        fail("OVERTE_CI_OUTPUT_DIR must be outside the source workspace")
    raw_destination = Path(environment("OVERTE_CI_STAGED_OUTPUT_DIR")).expanduser()
    if has_symlink_component(raw_destination):
        fail("OVERTE_CI_STAGED_OUTPUT_DIR must not contain symbolic-link components")
    destination = raw_destination.resolve()
    suite = checked_suite()
    selector = environment("OVERTE_DEVICE_TARGET_SELECTOR")
    if destination == root or not is_within(destination, root):
        fail("OVERTE_CI_STAGED_OUTPUT_DIR must be inside the Jenkins workspace")
    prepare_destination(destination)

    diagnostic = None
    if source_path_unsafe:
        diagnostic = "The device result path contained a symbolic link."
    elif not source.is_dir():
        diagnostic = "The device runner produced no result directory."
    else:
        try:
            diagnostic = inspect_publishable(source, selector)
        except OSError:
            diagnostic = "The result tree could not be inspected safely."
    if diagnostic:
        (destination / "pipeline-error.txt").write_text(diagnostic + "\n", encoding="utf-8")
        write_synthetic_junit(destination, suite, diagnostic)
        print(f"Staged a private-safe infrastructure result: {diagnostic}")
        return 2

    try:
        copy_publishable_results(source, destination)
    except OSError:
        diagnostic = "The inspected result tree could not be copied completely."
        (destination / "pipeline-error.txt").write_text(diagnostic + "\n", encoding="utf-8")
        write_synthetic_junit(destination, suite, diagnostic)
        print("Device result copying failed; staged an infrastructure result.")
        return 2
    try:
        copied_diagnostic = inspect_publishable(destination, selector)
    except OSError:
        copied_diagnostic = "The copied result tree could not be inspected safely."
    if copied_diagnostic:
        prepare_destination(destination)
        (destination / "pipeline-error.txt").write_text(
            copied_diagnostic + "\n", encoding="utf-8")
        write_synthetic_junit(destination, suite, copied_diagnostic)
        print(f"Staged a private-safe infrastructure result: {copied_diagnostic}")
        return 2
    if not (destination / "junit.xml").is_file():
        diagnostic = "The device runner did not finish writing junit.xml."
        (destination / "pipeline-error.txt").write_text(diagnostic + "\n", encoding="utf-8")
        write_synthetic_junit(destination, suite, diagnostic)
        print("Device results were incomplete; staged an infrastructure result.")
        return 2
    print("Device results staged for Jenkins publication.")
    return 0


def self_check() -> int:
    root = workspace()
    commands = [
        [sys.executable, str(root / "tests/device/fixture/serve.py"), "--check"],
        [sys.executable, "-m", "unittest", "discover", "-s",
         str(root / "tests/device/self_tests"), "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s",
         str(root / "tests/device/ios"), "-p", "test_*.py", "-v"],
        [sys.executable, str(root / "tests/device/jenkins/test_run_ci.py"), "-v"],
        [sys.executable, str(root / "tests/device/jenkins/test_local_lab.py"), "-v"],
        [sys.executable, str(root / "tests/device/ios/validate_toolchain_lock.py")],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=root, check=False)
        if result.returncode:
            return result.returncode
    return 0


def ios_runtime_preflight() -> int:
    root = workspace()
    command = [
        sys.executable,
        str(root / "tests/device/ios/remotexpc_tunnel.py"),
        "status",
    ]
    return subprocess.run(command, cwd=root, timeout=15, check=False).returncode


def selected_private_ios_target(root: Path, selector: str) -> dict:
    raw = Path(environment("OVERTE_IOS_JOB_TARGET_CONFIG")).expanduser()
    if not raw.is_absolute() or has_symlink_component(raw):
        fail("job-private iOS target configuration must be absolute and symlink-free")
    path = raw.resolve()
    if path == root or is_within(path, root) or not path.is_file():
        fail("job-private iOS target configuration is outside its allowed scope")
    value = path.lstat()
    parent = path.parent.lstat()
    if (not stat.S_ISREG(value.st_mode) or not stat.S_ISDIR(parent.st_mode)
            or value.st_uid != os.geteuid() or parent.st_uid != os.geteuid()
            or stat.S_IMODE(value.st_mode) != 0o600 or parent.st_mode & 0o077):
        fail("job-private iOS target configuration is not private")
    config = json.loads(path.read_text(encoding="utf-8"))
    targets = config.get("targets") if isinstance(config, dict) else None
    matches = [item for item in targets or [] if isinstance(item, dict)
               and item.get("selector") == selector]
    if (config.get("schemaVersion") != 1 or not isinstance(targets, list)
            or len(matches) != 1
            or matches[0].get("platform") != "ios"):
        fail("private selector does not identify exactly one iOS target")
    return matches[0]


def ios_ddi_preflight() -> int:
    """Mount and bind the private pinned DDI immediately under the device lock."""
    root = workspace()
    selector = environment("OVERTE_DEVICE_TARGET_SELECTOR")
    target = selected_private_ios_target(root, selector)
    capabilities = target.get("capabilities")
    udid = capabilities.get("appium:udid") if isinstance(capabilities, dict) else None
    if (not isinstance(udid, str) or not 8 <= len(udid) <= 128
            or any(character in udid for character in "\0\r\n")):
        fail("private iOS target has no physical device identity")
    raw_ddi = Path(environment("OVERTE_IOS_DDI_ROOT")).expanduser()
    if (not raw_ddi.is_absolute() or has_symlink_component(raw_ddi)
            or raw_ddi == root or is_within(raw_ddi.resolve(), root)):
        fail("private Developer Disk Image root is outside its allowed scope")
    ddi_root = raw_ddi.resolve()
    value = ddi_root.lstat()
    if (not stat.S_ISDIR(value.st_mode) or value.st_uid != os.geteuid()
            or stat.S_IMODE(value.st_mode) != 0o700):
        fail("private Developer Disk Image root must be account-owned with mode 0700")
    command = [
        sys.executable, str(root / "tests/device/ios/remotexpc_tunnel.py"),
        "device-ddi-mount",
    ]
    request = json.dumps({
        "udid": udid,
        "image": str(ddi_root / "Image.dmg"),
        "manifest": str(ddi_root / "BuildManifest.plist"),
        "trustcache": str(ddi_root / "Image.dmg.trustcache"),
    }, separators=(",", ":"))
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, text=True, cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **subprocess_group_options(),
    )
    previous_handlers = {}

    def forward_signal(_signum: int, _frame: object) -> None:
        stop_process(process, grace_seconds=1)
        raise InterruptedError("private iOS Developer Disk Image gate was interrupted")

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, forward_signal)
    try:
        process.communicate(input=request, timeout=6 * 60)
    except subprocess.TimeoutExpired:
        stop_process(process, grace_seconds=2)
        print("error: private iOS Developer Disk Image gate timed out", file=sys.stderr)
        return 2
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    if process.returncode:
        print("error: private iOS Developer Disk Image gate failed", file=sys.stderr)
        return process.returncode
    print("iOS Personalized DDI and XCTest services are ready.")
    return 0


def private_existing_file(variable: str, root: Path) -> Path:
    raw_path = Path(environment(variable)).expanduser()
    if not raw_path.is_absolute() or has_symlink_component(raw_path):
        fail(f"{variable} must be an absolute symlink-free private file")
    path = raw_path.resolve()
    if path == root or is_within(path, root) or not path.is_file():
        fail(f"{variable} must name an existing private file")
    value = path.lstat()
    if not stat.S_ISREG(value.st_mode):
        fail(f"{variable} must name an ordinary private file")
    if os.name != "nt" and (value.st_uid != os.geteuid() or value.st_mode & 0o077):
        fail(f"{variable} must be account-owned and inaccessible to group or other users")
    return path


def prepare_private_build_root(root: Path, path: Path) -> None:
    if (not path.is_absolute() or has_symlink_component(path)
            or path == Path(path.anchor) or path == root or is_within(path, root)):
        fail("private iOS build root is unsafe")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = path.lstat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o077):
        fail("private iOS build root must be account-owned with mode 0700")
    marker = path / PRIVATE_BUILD_MARKER
    if marker.exists() or marker.is_symlink():
        fail("private iOS build root marker already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(marker, flags, 0o600)
    try:
        os.write(descriptor, b"overte-ios-ci-private-build-v1\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ios_artifact_sync() -> int:
    root = workspace()
    artifact_source = environment(
        "OVERTE_IOS_ARTIFACT_SOURCE", required=False,
        default="personal-team-preinstalled")
    if artifact_source not in IOS_ARTIFACT_SOURCES:
        fail("OVERTE_IOS_ARTIFACT_SOURCE is unsupported")
    source_config = private_existing_file("OVERTE_APPIUM_TARGETS", root)
    local_inputs: dict[str, Path] = {}
    if artifact_source == "local-personal-team":
        local_inputs = {
            option: private_existing_file(variable, root)
            for option, variable in (
                ("--unsigned-kit", "OVERTE_IOS_LOCAL_UNSIGNED_KIT"),
                ("--attestation", "OVERTE_IOS_LOCAL_ATTESTATION"),
                ("--overte-ipa", "OVERTE_IOS_LOCAL_OVERTE_IPA"),
                ("--wda-ipa", "OVERTE_IOS_LOCAL_WDA_IPA"),
            )
        }
    elif artifact_source == "personal-team-preinstalled":
        local_inputs = {
            "--attestation": private_existing_file(
                "OVERTE_IOS_PREINSTALLED_ATTESTATION", root),
        }
    raw_target_config = Path(environment("OVERTE_IOS_JOB_TARGET_CONFIG")).expanduser()
    target_config = raw_target_config.resolve()
    artifact_root = external_directory(root, "OVERTE_IOS_ARTIFACT_ROOT")
    if target_config == root or is_within(target_config, root):
        fail("OVERTE_IOS_JOB_TARGET_CONFIG must be outside the source workspace")
    if (raw_target_config.is_symlink() or target_config.exists()
            or raw_target_config.parent.exists() and raw_target_config.parent.is_symlink()):
        fail("per-build iOS target configuration already exists or has an unsafe parent")
    prepare_private_build_root(root, target_config.parent)
    shutil.copyfile(source_config, target_config)
    if os.name != "nt":
        target_config.chmod(0o600)

    command = [sys.executable, str(root / "tests/device/ios/sync_fedora_artifacts.py")]
    environment("OVERTE_DEVICE_TARGET_SELECTOR")
    if artifact_source in {"local-personal-team", "personal-team-preinstalled"}:
        command.append("local-import" if artifact_source == "local-personal-team"
                       else "personal-team-preinstalled")
        for option, path in local_inputs.items():
            command.extend((option, str(path)))
        command.extend(("--destination", str(artifact_root),
                        "--target-config", str(target_config)))
    else:
        command.extend(("--destination", str(artifact_root),
                        "--target-config", str(target_config)))
        run_id = environment("OVERTE_IOS_PRODUCER_RUN_ID", required=False)
        run_attempt = environment("OVERTE_IOS_PRODUCER_RUN_ATTEMPT", required=False)
        if bool(run_id) != bool(run_attempt):
            fail("protected producer run ID and attempt must be supplied together")
        if run_id:
            if (not run_id.isdigit() or int(run_id) <= 0
                    or not run_attempt.isdigit() or int(run_attempt) <= 0):
                fail("protected producer run ID and attempt must be positive integers")
            command.extend(("--run-id", run_id, "--run-attempt", run_attempt))
        else:
            inputs = (
                ("--qt-host-cache-key", "OVERTE_IOS_QT_HOST_CACHE_KEY"),
                ("--qt-ios-cache-key", "OVERTE_IOS_QT_IOS_CACHE_KEY"),
                ("--qt-host-artifact-prefix", "OVERTE_IOS_QT_HOST_ARTIFACT_PREFIX"),
                ("--qt-ios-artifact-prefix", "OVERTE_IOS_QT_IOS_ARTIFACT_PREFIX"),
            )
            for option, variable in inputs:
                command.extend((option, environment(variable)))
    try:
        result = subprocess.run(command, cwd=root, timeout=8 * 60 * 60 + 300, check=False)
    except BaseException:
        target_config.unlink(missing_ok=True)
        raise
    if result.returncode and target_config.exists():
        target_config.unlink()
    return result.returncode


def cleanup_ios_private() -> int:
    """Remove the exact marker-bound private iOS build tree after publication."""
    root = workspace()
    external_raw = Path(environment("OVERTE_EXTERNAL_RESULT_ROOT")).expanduser()
    artifact_raw = Path(environment("OVERTE_IOS_ARTIFACT_ROOT")).expanduser()
    config_raw = Path(environment("OVERTE_IOS_JOB_TARGET_CONFIG")).expanduser()
    values = (external_raw, artifact_raw, config_raw)
    if not all(path.is_absolute() for path in values) or any(
            has_symlink_component(path.parent if path == config_raw else path) for path in values):
        fail("private iOS cleanup paths must be absolute and symlink-free")
    external = external_raw.resolve()
    artifact = artifact_raw.resolve()
    config = config_raw.resolve()
    if (external == Path(external.anchor) or external == root or is_within(external, root)
            or artifact != external / "private-ios-artifacts"
            or config != external / "private-ios-targets.json"):
        fail("private iOS cleanup paths are outside the exact build-result scope")
    if not external.exists():
        if artifact_raw.exists() or artifact_raw.is_symlink() \
                or config_raw.exists() or config_raw.is_symlink():
            fail("private iOS cleanup root is unavailable")
        return 0
    external_stat = external.lstat()
    if (not stat.S_ISDIR(external_stat.st_mode) or external_stat.st_uid != os.geteuid()
            or external_stat.st_mode & 0o077):
        fail("private iOS cleanup root is not an account-private directory")
    marker = external / PRIVATE_BUILD_MARKER
    if (marker.is_symlink() or not marker.is_file()
            or marker.lstat().st_uid != os.geteuid()
            or marker.lstat().st_mode & 0o077
            or marker.read_text(encoding="utf-8")
            != "overte-ios-ci-private-build-v1\n"):
        fail("private iOS cleanup root has no valid build marker")
    shutil.rmtree(external)
    print("Private iOS raw results, receipts, and artifact copies removed.")
    return 0


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run-suite", "cleanup-target", "stage-results",
                                           "self-check", "ios-runtime-preflight",
                                           "ios-ddi-preflight", "ios-artifact-sync",
                                           "cleanup-ios-private"))
    return parser.parse_args()


def main() -> int:
    action = arguments().action
    if action == "run-suite":
        return run_suite()
    if action == "cleanup-target":
        return cleanup_target()
    if action == "stage-results":
        return stage_results()
    if action == "ios-runtime-preflight":
        return ios_runtime_preflight()
    if action == "ios-ddi-preflight":
        return ios_ddi_preflight()
    if action == "ios-artifact-sync":
        return ios_artifact_sync()
    if action == "cleanup-ios-private":
        return cleanup_ios_private()
    return self_check()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        message = str(error)
        selector = os.environ.get("OVERTE_DEVICE_TARGET_SELECTOR")
        if selector:
            message = message.replace(selector, "<target>")
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(2)
