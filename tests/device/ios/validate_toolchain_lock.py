#!/usr/bin/env python3
"""Validate the exact Fedora iOS Appium and security-tool locks offline."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DEFAULT_LOCK = ROOT / "toolchain.lock.json"
DEFAULT_PACKAGE = ROOT / "package.json"
DEFAULT_NPM_LOCK = ROOT / "package-lock.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
SHA1 = re.compile(r"[0-9a-f]{40}")
SHA384 = re.compile(r"[0-9a-f]{96}")
SEMVER = re.compile(r"(?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)")
EXPECTED = {
    "core": ("appium", "3.7.0"),
    "xcuitest": ("appium-xcuitest-driver", "12.8.0"),
    "remoteXpc": ("appium-ios-remotexpc", "5.15.3"),
    "webdriverAgent": ("appium-webdriveragent", "16.8.0"),
}


class LockError(ValueError):
    """The checked-in Fedora iOS toolchain lock is inconsistent."""


def fail(message: str) -> "NoReturn":
    raise LockError(message)


def read_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"{label} is unreadable: {type(error).__name__}")
    if not isinstance(value, dict):
        fail(f"{label} must contain an object")
    return value


def exact_keys(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        fail(f"{label} has unexpected or missing fields")
    return value


def https_url(value: object, host: str | None, label: str) -> str:
    if not isinstance(value, str):
        fail(f"{label} must be an HTTPS URL")
    parsed = urlparse(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or host is not None and parsed.hostname != host):
        fail(f"{label} is outside its pinned HTTPS origin")
    return value


def npm_integrity(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha512-"):
        fail(f"{label} must be an npm SHA-512 integrity value")
    try:
        digest = base64.b64decode(value.removeprefix("sha512-"), validate=True)
    except (binascii.Error, ValueError):
        fail(f"{label} has invalid base64")
    if len(digest) != 64:
        fail(f"{label} is not SHA-512")
    return value


def npm_entries(lock: dict) -> dict[str, dict]:
    appium = exact_keys(
        lock.get("appium"),
        {"license", "runtime", "nodeRange", "npmRange", "core", "drivers",
         "iosRuntime", "iosSecurity"},
        "appium lock",
    )
    if appium["license"] != "Apache-2.0":
        fail("Appium license pin must be Apache-2.0")
    runtime = exact_keys(appium["runtime"], {"node", "npm"}, "Appium runtime")
    if runtime != {"node": "24.19.0", "npm": "11.17.0"}:
        fail("Node/npm runtime pins drifted")
    if appium["nodeRange"] != "^20.19.0 || ^22.12.0 || >=24.0.0" or appium["npmRange"] != ">=10":
        fail("Appium engine contract drifted")
    drivers = exact_keys(appium["drivers"], {"xcuitest"}, "Appium driver lock")
    ios_runtime = exact_keys(
        appium["iosRuntime"], {"pymobiledevice3", "remoteXpc", "webdriverAgent"},
        "iOS runtime lock",
    )
    values = {
        "core": appium["core"],
        "xcuitest": drivers["xcuitest"],
        "remoteXpc": ios_runtime["remoteXpc"],
        "webdriverAgent": ios_runtime["webdriverAgent"],
    }
    result: dict[str, dict] = {}
    for role, (package_name, version) in EXPECTED.items():
        entry = values[role]
        required = {"package", "version", "artifact"}
        if role == "xcuitest":
            required |= {"appiumPeerRange", "remoteXpcRange", "webdriverAgentRange"}
        entry = exact_keys(entry, required, f"{role} package lock")
        if entry["package"] != package_name or entry["version"] != version:
            fail(f"{role} package/version pin drifted")
        artifact = exact_keys(
            entry["artifact"], {"url", "sha256", "sha1", "integrity"},
            f"{role} npm artifact",
        )
        expected_url = f"https://registry.npmjs.org/{package_name}/-/{package_name}-{version}.tgz"
        if https_url(artifact["url"], "registry.npmjs.org", f"{role} URL") != expected_url:
            fail(f"{role} npm URL does not identify the exact package tarball")
        if not isinstance(artifact["sha256"], str) or not SHA256.fullmatch(artifact["sha256"]):
            fail(f"{role} npm artifact lacks an exact SHA-256")
        if not isinstance(artifact["sha1"], str) or not SHA1.fullmatch(artifact["sha1"]):
            fail(f"{role} npm artifact lacks the registry SHA-1")
        npm_integrity(artifact["integrity"], f"{role} integrity")
        result[package_name] = entry
    xcuitest = values["xcuitest"]
    if (xcuitest["appiumPeerRange"] != "^3.0.0-rc.2"
            or xcuitest["remoteXpcRange"] != "^5.13.2"
            or xcuitest["webdriverAgentRange"] != "^16.8.0"):
        fail("XCUITest peer/runtime ranges drifted")
    return result


def validate_pymobiledevice3(lock: dict) -> None:
    value = exact_keys(
        lock["appium"]["iosRuntime"]["pymobiledevice3"],
        {"package", "version", "license", "pythonAbi", "pythonVersion",
         "pythonExecutable", "pythonExecutableSha256", "distributionCount",
         "freezeSha256", "sitePackagesTreeSha256", "upstreamWdaHostOpsSha256"},
        "PyMobileDevice3 runtime",
    )
    if ({key: value[key] for key in (
            "package", "version", "license", "pythonAbi", "pythonVersion",
            "pythonExecutable", "distributionCount")} != {
                "package": "pymobiledevice3",
                "version": "11.1.5",
                "license": "GPL-3.0-or-later",
                "pythonAbi": "cp314",
                "pythonVersion": "3.14.7",
                "pythonExecutable": "/usr/bin/python3.14",
                "distributionCount": 99,
            }
            or any(not isinstance(value[key], str) or not SHA256.fullmatch(value[key])
                   for key in ("pythonExecutableSha256", "freezeSha256",
                               "sitePackagesTreeSha256", "upstreamWdaHostOpsSha256"))):
        fail("PyMobileDevice3 runtime pin drifted")


def validate_security_tools(lock: dict) -> None:
    tools = exact_keys(
        lock["appium"]["iosSecurity"], {"age", "rcodesign", "resigner"},
        "security tools",
    )
    expected = {
        "age": (
            "1.2.1", "BSD-3-Clause", "github.com",
            "https://github.com/FiloSottile/age/releases/download/v1.2.1/"
            "age-v1.2.1-linux-amd64.tar.gz",
            "7df45a6cc87d4da11cc03a539a7470c15b1041ab2b396af088fe9990f7c79d50",
            "aaec874ed903da4b02a9d503778ae05ee5005b2acc0f4a4cf10e5d0f17fd4384",
        ),
        "rcodesign": (
            "0.29.0", "MPL-2.0", "github.com",
            "https://github.com/indygreg/apple-platform-rs/releases/download/"
            "apple-codesign%2F0.29.0/"
            "apple-codesign-0.29.0-x86_64-unknown-linux-musl.tar.gz",
            "dbe85cedd8ee4217b64e9a0e4c2aef92ab8bcaaa41f20bde99781ff02e600002",
            "dab9a7465f96aba3c81e793775510f745b91a46b6418e89f7317b5d8fc7bcea2",
        ),
        "resigner": (
            "0.3.1", "Apache-2.0", "github.com",
            "https://github.com/appium/resigner/releases/download/v0.3.1/"
            "linux-amd64.tar.gz",
            "e8672bfcced781bee017f84d17a84f645668bb664fe709d7dda011c9f1d8d0cd",
            "57a837d4674a5bb4eea9ff0d006b84fd5273fdd0c9d3c05143a46135ae4b988e",
        ),
    }
    for name, (
        version, license_name, host, artifact_url, artifact_sha256,
        executable_sha256,
    ) in expected.items():
        value = exact_keys(
            tools[name], {"version", "license", "executableSha256", "artifact"},
            f"{name} lock",
        )
        if value["version"] != version or value["license"] != license_name:
            fail(f"{name} version/license pin drifted")
        if not isinstance(value["executableSha256"], str) or not SHA256.fullmatch(
            value["executableSha256"]
        ):
            fail(f"{name} executable SHA-256 is invalid")
        if value["executableSha256"] != executable_sha256:
            fail(f"{name} executable SHA-256 pin drifted")
        artifact = exact_keys(value["artifact"], {"url", "sha256"}, f"{name} artifact")
        if https_url(artifact["url"], host, f"{name} URL") != artifact_url:
            fail(f"{name} artifact URL pin drifted")
        if not isinstance(artifact["sha256"], str) or not SHA256.fullmatch(artifact["sha256"]):
            fail(f"{name} archive SHA-256 is invalid")
        if artifact["sha256"] != artifact_sha256:
            fail(f"{name} archive SHA-256 pin drifted")


def validate_developer_disk_image(lock: dict) -> None:
    ddi = exact_keys(
        lock["developerDiskImage"], {"provenance", "files"},
        "Developer Disk Image lock",
    )
    provenance = exact_keys(
        ddi["provenance"],
        {"repository", "commit", "productBuildVersion", "handling"},
        "Developer Disk Image provenance",
    )
    if (https_url(provenance["repository"], "github.com", "Developer Disk Image repository")
            != "https://github.com/doronz88/DeveloperDiskImage"
            or not isinstance(provenance["commit"], str)
            or not SHA1.fullmatch(provenance["commit"])
            or provenance["productBuildVersion"] != "27A5228h"
            or provenance["handling"] != "operator-supplied-private-apple-payload"):
        fail("Developer Disk Image provenance drifted")
    files = exact_keys(
        ddi["files"],
        {"BuildManifest.plist", "Image.dmg", "Image.dmg.trustcache"},
        "Developer Disk Image files",
    )
    expected_sizes = {
        "BuildManifest.plist": 801505,
        "Image.dmg": 15733248,
        "Image.dmg.trustcache": 1895,
    }
    for name, expected_size in expected_sizes.items():
        expected_keys = {"size", "sha256"} if name == "BuildManifest.plist" \
            else {"size", "sha256", "sha1", "sha384"}
        value = exact_keys(files[name], expected_keys, f"Developer Disk Image {name}")
        if (value["size"] != expected_size or isinstance(value["size"], bool)
                or not isinstance(value["sha256"], str)
                or not SHA256.fullmatch(value["sha256"])
                or "sha1" in value and (not isinstance(value["sha1"], str)
                                         or not SHA1.fullmatch(value["sha1"]))
                or "sha384" in value and (not isinstance(value["sha384"], str)
                                           or not SHA384.fullmatch(value["sha384"]))):
            fail(f"Developer Disk Image {name} pin is invalid")


def validate_npm_lock(package_path: Path, npm_lock_path: Path, entries: dict[str, dict]) -> None:
    package = exact_keys(
        read_object(package_path, "Appium package.json"),
        {"name", "private", "version", "license", "dependencies"},
        "Appium package.json",
    )
    expected_dependencies = {name: value["version"] for name, value in entries.items()}
    if (package["name"] != "overte-ios-fedora-appium-runtime"
            or package["private"] is not True or package["version"] != "1.0.0"
            or package["license"] != "Apache-2.0"
            or package["dependencies"] != expected_dependencies):
        fail("Appium package.json does not contain only the exact runtime pins")
    npm_lock = exact_keys(
        read_object(npm_lock_path, "npm lock"),
        {"name", "version", "lockfileVersion", "requires", "packages"},
        "npm lock",
    )
    if (npm_lock["name"] != package["name"] or npm_lock["version"] != package["version"]
            or npm_lock["lockfileVersion"] != 3 or npm_lock["requires"] is not True):
        fail("npm lock header drifted")
    packages = npm_lock["packages"]
    if not isinstance(packages, dict) or not packages or packages.get("", {}).get(
        "dependencies"
    ) != expected_dependencies:
        fail("npm lock root dependencies do not match package.json")
    for path, value in packages.items():
        if path == "":
            continue
        if not isinstance(path, str) or not path.startswith("node_modules/") or not isinstance(value, dict):
            fail("npm lock contains an invalid package entry")
        if value.get("link") is True:
            fail("npm lock must not contain mutable linked dependencies")
        https_url(value.get("resolved"), "registry.npmjs.org", f"npm lock {path} URL")
        npm_integrity(value.get("integrity"), f"npm lock {path} integrity")
    for package_name, entry in entries.items():
        installed = packages.get(f"node_modules/{package_name}")
        artifact = entry["artifact"]
        if not isinstance(installed, dict) or {
            "version": installed.get("version"),
            "resolved": installed.get("resolved"),
            "integrity": installed.get("integrity"),
        } != {
            "version": entry["version"],
            "resolved": artifact["url"],
            "integrity": artifact["integrity"],
        }:
            fail(f"npm lock entry for {package_name} differs from the toolchain lock")
    ios_device = packages.get(
        "node_modules/appium-xcuitest-driver/node_modules/appium-ios-device"
    )
    if (not isinstance(ios_device, dict) or ios_device.get("version") != "3.1.21"
            or ios_device.get("resolved")
            != "https://registry.npmjs.org/appium-ios-device/-/appium-ios-device-3.1.21.tgz"
            or ios_device.get("integrity")
            != "sha512-jufABr3k6fBGMzBlbzU4R2J8JfLvC5HYWscKEu0ntXz2YmYc+q8/"
            "iqXCpmp3rpqR/jGK5Ibqdrt0WkIpnQHQ3g=="):
        fail("nested appium-ios-device installation-proxy helper pin drifted")


def validate(lock_path: Path = DEFAULT_LOCK, package_path: Path = DEFAULT_PACKAGE,
             npm_lock_path: Path = DEFAULT_NPM_LOCK) -> dict:
    lock = exact_keys(
        read_object(lock_path, "Fedora iOS toolchain lock"),
        {"schemaVersion", "serviceRuntimeRevision", "resolvedAt", "sources",
         "developerDiskImage", "appium"},
        "Fedora iOS toolchain lock",
    )
    if (lock["schemaVersion"] != 1 or lock["serviceRuntimeRevision"] != 12
            or lock["resolvedAt"] != "2026-08-28"):
        fail("Fedora iOS toolchain lock header drifted")
    sources = exact_keys(
        lock["sources"],
        {"npmRegistry", "ageRelease", "rcodesignRelease", "resignerRelease",
         "pymobiledevice3Release"},
        "sources",
    )
    for label, value in lock["sources"].items():
        https_url(value, None, f"source {label}")
    if sources["resignerRelease"] != (
        "https://github.com/appium/resigner/releases/tag/v0.3.1"
    ):
        fail("Appium resigner release source pin drifted")
    if sources["pymobiledevice3Release"] != (
        "https://github.com/doronz88/pymobiledevice3/releases/tag/v11.1.5"
    ):
        fail("PyMobileDevice3 release source pin drifted")
    entries = npm_entries(lock)
    validate_pymobiledevice3(lock)
    validate_security_tools(lock)
    validate_developer_disk_image(lock)
    validate_npm_lock(package_path, npm_lock_path, entries)
    return lock


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_host(lock: dict) -> None:
    for executable, expected in (("node", lock["appium"]["runtime"]["node"]),
                                 ("npm", lock["appium"]["runtime"]["npm"])):
        completed = subprocess.run(
            [executable, "--version"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=10, check=False,
        )
        actual = completed.stdout.strip().removeprefix("v")
        if completed.returncode or actual != expected:
            fail(f"host {executable} version {actual or 'unknown'} differs from {expected}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--npm-lock", type=Path, default=DEFAULT_NPM_LOCK)
    parser.add_argument("--check-host", action="store_true")
    parser.add_argument(
        "--artifact", action="append", default=[], metavar="TOOL=PATH",
        help="also hash an already downloaded security-tool archive/executable",
    )
    arguments = parser.parse_args(argv)
    try:
        lock = validate(arguments.lock, arguments.package, arguments.npm_lock)
        if arguments.check_host:
            check_host(lock)
        tools = lock["appium"]["iosSecurity"]
        expected = {
            "age.archive": tools["age"]["artifact"]["sha256"],
            "age.executable": tools["age"]["executableSha256"],
            "rcodesign.archive": tools["rcodesign"]["artifact"]["sha256"],
            "rcodesign.executable": tools["rcodesign"]["executableSha256"],
            "resigner.archive": tools["resigner"]["artifact"]["sha256"],
            "resigner.executable": tools["resigner"]["executableSha256"],
        }
        for specification in arguments.artifact:
            name, separator, raw_path = specification.partition("=")
            if not separator or name not in expected:
                fail("--artifact must be one of the documented TOOL=PATH identifiers")
            if sha256_file(Path(raw_path)) != expected[name]:
                fail(f"{name} SHA-256 mismatch")
        print("PASS: Fedora iOS Appium/npm/security toolchain lock is exact")
        return 0
    except (LockError, OSError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
