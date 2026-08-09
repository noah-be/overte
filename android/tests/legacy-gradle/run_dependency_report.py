#!/usr/bin/env python3
"""Prepare Gradle 6.5 or report the committed legacy dependency graph."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import process_control  # noqa: E402

ANDROID_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ANDROID_ROOT.parent
GRADLE_VERSION = "6.5"
GRADLE_URL = "https://services.gradle.org/distributions/gradle-6.5-bin.zip"
GRADLE_SHA256 = "23e7d37e9bb4f8dabb8a3ea7fdee9dd0428b9b1a71d298aefd65b11dccea220f"
REPORTED_MODULES = ("qt", "oculus", "interface", "questInterface", "framePlayer", "questFramePlayer")
EXCLUDED_MODULES = ({"name": "picoInterface", "reason": "dedicated Gradle 8.13 graph; outside Gradle 6.5 harness"},)
FAILURE_MARKERS = ("Could not resolve", " FAILED", "-> FAILED")
REPORT_VERSION_CODE = "1"
REPORT_RELEASE_NUMBER = "1.0"
TASK_HEADER = re.compile(r"^> Task :([^:]+):dependencies$")
CONFIGURATION_HEADER = re.compile(r"^([^\s]+) - .+$")
FAILED_DEPENDENCY = re.compile(r"^[+\\| ]*--- (project :[^ ]+|[^\s]+:[^\s]+:[^\s]+) FAILED$")


class HarnessError(RuntimeError):
    pass


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


@contextlib.contextmanager
def lock(path: Path, timeout: float = 600):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise HarnessError("timed out waiting for legacy Gradle lock")
                time.sleep(.05)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Overte-legacy-gradle-harness/1"})
    last = None
    for _ in range(4):
        try:
            with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as output:
                shutil.copyfileobj(response, output)
            return
        except OSError as error:
            last = error
    raise HarnessError("Gradle distribution download failed") from last


def safe_zip_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != f"gradle-{GRADLE_VERSION}":
                raise HarnessError("unsafe Gradle distribution member")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise HarnessError("symlinked Gradle distribution member")
        source.extractall(destination)
        for member in source.infolist():
            mode = (member.external_attr >> 16) & 0o777
            if mode:
                (destination / member.filename).chmod(mode)


def ensure_distribution(cache: Path, network: bool, downloader=download) -> Path:
    downloads = cache / "downloads"
    archive = downloads / f"gradle-{GRADLE_VERSION}-bin.zip"
    installation = cache / f"gradle-{GRADLE_VERSION}"
    sentinel = installation / ".overte-distribution-sha256"
    downloads.mkdir(parents=True, exist_ok=True)
    with lock(cache / ".toolchain.lock"):
        archive_valid = archive.is_file() and digest(archive) == GRADLE_SHA256
        if not archive_valid:
            if not network:
                raise HarnessError("verified Gradle distribution is unavailable offline")
            temporary = Path(tempfile.mkstemp(prefix=".gradle-download-", dir=downloads)[1])
            try:
                downloader(GRADLE_URL, temporary)
                if digest(temporary) != GRADLE_SHA256:
                    raise HarnessError("Gradle distribution checksum mismatch")
                os.replace(temporary, archive)
            finally:
                temporary.unlink(missing_ok=True)
        gradle_executable = installation / "bin/gradle"
        if sentinel.is_file() and sentinel.read_text(encoding="ascii").strip() == GRADLE_SHA256 \
                and gradle_executable.is_file() and os.access(gradle_executable, os.X_OK):
            return installation
        staging = Path(tempfile.mkdtemp(prefix=".gradle-extract-", dir=cache))
        try:
            safe_zip_extract(archive, staging)
            extracted = staging / f"gradle-{GRADLE_VERSION}"
            (extracted / ".overte-distribution-sha256").write_text(GRADLE_SHA256 + "\n", encoding="ascii")
            if installation.exists():
                shutil.rmtree(installation)
            os.replace(extracted, installation)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return installation


def run(command: list[str], env: dict[str, str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    process = subprocess.Popen(command, cwd=cwd, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               **process_control.popen_session_kwargs())
    try:
        stdout, stderr = process_control.communicate_with_timeout(
            process, timeout, termination_grace=30)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired as error:
        raise HarnessError("legacy Gradle command timed out") from error


def gate_java(java_home: Path, runner=run) -> str:
    java, javac = java_home / "bin/java", java_home / "bin/javac"
    if not java.is_file() or not os.access(java, os.X_OK) or not javac.is_file() or not os.access(javac, os.X_OK):
        raise HarnessError("a complete executable JDK 8 is required")
    result = runner([str(java), "-version"], {}, java_home, 30)
    output = result.stdout + result.stderr
    if result.returncode or not re.search(r'version "1\.8\.', output):
        raise HarnessError("JDK is not Java 8")
    return output.splitlines()[0] if output.splitlines() else "Java 8"


def gate_gradle(installation: Path, java_home: Path, runner=run) -> None:
    env = {"JAVA_HOME": str(java_home), "PATH": "/usr/bin:/bin", "HOME": str(installation)}
    result = runner([str(installation / "bin/gradle"), "--no-daemon", "--version"], env, installation, 60)
    if result.returncode or f"Gradle {GRADLE_VERSION}" not in result.stdout or "1.8" not in result.stdout:
        raise HarnessError("Gradle/JDK toolchain gate failed")


def safe_tar_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise HarnessError("unsafe Git archive member")
        source.extractall(destination)


def source_snapshot(staging: Path, revision: str, runner=run) -> Path:
    archive = staging / "source.tar"
    result = runner(["git", "archive", "--format=tar", "-o", str(archive), revision],
                    {"PATH": "/usr/bin:/bin"}, REPOSITORY_ROOT, 300)
    if result.returncode:
        raise HarnessError("could not archive committed source revision")
    source = staging / "source"
    source.mkdir()
    safe_tar_extract(archive, source)
    archive.unlink()
    return source


def sanitize(value: str, replacements: dict[Path, str]) -> str:
    for path, label in sorted(replacements.items(), key=lambda item: len(str(item[0])), reverse=True):
        value = value.replace(str(path), label)
    return value


def unresolved_dependencies(output: str) -> list[dict[str, str]]:
    """Return only Gradle dependency-tree failures with known task/configuration context."""
    module = None
    configuration = None
    unresolved = set()
    for line in output.splitlines():
        task_match = TASK_HEADER.fullmatch(line)
        if task_match:
            module = task_match.group(1)
            configuration = None
            continue
        configuration_match = CONFIGURATION_HEADER.fullmatch(line)
        if configuration_match:
            configuration = configuration_match.group(1)
            continue
        dependency_match = FAILED_DEPENDENCY.fullmatch(line)
        if module is not None and configuration is not None and dependency_match:
            unresolved.add((module, configuration, dependency_match.group(1)))
    return [
        {"module": module, "configuration": configuration, "dependency": dependency}
        for module, configuration, dependency in sorted(unresolved)
    ]


def resolve(cache: Path, installation: Path, java_home: Path, report_root: Path,
            network: bool, runner=run) -> bool:
    with lock(report_root / ".report.lock"):
        current = report_root / "current"
        if current.is_symlink() or current.exists() and not (current / ".overte-legacy-gradle-report").is_file():
            raise HarnessError("refusing unsafe legacy Gradle report target")
        if current.exists():
            shutil.rmtree(current)
        report_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".report-", dir=report_root))
        try:
            (staging / ".overte-legacy-gradle-report").write_text("1\n", encoding="ascii")
            sdk_value = os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", ""))
            sdk_root = Path(sdk_value) if sdk_value else None
            ndk_value = os.environ.get("OVERTE_LEGACY_NDK_HOME", "")
            ndk_root = Path(ndk_value) if ndk_value else (
                sdk_root / "ndk-bundle" if sdk_root is not None else None)
            missing_precondition = None
            if sdk_root is None or not sdk_root.is_dir():
                missing_precondition = "android_sdk"
            elif ndk_root is None or not ndk_root.is_dir():
                missing_precondition = "android_ndk"
            if missing_precondition is not None:
                manifest = {"schemaVersion": 1, "status": "precondition_failed",
                            "precondition": missing_precondition,
                            "reportedModules": list(REPORTED_MODULES),
                            "excludedModules": list(EXCLUDED_MODULES), "gradle": GRADLE_VERSION,
                            "java": "8", "distributionUrl": GRADLE_URL,
                            "distributionSha256": GRADLE_SHA256,
                            "mode": "network" if network else "offline",
                            "networkAllowed": network, "gradleOffline": not network,
                            "dependencyResolutionAttempted": False,
                            "resolutionSucceeded": False, "resolvedGraph": False,
                            "artifactsVerified": False, "apkBuilt": False, "sbom": False}
                (staging / "result.json").write_text(
                    json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
                os.replace(staging, current)
                return False
            revision_result = runner(["git", "rev-parse", "HEAD"], {"PATH": "/usr/bin:/bin"}, REPOSITORY_ROOT, 30)
            if revision_result.returncode:
                raise HarnessError("could not determine source revision")
            revision = revision_result.stdout.strip()
            source = source_snapshot(staging, revision, runner)
            (source / "android/local.properties").write_text(
                f"sdk.dir={sdk_root}\nndk.dir={ndk_root}\n", encoding="utf-8")
            for name in ("home", "tmp", "project-cache", "precompiled"):
                (staging / name).mkdir()
            env = {"JAVA_HOME": str(java_home), "PATH": "/usr/bin:/bin", "HOME": str(staging / "home"),
                   "GRADLE_USER_HOME": str(cache / "gradle-user-home"),
                   "ANDROID_HOME": str(sdk_root),
                   "ANDROID_NDK_HOME": str(ndk_root),
                   "HIFI_ANDROID_PRECOMPILED": str(staging / "precompiled")}
            command = [str(installation / "bin/gradle"), "--no-daemon", "--no-build-cache", "--no-scan", "--stacktrace",
                       "--console", "plain", "--project-cache-dir", str(staging / "project-cache"),
                       "-Djava.io.tmpdir=" + str(staging / "tmp"),
                       "-PVERSION_CODE=" + REPORT_VERSION_CODE,
                       "-PRELEASE_NUMBER=" + REPORT_RELEASE_NUMBER,
                       "-PSUPPRESS_PICO_INTERFACE"]
            if not network:
                command.append("--offline")
            command.extend(f":{module}:dependencies" for module in REPORTED_MODULES)
            result = runner(command, env, source / "android", 900)
            replacements = {source: "<source>", cache: "<cache>", java_home: "<java-home>", staging: "<staging>"}
            stdout, stderr = sanitize(result.stdout, replacements), sanitize(result.stderr, replacements)
            (staging / "stdout.txt").write_text(stdout, encoding="utf-8")
            (staging / "stderr.txt").write_text(stderr, encoding="utf-8")
            gradle_succeeded = result.returncode == 0
            unresolved = unresolved_dependencies(stdout)
            success = gradle_succeeded and not unresolved \
                and not any(marker in stdout + stderr for marker in FAILURE_MARKERS)
            raw_hash = hashlib.sha256((stdout + stderr).encode()).hexdigest()
            manifest = {"schemaVersion": 1, "status": "passed" if success else "failed",
                        "sourceRevision": revision, "reportedModules": list(REPORTED_MODULES),
                        "excludedModules": list(EXCLUDED_MODULES), "gradle": GRADLE_VERSION, "java": "8",
                        "distributionUrl": GRADLE_URL, "distributionSha256": GRADLE_SHA256,
                        "mode": "network" if network else "offline", "networkAllowed": network,
                        "gradleOffline": not network, "dependencyResolutionAttempted": True,
                        "gradleCommandSucceeded": gradle_succeeded,
                        "unresolvedDependencies": unresolved,
                        "resolutionSucceeded": success, "resolvedGraph": success,
                        "artifactsVerified": False, "apkBuilt": False, "sbom": False,
                        "rawReportSha256": raw_hash}
            (staging / "result.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            if success:
                (staging / ".complete").write_text(raw_hash + "\n", encoding="ascii")
            os.replace(staging, current)
            return success
        finally:
            if staging.exists():
                shutil.rmtree(staging)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("toolchain", "resolve"))
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--offline", action="store_true")
    modes.add_argument("--network", action="store_true")
    args = parser.parse_args(argv)
    cache = Path(os.environ.get("OVERTE_LEGACY_GRADLE_CACHE_DIR", ANDROID_ROOT / "build/tools/legacy-gradle-6.5"))
    report = Path(os.environ.get("OVERTE_LEGACY_DEPENDENCY_REPORT_DIR", ANDROID_ROOT / "build/reports/legacy-gradle-dependencies"))
    java_home = Path(os.environ.get("OVERTE_LEGACY_JAVA_HOME", "/usr/lib/jvm/java-8-temurin-jdk"))
    try:
        gate_java(java_home)
        installation = ensure_distribution(cache, args.network)
        gate_gradle(installation, java_home)
        if args.operation == "toolchain":
            return 0
        return 0 if resolve(cache, installation, java_home, report, args.network) else 1
    except HarnessError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
