#!/usr/bin/env python3
"""Appium W3C adapter for physical Android and iOS/iPadOS targets."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


REPOSITORY = Path(__file__).resolve().parents[4]
DEVICE_ROOT = Path(__file__).resolve().parents[2]
for module_path in (str(REPOSITORY), str(DEVICE_ROOT)):
    if module_path not in sys.path:
        sys.path.insert(0, module_path)

from adapters.common import (EMBEDDED_FIXTURE_URL, emit, fail,  # noqa: E402
                             parse_operation_arguments,
                             read_fresh_json, require_fresh_snapshot,
                             state_directory)


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("android", "ios"), required=True)
    parser.add_argument("action", choices=("discover", "describe", "invoke", "cleanup"))
    parser.add_argument("--target")
    parser.add_argument("--operation")
    parser.add_argument("--arguments", default="{}")
    return parser.parse_args()


class WebDriver:
    MAX_RESPONSE_BYTES = 32 * 1024 * 1024

    def __init__(self, server_url: str) -> None:
        if not server_url.startswith(("http://127.0.0.1:", "http://localhost:", "https://")):
            fail("Appium server URL must use local HTTP or HTTPS")
        self.server_url = server_url.rstrip("/")

    def call(self, method: str, path: str, payload: dict | None = None) -> object:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self.server_url + path, data=data, method=method,
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                declared = response.headers.get("Content-Length")
                if declared:
                    try:
                        declared_bytes = int(declared)
                    except ValueError:
                        fail("Appium response has an invalid Content-Length")
                    if declared_bytes < 0 or declared_bytes > self.MAX_RESPONSE_BYTES:
                        fail("Appium response exceeds the safety limit")
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
                if len(raw) > self.MAX_RESPONSE_BYTES:
                    fail("Appium response exceeds the safety limit")
                document = json.loads(raw)
        except HTTPError as error:
            fail(f"Appium request failed with HTTP {error.code}")
        except (URLError, OSError, json.JSONDecodeError):
            fail("Appium server is unavailable or returned an invalid response")
        if not isinstance(document, dict) or "value" not in document:
            fail("Appium response does not satisfy the WebDriver protocol")
        value = document["value"]
        if isinstance(value, dict) and value.get("error"):
            fail("Appium rejected the WebDriver command")
        return value

    def execute(self, session: str, script: str, arguments: dict | None = None) -> object:
        return self.call("POST", f"/session/{session}/execute/sync",
                         {"script": script, "args": [arguments or {}]})


class AppiumAdapter:
    ANDROID_DEBUG_PROBE = "files/overte-e2e/overte-probe.json"
    IOS_TEST_BUILD_CONTRACT = "overte-ios-e2e-v1"
    IOS_TEST_BUILD_PLIST_KEY = "OverteE2ETestBuildContractVersion"
    IOS_PROBE_SCRIPT_PATH = "/overte_e2e_probe.js"
    IOS_RESERVED_LAUNCH_OPTIONS = {
        "--url", "--testScript", "--testResultsLocation", "--quitWhenFinished",
    }
    IOS_RECEIPT_CONTRACT = "overte-ios-fedora-e2e-receipt-v1"
    IOS_XCODE_ONLY_CAPABILITIES = {
        "appium:usePrebuiltWDA", "appium:useXctestrunFile", "appium:prebuildWDA",
        "appium:xcodeOrgId", "appium:xcodeSigningId", "appium:xcodeConfigFile",
        "appium:keychainPath", "appium:keychainPassword",
        "appium:allowProvisioningDeviceRegistration", "appium:resultBundlePath",
    }

    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.adapter_id = f"appium-{platform}"
        self.targets = self.load_targets()

    def load_targets(self) -> dict[str, dict]:
        path_value = os.environ.get("OVERTE_APPIUM_TARGETS")
        if not path_value:
            fail("OVERTE_APPIUM_TARGETS must name a private target configuration")
        path = Path(path_value).resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("targets")
        if payload.get("schemaVersion") != 1 or not isinstance(entries, list):
            fail("unsupported Appium target configuration schema")
        targets: dict[str, dict] = {}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("platform") not in {"android", "ios"}:
                fail("Appium target configuration contains an invalid target")
            selector = entry.get("selector")
            if not isinstance(selector, str) or not selector or selector in targets:
                fail("Appium target selectors must be unique non-empty strings")
            if not isinstance(entry.get("capabilities"), dict) or not entry["capabilities"]:
                fail("Appium target requires W3C capabilities")
            if (not isinstance(entry.get("serverUrl"), str) or not entry["serverUrl"]
                    or not isinstance(entry.get("appId"), str) or not entry["appId"]):
                fail("Appium target requires serverUrl and appId")
            if not isinstance(entry.get("physical", False), bool):
                fail("Appium target physical must be boolean")
            if not isinstance(entry.get("enabled", True), bool):
                fail("Appium target enabled must be boolean")
            for section in ("process", "scene", "controls", "probe", "background"):
                if not isinstance(entry.get(section, {}), dict):
                    fail(f"Appium target {section} must be an object")
            tablet = entry.get("controls", {}).get("tablet", {})
            if not isinstance(tablet, dict):
                fail("Appium target controls.tablet must be an object")
            for point_name in ("togglePoint", "openPoint", "closePoint"):
                if point_name in tablet:
                    self.validate_fractional_point(
                        tablet[point_name], f"controls.tablet.{point_name}")
            capabilities = entry["capabilities"]
            expected_platform = "Android" if entry["platform"] == "android" else "iOS"
            if capabilities.get("platformName") != expected_platform:
                fail("Appium platformName does not match the target platform")
            expected_automation = "UiAutomator2" if entry["platform"] == "android" else "XCUITest"
            if capabilities.get("appium:automationName") != expected_automation:
                fail("Appium automationName does not match the supported platform driver")
            configured_id = capabilities.get(
                "appium:appPackage" if entry["platform"] == "android" else "appium:bundleId")
            if configured_id is not None and configured_id != entry["appId"]:
                fail("Appium application capability does not match appId")
            if entry["platform"] == "ios" and not isinstance(configured_id, str):
                fail("iOS Appium targets require appium:bundleId")
            process = entry.get("process", {})
            if process and (not isinstance(process, dict) or process.get("kind") != "adb"
                            or entry["platform"] != "android"):
                fail("only Android targets support process.kind=adb")
            if entry.get("physical") and entry["platform"] == "android":
                udid = capabilities.get("appium:udid")
                if (process.get("kind") != "adb" or not isinstance(udid, str) or not udid
                        or "appium:avd" in capabilities):
                    fail("physical Android targets require ADB/UDID and must not select an AVD")
                if process.get("selector") not in (None, udid):
                    fail("Android Appium and process observation must select the same device")
            scene = entry.get("scene", {})
            if (scene.get("kind") == "android-debug-e2e"
                    and capabilities.get("appium:autoLaunch") is not False):
                fail("Android debug E2E targets require appium:autoLaunch=false")
            probe = entry.get("probe", {})
            if probe.get("kind") == "android-run-as":
                if (entry["platform"] != "android"
                        or probe.get("relativePath") != self.ANDROID_DEBUG_PROBE):
                    fail("android-run-as probe requires the fixed app-private debug path")
            if (entry.get("physical") and scene.get("kind") == "android-debug-e2e"
                    and probe != {"kind": "android-run-as",
                                  "relativePath": self.ANDROID_DEBUG_PROBE}):
                fail("physical Android debug E2E targets require the app-private run-as probe")
            if entry["platform"] == "ios":
                self.validate_ios_host_strategy(entry)
                self.validate_ios_test_build(entry)
                self.validate_ios_artifact_receipt(entry)
            targets[selector] = entry
        return {key: value for key, value in targets.items() if value["platform"] == self.platform}

    @staticmethod
    def normalized_http_origin(value: object, label: str) -> str:
        if not isinstance(value, str) or not value:
            fail(f"{label} must be an absolute HTTP(S) origin")
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            fail(f"{label} must be an absolute HTTP(S) origin")
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"

    @classmethod
    def validate_ios_host_strategy(cls, target: dict) -> None:
        if not target.get("physical") or target.get("enabled", True) is False:
            return
        capabilities = target["capabilities"]
        udid = capabilities.get("appium:udid")
        if not isinstance(udid, str) or not udid or udid.lower() == "auto":
            fail("physical iOS targets require an explicit private appium:udid")
        if sys.platform == "darwin":
            return
        platform_version = capabilities.get("appium:platformVersion")
        match = re.fullmatch(r"([0-9]+)(?:[.][0-9]+){0,2}", platform_version or "")
        if not match or int(match.group(1)) < 18:
            fail("non-macOS physical iOS targets require appium:platformVersion 18 or newer")
        external_wda = capabilities.get("appium:webDriverAgentUrl")
        preinstalled = capabilities.get("appium:usePreinstalledWDA") is True
        if not preinstalled and not external_wda:
            fail("non-macOS physical iOS targets require preinstalled or external WDA")
        if external_wda is not None:
            if (not isinstance(external_wda, str)
                    or not external_wda.startswith(("http://127.0.0.1:",
                                                    "http://localhost:", "https://"))):
                fail("appium:webDriverAgentUrl must use local HTTP or HTTPS")
        if preinstalled:
            wda_id = capabilities.get("appium:updatedWDABundleId")
            if not isinstance(wda_id, str) or not wda_id:
                fail("preinstalled WDA requires appium:updatedWDABundleId")
            forbidden = sorted(cls.IOS_XCODE_ONLY_CAPABILITIES & set(capabilities))
            if forbidden:
                fail("non-macOS preinstalled WDA configuration contains Xcode-only capabilities")

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @classmethod
    def validate_ios_artifact_receipt(cls, target: dict, *, hash_files: bool = False) -> None:
        capabilities = target["capabilities"]
        artifact_paths = {
            "overte": capabilities.get("appium:app"),
            "wda": capabilities.get("appium:prebuiltWDAPath"),
        }
        receipt_value = target.get("artifactReceipt")
        enabled = target.get("enabled", True)
        if receipt_value is None:
            if enabled and any(artifact_paths.values()):
                fail("automatic iOS artifact installation requires artifactReceipt")
            return
        if not isinstance(receipt_value, str) or not Path(receipt_value).is_absolute():
            fail("iOS artifactReceipt must be an absolute private path")
        receipt_path = Path(receipt_value)
        if not receipt_path.is_file():
            if enabled:
                fail("enabled iOS artifactReceipt does not exist")
            return
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fail("iOS artifactReceipt is unreadable")
        if not isinstance(receipt, dict) or set(receipt) != {
            "schemaVersion", "contract", "sourceRevision", "overte", "wda", "toolchain"
        }:
            fail("iOS artifactReceipt has unexpected or missing fields")
        if (receipt.get("schemaVersion") != 1
                or receipt.get("contract") != cls.IOS_RECEIPT_CONTRACT
                or not isinstance(receipt.get("sourceRevision"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", receipt["sourceRevision"])):
            fail("iOS artifactReceipt contract is invalid")
        lock = json.loads((DEVICE_ROOT / "toolchain.lock.json").read_text(encoding="utf-8"))
        expected_toolchain = {
            "xcuitestDriver": lock["appium"]["drivers"]["xcuitest"]["version"],
            "remoteXpc": lock["appium"]["iosRuntime"]["remoteXpc"]["version"],
            "webdriverAgent": lock["appium"]["iosRuntime"]["webdriverAgent"]["version"],
        }
        if receipt.get("toolchain") != expected_toolchain:
            fail("iOS artifactReceipt does not match the pinned Fedora toolchain")
        for role in ("overte", "wda"):
            item = receipt.get(role)
            if (not isinstance(item, dict) or set(item) != {"path", "sha256", "bundleId"}
                    or not isinstance(item.get("path"), str)
                    or not Path(item["path"]).is_absolute()
                    or not isinstance(item.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                    or not isinstance(item.get("bundleId"), str)):
                fail(f"iOS artifactReceipt {role} entry is invalid")
            if artifact_paths[role] != item["path"]:
                fail(f"iOS {role} capability path does not match artifactReceipt")
            artifact = Path(item["path"])
            if not artifact.is_file():
                fail(f"iOS {role} artifact from receipt does not exist")
            if hash_files and cls._sha256_file(artifact) != item["sha256"]:
                fail(f"iOS {role} artifact failed its receipt SHA-256")
        if receipt["overte"]["bundleId"] != target["appId"]:
            fail("iOS artifactReceipt Overte bundle does not match appId")
        suffix = capabilities.get("appium:updatedWDABundleIdSuffix", ".xctrunner")
        if not isinstance(suffix, str):
            fail("appium:updatedWDABundleIdSuffix must be a string")
        if receipt["wda"]["bundleId"] != capabilities.get("appium:updatedWDABundleId", "") + suffix:
            fail("iOS artifactReceipt WDA bundle does not match Appium capabilities")
        target["_artifactReceiptSha256"] = cls._sha256_file(receipt_path)

    @classmethod
    def validate_ios_test_build(cls, target: dict) -> None:
        behavioral_sections = bool(target.get("scene") or target.get("probe")
                                   or target.get("controls"))
        contract = target.get("testBuild")
        if contract is None:
            if behavioral_sections:
                fail("iOS scene, probe and controls require the fail-closed testBuild contract")
            return
        if not isinstance(contract, dict):
            fail("iOS testBuild must be an object")
        allowed_contract_fields = {
            "contract", "contractVersion", "fixtureOrigin", "probeScriptPath",
            "resultsDirectory", "launchArguments", "launchEnvironment",
        }
        if set(contract) - allowed_contract_fields:
            fail("iOS testBuild contains unsupported fields")
        if contract.get("contract") != cls.IOS_TEST_BUILD_CONTRACT:
            fail(f"iOS testBuild contract must be {cls.IOS_TEST_BUILD_CONTRACT}")
        if contract.get("contractVersion") != 1:
            fail("iOS testBuild contractVersion must be 1")
        origin = cls.normalized_http_origin(contract.get("fixtureOrigin"),
                                            "iOS testBuild fixtureOrigin")
        if contract.get("probeScriptPath") != cls.IOS_PROBE_SCRIPT_PATH:
            fail(f"iOS testBuild probeScriptPath must be {cls.IOS_PROBE_SCRIPT_PATH}")

        results = contract.get("resultsDirectory")
        if (not isinstance(results, str) or not results or "\\" in results
                or PurePosixPath(results).is_absolute()
                or any(part in {"", ".", ".."} for part in PurePosixPath(results).parts)):
            fail("iOS testBuild resultsDirectory must be a safe relative Documents path")

        arguments = contract.get("launchArguments", [])
        if (not isinstance(arguments, list) or not all(isinstance(item, str) and item
                                                       for item in arguments)):
            fail("iOS testBuild launchArguments must contain non-empty strings")
        for argument in arguments:
            option = argument.split("=", 1)[0]
            if option in cls.IOS_RESERVED_LAUNCH_OPTIONS:
                fail(f"iOS testBuild launchArguments must not override {option}")

        environment = contract.get("launchEnvironment")
        if (not isinstance(environment, dict)
                or environment.get("OVERTE_E2E_TEST_BUILD") != "1"):
            fail("iOS testBuild launchEnvironment must assert OVERTE_E2E_TEST_BUILD=1")
        if not all(isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
                   and isinstance(value, str) for key, value in environment.items()):
            fail("iOS testBuild launchEnvironment must contain string environment variables")

        capabilities = target["capabilities"]
        if capabilities.get("appium:autoLaunch") is not False:
            fail("iOS testBuild targets require appium:autoLaunch=false")
        if target.get("scene") != {"kind": "ios-test-build"}:
            fail("iOS testBuild targets require scene.kind=ios-test-build")
        if target.get("probe") != {"kind": "ios-documents"}:
            fail("iOS testBuild targets require probe.kind=ios-documents")
        if contract.get("fixtureOrigin") != origin:
            fail("iOS testBuild fixtureOrigin must use normalized lowercase spelling")

    @staticmethod
    def advertised_capabilities(target: dict) -> list[str]:
        values = ["accessibility.snapshot", "app.foreground", "app.launch",
                  "artifact.screenshot", "lifecycle.background"]
        process = target.get("process", {})
        if target["platform"] == "ios" or process.get("kind") == "adb":
            values.append("app.process")
        if target["platform"] == "android" and process.get("kind") == "adb":
            values.append("telemetry.snapshot")
        controls = target.get("controls", {})
        if target.get("scene"):
            values.append("scene.load")
        if target.get("probe"):
            values.append("probe.snapshot")
        if isinstance(controls.get("look"), dict):
            values.append("input.look")
        if isinstance(controls.get("move"), dict):
            values.append("input.move")
        tablet = controls.get("tablet")
        if isinstance(tablet, dict) and (tablet.get("toggleAccessibilityId") or
                                         tablet.get("togglePoint") or
                                         (tablet.get("openAccessibilityId") and
                                          tablet.get("closeAccessibilityId")) or
                                         (tablet.get("openPoint") and
                                          tablet.get("closePoint"))):
            values += ["tablet.close", "tablet.open"]
        return sorted(values)

    @staticmethod
    def validate_fractional_point(value: object, label: str) -> list[float]:
        if (not isinstance(value, list) or len(value) != 2
                or not all(isinstance(item, (int, float)) and not isinstance(item, bool)
                           and math.isfinite(float(item)) and 0.0 <= float(item) < 1.0
                           for item in value)):
            fail(f"{label} must contain two finite fractions from 0 inclusive through 1 exclusive")
        return [float(value[0]), float(value[1])]

    def discover(self) -> list[dict]:
        return [{
            "selector": selector,
            "displayName": target.get("displayName", f"Appium {self.platform}"),
            "platform": self.platform,
            "physical": target.get("physical") is True,
            "capabilities": self.advertised_capabilities(target),
        } for selector, target in sorted(self.targets.items()) if target.get("enabled", True)]

    def target(self, selector: str) -> dict:
        target = self.targets.get(selector)
        if not target or not target.get("enabled", True):
            fail("requested Appium target is not configured")
        return target

    def describe(self, selector: str) -> dict:
        target = self.target(selector)
        return {
            "adapter": self.adapter_id,
            "model": target.get("model"),
            "os": "Android" if self.platform == "android" else "iOS/iPadOS",
            "osVersion": target.get("osVersion"),
            "role": target.get("role", "physical-mobile-e2e"),
        }

    def state_path(self, selector: str) -> Path:
        return state_directory(self.adapter_id, selector) / "session.json"

    def read_session(self, selector: str) -> dict | None:
        path = self.state_path(selector)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) and isinstance(value.get("sessionId"), str) else None

    def save_session(self, selector: str, value: dict) -> None:
        path = self.state_path(selector)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)

    def attest_physical_target(self, client: WebDriver, session: str, target: dict) -> None:
        if not target.get("physical"):
            return
        if self.platform == "ios":
            value = client.execute(session, "mobile: deviceInfo")
            if not isinstance(value, dict) or value.get("isSimulator") not in (False, 0):
                fail("configured physical iOS target is a simulator or cannot be attested")
            if target.get("testBuild"):
                apps = client.execute(session, "mobile: listApps", {
                    "applicationType": "User",
                    "returnAttributes": ["CFBundleIdentifier", "UIFileSharingEnabled",
                                         self.IOS_TEST_BUILD_PLIST_KEY],
                })
                installed = apps.get(target["appId"]) if isinstance(apps, dict) else None
                if (not isinstance(installed, dict)
                        or installed.get("CFBundleIdentifier") != target["appId"]
                        or installed.get("UIFileSharingEnabled") not in (True, 1)
                        or installed.get(self.IOS_TEST_BUILD_PLIST_KEY) != 1):
                    fail("installed iOS application does not attest the E2E test-build contract")
        else:
            from android.common.device_tests.adb_transport import AdbTransport
            device = target["capabilities"]["appium:udid"]
            adb = AdbTransport()
            adb.require_connected(device)
            if adb.prop(device, "ro.kernel.qemu") == "1":
                fail("configured physical Android target is an emulator")

    def ensure_session(self, selector: str) -> tuple[WebDriver, str, dict]:
        target = self.target(selector)
        client = WebDriver(target["serverUrl"])
        state = self.read_session(selector)
        fingerprint = hashlib.sha256(json.dumps(target, sort_keys=True,
                                                 separators=(",", ":")).encode()).hexdigest()
        previous_generation = int((state or {}).get("generation", 0))
        if state and state.get("targetFingerprint") != fingerprint:
            self.state_path(selector).unlink(missing_ok=True)
            state = None
        if state:
            try:
                client.call("GET", f"/session/{state['sessionId']}")
                self.attest_physical_target(client, state["sessionId"], target)
                return client, state["sessionId"], state
            except RuntimeError:
                self.state_path(selector).unlink(missing_ok=True)
        if self.platform == "ios":
            self.validate_ios_artifact_receipt(target, hash_files=True)
        value = client.call("POST", "/session", {
            "capabilities": {"alwaysMatch": target["capabilities"], "firstMatch": [{}]},
        })
        if not isinstance(value, dict) or not isinstance(value.get("sessionId"), str):
            fail("Appium did not create a WebDriver session")
        generation = previous_generation + 1
        state = {"sessionId": value["sessionId"], "generation": generation,
                 "targetFingerprint": fingerprint}
        self.save_session(selector, state)
        self.attest_physical_target(client, value["sessionId"], target)
        return client, value["sessionId"], state

    def query_app_state(self, client: WebDriver, session: str, target: dict) -> int:
        key = "appId" if self.platform == "android" else "bundleId"
        value = client.execute(session, "mobile: queryAppState", {key: target["appId"]})
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4:
            fail("Appium queryAppState returned an invalid state")
        return value

    @staticmethod
    def expand(value: object, variables: dict[str, object]) -> object:
        if isinstance(value, str) and value.startswith("$") and value[1:] in variables:
            return variables[value[1:]]
        if isinstance(value, dict):
            return {key: AppiumAdapter.expand(item, variables) for key, item in value.items()}
        if isinstance(value, list):
            return [AppiumAdapter.expand(item, variables) for item in value]
        return value

    def gesture(self, client: WebDriver, session: str, definition: dict,
                duration_override: float | None = None,
                end_override: list[float] | None = None) -> None:
        rect = client.call("GET", f"/session/{session}/window/rect")
        if not isinstance(rect, dict) or not all(isinstance(rect.get(key), (int, float))
                                                 for key in ("width", "height")):
            fail("Appium window rectangle is invalid")
        start, end = definition.get("start"), end_override or definition.get("end")
        if not (isinstance(start, list) and isinstance(end, list) and
                len(start) == len(end) == 2 and all(isinstance(item, (int, float))
                                                     and not isinstance(item, bool)
                                                     and math.isfinite(float(item))
                                                     for item in start + end)):
            fail("Appium gesture requires fractional start and end coordinates")
        if not all(0.0 <= item < 1.0 for item in start + end):
            fail("Appium gesture coordinates must be from 0 inclusive through 1 exclusive")
        duration_value = (duration_override if duration_override is not None
                          else definition.get("durationSeconds", 0.7))
        if (not isinstance(duration_value, (int, float)) or isinstance(duration_value, bool)
                or not math.isfinite(float(duration_value))
                or not 0.05 <= duration_value <= 10.0):
            fail("Appium gesture duration must be from 0.05 through 10 seconds")
        duration = int(duration_value * 1000)
        origin_x = int(rect.get("x", 0))
        origin_y = int(rect.get("y", 0))
        start_x = origin_x + int((rect["width"] - 1) * start[0])
        start_y = origin_y + int((rect["height"] - 1) * start[1])
        end_x = origin_x + int((rect["width"] - 1) * end[0])
        end_y = origin_y + int((rect["height"] - 1) * end[1])
        if definition.get("mode", "swipe") not in {"swipe", "hold"}:
            fail("Appium gesture mode must be swipe or hold")
        pointer_actions = [
            {"type": "pointerMove", "duration": 0, "origin": "viewport",
             "x": start_x, "y": start_y},
            {"type": "pointerDown", "button": 0},
        ]
        if definition.get("mode") == "hold":
            pointer_actions += [
                {"type": "pointerMove", "duration": 150, "origin": "viewport",
                 "x": end_x, "y": end_y},
                {"type": "pause", "duration": duration},
            ]
        else:
            pointer_actions.append(
                {"type": "pointerMove", "duration": duration, "origin": "viewport",
                 "x": end_x, "y": end_y})
        pointer_actions.append({"type": "pointerUp", "button": 0})
        body = {"actions": [{
            "type": "pointer", "id": "overte-touch", "parameters": {"pointerType": "touch"},
            "actions": pointer_actions,
        }]}
        client.call("POST", f"/session/{session}/actions", body)

    def tap_fractional_point(self, client: WebDriver, session: str,
                             value: object, label: str) -> None:
        point = self.validate_fractional_point(value, label)
        rect = client.call("GET", f"/session/{session}/window/rect")
        if not isinstance(rect, dict) or not all(isinstance(rect.get(key), (int, float))
                                                 for key in ("width", "height")):
            fail("Appium window rectangle is invalid")
        x = int(rect.get("x", 0)) + int((rect["width"] - 1) * point[0])
        y = int(rect.get("y", 0)) + int((rect["height"] - 1) * point[1])
        if self.platform == "android":
            client.execute(session, "mobile: clickGesture", {"x": x, "y": y})
            return
        body = {"actions": [{
            "type": "pointer", "id": "overte-tap", "parameters": {"pointerType": "touch"},
            "actions": [
                {"type": "pointerMove", "duration": 0, "origin": "viewport", "x": x, "y": y},
                {"type": "pointerDown", "button": 0},
                {"type": "pause", "duration": 100},
                {"type": "pointerUp", "button": 0},
            ],
        }]}
        client.call("POST", f"/session/{session}/actions", body)
        client.call("DELETE", f"/session/{session}/actions")

    def click_accessibility(self, client: WebDriver, session: str, identifier: str) -> None:
        value = client.call("POST", f"/session/{session}/element",
                            {"using": "accessibility id", "value": identifier})
        if not isinstance(value, dict):
            fail("Appium did not return an element reference")
        element = value.get("element-6066-11e4-a52e-4f735466cecf") or value.get("ELEMENT")
        if not isinstance(element, str):
            fail("Appium element reference is invalid")
        client.call("POST", f"/session/{session}/element/{element}/click", {})

    def probe_snapshot(self, client: WebDriver, session: str, target: dict) -> dict:
        probe = target.get("probe", {})
        kind = probe.get("kind")
        if kind == "host-file":
            path = probe.get("path")
            if not isinstance(path, str):
                fail("host-file probe requires a path")
            return read_fresh_json(Path(os.path.expandvars(path)).resolve())
        if kind == "appium-pull-file":
            remote = probe.get("remotePath")
            if not isinstance(remote, str) or ".." in remote:
                fail("Appium pull-file probe requires a safe remotePath")
            value = client.execute(session, probe.get("script", "mobile: pullFile"),
                                   {"remotePath": remote})
            if not isinstance(value, str):
                fail("Appium probe pull did not return base64 content")
            try:
                snapshot = json.loads(base64.b64decode(value, validate=True).decode("utf-8"))
            except (ValueError, UnicodeError, json.JSONDecodeError):
                fail("Appium probe pull returned invalid content")
            return require_fresh_snapshot(snapshot)
        if kind == "android-run-as" and self.platform == "android":
            if probe.get("relativePath") != self.ANDROID_DEBUG_PROBE:
                fail("android-run-as probe requires the fixed app-private debug path")
            process = target.get("process", {})
            device = process.get("selector") or target["capabilities"].get("appium:udid")
            if (process.get("kind") != "adb" or not isinstance(device, str) or not device
                    or device.startswith("REPLACE_")):
                fail("Android run-as probe requires a private ADB device selector")
            from android.common.device_tests.adb_transport import AdbTransport
            adb = AdbTransport()
            adb.require_connected(device)
            raw = adb.read_debug_app_file(
                device, target["appId"], self.ANDROID_DEBUG_PROBE)
            try:
                snapshot = json.loads(raw)
            except json.JSONDecodeError:
                fail("Android run-as probe snapshot is unavailable or incomplete")
            return require_fresh_snapshot(snapshot)
        if kind == "ios-documents" and self.platform == "ios":
            contract = target.get("testBuild", {})
            remote = (f"@{target['appId']}:documents/"
                      f"{contract['resultsDirectory']}/overte-probe.json")
            value = client.execute(session, "mobile: pullFile", {"remotePath": remote})
            if not isinstance(value, str):
                fail("iOS Documents probe pull did not return base64 content")
            try:
                snapshot = json.loads(base64.b64decode(value, validate=True).decode("utf-8"))
            except (ValueError, UnicodeError, json.JSONDecodeError):
                fail("iOS Documents probe pull returned invalid content")
            return require_fresh_snapshot(snapshot)
        fail("unsupported Appium probe transport")

    def process_state(self, selector: str, client: WebDriver, session: str,
                      state: dict, target: dict) -> dict:
        app_state = self.query_app_state(client, session, target)
        if app_state < 2:
            return {"running": False, "identity": None}
        if self.platform == "android":
            process = target.get("process", {})
            if process.get("kind") != "adb":
                fail("Android app.process requires process.kind=adb")
            device = process.get("selector") or target["capabilities"].get("appium:udid")
            if not isinstance(device, str) or not device or device.startswith("REPLACE_"):
                fail("Android ADB process observation requires a private device selector")
            from android.common.device_tests.adb_transport import AdbTransport
            adb = AdbTransport()
            adb.require_connected(device)
            return adb.process_state(device, target["appId"])

        identity = state.get("processIdentity")
        if app_state == 4:
            info = client.execute(session, "mobile: activeAppInfo")
            pid = info.get("pid") if isinstance(info, dict) else None
            bundle = info.get("bundleId") if isinstance(info, dict) else None
            if (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0
                    or bundle != target["appId"]):
                fail("XCUITest activeAppInfo did not identify the configured application")
            identity = str(pid)
            state["processIdentity"] = identity
            self.save_session(selector, state)
        if not isinstance(identity, str) or not identity:
            fail("iOS process identity is unavailable until the app is foregrounded")
        return {"running": True, "identity": identity}

    @staticmethod
    def start_android_e2e(client: WebDriver, session: str, target: dict) -> None:
        component = f"{target['appId']}/.E2eLauncherActivity"
        client.execute(session, "mobile: startActivity", {
            "intent": component,
            "stop": True,
            "wait": False,
        })

    def launch_ios_test_build(self, selector: str, client: WebDriver, session: str,
                              state: dict, target: dict, scene_url: str | None = None,
                              *, force_relaunch: bool = False) -> None:
        contract = target["testBuild"]
        arguments = list(contract.get("launchArguments", []))
        if scene_url is not None:
            parsed = urlsplit(scene_url)
            origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
            if origin != contract["fixtureOrigin"]:
                fail("iOS test-build scene URL must use the configured fixtureOrigin")
            if parsed.scheme not in {"http", "https"} or not parsed.path:
                fail("iOS test-build scene URL must be an absolute HTTP(S) resource")
            probe_url = origin + self.IOS_PROBE_SCRIPT_PATH
            arguments += [
                "--url", scene_url,
                "--testScript", probe_url,
                "--testResultsLocation", contract["resultsDirectory"],
            ]
        if not force_relaunch and self.query_app_state(client, session, target) >= 2:
            client.execute(session, "mobile: activateApp", {"bundleId": target["appId"]})
            return
        state.pop("processIdentity", None)
        self.save_session(selector, state)
        if force_relaunch:
            client.execute(session, "mobile: terminateApp", {"bundleId": target["appId"]})
        client.execute(session, "mobile: launchApp", {
            "bundleId": target["appId"],
            "arguments": arguments,
            "environment": contract["launchEnvironment"],
        })

    def invoke(self, selector: str, operation: str, values: dict) -> dict:
        target = self.target(selector)
        client, session, state = self.ensure_session(selector)
        if operation == "app.launch":
            if self.platform == "android" and target.get("scene", {}).get("kind") == "android-debug-e2e":
                if self.query_app_state(client, session, target) >= 2:
                    client.execute(session, "mobile: activateApp", {"appId": target["appId"]})
                else:
                    self.start_android_e2e(client, session, target)
            elif self.platform == "ios" and target.get("testBuild"):
                self.launch_ios_test_build(selector, client, session, state, target)
            else:
                key = "appId" if self.platform == "android" else "bundleId"
                script = "mobile: activateApp" if self.platform == "android" else "mobile: launchApp"
                client.execute(session, script, {key: target["appId"]})
            return {"launched": True}
        if operation == "app.process":
            return self.process_state(selector, client, session, state, target)
        if operation == "app.foreground":
            return {"foreground": self.query_app_state(client, session, target) == 4}
        if operation == "lifecycle.background":
            default = ("mobile: pressKey", {"keycode": 3}) if self.platform == "android" else (
                "mobile: backgroundApp", {"seconds": -1})
            config = target.get("background", {})
            client.execute(session, config.get("script", default[0]), config.get("arguments", default[1]))
            return {"backgrounded": True}
        if operation == "telemetry.snapshot":
            process = target.get("process", {})
            if self.platform != "android" or process.get("kind") != "adb":
                fail("Appium telemetry requires an Android process.kind=adb target")
            device = process.get("selector") or target["capabilities"].get("appium:udid")
            if not isinstance(device, str) or not device or device.startswith("REPLACE_"):
                fail("Android telemetry requires a private ADB device selector")
            from android.common.device_tests.adb_transport import AdbTransport
            adb = AdbTransport()
            adb.require_connected(device)
            return adb.telemetry_snapshot(device, target["appId"])
        if operation == "scene.load":
            scene = target.get("scene", {})
            url = values.get("url")
            if not isinstance(url, str) or "://" not in url:
                fail("scene.load requires an absolute URL")
            if scene.get("kind") == "android-debug-e2e" and self.platform == "android":
                if url != EMBEDDED_FIXTURE_URL:
                    fail("Android debug scene.load accepts only the embedded fixture URL")
                self.start_android_e2e(client, session, target)
                return {"requested": True, "verification": "fixture-markers"}
            if scene.get("kind") == "ios-test-build" and self.platform == "ios":
                self.launch_ios_test_build(
                    selector, client, session, state, target, url, force_relaunch=True,
                )
                return {"requested": True, "verification": "fixture-markers"}
            if not isinstance(scene.get("script"), str):
                fail("Appium target has no scene deep-link strategy")
            variables = {"url": url, "appId": target["appId"]}
            client.execute(session, scene["script"], self.expand(scene.get("arguments", {}), variables))
            return {"requested": True}
        if operation == "probe.snapshot":
            return self.probe_snapshot(client, session, target)
        if operation == "accessibility.snapshot":
            source = client.call("GET", f"/session/{session}/source")
            if not isinstance(source, str):
                fail("Appium page source is not text")
            artifact_dir = os.environ.get("OVERTE_DEVICE_ARTIFACT_DIR")
            artifact = None
            if artifact_dir and os.environ.get("OVERTE_E2E_CAPTURE_ARTIFACTS") == "1":
                destination = Path(artifact_dir) / "accessibility.xml"
                destination.write_text(source, encoding="utf-8")
                destination.chmod(0o600)
                artifact = destination.name
            return {"source": source, "artifact": artifact}
        if operation == "artifact.screenshot":
            encoded = client.call("GET", f"/session/{session}/screenshot")
            artifact_dir = os.environ.get("OVERTE_DEVICE_ARTIFACT_DIR")
            if not isinstance(encoded, str) or not artifact_dir:
                fail("screenshot operation requires an artifact directory")
            try:
                content = base64.b64decode(encoded, validate=True)
            except ValueError:
                fail("Appium screenshot is not valid base64")
            if not content:
                fail("Appium screenshot is empty")
            destination = Path(artifact_dir) / "screenshot.png"
            destination.unlink(missing_ok=True)
            destination.write_bytes(content)
            destination.chmod(0o600)
            return {"artifact": destination.name}
        controls = target.get("controls", {})
        if operation == "input.look":
            look = controls.get("look", {})
            horizontal = values.get("horizontal", 0.25)
            vertical = values.get("vertical", 0.0)
            if (not all(isinstance(item, (int, float)) and not isinstance(item, bool)
                        and math.isfinite(float(item)) for item in (horizontal, vertical))
                    or abs(float(horizontal)) > 0.45 or abs(float(vertical)) > 0.45):
                fail("Appium look input must use finite fractions from -0.45 through 0.45")
            start = look.get("start")
            end = ([float(start[0]) - float(horizontal), float(start[1]) - float(vertical)]
                   if isinstance(start, list) and len(start) == 2 else None)
            self.gesture(client, session, look, end_override=end)
            return {"performed": True}
        if operation == "input.move":
            direction = values.get("direction", "forward")
            movement = controls.get("move", {}).get(direction)
            if not isinstance(movement, dict):
                fail("Appium target does not define this movement direction")
            duration = values.get("durationSeconds")
            self.gesture(client, session, movement,
                         float(duration) if isinstance(duration, (int, float)) else None)
            return {"performed": True}
        if operation in {"tablet.open", "tablet.close"}:
            tablet = controls.get("tablet", {})
            key = "openAccessibilityId" if operation.endswith("open") else "closeAccessibilityId"
            identifier = tablet.get(key) or tablet.get("toggleAccessibilityId")
            if isinstance(identifier, str) and identifier:
                self.click_accessibility(client, session, identifier)
            else:
                point_key = "openPoint" if operation.endswith("open") else "closePoint"
                point = tablet.get(point_key) or tablet.get("togglePoint")
                if point is None:
                    fail("Appium target does not define a tablet control")
                self.tap_fractional_point(client, session, point,
                                          f"tablet.{point_key}")
            return {"performed": True}
        fail(f"unsupported operation: {operation}")

    def cleanup(self, selector: str) -> dict:
        target = self.target(selector)
        state = self.read_session(selector)
        if state:
            client = WebDriver(target["serverUrl"])
            try:
                key = "appId" if self.platform == "android" else "bundleId"
                client.execute(state["sessionId"], "mobile: terminateApp", {key: target["appId"]})
            except RuntimeError:
                pass
            try:
                client.call("DELETE", f"/session/{state['sessionId']}")
            except RuntimeError:
                pass
            self.state_path(selector).unlink(missing_ok=True)
        return {"cleaned": True}


def main() -> int:
    args = cli()
    adapter = AppiumAdapter(args.platform)
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
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
