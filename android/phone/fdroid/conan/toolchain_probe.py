#!/usr/bin/env python3
"""Fail-closed probe for the protected SH-001 F-Droid build environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


class ToolchainError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_lock(path: Path) -> dict:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ToolchainError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    if document.get("schema_version") != 1:
        raise ToolchainError("unsupported toolchain provisioning lock")
    return document


def validate_versions(expected: dict, actual: dict) -> None:
    for name, version in expected.items():
        if actual.get(name) != version:
            raise ToolchainError(f"wrong {name}: expected {version}, got {actual.get(name)}")


def _run(command):
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout


def inspect(repo_root: Path, sdk_root: Path, lock_path: Path) -> dict:
    lock = load_lock(lock_path)
    image = lock["build_image"]
    for relative, expected in {
        image["containerfile"]: image["containerfile_sha256"],
        **lock["gradle_bindings"],
    }.items():
        if relative in {"distribution_sha256", "gradle", "android_gradle_plugin"}:
            continue
        path = repo_root / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise ToolchainError(f"repository tool binding mismatch: {relative}")
    for relative, expected in lock["android_sdk_bindings"].items():
        path = sdk_root / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise ToolchainError(f"Android SDK binding mismatch: {relative}")

    metadata = json.loads(_run(["podman", "image", "inspect", image["reference"]]))[0]
    if metadata.get("Id") != image["image_id"]:
        raise ToolchainError("protected build image digest mismatch")
    if metadata.get("Digest") != image["manifest_digest"]:
        raise ToolchainError("protected build image manifest mismatch")
    labels = metadata.get("Config", {}).get("Labels", {})
    if labels.get("org.overte.sh001.base-digest") != lock["base_image"]["digest"]:
        raise ToolchainError("protected image does not bind the official F-Droid base")
    if labels.get("org.overte.sh001.fdroidserver-revision") != lock["base_image"]["fdroidserver_revision"]:
        raise ToolchainError("fdroidserver revision label mismatch")

    command = [
        "podman", "run", "--rm", "--network=none", "--read-only",
        "--security-opt", "label=disable", "--tmpfs", "/tmp:rw,size=256m",
        "--tmpfs", "/root:rw,size=128m", "-e", "CONAN_HOME=/root/conan",
        image["reference"], "/bin/sh", "-c",
        "export PATH=/opt/sh001/conan/bin:/usr/lib/jvm/java-17-openjdk-amd64/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; "
        "python3 - <<'PY'\n"
        "import json, re, socket, subprocess\n"
        "def out(*a): return subprocess.check_output(a, text=True, stderr=subprocess.STDOUT)\n"
        "def version(command, pattern):\n"
        " m=re.search(pattern, out(*command)); return m.group(1) if m else ''\n"
        "network='blocked'\n"
        "try: socket.getaddrinfo('example.com', 443); network='reachable'\n"
        "except OSError: pass\n"
        "print(json.dumps({\n"
        " 'gcc': version(['/usr/bin/gcc','--version'], r'gcc .*?([0-9]+\\.[0-9]+\\.[0-9]+)'),\n"
        " 'g++': version(['/usr/bin/g++','--version'], r'g\\+\\+ .*?([0-9]+\\.[0-9]+\\.[0-9]+)'),\n"
        " 'java_major': version(['/usr/lib/jvm/java-17-openjdk-amd64/bin/java','-version'], r'version \\\"([0-9]+)'),\n"
        " 'conan': version(['/opt/sh001/conan/bin/conan','--version'], r'Conan version ([0-9.]+)'),\n"
        " 'cmake': version(['/usr/bin/cmake','--version'], r'cmake version ([0-9.]+)'),\n"
        " 'ninja': out('/usr/bin/ninja','--version').strip(), 'network': network}))\n"
        "PY",
    ]
    actual = json.loads(_run(command))
    validate_versions(lock["required_versions"], actual)
    if actual.get("network") != "blocked":
        raise ToolchainError("container network is available")
    wrapper = (repo_root / "android/common/gradle/wrapper/gradle-wrapper.properties").read_text(encoding="utf-8")
    if f"gradle-{lock['gradle_bindings']['gradle']}-bin.zip" not in wrapper:
        raise ToolchainError("wrong Gradle wrapper distribution")
    if lock["gradle_bindings"]["distribution_sha256"] not in wrapper:
        raise ToolchainError("Gradle distribution checksum mismatch")
    phone_gradle = (repo_root / "android/phone/build.gradle").read_text(encoding="utf-8")
    if not re.search(r"com\.android\.application' version '" + re.escape(lock["gradle_bindings"]["android_gradle_plugin"]) + r"'", phone_gradle):
        raise ToolchainError("Android Gradle Plugin version mismatch")
    return {"status": "PASS", "image_id": metadata["Id"], "versions": actual}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.repo_root.resolve(), args.sdk_root.resolve(), args.lock.resolve()), indent=2, sort_keys=True))
        return 0
    except (ToolchainError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
