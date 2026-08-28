#!/usr/bin/env python3
"""macOS desktop adapter with target-scoped OculiX automation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


DEVICE_ROOT = Path(__file__).resolve().parents[2]
if str(DEVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVICE_ROOT))

from adapters.common import (emit, fail, parse_operation_arguments,  # noqa: E402
                             read_fresh_json, state_directory)
from contracts import validate_operation_arguments  # noqa: E402


DRIVER = Path(__file__).resolve().parent / "overte.sikuli"
PROBE_SCRIPT = DEVICE_ROOT / "probe" / "overte_e2e_probe.js"


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("discover", "describe", "invoke", "cleanup"))
    parser.add_argument("--target")
    parser.add_argument("--operation")
    parser.add_argument("--arguments", default="{}")
    return parser.parse_args()


def expanded_path(value: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(value))).resolve()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class MacOSAdapter:

    def __init__(self) -> None:
        self.adapter_id = "macos-desktop"
        self.targets = self.load_targets()

    def require_interactive_host(self) -> None:
        physical = any(
            target.get("physical") is True and target.get("enabled", True)
            for target in self.targets.values()
        )
        if physical and sys.platform != "darwin":
            fail("physical macOS desktop targets require a macOS host")

    def load_targets(self) -> dict[str, dict]:
        config_value = os.environ.get("OVERTE_MACOS_TARGETS")
        if not config_value:
            fail("OVERTE_MACOS_TARGETS must name a private target configuration")
        payload = json.loads(expanded_path(config_value).read_text(encoding="utf-8"))
        entries = payload.get("targets")
        if payload.get("schemaVersion") != 1 or not isinstance(entries, list):
            fail("unsupported macOS target configuration schema")
        targets: dict[str, dict] = {}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("platform") != "macos":
                fail("macOS target configuration contains a non-macOS target")
            selector = entry.get("selector")
            if not isinstance(selector, str) or not selector or selector in targets:
                fail("macOS target selectors must be unique non-empty strings")
            if not all(isinstance(entry.get(field), str) and entry[field]
                       for field in ("executable", "windowTitle", "oculixJar",
                                     "oculixSha256")):
                fail("macOS target requires executable, windowTitle and OculiX")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", entry["oculixSha256"]):
                fail("macOS target OculiX SHA-256 must contain 64 hexadecimal digits")
            for field in ("arguments", "javaArguments"):
                if not isinstance(entry.get(field, []), list) or not all(
                        isinstance(item, str) and "\x00" not in item
                        for item in entry.get(field, [])):
                    fail(f"macOS target {field} must be a NUL-free string list")
            environment = entry.get("environment", {})
            if (not isinstance(environment, dict) or not all(
                    isinstance(key, str) and re.fullmatch(
                        r"[A-Za-z_][A-Za-z0-9_]*", key)
                    and isinstance(value, str) and "\x00" not in value
                    for key, value in environment.items())):
                fail("macOS target environment must contain safe string assignments")
            probe = entry.get("probe")
            if probe is not None:
                if not isinstance(probe, dict) or probe.get("kind") not in {
                        "host-file", "injected-test-script"}:
                    fail("macOS probe must use a supported transport")
                if (probe["kind"] == "host-file"
                        and (not isinstance(probe.get("path"), str)
                             or not probe["path"] or "\x00" in probe["path"])):
                    fail("macOS host-file probe requires a safe path")
            control = entry.get("clientControl")
            if control is not None:
                if control != {"kind": "probe-command-file"}:
                    fail("macOS clientControl must select probe-command-file")
                if not isinstance(probe, dict) or probe.get("kind") != "injected-test-script":
                    fail("macOS clientControl requires the injected in-client probe")
            targets[selector] = entry
        return targets

    @staticmethod
    def capabilities(target: dict) -> list[str]:
        values = [
            "app.foreground", "app.launch", "app.process",
            "artifact.screenshot", "input.look", "input.move", "scene.load",
        ]
        if target.get("probe"):
            values += ["probe.snapshot", "tablet.close", "tablet.open"]
        if MacOSAdapter.controlled_client(target):
            values += ["asset.load", "navigation.enter-domain", "sound.play"]
        return sorted(values)

    @staticmethod
    def controlled_client(target: dict) -> bool:
        probe = target.get("probe")
        return (isinstance(probe, dict)
                and probe.get("kind") == "injected-test-script"
                and target.get("clientControl") == {"kind": "probe-command-file"})

    def discover(self) -> list[dict]:
        self.require_interactive_host()
        return [{
            "selector": selector,
            "displayName": target.get("displayName", "Overte macOS"),
            "platform": "macos",
            "physical": target.get("physical") is True,
            "capabilities": self.capabilities(target),
        } for selector, target in sorted(self.targets.items()) if target.get("enabled", True)]

    def target(self, selector: str) -> dict:
        target = self.targets.get(selector)
        if not target or not target.get("enabled", True):
            fail("requested desktop target is not configured")
        return target

    def target_environment(
            self, target: dict, *, visual_driver: bool = False) -> dict[str, str]:
        del visual_driver
        environment = os.environ.copy()
        environment.pop("HIFI_ALLOW_MULTIPLE_INSTANCES", None)
        environment.update(target.get("environment", {}))
        return environment

    def runtime_environment(
            self, target: dict, *, visual_driver: bool = False,
            start_isolated: bool = False) -> dict[str, str]:
        del start_isolated
        return self.target_environment(target, visual_driver=visual_driver)

    def describe(self, selector: str) -> dict:
        target = self.target(selector)
        return {
            "adapter": self.adapter_id,
            "model": target.get("model", "physical desktop"),
            "os": "macos",
            "osVersion": target.get("osVersion"),
            "role": "physical-desktop-e2e",
        }

    def state_path(self, selector: str) -> Path:
        return state_directory(self.adapter_id, selector) / "process.json"

    def read_state(self, selector: str) -> dict | None:
        path = self.state_path(selector)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) and isinstance(value.get("pid"), int) else None

    @staticmethod
    def process_token(pid: int) -> str | None:
        result = subprocess.run(
            ["/bin/ps", "-o", "state=", "-o", "lstart=", "-p", str(pid)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        value = result.stdout.strip()
        state, separator, started = value.partition(" ")
        if (result.returncode != 0 or not separator or state.startswith("Z")
                or not started.strip()):
            return None
        return started.strip()

    @classmethod
    def alive(cls, pid: int, expected_token: str | None = None) -> bool:
        observed = cls.process_token(pid)
        return observed is not None and (expected_token is None or observed == expected_token)

    @classmethod
    def state_alive(cls, state: dict) -> bool:
        token = state.get("processToken")
        return isinstance(token, str) and bool(token) and cls.alive(state["pid"], token)

    @classmethod
    def process_tree_alive(cls, state: dict) -> bool:
        try:
            os.killpg(state["pid"], 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @staticmethod
    def terminate_process_tree(pid: int, *, force: bool) -> None:
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)

    def probe_path(self, selector: str, target: dict) -> Path:
        probe = target.get("probe", {})
        if probe.get("kind") == "host-file":
            path = probe.get("path")
            if not isinstance(path, str):
                fail("desktop host-file probe requires a path")
            return expanded_path(path)
        if probe.get("kind") == "injected-test-script":
            return state_directory(self.adapter_id, selector) / "probe" / "overte-probe.json"
        fail("unsupported desktop probe transport")

    def probe_script_path(self, selector: str) -> Path:
        return state_directory(self.adapter_id, selector) / "probe" / PROBE_SCRIPT.name

    def client_command_path(self, selector: str) -> Path:
        return state_directory(self.adapter_id, selector) / "probe" / "e2e-client-command.json"

    @staticmethod
    def write_private_json(path: Path, value: dict) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)

    def prepare_injected_probe(self, selector: str) -> Path:
        result_dir = self.probe_script_path(selector).parent
        result_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        script = self.probe_script_path(selector)
        temporary = script.with_suffix(script.suffix + ".tmp")
        shutil.copyfile(PROBE_SCRIPT, temporary)
        temporary.chmod(0o600)
        temporary.replace(script)
        self.write_private_json(self.client_command_path(selector), {
            "schemaVersion": 1, "commandId": "", "action": "idle",
        })
        return script

    def write_client_command(
            self, selector: str, target: dict, state: dict, command: dict) -> None:
        if not self.controlled_client(target):
            fail("desktop operation requires the controlled in-client probe channel")
        if not self.state_alive(state):
            fail("Overte desktop process changed before the in-client command")
        path = self.client_command_path(selector)
        if not path.parent.is_dir():
            fail("desktop in-client command channel was not prepared at app.launch")
        self.write_private_json(path, command)
        if not self.state_alive(state):
            fail("Overte desktop process changed while delivering the in-client command")

    @staticmethod
    def controlled_http_url(value: str, label: str) -> tuple[str, str, int | None]:
        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError as error:
            fail(f"{label} has an invalid port")
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment):
            fail(f"{label} must be an absolute credential-free HTTP(S) URL")
        return parsed.scheme, parsed.hostname.lower(), port

    def request_sound(self, selector: str, target: dict,
                      state: dict, values: dict) -> dict:
        sound_origin = self.controlled_http_url(values["url"], "sound.play url")
        command_origin = self.controlled_http_url(
            values["commandUrl"], "sound.play commandUrl")
        command_url = urlsplit(values["commandUrl"])
        if (sound_origin != command_origin or command_url.path != "/sound-command.json"
                or command_url.query):
            fail("sound.play URLs must use the same controlled fixture origin and command path")
        payload = {
            "schemaVersion": 1,
            "commandId": values["commandId"],
            "action": "play",
            "soundUrl": values["url"],
        }
        request = Request(
            values["commandUrl"],
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                fail("controlled fixture rejected the sound command")
            encoded = response.read(4097)
        if len(encoded) > 4096:
            fail("controlled fixture returned an oversized sound response")
        try:
            accepted = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("controlled fixture returned an invalid sound response") from error
        if accepted != payload:
            fail("controlled fixture did not acknowledge the exact sound command")
        self.write_client_command(selector, target, state, {
            "schemaVersion": 1,
            "commandId": "sound-channel-" + values["commandId"],
            "action": "sound-channel",
            "url": values["commandUrl"],
        })
        return {"requested": True, "commandId": values["commandId"]}

    def save_state(self, selector: str, state: dict) -> None:
        path = self.state_path(selector)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)

    def launch(self, selector: str, target: dict) -> dict:
        state = self.read_state(selector)
        if state and self.state_alive(state):
            self.visual_action(target, "focus", {"processId": state["pid"]})
            return {"launched": True}
        self.require_interactive_host()
        executable = expanded_path(target["executable"])
        if not executable.is_file():
            fail("configured Overte desktop executable was not found")
        configured_arguments = target.get("arguments", [])
        controlled = {"--allowMultipleInstances", "--display", "--testScript",
                      "--testResultsLocation", "--url"}
        if any(item in controlled or any(item.startswith(option + "=") for option in controlled)
               for item in configured_arguments):
            fail("desktop target arguments contain a harness-controlled option")
        arguments = [str(executable), *configured_arguments,
                     "--no-launcher", "--no-updater", "--no-login-suggestion",
                     "--display=Desktop"]
        initial_scene_url = os.environ.get("OVERTE_E2E_SCENE_URL")
        if initial_scene_url:
            if "://" not in initial_scene_url or "\x00" in initial_scene_url:
                fail("OVERTE_E2E_SCENE_URL must be an absolute URL")
            # Loading the fixture as part of the one authoritative process is
            # intentional. Starting Interface again merely to forward --url
            # can race its local socket, display a second mode selector, and
            # makes process lifecycle assertions ambiguous.
            arguments += ["--url", initial_scene_url]
        probe = target.get("probe", {})
        if probe.get("kind") == "injected-test-script":
            result_dir = self.probe_path(selector, target).parent
            result_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.probe_path(selector, target).unlink(missing_ok=True)
            script = self.prepare_injected_probe(selector)
            arguments += ["--testScript", str(script),
                          "--testResultsLocation", str(result_dir)]
        working = expanded_path(target.get("workingDirectory", str(executable.parent)))
        if not working.is_dir():
            fail("configured desktop working directory was not found")
        log = state_directory(self.adapter_id, selector) / "interface.log"
        with log.open("ab") as output:
            process = subprocess.Popen(
                arguments,
                cwd=working,
                stdout=output,
                stderr=subprocess.STDOUT,
                env=self.runtime_environment(target),
                start_new_session=True,
            )
        token = self.process_token(process.pid)
        if token is None:
            process.terminate()
            fail("launched Overte process could not be identified")
        state = {"pid": process.pid, "processToken": token,
                 "identity": f"{process.pid}:{token}",
                 "initialSceneUrl": initial_scene_url}
        self.save_state(selector, state)
        try:
            self.visual_action(target, "focus", {"processId": process.pid})
        except RuntimeError:
            self.cleanup(selector)
            raise
        return {"launched": True}

    def oculix(self, target: dict, action: str, values: dict) -> None:
        self.require_interactive_host()
        jar = expanded_path(target["oculixJar"])
        if not jar.is_file():
            fail("configured OculiX runtime JAR was not found")
        digest = file_sha256(jar)
        if digest.lower() != target["oculixSha256"].lower():
            fail("configured OculiX runtime JAR failed its SHA-256 check")
        java_value = target.get("javaExecutable", "java")
        is_path = os.path.isabs(java_value) or "/" in java_value or "\\" in java_value
        java = str(expanded_path(java_value)) if is_path else shutil.which(java_value)
        if not java:
            fail("Java executable for OculiX was not found")
        arguments = dict(values)
        arguments["windowTitle"] = target["windowTitle"]
        environment = self.runtime_environment(target, visual_driver=True)
        result = subprocess.run(
            [java, *target.get("javaArguments", []), "-jar", str(jar), "-r", str(DRIVER), "--", action,
             json.dumps(arguments, separators=(",", ":"))],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=60, check=False, env=environment,
        )
        if result.returncode != 0:
            streams = []
            if result.stdout.strip():
                streams.append("stdout:\n" + result.stdout.strip())
            if result.stderr.strip():
                streams.append("stderr:\n" + result.stderr.strip())
            raw_detail = "\n".join(streams)
            detail = raw_detail if len(raw_detail) <= 6000 else (
                raw_detail[:3000] + "\n... OculiX output truncated ...\n" + raw_detail[-3000:]
            )
            fail(f"OculiX action {action} failed" + (f": {detail}" if detail else ""))

    def visual_action(self, target: dict, action: str, values: dict) -> None:
        self.oculix(target, action, values)

    def invoke(self, selector: str, operation: str, values: dict) -> dict:
        target = self.target(selector)
        values = validate_operation_arguments(operation, values)
        if operation == "app.launch":
            return self.launch(selector, target)
        state = self.read_state(selector)
        running = bool(state and self.state_alive(state))
        if operation == "app.process":
            return {"running": running, "identity": state["identity"] if running else None}
        if not running:
            fail("Overte desktop process is not running")
        if operation == "app.foreground":
            probe = target.get("probe")
            if probe:
                try:
                    foreground = read_fresh_json(self.probe_path(selector, target))["application"]["foreground"]
                except (KeyError, TypeError):
                    fail("desktop probe has no foreground state")
                return {"foreground": foreground is True}
            self.visual_action(target, "focus", {"processId": state["pid"]})
            return {"foreground": True}
        if operation == "probe.snapshot":
            return read_fresh_json(self.probe_path(selector, target))
        if operation == "navigation.enter-domain":
            self.write_client_command(selector, target, state, {
                "schemaVersion": 1,
                "commandId": "navigation-" + uuid.uuid4().hex,
                "action": "navigate",
                "url": values["url"],
            })
            return {"requested": True}
        if operation == "asset.load":
            self.controlled_http_url(values["url"], "asset.load url")
            self.write_client_command(selector, target, state, {
                "schemaVersion": 1,
                "commandId": "asset-" + hashlib.sha256(json.dumps(
                    values, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")).hexdigest(),
                "action": "asset-load",
                **values,
            })
            return {"requested": True}
        if operation == "sound.play":
            return self.request_sound(selector, target, state, values)
        if operation == "scene.load":
            url = values.get("url")
            if not isinstance(url, str) or "://" not in url:
                fail("scene.load requires an absolute URL")
            if state.get("initialSceneUrl") != url:
                fail("desktop scene must be supplied at app.launch; live relaunch is forbidden")
            return {"requested": True, "lifecycle": "initial-process"}
        if operation == "input.look":
            horizontal = values.get("horizontal", 0.25)
            vertical = values.get("vertical", 0.0)
            if (not all(isinstance(item, (int, float)) and not isinstance(item, bool)
                        and math.isfinite(float(item)) for item in (horizontal, vertical))
                    or abs(float(horizontal)) > 0.45 or abs(float(vertical)) > 0.45):
                fail("desktop look input must use finite fractions from -0.45 through 0.45")
            self.visual_action(target, "look", {**values, "processId": state["pid"]})
            return {"performed": True}
        if operation == "input.move":
            duration = values.get("durationSeconds", 1.5)
            if (not isinstance(duration, (int, float)) or isinstance(duration, bool)
                    or not math.isfinite(float(duration)) or not 0.05 <= duration <= 10.0):
                fail("desktop movement duration must be from 0.05 through 10 seconds")
            self.visual_action(target, "move", {**values, "processId": state["pid"]})
            return {"performed": True}
        if operation in {"tablet.open", "tablet.close"}:
            if not target.get("probe"):
                fail("desktop tablet operation requires the in-client probe")
            desired = operation.endswith("open")
            try:
                opened = read_fresh_json(self.probe_path(selector, target))["tablet"]["open"]
            except (KeyError, TypeError):
                fail("desktop probe has no tablet state")
            if not isinstance(opened, bool):
                fail("desktop probe tablet state is invalid")
            initial = opened
            if opened is not desired:
                deadline = time.monotonic() + 5.0
                for attempt in range(3):
                    action = "tablet-open" if desired else "tablet-close"
                    self.visual_action(target, action, {
                        "processId": state["pid"],
                        "normalizeKeyUp": attempt > 0,
                    })
                    # Probe-gate every retry.  This prevents a delayed
                    # successful toggle from being toggled back by the next
                    # pulse while keeping the complete retry sequence bounded.
                    for _ in range(10):
                        current = read_fresh_json(
                            self.probe_path(selector, target))["tablet"]["open"]
                        if not isinstance(current, bool):
                            fail("desktop probe tablet state is invalid")
                        opened = current
                        if opened is desired or time.monotonic() >= deadline:
                            break
                        time.sleep(0.1)
                    if opened is desired or time.monotonic() >= deadline:
                        break
                if opened is not desired:
                    fail("desktop Tab action did not reach the requested tablet state")
            return {"performed": True, "changed": initial is not desired}
        if operation == "artifact.screenshot":
            artifact_dir = os.environ.get("OVERTE_DEVICE_ARTIFACT_DIR")
            if not artifact_dir:
                fail("screenshot operation requires an artifact directory")
            screenshot = Path(artifact_dir) / "screenshot.png"
            screenshot.unlink(missing_ok=True)
            self.oculix(target, "screenshot", {
                "artifactDirectory": artifact_dir,
                "filename": "screenshot.png",
                "processId": state["pid"],
            })
            if not screenshot.is_file() or screenshot.stat().st_size == 0:
                fail("OculiX did not create a non-empty requested screenshot")
            screenshot.chmod(0o600)
            return {"artifact": "screenshot.png"}
        fail(f"unsupported operation: {operation}")

    def cleanup(self, selector: str) -> dict:
        target = self.target(selector)
        state = self.read_state(selector)
        if state and self.state_alive(state):
            try:
                self.visual_action(target, "close", {"processId": state["pid"]})
            except RuntimeError:
                pass
            deadline = time.monotonic() + 5
            while self.state_alive(state) and time.monotonic() < deadline:
                time.sleep(0.1)
        if state and self.process_tree_alive(state):
            try:
                self.terminate_process_tree(state["pid"], force=False)
            except OSError:
                pass
            deadline = time.monotonic() + 5
            while self.process_tree_alive(state) and time.monotonic() < deadline:
                time.sleep(0.1)
            if self.process_tree_alive(state):
                try:
                    self.terminate_process_tree(state["pid"], force=True)
                except OSError:
                    pass
                deadline = time.monotonic() + 5
                while self.process_tree_alive(state) and time.monotonic() < deadline:
                    time.sleep(0.1)
            if self.process_tree_alive(state):
                fail("Overte desktop process could not be terminated")
        self.state_path(selector).unlink(missing_ok=True)
        self.client_command_path(selector).unlink(missing_ok=True)
        self.probe_script_path(selector).unlink(missing_ok=True)
        return {"cleaned": True}


def main() -> int:
    args = cli()
    adapter = MacOSAdapter()
    if args.action == "discover":
        emit(adapter.discover())
        return 0
    if not args.target:
        fail(f"{args.action} requires --target")
    if args.action == "describe":
        emit(adapter.describe(args.target))
    elif args.action == "cleanup":
        emit(adapter.cleanup(args.target))
    else:
        if not args.operation:
            fail("invoke requires --operation")
        emit(adapter.invoke(args.target, args.operation,
                            parse_operation_arguments(args.arguments)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
