#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Identify compatible iOS compiler objects, independently of SDK packaging receipts.

This is a storage namespace and sccache custom buster, not a native dependency
qualification. sccache must still hash the actual source, preprocessed headers,
compiler flags and compiler identity for every lookup. SDK output provenance is
validated separately before compilation. Never import an older buster as a hit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


DOMAIN = "overte-ios-device-client-compiler-v1"
# Bump only when changing assumptions about compiler cache correctness. CMake,
# packaging scripts and dependency receipt changes are not compiler inputs.
POLICY_EPOCH = 1


def token(value, name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", value):
        raise ValueError(f"invalid or missing {name}")
    return value


def identity(compiler, arch, xcode_build, sdk_build, sdk_version):
    compiler = Path(compiler)
    if not compiler.is_file() or compiler.stat().st_size == 0:
        raise ValueError("compiler must be an existing nonempty file")
    with compiler.open("rb") as stream:
        compiler_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "domain": DOMAIN,
        "policyEpoch": POLICY_EPOCH,
        "target": "iphoneos-arm64",
        "runnerArch": token(arch, "runner architecture"),
        "xcodeBuild": token(xcode_build, "Xcode build"),
        "sdkBuild": token(sdk_build, "SDK build"),
        "sdkVersion": token(sdk_version, "SDK version"),
        "compilerSha256": compiler_sha,
    }


def outputs(inputs, run_id, run_attempt):
    if not re.fullmatch(r"[1-9][0-9]*", run_id) or not re.fullmatch(r"[1-9][0-9]*", run_attempt):
        raise ValueError("run ID and attempt must be positive integers")
    namespace = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # New epoch deliberately cannot consume the old dependency-receipt buster.
    # Existing artifacts/caches remain intact for their original source builds.
    prefix = f"overte-ios-client-sccache-v3-{inputs['runnerArch']}-{namespace}-"
    return {
        "namespace": namespace,
        "artifact-prefix": f"overte-ios-client-objects-v2-{inputs['runnerArch']}-{namespace}",
        "prefix": prefix,
        "prune_prefix": f"overte-ios-client-sccache-v3-{inputs['runnerArch']}-",
        "key": f"{prefix}{run_id}-{run_attempt}",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("compiler", "arch", "xcode-build", "sdk-build", "sdk-version", "run-id", "run-attempt"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args()
    inputs = identity(args.compiler, args.arch, args.xcode_build, args.sdk_build, args.sdk_version)
    result = outputs(inputs, args.run_id, args.run_attempt)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in result.items())
    if args.github_env:
        with args.github_env.open("a", encoding="utf-8") as stream:
            stream.write(f"SCCACHE_C_CUSTOM_CACHE_BUSTER={result['namespace']}\n")
    print(json.dumps({"inputs": inputs, "outputs": result}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(f"client-compiler-cache-key: {error}")
