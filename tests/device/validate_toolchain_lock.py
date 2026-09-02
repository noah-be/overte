#!/usr/bin/env python3
"""Offline validation for the physical-device E2E toolchain lock.

The default check performs no downloads and contacts no device. Optional
``--artifact ID=PATH`` arguments hash already downloaded files and compare them
with the immutable SHA-256 values in the lock.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse


DEVICE_ROOT = Path(__file__).resolve().parent
DEFAULT_LOCK = DEVICE_ROOT / "toolchain.lock.json"
DEFAULT_DIRECT_PLUGINS = DEVICE_ROOT / "jenkins" / "plugins.txt"
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PLUGIN_RE = re.compile(r"^([a-z0-9][a-z0-9-]*):([^\s:]+)$")


class LockValidationError(ValueError):
    """Raised when the lock is structurally inconsistent or has drifted."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def _mapping(value: Any, label: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    return value


def _semver(value: Any, label: str, errors: list[str]) -> tuple[int, int, int] | None:
    if not isinstance(value, str) or not (match := SEMVER_RE.fullmatch(value)):
        errors.append(f"{label} must be an exact MAJOR.MINOR.PATCH version")
        return None
    return tuple(int(part) for part in match.groups())


def _https_url(value: Any, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str):
        errors.append(f"{label} must be an HTTPS URL")
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        errors.append(f"{label} must be an HTTPS URL without credentials")
        return None
    return value


def _artifact(value: Any, label: str, errors: list[str]) -> dict[str, str]:
    artifact = _mapping(value, label, errors)
    allowed = {"url", "sha256", "integrity"}
    unknown = set(artifact) - allowed
    if unknown:
        errors.append(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
    url = _https_url(artifact.get("url"), f"{label}.url", errors)
    sha256 = artifact.get("sha256")
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        errors.append(f"{label}.sha256 must be 64 lower-case hexadecimal characters")
    elif sha256 == "0" * 64:
        errors.append(f"{label}.sha256 must not be a placeholder digest")
    integrity = artifact.get("integrity")
    if integrity is not None:
        if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
            errors.append(f"{label}.integrity must be an npm sha512 SRI value")
        else:
            try:
                digest = base64.b64decode(integrity.removeprefix("sha512-"), validate=True)
            except (binascii.Error, ValueError):
                errors.append(f"{label}.integrity contains invalid base64")
            else:
                if len(digest) != 64:
                    errors.append(f"{label}.integrity is not a SHA-512 digest")
    return {"url": url or "", "sha256": sha256 if isinstance(sha256, str) else ""}


def _runtime_satisfies(version: tuple[int, int, int], expression: str) -> bool:
    """Evaluate the small npm-engine subset used by the pinned Appium stack."""
    for alternative in (part.strip() for part in expression.split("||")):
        if alternative.startswith("^"):
            base_text = alternative[1:]
            base = _coerce_version(base_text)
            if base is not None and base <= version < (base[0] + 1, 0, 0):
                return True
        elif alternative.startswith(">="):
            base = _coerce_version(alternative[2:])
            if base is not None and version >= base:
                return True
    return False


def _coerce_version(value: str) -> tuple[int, int, int] | None:
    parts = value.strip().split(".")
    if not 1 <= len(parts) <= 3 or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in (parts + ["0"] * (3 - len(parts))))


def _parse_plugin_file(path: Path, label: str, errors: list[str]) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"{label} cannot be read: {exc}")
        return {}

    result: dict[str, str] = {}
    ordered_names: list[str] = []
    for number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PLUGIN_RE.fullmatch(line)
        if not match:
            errors.append(f"{label}:{number} must be plugin-id:exact-version")
            continue
        plugin, version = match.groups()
        if plugin in result:
            errors.append(f"{label}:{number} duplicates {plugin}")
            continue
        result[plugin] = version
        ordered_names.append(plugin)
    if ordered_names != sorted(ordered_names):
        errors.append(f"{label} entries must be sorted by plugin id")
    return result


def _relative_lock_path(
    lock_path: Path, relative_value: Any, label: str, errors: list[str]
) -> Path:
    if not isinstance(relative_value, str) or not relative_value:
        errors.append(f"{label} must be a non-empty relative path")
        return lock_path.parent / "missing-lock-file"
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        errors.append(f"{label} must stay beside or below the toolchain lock")
        return lock_path.parent / "missing-lock-file"
    return lock_path.parent / relative


def _read_plugin_artifacts(
    path: Path,
    core_version: str,
    resolved: dict[str, str],
    errors: list[str],
) -> dict[str, dict[str, str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"resolved plugin artifact lock cannot be read: {exc}")
        return {}
    data = _mapping(document, "resolved plugin artifact lock", errors)
    if set(data) != {"schemaVersion", "jenkinsCore", "plugins"}:
        errors.append("resolved plugin artifact lock has unexpected or missing fields")
    if data.get("schemaVersion") != 1:
        errors.append("resolved plugin artifact lock schemaVersion must be 1")
    if data.get("jenkinsCore") != core_version:
        errors.append("resolved plugin artifact lock was not resolved for the pinned Jenkins core")
    rows = data.get("plugins")
    if not isinstance(rows, list):
        errors.append("resolved plugin artifact lock plugins must be an array")
        return {}

    pinned_core = _coerce_version(core_version)
    result: dict[str, dict[str, str]] = {}
    ordered_names: list[str] = []
    for index, raw_row in enumerate(rows):
        label = f"resolved plugin artifact lock plugins[{index}]"
        row = _mapping(raw_row, label, errors)
        expected = {"id", "version", "requiredCore", "url", "sha256"}
        if set(row) != expected:
            errors.append(f"{label} has unexpected or missing fields")
        plugin = row.get("id")
        version = row.get("version")
        if not isinstance(plugin, str) or not isinstance(version, str) or not PLUGIN_RE.fullmatch(
            f"{plugin}:{version}"
        ):
            errors.append(f"{label} must contain a valid plugin id and exact version")
            continue
        if plugin in result:
            errors.append(f"resolved plugin artifact lock duplicates {plugin}")
            continue
        ordered_names.append(plugin)
        required_core = _coerce_version(str(row.get("requiredCore", "")))
        if required_core is None:
            errors.append(f"{label}.requiredCore must be a dotted numeric Jenkins version")
        elif pinned_core is not None and required_core > pinned_core:
            errors.append(f"{plugin}:{version} requires Jenkins {row['requiredCore']} newer than the pin")
        artifact = _artifact(
            {"url": row.get("url"), "sha256": row.get("sha256")}, label, errors
        )
        if artifact["url"] and f"/{plugin}/{version}/{plugin}.hpi" not in artifact["url"]:
            errors.append(f"{label}.url does not identify the pinned plugin artifact")
        result[plugin] = artifact
    if ordered_names != sorted(ordered_names):
        errors.append("resolved plugin artifact lock entries must be sorted by plugin id")
    if set(result) != set(resolved):
        errors.append("plugin version and artifact locks must contain the same plugin ids")
    for plugin, version in resolved.items():
        matching_rows = [row for row in rows if isinstance(row, dict) and row.get("id") == plugin]
        if len(matching_rows) == 1 and matching_rows[0].get("version") != version:
            errors.append(f"plugin artifact lock version differs for {plugin}")
    return result


def _validate_npm_package(
    value: Any,
    label: str,
    errors: list[str],
    artifacts: dict[str, dict[str, str]],
    artifact_id: str,
    expected_package: str,
) -> tuple[int, int, int] | None:
    package = _mapping(value, label, errors)
    if package.get("package") != expected_package:
        errors.append(f"{label}.package must be {expected_package!r}")
    version = _semver(package.get("version"), f"{label}.version", errors)
    artifact = _artifact(package.get("artifact"), f"{label}.artifact", errors)
    artifacts[artifact_id] = artifact
    if version is not None and artifact["url"]:
        filename = f"{expected_package}-{package['version']}.tgz"
        if not artifact["url"].endswith("/" + filename):
            errors.append(f"{label}.artifact.url does not identify {filename}")
    return version


def validate_lock(
    lock_path: Path = DEFAULT_LOCK,
    *,
    resolved_plugins_path: Path | None = None,
    direct_plugins_path: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Validate a lock and return its addressable artifact map."""
    errors: list[str] = []
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LockValidationError([f"cannot read {lock_path}: {exc}"]) from exc
    root = _mapping(data, "lock", errors)
    expected_root = {"schemaVersion", "resolvedAt", "sources", "appium", "jenkins"}
    if set(root) != expected_root:
        missing = expected_root - set(root)
        unknown = set(root) - expected_root
        if missing:
            errors.append(f"lock is missing fields: {', '.join(sorted(missing))}")
        if unknown:
            errors.append(f"lock has unknown fields: {', '.join(sorted(unknown))}")
    if root.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    try:
        date.fromisoformat(root.get("resolvedAt", ""))
    except (TypeError, ValueError):
        errors.append("resolvedAt must be an ISO-8601 calendar date")

    sources = _mapping(root.get("sources"), "sources", errors)
    if not sources:
        errors.append("sources must not be empty")
    for name, source in sources.items():
        _https_url(source, f"sources.{name}", errors)

    artifacts: dict[str, dict[str, str]] = {}
    appium = _mapping(root.get("appium"), "appium", errors)
    if appium.get("license") != "Apache-2.0":
        errors.append("appium.license must be Apache-2.0")
    runtime = _mapping(appium.get("runtime"), "appium.runtime", errors)
    node_version = _semver(runtime.get("node"), "appium.runtime.node", errors)
    npm_version = _semver(runtime.get("npm"), "appium.runtime.npm", errors)
    node_range = appium.get("nodeRange")
    npm_range = appium.get("npmRange")
    if not isinstance(node_range, str) or node_version is None or not _runtime_satisfies(node_version, node_range):
        errors.append("pinned Node.js version does not satisfy appium.nodeRange")
    if not isinstance(npm_range, str) or npm_version is None or not _runtime_satisfies(npm_version, npm_range):
        errors.append("pinned npm version does not satisfy appium.npmRange")
    core_version = _validate_npm_package(
        appium.get("core"), "appium.core", errors, artifacts, "appium.core", "appium"
    )
    drivers = _mapping(appium.get("drivers"), "appium.drivers", errors)
    expected_drivers = {
        "uiautomator2": "appium-uiautomator2-driver",
        "xcuitest": "appium-xcuitest-driver",
    }
    if set(drivers) != set(expected_drivers):
        errors.append("appium.drivers must contain exactly uiautomator2 and xcuitest")
    for driver_name, package_name in expected_drivers.items():
        driver = _mapping(drivers.get(driver_name), f"appium.drivers.{driver_name}", errors)
        _validate_npm_package(
            driver,
            f"appium.drivers.{driver_name}",
            errors,
            artifacts,
            f"appium.drivers.{driver_name}",
            package_name,
        )
        peer = driver.get("appiumPeerRange")
        peer_match = re.match(r"^\^(\d+)\.", peer) if isinstance(peer, str) else None
        if core_version is None or peer_match is None or int(peer_match.group(1)) != core_version[0]:
            errors.append(f"appium.drivers.{driver_name}.appiumPeerRange rejects the pinned core")

    ios_runtime = _mapping(appium.get("iosRuntime"), "appium.iosRuntime", errors)
    expected_ios_runtime = {
        "remoteXpc": "appium-ios-remotexpc",
        "webdriverAgent": "appium-webdriveragent",
    }
    if set(ios_runtime) != set(expected_ios_runtime):
        errors.append("appium.iosRuntime must contain exactly remoteXpc and webdriverAgent")
    ios_versions: dict[str, tuple[int, int, int] | None] = {}
    for runtime_name, package_name in expected_ios_runtime.items():
        ios_versions[runtime_name] = _validate_npm_package(
            ios_runtime.get(runtime_name),
            f"appium.iosRuntime.{runtime_name}",
            errors,
            artifacts,
            f"appium.iosRuntime.{runtime_name}",
            package_name,
        )
    xcuitest = _mapping(drivers.get("xcuitest"), "appium.drivers.xcuitest", errors)
    for field, runtime_name in (
        ("remoteXpcRange", "remoteXpc"),
        ("webdriverAgentRange", "webdriverAgent"),
    ):
        expression = xcuitest.get(field)
        version = ios_versions.get(runtime_name)
        if (not isinstance(expression, str) or version is None
                or not _runtime_satisfies(version, expression)):
            errors.append(
                f"appium.drivers.xcuitest.{field} rejects the pinned iOS runtime"
            )

    ios_security = _mapping(appium.get("iosSecurity"), "appium.iosSecurity", errors)
    expected_ios_security = {
        "age": ("BSD-3-Clause", "age-v"),
        "rcodesign": ("MPL-2.0", "apple-codesign-"),
    }
    if set(ios_security) != set(expected_ios_security):
        errors.append("appium.iosSecurity must contain exactly age and rcodesign")
    for tool_name, (license_name, filename_prefix) in expected_ios_security.items():
        tool = _mapping(ios_security.get(tool_name), f"appium.iosSecurity.{tool_name}", errors)
        version = _semver(tool.get("version"), f"appium.iosSecurity.{tool_name}.version", errors)
        if tool.get("license") != license_name:
            errors.append(f"appium.iosSecurity.{tool_name}.license must be {license_name}")
        executable_sha = tool.get("executableSha256")
        if not isinstance(executable_sha, str) or not SHA256_RE.fullmatch(executable_sha):
            errors.append(
                f"appium.iosSecurity.{tool_name}.executableSha256 must be a SHA-256"
            )
        artifact = _artifact(
            tool.get("artifact"), f"appium.iosSecurity.{tool_name}.artifact", errors
        )
        artifacts[f"appium.iosSecurity.{tool_name}"] = artifact
        if (version is not None and artifact["url"]
                and f"{filename_prefix}{tool['version']}" not in artifact["url"]):
            errors.append(
                f"appium.iosSecurity.{tool_name}.artifact does not identify its version"
            )

    jenkins = _mapping(root.get("jenkins"), "jenkins", errors)
    if jenkins.get("license") != "MIT":
        errors.append("jenkins.license must be MIT")
    java_majors = jenkins.get("javaMajors")
    recommended_java = jenkins.get("recommendedJavaMajor")
    if (
        not isinstance(java_majors, list)
        or not java_majors
        or any(not isinstance(item, int) for item in java_majors)
        or len(set(java_majors)) != len(java_majors)
    ):
        errors.append("jenkins.javaMajors must be a non-empty list of unique integers")
    elif recommended_java not in java_majors:
        errors.append("jenkins.recommendedJavaMajor must occur in jenkins.javaMajors")

    for field, artifact_id in (("lts", "jenkins.lts"), ("pluginInstallationManager", "jenkins.pluginManager")):
        item = _mapping(jenkins.get(field), f"jenkins.{field}", errors)
        _semver(item.get("version"), f"jenkins.{field}.version", errors)
        artifacts[artifact_id] = _artifact(item.get("artifact"), f"jenkins.{field}.artifact", errors)
    lts_version = _mapping(jenkins.get("lts"), "jenkins.lts", errors).get("version")
    manager_version = _mapping(jenkins.get("pluginInstallationManager"), "jenkins.pluginInstallationManager", errors).get("version")
    if jenkins.get("resolvedForCore") != lts_version:
        errors.append("jenkins.resolvedForCore must equal jenkins.lts.version")
    if jenkins.get("resolvedWithPluginManager") != manager_version:
        errors.append("jenkins.resolvedWithPluginManager must equal pluginInstallationManager.version")
    policy = _mapping(jenkins.get("installPolicy"), "jenkins.installPolicy", errors)
    if policy != {"latest": False, "includeOptionalDependencies": False}:
        errors.append("jenkins.installPolicy must disable latest and optional dependency drift")

    direct = _mapping(jenkins.get("directPlugins"), "jenkins.directPlugins", errors)
    if not direct or any(not PLUGIN_RE.fullmatch(f"{name}:{version}") for name, version in direct.items()):
        errors.append("jenkins.directPlugins must contain exact plugin-id:version pairs")
    plugin_artifacts = _mapping(jenkins.get("directPluginArtifacts"), "jenkins.directPluginArtifacts", errors)
    if set(plugin_artifacts) != set(direct):
        errors.append("jenkins.directPluginArtifacts keys must equal jenkins.directPlugins keys")
    for plugin, value in plugin_artifacts.items():
        artifact = _artifact(value, f"jenkins.directPluginArtifacts.{plugin}", errors)
        artifacts[f"jenkins.plugins.{plugin}"] = artifact
        version = direct.get(plugin)
        if version and artifact["url"] and f"/{plugin}/{version}/" not in artifact["url"]:
            errors.append(f"Jenkins artifact URL for {plugin} does not contain its pinned version")

    resolved_path = resolved_plugins_path or _relative_lock_path(
        lock_path,
        jenkins.get("resolvedPluginsFile"),
        "jenkins.resolvedPluginsFile",
        errors,
    )
    plugin_artifact_path = _relative_lock_path(
        lock_path,
        jenkins.get("resolvedPluginArtifactsFile"),
        "jenkins.resolvedPluginArtifactsFile",
        errors,
    )
    declared_path = direct_plugins_path or lock_path.parent / "jenkins" / "plugins.txt"
    external_plugin_inputs = (resolved_path, declared_path, plugin_artifact_path)
    if any(path.exists() for path in external_plugin_inputs):
        resolved = _parse_plugin_file(resolved_path, "resolved plugin lock", errors)
        for plugin, version in direct.items():
            if resolved.get(plugin) != version:
                errors.append(f"resolved plugin lock does not pin {plugin}:{version}")
        declared = _parse_plugin_file(declared_path, "direct plugin list", errors)
        if declared != direct:
            errors.append("jenkins/plugins.txt must exactly match jenkins.directPlugins")
        all_plugin_artifacts = _read_plugin_artifacts(
            plugin_artifact_path,
            lts_version if isinstance(lts_version, str) else "",
            resolved,
            errors,
        )
        for plugin, artifact in all_plugin_artifacts.items():
            direct_artifact = artifacts.get(f"jenkins.plugins.{plugin}")
            if plugin in direct and direct_artifact != artifact:
                errors.append(f"direct and resolved artifact metadata differs for {plugin}")
            artifacts[f"jenkins.plugins.{plugin}"] = artifact

    if errors:
        raise LockValidationError(errors)
    return artifacts


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact_argument(value: str) -> tuple[str, Path]:
    artifact_id, separator, path = value.partition("=")
    if not separator or not artifact_id or not path:
        raise argparse.ArgumentTypeError("expected ARTIFACT_ID=PATH")
    return artifact_id, Path(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        type=_artifact_argument,
        metavar="ID=PATH",
        help="also verify an already downloaded artifact; repeat as needed",
    )
    parser.add_argument("--list-artifacts", action="store_true")
    args = parser.parse_args(argv)

    try:
        artifacts = validate_lock(args.lock)
        for artifact_id, path in args.artifact:
            if artifact_id not in artifacts:
                raise LockValidationError([f"unknown artifact id: {artifact_id}"])
            if not path.is_file():
                raise LockValidationError([f"artifact is not a regular file: {path}"])
            actual = file_sha256(path)
            expected = artifacts[artifact_id]["sha256"]
            if actual != expected:
                raise LockValidationError(
                    [f"SHA-256 mismatch for {artifact_id}: expected {expected}, got {actual}"]
                )
    except LockValidationError as exc:
        for error in exc.errors:
            print(f"toolchain lock error: {error}", file=sys.stderr)
        return 1

    if args.list_artifacts:
        for artifact_id, artifact in sorted(artifacts.items()):
            print(f"{artifact_id}\t{artifact['sha256']}\t{artifact['url']}")
    print(f"toolchain lock valid: {args.lock} ({len(artifacts)} pinned artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
