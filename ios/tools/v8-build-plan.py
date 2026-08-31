#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Create the canonical, output-affecting identity for the iOS V8 package."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Dict


ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / "ios/v8.env"
SIMULATOR_PATCH = ROOT / "ios/patches/v8-12.4-jitless-ios-simulator.patch"
SIMULATOR_PATCH_ID = "ios/patches/v8-12.4-jitless-ios-simulator.patch"

SCHEMA = 2
TOOLCHAIN_POLICY = "xcode-clang-with-deps-pinned-llvm-ar-v1"
BUILD_TARGET = "v8_monolith"


def read_env(path: pathlib.Path | None = None) -> Dict[str, str]:
    path = path or ENV_PATH
    values: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid environment line in {path}: {raw!r}")
        key, value = line.split("=", 1)
        values[key] = value
    required = (
        "OVERTE_IOS_V8_VERSION",
        "OVERTE_IOS_V8_REVISION",
        "OVERTE_IOS_DEPOT_TOOLS_REVISION",
        "OVERTE_IOS_V8_DEPLOYMENT_TARGET",
    )
    for key in required:
        if not values.get(key):
            raise ValueError(f"missing {key} in {path}")
    return values


def platform_fields(platform: str) -> Dict[str, str]:
    if platform == "device":
        return {"sdkName": "iphoneos", "targetEnvironment": "device"}
    if platform == "simulator":
        return {"sdkName": "iphonesimulator", "targetEnvironment": "simulator"}
    raise ValueError("platform must be device or simulator")


def gn_args(platform: str, deployment_target: str) -> list[str]:
    target = platform_fields(platform)
    return [
        'target_os = "ios"',
        'target_cpu = "arm64"',
        f'target_environment = "{target["targetEnvironment"]}"',
        f'ios_deployment_target = "{deployment_target}"',
        "ios_enable_code_signing = false",
        "is_debug = false",
        "is_component_build = false",
        "use_custom_libcxx = false",
        'clang_base_path = "//buildtools/overte-xcode-toolchain"',
        "clang_use_chrome_plugins = false",
        "use_lld = false",
        "symbol_level = 0",
        "strip_debug_info = true",
        "v8_monolithic = true",
        "v8_use_external_startup_data = false",
        "v8_enable_i18n_support = false",
        "v8_enable_lite_mode = true",
        "v8_jitless = true",
        "v8_enable_webassembly = false",
        "v8_enable_pointer_compression = false",
        "treat_warnings_as_errors = false",
    ]


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_plan(args: argparse.Namespace) -> dict:
    env = read_env()
    target = platform_fields(args.platform)
    patches = []
    if args.platform == "simulator":
        patches.append(
            {
                "path": SIMULATOR_PATCH_ID,
                "sha256": sha256_file(SIMULATOR_PATCH),
            }
        )
    plan = {
        "schemaVersion": SCHEMA,
        "source": {
            "v8Version": env["OVERTE_IOS_V8_VERSION"],
            "v8Revision": env["OVERTE_IOS_V8_REVISION"],
            "depotToolsRevision": env["OVERTE_IOS_DEPOT_TOOLS_REVISION"],
        },
        "target": {
            "os": "ios",
            "platform": args.platform,
            "environment": target["targetEnvironment"],
            "cpu": "arm64",
            "runnerArch": canonical_arch(args.runner_arch),
            "sdkName": target["sdkName"],
            "deploymentTarget": env["OVERTE_IOS_V8_DEPLOYMENT_TARGET"],
        },
        "toolchain": {
            "xcodeBuild": args.xcode_build,
            "sdkVersion": args.sdk_version,
            "sdkBuild": args.sdk_build,
            "compilerVersion": args.compiler_version.strip(),
            "compilerSha256": args.compiler_sha256,
            "policy": TOOLCHAIN_POLICY,
        },
        "build": {
            "target": BUILD_TARGET,
            "gnArgs": gn_args(args.platform, env["OVERTE_IOS_V8_DEPLOYMENT_TARGET"]),
            "patches": patches,
        },
    }
    validate_plan(plan)
    return plan


def validate_plan(plan: dict) -> None:
    sha_pattern = re.compile(r"^[0-9a-f]{64}$")
    if not plan["target"]["runnerArch"]:
        raise ValueError("runner architecture must not be empty")
    if not plan["toolchain"]["xcodeBuild"]:
        raise ValueError("Xcode build must not be empty")
    if not plan["toolchain"]["sdkVersion"] or not plan["toolchain"]["sdkBuild"]:
        raise ValueError("SDK version/build must not be empty")
    if not plan["toolchain"]["compilerVersion"].startswith("Apple clang version "):
        raise ValueError("compiler version must identify Apple clang")
    if not sha_pattern.fullmatch(plan["toolchain"]["compilerSha256"]):
        raise ValueError("compiler SHA-256 must contain 64 lowercase hex characters")


def canonical_arch(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in ("arm64", "aarch64"):
        return "arm64"
    raise ValueError(f"unsupported runner architecture: {value}")


def canonical_json(plan: dict) -> str:
    return json.dumps(plan, sort_keys=True, separators=(",", ":"))


def identity(plan: dict) -> str:
    return hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()


def write_output(path: pathlib.Path, plan: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    gn = subparsers.add_parser("gn-args")
    gn.add_argument("--platform", choices=("device", "simulator"), required=True)
    gn.add_argument("--compiler-launcher")

    identify = subparsers.add_parser("identity")
    identify.add_argument("--platform", choices=("device", "simulator"), required=True)
    identify.add_argument("--runner-arch", required=True)
    identify.add_argument("--xcode-build", required=True)
    identify.add_argument("--sdk-version", required=True)
    identify.add_argument("--sdk-build", required=True)
    identify.add_argument("--compiler-version", required=True)
    identify.add_argument("--compiler-sha256", required=True)
    identify.add_argument("--json-output", type=pathlib.Path)
    identify.add_argument("--github-output", type=pathlib.Path)

    args = parser.parse_args()
    env = read_env()
    if args.command == "gn-args":
        for line in gn_args(args.platform, env["OVERTE_IOS_V8_DEPLOYMENT_TARGET"]):
            print(line)
        if args.compiler_launcher:
            if '"' in args.compiler_launcher or "\\" in args.compiler_launcher:
                raise ValueError("compiler launcher contains unsupported characters")
            print(f'cc_wrapper = "{args.compiler_launcher}"')
        return 0

    plan = build_plan(args)
    digest = identity(plan)
    if args.json_output:
        write_output(args.json_output, plan)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write(f"identity={digest}\n")
            stream.write(f"key=overte-v8-ios-v2-{digest}\n")
            stream.write(f"artifact-prefix=overte-v8-ios-checkpoint-v2-{digest}\n")
            stream.write(f"sccache-prefix=overte-v8-ios-sccache-v2-{digest}-\n")
    print(canonical_json(plan))
    print(f"identity={digest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"v8-build-plan: {exc}", file=sys.stderr)
        raise SystemExit(1)
