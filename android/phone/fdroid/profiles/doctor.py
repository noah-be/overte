#!/usr/bin/env python3
"""Read-only validator for the neutral Phone/Pico Android input maps."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

CONSUMERS = ("phone", "pico")
EXPECTED_BASELINE = {
    "builder_image": {
        "name": "fdroidserver/buildserver-trixie",
        "digest": "sha256:f81172f142454bccb6e198739d40bf3a98a393f09805140c1aa8b49807d0e3b7",
    },
    "host": {
        "os": "Linux", "arch": "x86_64", "compiler": "gcc",
        "compiler_version": "15", "compiler_libcxx": "libstdc++11",
        "cppstd": "gnu20", "build_type": "Release",
    },
    "android": {
        "sdk_platform": "36", "build_tools": "36.0.0", "ndk": "27.3.13750724",
        "ndk_clang": "18", "minimum_api": 26, "abi": "arm64-v8a",
        "conan_arch": "armv8", "libcxx": "c++_shared", "page_size": 16384,
    },
    "build_clients": {
        "java": "17", "gradle": "8.13", "android_gradle_plugin": "8.13.2",
        "android_cmake": "3.31.6", "conan": "2.25.2",
    },
    "builder_image_bound_tools": [
        "gcc", "g++", "binutils", "python3", "perl", "git", "make",
        "patch", "tar", "xz",
    ],
    "required_environment": ["ANDROID_SDK_ROOT", "ANDROID_NDK_HOME", "JAVA_HOME", "CONAN_HOME"],
    "allowed_path_entries": [
        "$JAVA_HOME/bin",
        "$ANDROID_SDK_ROOT/build-tools/36.0.0",
        "$ANDROID_SDK_ROOT/platform-tools",
        "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin",
        "/usr/bin",
        "/bin",
    ],
    "forbidden_implicit_inputs": [
        "conan-default-profile", "conan-remote", "conan-cache-restore",
        "profile-detect", "package-manager", "sudo", "undeclared-path-tool",
        "product-selector",
    ],
}
EXPECTED_ROLES = {
    "base-toolchain", "cmake-toolchain", "bootstrap-graph",
    "bootstrap-profile", "hosttools-profile", "target-profile",
}
FORBIDDEN_TEXT = re.compile(
    r"(?i)(--build[= ]missing|--build[= ]never|profile\s+detect|"
    r"\bdefault\b|\bsudo\b|\b(?:apt|apt-get|dnf|yum|pacman)\b|"
    r"artifactory|cache[ _-]?restore)"
)


class ContractError(RuntimeError):
    pass


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ContractError(f"duplicate JSON key in {path}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot load {path}: {error}") from error


def validate_base(root: Path) -> tuple[dict[str, Any], str]:
    path = root / "android/phone/fdroid/manifests/base-toolchain.lock.json"
    document = load_json(path)
    if document.get("schema") != 1 or document.get("baseline") != EXPECTED_BASELINE:
        raise ContractError("base toolchain differs from the fixed SH-010 baseline")
    identity = canonical_digest(document["baseline"])
    if document.get("identity_sha256") != identity:
        raise ContractError("base toolchain identity_sha256 mismatch")
    return document["baseline"], file_digest(path)


def validate_map(root: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    map_path = root / "android/phone/fdroid/profiles/input-map.json"
    document = load_json(map_path)
    entries = document.get("neutral_inputs")
    if document.get("schema") != 1 or not isinstance(entries, list):
        raise ContractError("input map schema mismatch")
    if {entry.get("role") for entry in entries} != EXPECTED_ROLES or len(entries) != len(EXPECTED_ROLES):
        raise ContractError("input map roles are missing or duplicated")

    verified: list[dict[str, str]] = []
    for entry in entries:
        relative = str(entry.get("path", ""))
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            raise ContractError(f"unsafe input path: {relative}")
        implementation_name = "/".join(pure.parts[3:]).casefold()
        if "pico" in implementation_name or re.search(r"(^|[-_/])phone($|[-_/])", implementation_name):
            raise ContractError(f"product-named implementation input: {relative}")
        target = root / pure
        if not target.is_file():
            raise ContractError(f"declared input is absent: {relative}")
        actual = file_digest(target)
        if entry.get("sha256") != actual:
            raise ContractError(f"input digest mismatch: {relative}")
        if target.suffix in {"", ".cmake", ".py"}:
            text = target.read_text(encoding="utf-8")
            for explicit_non_mutating_setting in (
                "tools.system.package_manager:mode=report",
                "tools.system.package_manager:sudo=False",
            ):
                text = text.replace(explicit_non_mutating_setting, "")
            match = FORBIDDEN_TEXT.search(text)
            if match:
                raise ContractError(f"forbidden implicit input in {relative}: {match.group(0)}")
        verified.append({"role": entry["role"], "path": relative, "sha256": actual})
    return document, sorted(verified, key=lambda item: item["role"])


def validate_profile_contract(entries: list[dict[str, str]], root: Path) -> None:
    by_role = {entry["role"]: root / entry["path"] for entry in entries}
    target = by_role["target-profile"].read_text(encoding="utf-8")
    for required in (
        "os=Android", "os.api_level=26", "arch=armv8", "compiler=clang",
        "compiler.version=18", "compiler.libcxx=c++_shared", "compiler.cppstd=gnu20",
        "-D__BIONIC_NO_PAGE_SIZE_MACRO", "max-page-size=16384", "common-page-size=16384",
    ):
        if required not in target:
            raise ContractError(f"target profile is missing: {required}")
    for role in ("bootstrap-profile", "hosttools-profile"):
        text = by_role[role].read_text(encoding="utf-8")
        for required in ("os=Linux", "arch=x86_64", "compiler=gcc", "compiler.version=15"):
            if required not in text:
                raise ContractError(f"{role} is missing: {required}")


def runtime_preflight(baseline: dict[str, Any]) -> None:
    missing = [name for name in baseline["required_environment"] if not os.environ.get(name)]
    if missing:
        raise ContractError(f"required runtime inputs are absent: {','.join(missing)}")
    ndk = Path(os.environ["ANDROID_NDK_HOME"])
    sdk = Path(os.environ["ANDROID_SDK_ROOT"])
    if ndk.name != baseline["android"]["ndk"] or not ndk.is_dir():
        raise ContractError("ANDROID_NDK_HOME is not the declared NDK")
    if not (sdk / "platforms" / f"android-{baseline['android']['sdk_platform']}").is_dir():
        raise ContractError("declared Android SDK platform is absent")
    if not (sdk / "build-tools" / baseline["android"]["build_tools"]).is_dir():
        raise ContractError("declared Android Build Tools are absent")
    if not Path(os.environ["JAVA_HOME"]).is_dir():
        raise ContractError("declared JAVA_HOME is absent")
    expected_path = [os.path.expandvars(entry) for entry in baseline["allowed_path_entries"]]
    actual_path = os.environ.get("PATH", "").split(os.pathsep)
    if actual_path != expected_path:
        raise ContractError("PATH differs from the declared tool allowlist")
    if any(not Path(entry).is_dir() for entry in expected_path):
        raise ContractError("a declared PATH entry is absent")
    forbidden_environment = [name for name in os.environ if name.startswith("CONAN_") and name != "CONAN_HOME"]
    if forbidden_environment:
        raise ContractError(f"undeclared Conan environment overrides: {','.join(sorted(forbidden_environment))}")
    conan_home = os.environ["CONAN_HOME"]
    if not Path(conan_home).is_dir():
        raise ContractError("CONAN_HOME must be an explicit empty directory")
    if any(Path(conan_home).iterdir()):
        raise ContractError("CONAN_HOME is not empty")


def inspect(root: Path, runtime: bool = False) -> dict[str, Any]:
    baseline, baseline_file_sha = validate_base(root)
    _, entries = validate_map(root)
    validate_profile_contract(entries, root)
    if runtime:
        runtime_preflight(baseline)
    shared_inputs = {
        "baseline_identity_sha256": canonical_digest(baseline),
        "baseline_file_sha256": baseline_file_sha,
        "inputs": entries,
    }
    identity = canonical_digest(shared_inputs)
    consumers = {consumer: {"input_identity_sha256": identity, **shared_inputs} for consumer in CONSUMERS}
    if consumers["phone"] != consumers["pico"]:
        raise ContractError("Phone and Pico input maps differ")
    return {
        "status": "PASS",
        "mode": "runtime" if runtime else "contract",
        "consumers": consumers,
        "equivalent": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--runtime", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect(args.root.resolve(), runtime=args.runtime)
    except ContractError as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
