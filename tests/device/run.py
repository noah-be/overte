#!/usr/bin/env python3
"""Run modular, platform-neutral Overte tests on one reserved device."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from adapter_client import load_command
from contracts import (contains_private_identity, load_capability_registry,
                       load_tablet_product_policy,
                       validate_capabilities, validate_discovered_targets,
                       validate_identifier)

if os.name == "nt":
    import msvcrt
else:
    import fcntl


ROOT = Path(__file__).resolve().parents[2]
MAX_OUTPUT_BYTES = 256 * 1024


class TargetLockTimeout(RuntimeError):
    """The target is owned by another run and was not acquired in time."""


def fail(message: str) -> "NoReturn":
    raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path.name} must contain a JSON object")
    return value


def validate_manifest(path: Path) -> dict:
    value = load_json(path)
    if value.get("schemaVersion") != 1:
        fail("unsupported adapter manifest schema")
    validate_identifier(value.get("id"), "adapter id")
    if set(value) != {"schemaVersion", "id", "command"}:
        fail("adapter manifest contains unsupported fields")
    load_command(path)
    return value


def load_modules(path: Path, suite: str) -> list[dict]:
    value = load_json(path)
    if value.get("schemaVersion") != 1 or not isinstance(value.get("modules"), list):
        fail("unsupported module catalog schema")
    selected, seen = [], set()
    registry = load_capability_registry()
    for module in value["modules"]:
        if not isinstance(module, dict):
            fail("catalog modules must be objects")
        identifier = module.get("id")
        validate_identifier(identifier, "module id")
        if identifier in seen:
            fail("module ids must be unique")
        seen.add(identifier)
        expected_fields = {"id", "description", "command", "suites", "requires",
                           "timeoutSeconds"}
        if set(module) != expected_fields:
            fail(f"module {identifier} contains unsupported or missing fields")
        command = module.get("command")
        suites = module.get("suites")
        requires = module.get("requires", [])
        timeout = module.get("timeoutSeconds", 600)
        if not isinstance(module.get("description"), str) or not module["description"]:
            fail(f"module {identifier} requires a description")
        if not isinstance(command, list) or not command or not all(
                isinstance(part, str) and part for part in command):
            fail(f"module {identifier} has an invalid command")
        if not isinstance(suites, list) or not suites or not all(
                isinstance(item, str) and item for item in suites):
            fail(f"module {identifier} has invalid suites")
        if suites != sorted(set(suites)):
            fail(f"module {identifier} suites must be unique and sorted")
        try:
            validate_capabilities(requires, registry)
        except ValueError as error:
            fail(f"module {identifier} has invalid capabilities: {error}")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
            fail(f"module {identifier} has an invalid timeout")
        if suite == "all" or suite in suites:
            selected.append(module)
    if not selected:
        fail(f"suite {suite!r} selects no modules")
    return selected


def adapter_call(command: list[str], action: str, target: str | None = None,
                 timeout: int = 30) -> object:
    argv = [*command, action]
    if target is not None:
        argv += ["--target", target]
    adapter_environment = os.environ.copy()
    adapter_environment.pop("OVERTE_E2E_TABLET_POLICY", None)
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, check=False,
                            env=adapter_environment)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"adapter {action} failed"
        if target:
            detail = detail.replace(target, "<target>")
        raise RuntimeError(detail)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"adapter {action} returned invalid JSON") from error


def discover(command: list[str], requested: str | None, allow_virtual: bool) -> dict:
    targets = validate_discovered_targets(adapter_call(command, "discover"))
    valid = []
    rejected_virtual = 0
    for target in targets:
        selector = target.get("selector")
        if target.get("physical") is not True and not allow_virtual:
            rejected_virtual += 1
            continue
        if requested is None or selector == requested:
            valid.append(target)
    if requested and not valid:
        fail("requested target is unavailable or does not satisfy the physical-device policy")
    if not valid and rejected_virtual:
        fail("no target satisfies the physical-device policy; use --allow-virtual to opt in")
    if len(valid) != 1:
        fail(f"expected exactly one eligible target, found {len(valid)}; use --target")
    return valid[0]


@contextmanager
def target_lock(reservation_key: str, lock_root: Path, timeout_seconds: float):
    lock_root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(reservation_key.encode()).hexdigest()[:24]
    path = lock_root / f"overte-device-{key}.lock"
    with path.open("a+b") as lock:
        deadline = time.monotonic() + timeout_seconds
        if os.name == "nt":
            if path.stat().st_size == 0:
                lock.write(b"\0")
                lock.flush()
            while True:
                try:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TargetLockTimeout("timed out waiting for target reservation")
                    time.sleep(0.1)
        else:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TargetLockTimeout("timed out waiting for target reservation")
                    time.sleep(0.1)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def resolve_module_command(catalog: Path, command: list[str]) -> list[str]:
    executable = Path(command[0])
    if not executable.is_absolute():
        executable = catalog.parent / executable
    executable = executable.resolve()
    if executable.suffix.lower() == ".py":
        return [sys.executable, str(executable), *command[1:]]
    return [str(executable), *command[1:]]


def stop_process(process: subprocess.Popen, grace_seconds: int = 3) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        try:
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


def bounded(text: str) -> str:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return text
    marker = b"\n... output truncated by device harness ...\n"
    size = (MAX_OUTPUT_BYTES - len(marker)) // 2
    return (encoded[:size] + marker + encoded[-size:]).decode("utf-8", errors="replace")


def redact(text: str, private_values: set[str]) -> str:
    for value in sorted(private_values, key=len, reverse=True):
        if value:
            text = text.replace(value, "<target>")
    return text


def run_module(module: dict, catalog: Path, environment: dict[str, str],
               artifact_dir: Path, selector: str, private_values: set[str],
               adapter_command: list[str],
               capabilities: set[str]) -> dict:
    artifact_dir.mkdir(parents=True, mode=0o700)
    invalid = artifact_dir / "INVALID"
    invalid.write_text("Module did not complete successfully.\n", encoding="utf-8")
    command = resolve_module_command(catalog, module["command"])
    started = time.monotonic()
    popen_options = {"cwd": ROOT, "env": environment, "text": True,
                     "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
    process = subprocess.Popen(command, **popen_options)
    timed_out = False
    try:
        output, _ = process.communicate(timeout=module.get("timeoutSeconds", 600))
    except subprocess.TimeoutExpired:
        timed_out = True
        stop_process(process)
        output, _ = process.communicate()
    output = bounded(redact(output, private_values))
    (artifact_dir / "module.log").write_text(output, encoding="utf-8")
    status = ("skipped" if process.returncode == 77 else
              "error" if process.returncode == 75 else
              "passed" if process.returncode == 0 else "failed")
    if timed_out:
        status = "failed"
        output += f"\nModule timed out after {module.get('timeoutSeconds', 600)} seconds.\n"
    if (status == "failed" and "artifact.screenshot" in capabilities
            and environment.get("OVERTE_E2E_CAPTURE_ARTIFACTS") == "1"):
        try:
            capture_environment = environment.copy()
            capture_environment.pop("OVERTE_E2E_TABLET_POLICY", None)
            capture = subprocess.run(
                [*adapter_command, "invoke", "--target", selector,
                 "--operation", "artifact.screenshot", "--arguments", "{}"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=30, check=False, env=capture_environment,
            )
            detail = (capture.stderr.strip() if capture.returncode else
                      "Failure screenshot captured.")
        except (OSError, subprocess.TimeoutExpired):
            detail = "Failure screenshot capture was unavailable."
        output += "\n" + bounded(redact(detail, private_values)) + "\n"
    (artifact_dir / "module.log").write_text(output, encoding="utf-8")
    if status == "passed":
        invalid.unlink()
    return {"id": module["id"], "description": module["description"],
            "status": status, "returncode": process.returncode,
            "durationSeconds": round(time.monotonic() - started, 3), "output": output}


def write_junit(results: list[dict], path: Path, suite: str) -> None:
    root = ET.Element("testsuite", name=f"device-{suite}", tests=str(len(results)),
                      failures=str(sum(r["status"] == "failed" for r in results)),
                      skipped=str(sum(r["status"] == "skipped" for r in results)),
                      errors=str(sum(r["status"] == "error" for r in results)),
                      time=f"{sum(r['durationSeconds'] for r in results):.3f}")
    for result in results:
        case = ET.SubElement(root, "testcase", classname="overte.device",
                             name=result["id"], time=f"{result['durationSeconds']:.3f}")
        if result["status"] == "failed":
            failure = ET.SubElement(case, "failure", message=f"exit code {result['returncode']}")
            failure.text = result["output"]
        elif result["status"] == "error":
            error = ET.SubElement(case, "error", message="device infrastructure failure")
            error.text = result["output"]
        elif result["status"] == "skipped":
            ET.SubElement(case, "skipped", message="module skipped")
        ET.SubElement(case, "system-out").text = result["output"]
    temporary = path.with_suffix(path.suffix + ".tmp")
    ET.ElementTree(root).write(temporary, encoding="utf-8", xml_declaration=True)
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-manifest", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--suite", default="smoke")
    parser.add_argument("--tablet-policy", type=Path,
                        help="versioned product expectations required by tablet-e2e")
    parser.add_argument("--target", help="private adapter selector; never persisted")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-virtual", action="store_true")
    parser.add_argument("--keep-running", action="store_true")
    parser.add_argument("--require-complete", action="store_true",
                        help="treat missing module capabilities as infrastructure errors")
    parser.add_argument("--fail-fast", action="store_true",
                        help="stop after the first failed or errored module")
    parser.add_argument("--list", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = args.adapter_manifest.resolve()
    catalog_path = args.catalog.resolve()
    manifest = validate_manifest(manifest_path)
    modules = load_modules(catalog_path, args.suite)
    if args.list:
        for module in modules:
            print(f"{module['id']}: {module['description']}")
        return 0
    tablet_policy_path = None
    if any(module["id"] == "tablet-e2e" for module in modules):
        if args.tablet_policy is None:
            fail("suite tablet-e2e requires --tablet-policy")
        tablet_policy_path = args.tablet_policy.resolve()
        load_tablet_product_policy(tablet_policy_path)
    command = load_command(manifest_path)
    target = discover(command, args.target, args.allow_virtual)
    selector = target["selector"]
    validate_capabilities(target["capabilities"])
    capabilities = set(target["capabilities"])
    if args.output_dir:
        output = args.output_dir.resolve()
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            fail("output directory must be absent or empty")
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
    else:
        output = Path(tempfile.mkdtemp(prefix="overte-device-run-"))
    if output == ROOT or ROOT in output.parents:
        fail("device artifacts must be stored outside the source worktree")
    run_started_epoch_ms = int(time.time() * 1000)
    run_started_monotonic = time.monotonic()

    environment = os.environ.copy()
    harness_python_path = str(Path(__file__).resolve().parent)
    inherited_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (harness_python_path if not inherited_python_path else
                                  f"{harness_python_path}{os.pathsep}{inherited_python_path}")
    environment.update({
        "OVERTE_DEVICE_ADAPTER_MANIFEST": str(manifest_path),
        "OVERTE_DEVICE_TARGET_SELECTOR": selector,
        "OVERTE_DEVICE_CAPABILITIES_JSON": json.dumps(sorted(capabilities)),
    })
    if tablet_policy_path is not None:
        environment["OVERTE_E2E_TABLET_POLICY"] = str(tablet_policy_path)
    results = []
    lock_root = Path(os.environ.get("OVERTE_DEVICE_LOCK_ROOT", tempfile.gettempdir()))
    try:
        lock_timeout = float(os.environ.get("OVERTE_DEVICE_LOCK_TIMEOUT_SECONDS", "600"))
    except ValueError:
        fail("OVERTE_DEVICE_LOCK_TIMEOUT_SECONDS must be numeric")
    if not 0.1 <= lock_timeout <= 86400.0:
        fail("OVERTE_DEVICE_LOCK_TIMEOUT_SECONDS must be from 0.1 through 86400")
    reservation_key = target.get("reservationKey", selector)
    private_values = {selector, reservation_key}
    try:
        with target_lock(reservation_key, lock_root, lock_timeout):
            try:
                description = adapter_call(command, "describe", selector)
                if not isinstance(description, dict):
                    fail("adapter describe result must be an object")
                if ("selector" in description
                        or contains_private_identity(description, private_values)):
                    fail("adapter describe result exposes a private target identity")
                (output / "device.json").write_text(
                    json.dumps(description, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                infrastructure_failure = False
                for module in modules:
                    if infrastructure_failure:
                        results.append({
                            "id": module["id"], "description": module["description"],
                            "status": "skipped", "returncode": 77,
                            "durationSeconds": 0.0,
                            "output": (
                                "Blocked by an earlier device infrastructure failure; "
                                "no device command was sent.\n"
                            ),
                        })
                        continue
                    missing = sorted(set(module.get("requires", [])) - capabilities)
                    if missing:
                        results.append({"id": module["id"], "description": module["description"],
                                        "status": "error" if args.require_complete else "skipped",
                                        "returncode": 75 if args.require_complete else 77,
                                        "durationSeconds": 0.0,
                                        "output": f"Missing capabilities: {', '.join(missing)}\n"})
                        continue
                    artifact = output / "modules" / module["id"]
                    module_env = environment | {"OVERTE_DEVICE_ARTIFACT_DIR": str(artifact)}
                    print(f"[{module['id']}] {module['description']}", flush=True)
                    result = run_module(module, catalog_path, module_env, artifact, selector,
                                        private_values, command, capabilities)
                    results.append(result)
                    infrastructure_failure = result["status"] == "error"
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
                detail = redact(str(error), private_values)
                results.append({"id": "target-execution",
                                "description": "Target setup or execution",
                                "status": "error", "returncode": 75,
                                "durationSeconds": 0.0, "output": detail + "\n"})
            finally:
                if not args.keep_running:
                    try:
                        adapter_call(command, "cleanup", selector)
                    except Exception as error:
                        results.append({"id": "target-cleanup", "description": "Target cleanup",
                                        "status": "error", "returncode": 75,
                                        "durationSeconds": 0.0,
                                        "output": redact(str(error), private_values) + "\n"})
    except TargetLockTimeout as error:
        results.append({"id": "target-reservation", "description": "Target reservation",
                        "status": "error", "returncode": 75,
                        "durationSeconds": 0.0, "output": str(error) + "\n"})
    summary = {"schemaVersion": 1, "adapter": manifest["id"], "suite": args.suite,
               "status": "failed" if any(r["status"] in {"failed", "error"} for r in results) else "passed",
               "results": [{key: value for key, value in result.items() if key != "output"}
                           for result in results]}
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_finished_epoch_ms = int(time.time() * 1000)
    run_manifest = {
        "schemaVersion": 1,
        "adapter": manifest["id"],
        "suite": args.suite,
        "platform": target["platform"],
        "physical": target["physical"],
        "requireComplete": args.require_complete,
        "capabilities": sorted(capabilities),
        "modules": [module["id"] for module in modules],
        "startedEpochMs": run_started_epoch_ms,
        "finishedEpochMs": run_finished_epoch_ms,
        "durationSeconds": round(time.monotonic() - run_started_monotonic, 3),
        "status": summary["status"],
    }
    (output / "run-manifest.json").write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_junit(results, output / "junit.xml", args.suite)
    print(f"Results: {output}")
    return 1 if summary["status"] == "failed" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
