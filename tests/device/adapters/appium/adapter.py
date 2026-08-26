#!/usr/bin/env python3
"""Appium W3C adapter for physical Android and iOS/iPadOS targets."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import math
import re
import stat
import subprocess
import tempfile
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
from contracts import validate_probe_snapshot  # noqa: E402
from ios.private_artifact_tree import (  # noqa: E402
    ArtifactTreeError,
    tree_sha256 as private_artifact_tree_sha256,
)


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
    IOS_WDA_VERSION_PLIST_KEY = "OverteE2EWebDriverAgentVersion"
    IOS_XCUITEST_VERSION_PLIST_KEY = "OverteE2EXCUITestDriverVersion"
    IOS_PROBE_SCRIPT_PATH = "/overte_e2e_probe.js"
    IOS_SCENE_PATH = "/scene.json?location=%2F0%2C2%2C4%2F0%2C0%2C0%2C1"
    IOS_RESERVED_LAUNCH_OPTIONS = {
        "--url", "--testScript", "--testResultsLocation", "--quitWhenFinished",
    }
    IOS_PROTECTED_RECEIPT_CONTRACT = "overte-ios-fedora-e2e-receipt-v1"
    IOS_PERSONAL_TEAM_RECEIPT_CONTRACT = "overte-ios-personal-team-artifact-receipt-v1"
    IOS_PREINSTALLED_RECEIPT_CONTRACT = "overte-ios-personal-team-preinstalled-receipt-v1"
    IOS_TABLET_IDENTIFIERS = {
        "openAccessibilityId": "OverteTabletOpen",
        "closeAccessibilityId": "OverteTabletClose",
    }
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
        path = self._private_external_file(
            Path(path_value).expanduser(), "Appium target configuration")
        if os.name != "nt" and stat.S_IMODE(path.lstat().st_mode) != 0o600:
            fail("Appium target configuration must have mode 0600")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fail("Appium target configuration is unreadable")
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
                if entry.get("physical") is not True:
                    fail("iOS Appium targets must select a physical device")
                self.validate_ios_artifact_receipt(entry)
                self.validate_ios_host_strategy(entry)
                self.validate_ios_test_build(entry)
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
        try:
            parsed_server = urlsplit(target.get("serverUrl", ""))
            server_port = parsed_server.port
        except ValueError:
            fail("Fedora iOS Appium server must use a bounded loopback URL")
        if (parsed_server.scheme != "http" or parsed_server.hostname != "127.0.0.1"
                or server_port is None or not 1 <= server_port <= 65535
                or parsed_server.username is not None or parsed_server.password is not None
                or parsed_server.path or parsed_server.query or parsed_server.fragment
                or parsed_server.netloc != f"127.0.0.1:{server_port}"):
            fail("Fedora iOS Appium server must use a bounded loopback URL")
        platform_version = capabilities.get("appium:platformVersion")
        match = re.fullmatch(r"([0-9]+)(?:[.][0-9]+){0,2}", platform_version or "")
        if not match or int(match.group(1)) < 18:
            fail("non-macOS physical iOS targets require appium:platformVersion 18 or newer")
        preinstalled = capabilities.get("appium:usePreinstalledWDA") is True
        if "appium:webDriverAgentUrl" in capabilities:
            fail("Fedora iOS targets must not bypass the receipt-bound prebuilt WDA")
        if not preinstalled:
            fail("non-macOS physical iOS targets require preinstalled WDA")
        wda_id = capabilities.get("appium:updatedWDABundleId")
        if not isinstance(wda_id, str) or not wda_id:
            fail("preinstalled WDA requires appium:updatedWDABundleId")
        artifact_mode = target.get("artifactMode")
        if artifact_mode not in {"signed-ipa", "personal-team-preinstalled"}:
            fail("enabled Fedora iOS targets require an explicit artifactMode")
        if artifact_mode == "personal-team-preinstalled":
            if any(name in capabilities for name in (
                    "appium:app", "appium:prebuiltWDAPath")):
                fail("preinstalled Personal-Team mode must not claim signed IPA paths")
        else:
            for name in ("appium:app", "appium:prebuiltWDAPath"):
                value = capabilities.get(name)
                if not isinstance(value, str) or not Path(value).is_absolute():
                    fail(f"Fedora iOS targets require an absolute private {name}")
        if not target.get("artifactReceipt"):
            fail("Fedora iOS targets require a receipt-bound Overte/WDA artifact pair")
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
    def _private_tree_sha256(cls, root: Path, label: str) -> str:
        """Attest and canonically hash a private extracted application tree."""
        resolved = root.resolve(strict=False)
        try:
            resolved.relative_to(REPOSITORY)
        except ValueError:
            pass
        else:
            fail(f"{label} must be outside the source checkout")
        try:
            return private_artifact_tree_sha256(
                root, owner_uid=os.geteuid(), require_private=os.name != "nt")
        except ArtifactTreeError:
            fail(f"{label} is not a safe current-user-owned private tree")

    @staticmethod
    def _private_external_file(path: Path, label: str) -> Path:
        if not path.is_absolute():
            fail(f"{label} must be an absolute private path")
        current = Path(path.anchor)
        for component in path.parts[1:]:
            current /= component
            if current.is_symlink():
                fail(f"{label} must not contain symbolic links")
        resolved = path.resolve()
        try:
            resolved.relative_to(REPOSITORY)
        except ValueError:
            pass
        else:
            fail(f"{label} must be outside the source checkout")
        if not resolved.is_file():
            fail(f"{label} does not exist")
        metadata = resolved.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            fail(f"{label} must be an ordinary private file")
        if (os.name != "nt" and (metadata.st_uid != os.geteuid()
                                  or metadata.st_mode & 0o077)):
            fail(f"{label} must be current-user-owned with mode 0600")
        return resolved

    @staticmethod
    def _receipt_time(value: object, label: str) -> datetime:
        if not isinstance(value, str) or not value.endswith("Z"):
            fail(f"iOS artifactReceipt {label} is invalid")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError:
            fail(f"iOS artifactReceipt {label} is invalid")
        if parsed.tzinfo is None:
            fail(f"iOS artifactReceipt {label} is invalid")
        return parsed.astimezone(timezone.utc)

    @classmethod
    def validate_ios_artifact_receipt(cls, target: dict, *, hash_files: bool = False) -> None:
        capabilities = target["capabilities"]
        artifact_paths = {
            "overte": capabilities.get("appium:app"),
            "wdaPrebuilt": capabilities.get("appium:prebuiltWDAPath"),
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
        receipt_path = cls._private_external_file(receipt_path, "iOS artifactReceipt")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fail("iOS artifactReceipt is unreadable")
        if not isinstance(receipt, dict) or set(receipt) != {
            "schemaVersion", "contract", "sourceRevision", "createdAt", "notAfter",
            "provenance", "overte", "wda", "toolchain"
        }:
            fail("iOS artifactReceipt has unexpected or missing fields")
        contract = receipt.get("contract")
        if (receipt.get("schemaVersion") != 1
                or contract not in {
                    cls.IOS_PROTECTED_RECEIPT_CONTRACT,
                    cls.IOS_PERSONAL_TEAM_RECEIPT_CONTRACT,
                    cls.IOS_PREINSTALLED_RECEIPT_CONTRACT,
                }
                or not isinstance(receipt.get("sourceRevision"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", receipt["sourceRevision"])):
            fail("iOS artifactReceipt contract is invalid")
        created = cls._receipt_time(receipt.get("createdAt"), "createdAt")
        not_after = cls._receipt_time(receipt.get("notAfter"), "notAfter")
        now = datetime.now(timezone.utc)
        if not created < not_after or created > now or now >= not_after:
            fail("iOS artifactReceipt validity window is invalid or expired")
        provenance = receipt.get("provenance")
        if contract == cls.IOS_PROTECTED_RECEIPT_CONTRACT:
            valid_provenance = (
                isinstance(provenance, dict) and set(provenance) == {
                    "repository", "repositoryId", "workflow", "reusableWorkflow", "ref",
                    "runId", "runAttempt"}
                and isinstance(provenance.get("repository"), str)
                and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
                                 provenance["repository"]) is not None
                and isinstance(provenance.get("repositoryId"), int)
                and not isinstance(provenance.get("repositoryId"), bool)
                and provenance["repositoryId"] > 0
                and provenance.get("workflow") == ".github/workflows/ios-bootstrap.yml"
                and provenance.get("reusableWorkflow")
                == ".github/workflows/ios-fedora-e2e-producer.yml"
                and provenance.get("ref") == "refs/heads/apple-ios"
                and all(isinstance(provenance.get(field), int)
                        and not isinstance(provenance[field], bool)
                        and provenance[field] > 0 for field in ("runId", "runAttempt"))
            )
        elif contract == cls.IOS_PERSONAL_TEAM_RECEIPT_CONTRACT:
            valid_provenance = (
                isinstance(provenance, dict) and set(provenance) == {
                    "mode", "unsignedKitContract", "unsignedKitManifestSha256",
                    "attestationContract", "derivationBinding"}
                and provenance.get("mode") == "personal-team-manual-signing"
                and provenance.get("unsignedKitContract")
                == "overte-ios-personal-team-e2e-kit-v1"
                and isinstance(provenance.get("unsignedKitManifestSha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}",
                                 provenance["unsignedKitManifestSha256"]) is not None
                and provenance.get("attestationContract")
                == "overte-ios-personal-team-signed-handoff-v1"
                and provenance.get("derivationBinding") == "human-verified"
            )
        else:
            observation = provenance.get("signingObservation") \
                if isinstance(provenance, dict) else None
            valid_observation = observation is None or (
                isinstance(observation, dict) and set(observation) == {
                    "teamIdentifier", "profileExpiration", "applicationIdentifiers"}
                and isinstance(observation.get("teamIdentifier"), str)
                and re.fullmatch(r"[A-Z0-9]{10}", observation["teamIdentifier"])
                is not None
                and isinstance(observation.get("profileExpiration"), str)
                and isinstance(observation.get("applicationIdentifiers"), dict)
            )
            valid_provenance = (
                isinstance(provenance, dict) and set(provenance) == {
                    "mode", "derivationBinding", "cryptographicByteBinding",
                    "installationProxyValidated", "attestationSha256",
                    "unsignedKitContract", "unsignedKitManifestSha256",
                    "attestationContract", "signingObservation"}
                and provenance.get("mode") == "personal-team-preinstalled"
                and provenance.get("derivationBinding") == "none-device-observed"
                and provenance.get("cryptographicByteBinding") is False
                and provenance.get("installationProxyValidated") is True
                and isinstance(provenance.get("attestationSha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", provenance["attestationSha256"])
                is not None
                and provenance.get("unsignedKitContract")
                == "overte-ios-personal-team-e2e-kit-v1"
                and isinstance(provenance.get("unsignedKitManifestSha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}",
                                 provenance["unsignedKitManifestSha256"]) is not None
                and provenance.get("attestationContract")
                == "overte-ios-personal-team-preinstalled-attestation-v1"
                and valid_observation
            )
        if not valid_provenance:
            fail("iOS artifactReceipt provenance is invalid")
        lock = json.loads((DEVICE_ROOT / "ios" / "toolchain.lock.json").read_text(
            encoding="utf-8"))
        expected_toolchain = {
            "xcuitestDriver": lock["appium"]["drivers"]["xcuitest"]["version"],
            "remoteXpc": lock["appium"]["iosRuntime"]["remoteXpc"]["version"],
            "webdriverAgent": lock["appium"]["iosRuntime"]["webdriverAgent"]["version"],
        }
        if receipt.get("toolchain") != expected_toolchain:
            fail("iOS artifactReceipt does not match the pinned Fedora toolchain")
        preinstalled_receipt = contract == cls.IOS_PREINSTALLED_RECEIPT_CONTRACT
        if preinstalled_receipt:
            overte = receipt.get("overte")
            wda = receipt.get("wda")
            if (overte != {"bundleId": "org.overte.interface.e2e", "installed": True}
                    or wda != {
                        "bundleId": "org.overte.WebDriverAgentRunner.xctrunner",
                        "xctestBundleId": "org.overte.WebDriverAgentRunner",
                        "installed": True,
                    } or any(artifact_paths.values())):
                fail("preinstalled iOS artifactReceipt inventory is invalid")
            observation = provenance["signingObservation"]
            if observation is not None:
                team = observation["teamIdentifier"]
                expected_identifiers = {
                    "overte": f"{team}.{overte['bundleId']}",
                    "wdaRunner": f"{team}.{wda['bundleId']}",
                    "wdaXCTest": f"{team}.{wda['xctestBundleId']}",
                }
                if observation["applicationIdentifiers"] != expected_identifiers:
                    fail("preinstalled iOS signing observation is inconsistent")
                profile_expiry = cls._receipt_time(
                    observation["profileExpiration"], "profileExpiration")
                if profile_expiry < not_after:
                    fail("preinstalled iOS signing observation expires before its receipt")
        else:
            overte = receipt.get("overte")
            wda = receipt.get("wda")
            if (not isinstance(overte, dict)
                    or set(overte) != {"path", "sha256", "bundleId"}
                    or not isinstance(overte.get("path"), str)
                    or not Path(overte["path"]).is_absolute()
                    or not isinstance(overte.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", overte["sha256"])
                    or not isinstance(overte.get("bundleId"), str)):
                fail("iOS artifactReceipt overte entry is invalid")
            if (not isinstance(wda, dict)
                    or set(wda) != {"ipaPath", "ipaSha256", "prebuiltPath",
                                    "prebuiltTreeSha256", "bundleId"}
                    or not all(isinstance(wda.get(field), str) for field in wda)
                    or not Path(wda["ipaPath"]).is_absolute()
                    or not Path(wda["prebuiltPath"]).is_absolute()
                    or Path(wda["prebuiltPath"]).suffix != ".app"
                    or not re.fullmatch(r"[0-9a-f]{64}", wda["ipaSha256"])
                    or not re.fullmatch(r"[0-9a-f]{64}", wda["prebuiltTreeSha256"])):
                fail("iOS artifactReceipt wda entry is invalid")
            if artifact_paths["overte"] != overte["path"]:
                fail("iOS overte capability path does not match artifactReceipt")
            if artifact_paths["wdaPrebuilt"] != wda["prebuiltPath"]:
                fail("iOS WDA prebuilt capability path does not match artifactReceipt")
            overte_ipa = cls._private_external_file(
                Path(overte["path"]), "iOS overte artifact from receipt")
            wda_ipa = cls._private_external_file(
                Path(wda["ipaPath"]), "iOS WDA IPA from receipt")
            prebuilt_digest = cls._private_tree_sha256(
                Path(wda["prebuiltPath"]), "iOS prebuilt WDA application")
            if not (Path(wda["prebuiltPath"]) / "Info.plist").is_file():
                fail("iOS prebuilt WDA application lacks Info.plist")
            if hash_files and cls._sha256_file(overte_ipa) != overte["sha256"]:
                fail("iOS overte artifact failed its receipt SHA-256")
            if hash_files and cls._sha256_file(wda_ipa) != wda["ipaSha256"]:
                fail("iOS WDA IPA failed its receipt SHA-256")
            if prebuilt_digest != wda["prebuiltTreeSha256"]:
                fail("iOS prebuilt WDA application failed its receipt tree SHA-256")
        if receipt["overte"]["bundleId"] != target["appId"]:
            fail("iOS artifactReceipt Overte bundle does not match appId")
        suffix = capabilities.get("appium:updatedWDABundleIdSuffix", ".xctrunner")
        if not isinstance(suffix, str):
            fail("appium:updatedWDABundleIdSuffix must be a string")
        if receipt["wda"]["bundleId"] != capabilities.get("appium:updatedWDABundleId", "") + suffix:
            fail("iOS artifactReceipt WDA bundle does not match Appium capabilities")
        expected_mode = "personal-team-preinstalled" if preinstalled_receipt else "signed-ipa"
        configured_mode = target.get("artifactMode")
        if target.get("enabled", True) and configured_mode != expected_mode:
            fail("iOS artifactMode does not match artifactReceipt")
        target["_artifactMode"] = expected_mode
        target["_receiptWdaBundleId"] = receipt["wda"]["bundleId"]
        target["_artifactReceiptSha256"] = cls._sha256_file(receipt_path)
        target["_artifactReceiptPath"] = str(receipt_path)

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
            "scenePath", "resultsDirectory", "launchArguments", "launchEnvironment",
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
        if contract.get("scenePath") != cls.IOS_SCENE_PATH:
            fail("iOS testBuild scenePath must select the repository-owned fixture")

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
        if capabilities.get("appium:enforceAppInstall") is not False:
            fail("iOS testBuild targets require appium:enforceAppInstall=false")
        if target.get("scene") != {"kind": "ios-test-build"}:
            fail("iOS testBuild targets require scene.kind=ios-test-build")
        if target.get("probe") != {"kind": "ios-documents"}:
            fail("iOS testBuild targets require probe.kind=ios-documents")
        if contract.get("fixtureOrigin") != origin:
            fail("iOS testBuild fixtureOrigin must use normalized lowercase spelling")
        tablet = target.get("controls", {}).get("tablet", {})
        if any(key in tablet for key in ("togglePoint", "openPoint", "closePoint")):
            fail("iOS tablet automation requires audited accessibility identifiers")
        if target.get("enabled", True) and tablet != cls.IOS_TABLET_IDENTIFIERS:
            fail("enabled iOS tablet automation requires the stable Overte identifiers")

    @staticmethod
    def advertised_capabilities(target: dict) -> list[str]:
        values = ["accessibility.snapshot", "app.foreground", "app.launch",
                  "artifact.screenshot"]
        if target["platform"] == "android":
            values.append("lifecycle.background")
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
                                         (tablet.get("openAccessibilityId") and
                                          tablet.get("closeAccessibilityId")) or
                                         (target["platform"] == "android" and
                                          (tablet.get("togglePoint") or
                                           (tablet.get("openPoint") and
                                            tablet.get("closePoint"))))):
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
        value = {
            "adapter": self.adapter_id,
            "os": "Android" if self.platform == "android" else "iOS/iPadOS",
            "role": target.get("role", "physical-mobile-e2e"),
        }
        if self.platform == "android":
            value.update({"model": target.get("model"),
                          "osVersion": target.get("osVersion")})
        return value

    def state_path(self, selector: str) -> Path:
        return state_directory(self.adapter_id, selector) / "session.json"

    def read_session(self, selector: str) -> dict | None:
        path = self.state_path(selector)
        if not path.exists():
            return None
        if path.is_symlink():
            fail("Appium session state must not be a symbolic link")
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                or os.name != "nt" and (metadata.st_uid != os.geteuid()
                                         or metadata.st_mode & 0o077)):
            fail("Appium session state is not a private ordinary file")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fail("Appium session state is unreadable")
        if not isinstance(value, dict) or not isinstance(value.get("sessionId"), str):
            fail("Appium session state has an invalid contract")
        return value

    def save_session(self, selector: str, value: dict) -> None:
        path = self.state_path(selector)
        descriptor = -1
        temporary: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".session-", suffix=".tmp", dir=path.parent)
            temporary = Path(temporary_name)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                descriptor = -1
                output.write(json.dumps(value, sort_keys=True) + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            temporary = None
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def validate_probe(value: object) -> dict:
        value = require_fresh_snapshot(value)
        try:
            return validate_probe_snapshot(value)
        except ValueError as error:
            fail(str(error))

    def attest_physical_target(self, client: WebDriver, session: str, target: dict) -> None:
        if not target.get("physical"):
            return
        if self.platform == "ios":
            value = client.execute(session, "mobile: deviceInfo")
            if not isinstance(value, dict) or value.get("isSimulator") not in (False, 0):
                fail("configured physical iOS target is a simulator or cannot be attested")
            observed_udid = value.get("udid", value.get("uniqueDeviceIdentifier"))
            expected_udid = target["capabilities"].get("appium:udid")
            if (not isinstance(observed_udid, str) or not observed_udid
                    or observed_udid != expected_udid):
                fail("XCUITest device identity does not match the private target")
            observed_version = next((value.get(key) for key in (
                "platformVersion", "productVersion", "ProductVersion", "osVersion")
                if value.get(key) is not None), None)
            expected_version = target["capabilities"].get("appium:platformVersion")
            if (self.normalized_ios_version(observed_version)
                    != self.normalized_ios_version(expected_version)):
                fail("XCUITest platform version does not match the private target")
            if target.get("testBuild"):
                apps = client.execute(session, "mobile: listApps", {
                    "applicationType": "User",
                    "returnAttributes": ["CFBundleIdentifier", "UIFileSharingEnabled",
                                         self.IOS_TEST_BUILD_PLIST_KEY,
                                         self.IOS_WDA_VERSION_PLIST_KEY,
                                         self.IOS_XCUITEST_VERSION_PLIST_KEY],
                })
                installed = apps.get(target["appId"]) if isinstance(apps, dict) else None
                suffix = target["capabilities"].get(
                    "appium:updatedWDABundleIdSuffix", ".xctrunner")
                wda_bundle = target.get("_receiptWdaBundleId") or (
                    target["capabilities"].get("appium:updatedWDABundleId", "") + suffix)
                installed_wda = apps.get(wda_bundle) if isinstance(apps, dict) else None
                if (not isinstance(installed, dict)
                        or installed.get("CFBundleIdentifier") != target["appId"]
                        or installed.get("UIFileSharingEnabled") not in (True, 1)
                        or installed.get(self.IOS_TEST_BUILD_PLIST_KEY) != 1):
                    fail("installed iOS application does not attest the E2E test-build contract")
                if (not isinstance(installed_wda, dict)
                        or installed_wda.get("CFBundleIdentifier") != wda_bundle
                        or installed_wda.get(self.IOS_WDA_VERSION_PLIST_KEY) != "16.8.0"
                        or installed_wda.get(self.IOS_XCUITEST_VERSION_PLIST_KEY) != "12.8.0"):
                    fail("installed iOS WebDriverAgent does not match the private receipt")
        else:
            from android.common.device_tests.adb_transport import AdbTransport
            device = target["capabilities"]["appium:udid"]
            adb = AdbTransport()
            adb.require_connected(device)
            if adb.prop(device, "ro.kernel.qemu") == "1":
                fail("configured physical Android target is an emulator")

    @staticmethod
    def normalized_ios_version(value: object) -> tuple[int, ...] | None:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:[.][0-9]+){0,2}", value):
            return None
        parts = [int(item) for item in value.split(".")]
        while len(parts) > 2 and parts[-1] == 0:
            parts.pop()
        return tuple(parts)

    @staticmethod
    def immutable_ios_runtime_wrapper() -> Path:
        lock = json.loads((DEVICE_ROOT / "ios" / "toolchain.lock.json").read_text(
            encoding="utf-8"))
        version = lock["appium"]["iosRuntime"]["remoteXpc"]["version"]
        revision = lock.get("serviceRuntimeRevision")
        if revision != 3:
            fail("unsupported immutable iOS device runtime revision")
        runtime = Path("/usr/local/lib/overte-ios-remotexpc") / f"{version}-r{revision}"
        wrapper = runtime / "remotexpc_tunnel.py"
        current = Path(wrapper.anchor)
        for component in wrapper.parts[1:]:
            current /= component
            if current.is_symlink():
                fail("immutable iOS device preflight runtime contains a symbolic link")
        for path, directory in ((runtime, True), (wrapper, False)):
            if path.is_symlink() or not (path.is_dir() if directory else path.is_file()):
                fail("immutable iOS device preflight runtime is not installed")
            value = path.lstat()
            if (os.name != "nt" and (value.st_uid != 0 or value.st_mode & 0o222)
                    or directory and not stat.S_ISDIR(value.st_mode)
                    or not directory and not stat.S_ISREG(value.st_mode)):
                fail("immutable iOS device preflight runtime failed attestation")
        return wrapper

    def pre_session_device_attestation(self, target: dict) -> None:
        if self.platform != "ios":
            return
        udid = target["capabilities"].get("appium:udid")
        if not isinstance(udid, str) or not udid:
            fail("physical iOS target identity is unavailable for device preflight")
        wrapper = self.immutable_ios_runtime_wrapper()
        try:
            result = subprocess.run(
                [str(wrapper), "device-preflight"],
                input=json.dumps({"udid": udid}, separators=(",", ":")),
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=65, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            fail("immutable iOS device preflight could not run")
        if result.returncode != 0:
            fail("installed iOS applications failed the private device preflight")

    def install_receipt_bound_ios_apps(self, target: dict) -> None:
        """Replace both strong-mode apps through the immutable device helper.

        The helper receives the private identity and receipt only on stdin.  It
        rechecks the receipt and IPA hashes immediately before removing stale
        installations and installing WDA followed by Overte.
        """
        if self.platform != "ios" or target.get("_artifactMode") != "signed-ipa":
            return
        udid = target["capabilities"].get("appium:udid")
        receipt = target.get("_artifactReceiptPath")
        if (not isinstance(udid, str) or not udid or not isinstance(receipt, str)
                or not Path(receipt).is_absolute()):
            fail("signed iOS installation inputs are unavailable")
        wrapper = self.immutable_ios_runtime_wrapper()
        try:
            result = subprocess.run(
                [str(wrapper), "device-install"],
                input=json.dumps({"udid": udid, "receipt": receipt},
                                 separators=(",", ":")),
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=15 * 60, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            fail("immutable signed iOS application installation could not run")
        if result.returncode != 0:
            fail("receipt-bound signed iOS application installation failed")

    def ensure_session(self, selector: str) -> tuple[WebDriver, str, dict]:
        target = self.target(selector)
        client = WebDriver(target["serverUrl"])
        state = self.read_session(selector)
        fingerprint = hashlib.sha256(json.dumps(target, sort_keys=True,
                                                 separators=(",", ":")).encode()).hexdigest()
        previous_generation = int((state or {}).get("generation", 0))
        if state and state.get("targetFingerprint") != fingerprint:
            try:
                client.call("DELETE", f"/session/{state['sessionId']}")
            except (OSError, RuntimeError, ValueError):
                pass
            self.state_path(selector).unlink(missing_ok=True)
            state = None
        if state:
            try:
                client.call("GET", f"/session/{state['sessionId']}")
                self.attest_physical_target(client, state["sessionId"], target)
                return client, state["sessionId"], state
            except RuntimeError:
                try:
                    client.call("DELETE", f"/session/{state['sessionId']}")
                except (OSError, RuntimeError, ValueError):
                    pass
                self.state_path(selector).unlink(missing_ok=True)
        if self.platform == "ios":
            self.validate_ios_artifact_receipt(target, hash_files=True)
            self.install_receipt_bound_ios_apps(target)
            self.pre_session_device_attestation(target)
        value = client.call("POST", "/session", {
            "capabilities": {"alwaysMatch": target["capabilities"], "firstMatch": [{}]},
        })
        if not isinstance(value, dict) or not isinstance(value.get("sessionId"), str):
            fail("Appium did not create a WebDriver session")
        generation = previous_generation + 1
        state = {"sessionId": value["sessionId"], "generation": generation,
                 "targetFingerprint": fingerprint}
        self.save_session(selector, state)
        try:
            self.attest_physical_target(client, value["sessionId"], target)
        except Exception:
            try:
                client.call("DELETE", f"/session/{value['sessionId']}")
            except (OSError, RuntimeError, ValueError):
                pass
            self.state_path(selector).unlink(missing_ok=True)
            raise
        return client, value["sessionId"], state

    def query_app_state(self, client: WebDriver, session: str, target: dict) -> int:
        key = "appId" if self.platform == "android" else "bundleId"
        value = client.execute(session, "mobile: queryAppState", {key: target["appId"]})
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4:
            fail("Appium queryAppState returned an invalid state")
        return value

    def assert_ios_process_identity(self, selector: str, client: WebDriver,
                                    session: str, state: dict, target: dict) -> str:
        if self.platform != "ios":
            fail("iOS process identity guard used for another platform")
        if self.query_app_state(client, session, target) != 4:
            raise RuntimeError("ASSERTION: iOS application is not foregrounded")
        info = client.execute(session, "mobile: activeAppInfo")
        pid = info.get("pid") if isinstance(info, dict) else None
        bundle = info.get("bundleId") if isinstance(info, dict) else None
        if (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0
                or bundle != target["appId"]):
            fail("XCUITest activeAppInfo did not identify the configured application")
        observed = str(pid)
        expected = state.get("processIdentity")
        if expected is not None and expected != observed:
            raise RuntimeError(
                "ASSERTION: iOS application process restarted during the E2E sequence")
        if expected is None:
            state["processIdentity"] = observed
            self.save_session(selector, state)
        return observed

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

    def probe_snapshot(self, selector: str, client: WebDriver, session: str,
                       state: dict, target: dict) -> dict:
        if self.platform == "ios":
            self.assert_ios_process_identity(selector, client, session, state, target)
        probe = target.get("probe", {})
        kind = probe.get("kind")
        if kind == "host-file":
            path = probe.get("path")
            if not isinstance(path, str):
                fail("host-file probe requires a path")
            return self.validate_probe(read_fresh_json(
                Path(os.path.expandvars(path)).resolve()))
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
            return self.validate_probe(snapshot)
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
            return self.validate_probe(snapshot)
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
            result = self.validate_probe(snapshot)
            self.assert_ios_process_identity(selector, client, session, state, target)
            return result
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

        if app_state != 4:
            raise RuntimeError(
                "ASSERTION: iOS process identity cannot be attested outside the foreground")
        identity = self.assert_ios_process_identity(
            selector, client, session, state, target)
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
                              *, reactivate: bool = False) -> None:
        contract = target["testBuild"]
        controlled_scene_url = contract["fixtureOrigin"] + contract["scenePath"]
        scene_url = scene_url or controlled_scene_url
        if scene_url != controlled_scene_url:
            fail("iOS test-build scene URL must be the controlled fixture scene")
        arguments = list(contract.get("launchArguments", []))
        parsed = urlsplit(scene_url)
        origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        if origin != contract["fixtureOrigin"]:
            fail("iOS test-build scene URL must use the configured fixtureOrigin")
        arguments += [
            "--url", scene_url,
            "--testScript", origin + self.IOS_PROBE_SCRIPT_PATH,
            "--testResultsLocation", contract["resultsDirectory"],
        ]
        if state.get("iosE2ELaunchCompleted") is True:
            if state.get("iosE2ESceneUrl") != scene_url:
                fail("iOS E2E session cannot change its controlled scene")
            app_state = self.query_app_state(client, session, target)
            if app_state < 2:
                raise RuntimeError(
                    "ASSERTION: iOS E2E application exited after its single controlled launch")
            if app_state != 4:
                if not reactivate:
                    raise RuntimeError(
                        "ASSERTION: iOS E2E application left the foreground before scene validation")
                client.execute(session, "mobile: activateApp", {"bundleId": target["appId"]})
            self.assert_ios_process_identity(selector, client, session, state, target)
            return
        # autoLaunch=false makes this the only application launch in the baseline
        # sequence. Terminating a stale process first prevents inherited argv.
        if self.query_app_state(client, session, target) >= 2:
            client.execute(session, "mobile: terminateApp", {"bundleId": target["appId"]})
        state.pop("processIdentity", None)
        client.execute(session, "mobile: launchApp", {
            "bundleId": target["appId"],
            "arguments": arguments,
            "environment": contract["launchEnvironment"],
        })
        state["iosE2ELaunchCompleted"] = True
        state["iosE2ESceneUrl"] = scene_url
        self.save_session(selector, state)

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
                self.launch_ios_test_build(
                    selector, client, session, state, target, reactivate=True)
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
            if self.platform == "ios":
                fail("iOS background lifecycle is unavailable without PID evidence")
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
                self.launch_ios_test_build(selector, client, session, state, target, url)
                return {"requested": True, "verification": "fixture-markers"}
            if not isinstance(scene.get("script"), str):
                fail("Appium target has no scene deep-link strategy")
            variables = {"url": url, "appId": target["appId"]}
            client.execute(session, scene["script"], self.expand(scene.get("arguments", {}), variables))
            return {"requested": True}
        if operation == "probe.snapshot":
            return self.probe_snapshot(selector, client, session, state, target)
        if operation == "accessibility.snapshot":
            source = client.call("GET", f"/session/{session}/source")
            if not isinstance(source, str):
                fail("Appium page source is not text")
            # The common accessibility audit reduces this transient source to
            # counts and explicitly requested identifiers. Raw account/user text
            # from the tree is never persisted as a Jenkins artifact.
            return {"source": source, "artifact": None}
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
            if self.platform == "ios":
                self.assert_ios_process_identity(selector, client, session, state, target)
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
            if self.platform == "ios":
                self.assert_ios_process_identity(selector, client, session, state, target)
            return {"performed": True}
        if operation == "input.move":
            if self.platform == "ios":
                self.assert_ios_process_identity(selector, client, session, state, target)
            direction = values.get("direction", "forward")
            movement = controls.get("move", {}).get(direction)
            if not isinstance(movement, dict):
                fail("Appium target does not define this movement direction")
            duration = values.get("durationSeconds")
            self.gesture(client, session, movement,
                         float(duration) if isinstance(duration, (int, float)) else None)
            if self.platform == "ios":
                self.assert_ios_process_identity(selector, client, session, state, target)
            return {"performed": True}
        if operation in {"tablet.open", "tablet.close"}:
            if self.platform == "ios":
                self.assert_ios_process_identity(selector, client, session, state, target)
            tablet = controls.get("tablet", {})
            key = "openAccessibilityId" if operation.endswith("open") else "closeAccessibilityId"
            identifier = tablet.get(key) or tablet.get("toggleAccessibilityId")
            if isinstance(identifier, str) and identifier:
                self.click_accessibility(client, session, identifier)
            else:
                if self.platform == "ios":
                    fail("iOS tablet automation requires an audited accessibility identifier")
                point_key = "openPoint" if operation.endswith("open") else "closePoint"
                point = tablet.get(point_key) or tablet.get("togglePoint")
                if point is None:
                    fail("Appium target does not define a tablet control")
                self.tap_fractional_point(client, session, point,
                                          f"tablet.{point_key}")
            if self.platform == "ios":
                self.assert_ios_process_identity(selector, client, session, state, target)
            return {"performed": True}
        fail(f"unsupported operation: {operation}")

    def cleanup(self, selector: str) -> dict:
        target = self.target(selector)
        state = self.read_session(selector)
        if state:
            client = WebDriver(target["serverUrl"])
            failed = False
            try:
                key = "appId" if self.platform == "android" else "bundleId"
                client.execute(state["sessionId"], "mobile: terminateApp", {key: target["appId"]})
            except RuntimeError:
                failed = True
            deleted = False
            try:
                client.call("DELETE", f"/session/{state['sessionId']}")
            except RuntimeError:
                failed = True
            else:
                deleted = True
            if deleted:
                self.state_path(selector).unlink(missing_ok=True)
            if failed:
                fail("Appium target cleanup did not complete")
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
