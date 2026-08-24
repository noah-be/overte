#!/usr/bin/env python3
"""Deterministic, dependency-free mutation runner for critical Phone policies."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT_LOCK_TIMEOUT_SECONDS = 600.0
SCRIPTS = ROOT.parent / "scripts/system"
JAVA_PRODUCTION = {
    "legacy-url": ROOT / "phone/apps/interface/src/main/java/io/highfidelity/hifiinterface/HifiUtils.java",
    "pico-audio": ROOT / "vr/pico/apps/picoInterface/src/main/java/org/overte/pico/AndroidAudioInputPolicy.java",
    "pico-activity": ROOT / "vr/pico/apps/picoInterface/src/main/java/org/overte/pico/PicoInterfaceActivityPolicy.java",
    "pico-instance": ROOT / "vr/pico/apps/picoInterface/src/main/java/org/overte/pico/PicoActivityInstancePolicy.java",
    "deep": ROOT / "phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneDeepLinkNormalizer.java",
    "launch": ROOT / "phone/apps/phoneInterface/src/main/java/org/overte/phone/PhoneLaunchState.java",
    "permission": ROOT / "phone/apps/phoneInterface/src/main/java/org/overte/phone/PhonePermissionFlow.java",
    "pending": ROOT / "phone/apps/phoneInterface/src/main/java/org/overte/phone/PhonePendingUrlPolicy.java",
    "asset": ROOT / "common/libraries/qt/src/main/java/io/highfidelity/utils/SafeAssetPath.java",
    "extractor": ROOT / "common/libraries/qt/src/main/java/io/highfidelity/utils/AssetCacheExtractor.java",
}
JAVA_TESTS = sorted((ROOT / "common/tests/java/org/overte/phone").glob("*Test.java")) + [
    ROOT / "common/tests/java/io/highfidelity/hifiinterface/HifiUtilsStandaloneTest.java",
    ROOT / "common/tests/java/org/overte/pico/AndroidAudioInputPolicyStandaloneTest.java",
    ROOT / "common/tests/java/org/overte/pico/PicoInterfaceActivityPolicyStandaloneTest.java",
    ROOT / "common/tests/java/io/highfidelity/utils/SafeAssetPathStandaloneTest.java",
    ROOT / "common/tests/java/io/highfidelity/utils/AssetCacheExtractorStandaloneTest.java",
]
JAVA_MAINS = [
    "io.highfidelity.hifiinterface.HifiUtilsStandaloneTest",
    "org.overte.pico.AndroidAudioInputPolicyStandaloneTest",
    "org.overte.pico.PicoInterfaceActivityPolicyStandaloneTest",
    "org.overte.phone.PhoneDeepLinkNormalizerTest",
    "org.overte.phone.PhoneLaunchStateStandaloneTest",
    "org.overte.phone.PhonePermissionFlowStandaloneTest",
    "org.overte.phone.PhonePendingUrlPolicyStandaloneTest",
    "io.highfidelity.utils.SafeAssetPathStandaloneTest",
    "io.highfidelity.utils.AssetCacheExtractorStandaloneTest",
]
GRAPHICS = ROOT.parent / "interface/src/ui/PhoneGraphicsPolicy.h"
HANDOFF = ROOT / "phone/apps/phoneInterface/src/PhonePendingHandoff.h"
LOGIN_STATE = ROOT.parent / "interface/src/ui/PhoneLoginState.h"
NATIVE_TESTS = {
    "graphics": sorted((ROOT / "common/tests/native").glob("phone_graphics_*_test.cpp")),
    "handoff": sorted((ROOT / "common/tests/native").glob("phone_pending_handoff_*_test.cpp")),
    "login": sorted((ROOT / "common/tests/native").glob("phone_login_state_*_test.cpp")),
}
JAVASCRIPT_TESTS = {
    SCRIPTS / "+android_phoneInterface/mobileTabletApps.js": ROOT / "common/tests/javascript/test/mobile-tablet-apps.production.test.js",
    SCRIPTS / "+android_phoneInterface/mobileActionBar.js": ROOT / "common/tests/javascript/test/mobile-action-bar.production.test.js",
    SCRIPTS / "quickGoto.js": ROOT / "common/tests/javascript/test/quick-goto.production.test.js",
    SCRIPTS / "places/places.js": ROOT / "common/tests/javascript/test/places.production.test.js",
    SCRIPTS / "places/portal.js": ROOT / "common/tests/javascript/test/portal.production.test.js",
}


@dataclass(frozen=True)
class Mutant:
    name: str
    family: str
    source: Path
    old: str
    new: str
    extended: bool = False


MUTANTS = [
    Mutant("legacy-url-skip-hifi-prefix", "java", JAVA_PRODUCTION["legacy-url"], 'urlString = "hifi://" + urlString;', "urlString = urlString;"),
    Mutant("legacy-asset-skip-base-prefix", "java", JAVA_PRODUCTION["legacy-url"], "String normalizedBase = baseUrl.trim();", 'String normalizedBase = "";'),
    Mutant("pico-audio-accept-unknown-source", "java", JAVA_PRODUCTION["pico-audio"], "return Source.CAMCORDER;\n        }\n        return null;", "return Source.CAMCORDER;\n        }\n        return Source.MIC;"),
    Mutant("pico-audio-disable-callback-overflow", "java", JAVA_PRODUCTION["pico-audio"], "return callbackBytes > MAX_CALLBACK_BYTES ? null : (int) callbackBytes;", "return (int) callbackBytes;"),
    Mutant("pico-audio-deliver-stale-read", "java", JAVA_PRODUCTION["pico-audio"], "return bytesRead > 0 && running && ownsRecorder;", "return bytesRead > 0;"),
    Mutant("pico-activity-null-extra-literal", "java", JAVA_PRODUCTION["pico-activity"], "hasApplicationArguments && applicationArguments != null", "hasApplicationArguments"),
    Mutant("pico-activity-pre-s-exact-alarm", "java", JAVA_PRODUCTION["pico-activity"], "sdkInt < 31 || canScheduleExactAlarms", "sdkInt < 31 && canScheduleExactAlarms"),
    Mutant("pico-instance-ignore-registration", "java", JAVA_PRODUCTION["pico-instance"], "current = instance;", "current = null;"),
    Mutant("pico-instance-retain-destroyed", "java", JAVA_PRODUCTION["pico-instance"], "if (current == instance)", "if (false)"),
    Mutant("deep-link-length-boundary", "java", JAVA_PRODUCTION["deep"], "> MAX_URL_LENGTH", ">= MAX_URL_LENGTH"),
    Mutant("deep-link-allow-unsafe", "java", JAVA_PRODUCTION["deep"], "|| containsUnsafeCharacter(value)", "|| false"),
    Mutant("deep-link-accept-any-scheme", "java", JAVA_PRODUCTION["deep"], 'if (!"overte".equalsIgnoreCase(scheme) && !"hifi".equalsIgnoreCase(scheme))', "if (false)", True),
    Mutant("launch-skip-restored-validation", "java", JAVA_PRODUCTION["launch"], "PhoneLaunchState(String pendingUrl, boolean interfaceLaunched) {\n        this.pendingUrl = PhoneDeepLinkNormalizer.normalize(pendingUrl);", "PhoneLaunchState(String pendingUrl, boolean interfaceLaunched) {\n        this.pendingUrl = pendingUrl;"),
    Mutant("launch-repeat-interface", "java", JAVA_PRODUCTION["launch"], "if (interfaceLaunched) {", "if (false) {", True),
    Mutant("permission-accept-unrelated", "java", JAVA_PRODUCTION["permission"], "requestCode == RECORD_AUDIO_REQUEST", "requestCode != RECORD_AUDIO_REQUEST"),
    Mutant("pending-attempt-while-paused", "java", JAVA_PRODUCTION["pending"], "pendingUrl != null && resumed", "pendingUrl != null || resumed"),
    Mutant("pending-retry-at-limit", "java", JAVA_PRODUCTION["pending"], "failedAttempts < maximumAttempts", "failedAttempts <= maximumAttempts", True),
    Mutant("asset-disable-containment", "java", JAVA_PRODUCTION["asset"], "!destination.getPath().startsWith(rootPrefix)", "false"),
    Mutant("asset-allow-root", "java", JAVA_PRODUCTION["asset"], "destination.equals(canonicalRoot)", "false", True),
    Mutant("asset-allow-absolute", "java", JAVA_PRODUCTION["asset"], "new File(relativePath).isAbsolute()", "false", True),
    Mutant("extractor-ignore-marker-validation", "java", JAVA_PRODUCTION["extractor"], 'if (cacheStamp == null || !cacheStamp.matches("(?:[0-9]{1,19}|[0-9a-f]{64})"))', "if (false)"),
    Mutant("extractor-disable-cache-hit", "java", JAVA_PRODUCTION["extractor"], "if (cacheStampFile.isFile())", "if (false)"),
    Mutant("extractor-accept-marker-directory", "java", JAVA_PRODUCTION["extractor"], "if (cacheStampFile.exists())", "if (false)", True),
    Mutant("extractor-accept-missing-root", "java", JAVA_PRODUCTION["extractor"], "if (!destinationRoot.isDirectory())", "if (false)", True),
    Mutant("extractor-disable-parent-creation", "java", JAVA_PRODUCTION["extractor"], "if (!parent.exists() && !parent.mkdirs() && !parent.isDirectory())", "if (!parent.exists())"),
    Mutant("extractor-disable-stale-replacement", "java", JAVA_PRODUCTION["extractor"], "if (destination.exists() && !destination.delete())", "if (false)"),
    Mutant("extractor-invent-missing-marker", "java", JAVA_PRODUCTION["extractor"], "String cacheStamp = assets.poll();", 'String cacheStamp = "123";', True),
    Mutant("login-initially-pending", "login", LOGIN_STATE, "bool _requestPending { false };", "bool _requestPending { true };"),
    Mutant("login-accept-duplicate-submit", "login", LOGIN_STATE, "if (_requestPending) {", "if (false) {"),
    Mutant("login-submit-does-not-pend", "login", LOGIN_STATE, "_requestPending = true;", "_requestPending = false;"),
    Mutant("login-terminal-keeps-pending", "login", LOGIN_STATE, "_requestPending = false;\n    }", "_requestPending = true;\n    }", True),
    Mutant("login-invert-observer", "login", LOGIN_STATE, "return _requestPending;", "return !_requestPending;", True),
    Mutant("login-share-state-between-instances", "login", LOGIN_STATE, "bool _requestPending { false };", "inline static bool _requestPending { false };", True),
    Mutant("graphics-bool-never-true", "graphics", GRAPHICS, 'normalized == "1" || normalized == "on" || normalized == "true" || normalized == "enabled"', "false"),
    Mutant("graphics-float-disable-lower-clamp", "graphics", GRAPHICS, "parsed < minimum ? minimum", "false ? minimum"),
    Mutant("graphics-unsigned-accept-suffix", "graphics", GRAPHICS, "*parseEnd != '\\0'", "false"),
    Mutant("graphics-disable-ascii-lowercase", "graphics", GRAPHICS, "return value >= 'A' && value <= 'Z' ? static_cast<char>(value - 'A' + 'a') : value;", "return value;", True),
    Mutant("graphics-float-accept-suffix", "graphics", GRAPHICS, "parser.peek() != std::char_traits<char>::eof()", "false", True),
    Mutant("graphics-unsigned-auto-base", "graphics", GRAPHICS, "&parseEnd, 10", "&parseEnd, 0", True),
    Mutant("handoff-never-pending", "handoff", HANDOFF, "_pending = true;", "_pending = false;"),
    Mutant("handoff-ignore-readiness", "handoff", HANDOFF, "if (!ready || !_pending)", "if (false)", True),
    Mutant("handoff-invalid-keeps-stale", "handoff", HANDOFF, "clear();\n            return;", "return;", True),
    Mutant("js-tablet-leak-menu-button", "javascript", SCRIPTS / "+android_phoneInterface/mobileTabletApps.js", "tablet.removeButton(menuButton);", "void 0;"),
    Mutant("js-actionbar-leak-goto-handler", "javascript", SCRIPTS / "+android_phoneInterface/mobileActionBar.js", 'disconnectSignal(gotoButton, "clicked", onGotoClicked);', "void 0;"),
    Mutant("js-quick-goto-disable-home", "javascript", SCRIPTS / "quickGoto.js", "if (home) {", "if (false) {"),
    Mutant("js-places-keep-message-subscription", "javascript", SCRIPTS / "places/places.js", "Messages.unsubscribe(portalChannelName);", "void 0;"),
    Mutant("js-portal-allow-duplicate-entry", "javascript", SCRIPTS / "places/portal.js", "if (!portalReady || teleportTimer !== null) {", "if (!portalReady) {"),
]


def command(args: list[str], cwd: Path, timeout: int = 30, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ) if env is None else dict(env)
    # javac/c++ may create compiler intermediates outside their output tree.
    # Keep those in the already unique mutation work directory as well.
    environment["TMPDIR"] = str(cwd)
    try:
        return subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                              timeout=timeout, check=False, env=environment)
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(args, 124, error.stdout or "", "mutation command timed out")
    except FileNotFoundError as error:
        return subprocess.CompletedProcess(args, 127, "", f"required command unavailable: {error.filename}")


def replace_once(source: Path, destination: Path, old: str, new: str) -> None:
    text = source.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"mutation pattern for {source} matched {count} times (expected exactly once)")
    destination.write_text(text.replace(old, new, 1), encoding="utf-8")


def java_run(work: Path, mutant: Mutant | None) -> tuple[str, str]:
    source_dir = work / "java-src"
    classes = work / "classes"
    source_dir.mkdir(parents=True)
    classes.mkdir()
    sources = []
    for source in JAVA_PRODUCTION.values():
        destination = source_dir / source.name
        if mutant and source == mutant.source:
            replace_once(source, destination, mutant.old, mutant.new)
        else:
            shutil.copy2(source, destination)
        sources.append(destination)
    compile_result = command([
        "javac", "-d", str(classes), *map(str, sources),
        *map(str, JAVA_TESTS),
    ], work)
    if compile_result.returncode:
        return "error", "javac failed:\n" + compile_result.stderr
    for main in JAVA_MAINS:
        result = command(["java", f"-Djava.io.tmpdir={work}", "-cp", str(classes), main], work)
        if result.returncode:
            output = result.stdout + result.stderr
            return ("killed", output) if "AssertionError" in output else ("error", f"harness crashed ({main}):\n{output}")
    return "survived", ""


def native_run(work: Path, family: str, mutant: Mutant | None) -> tuple[str, str]:
    include = work / "include"
    include.mkdir(parents=True)
    source = {"graphics": GRAPHICS, "handoff": HANDOFF, "login": LOGIN_STATE}[family]
    destination = include / source.name
    if mutant:
        replace_once(source, destination, mutant.old, mutant.new)
    else:
        shutil.copy2(source, destination)
    for test in NATIVE_TESTS[family]:
        binary = work / test.stem
        result = command([
            "c++", "-std=c++17", "-UNDEBUG", "-I", str(include),
            "-I", str(ROOT / "common/tests/native/support"), str(test), "-o", str(binary),
        ], work)
        if result.returncode:
            return "error", "C++ compilation failed:\n" + result.stderr
        result = command([str(binary)], work)
        if result.returncode:
            output = result.stdout + result.stderr
            return ("killed", output) if result.returncode == 1 and "expectation failed:" in output else ("error", f"harness crashed ({test.name}):\n{output}")
    return "survived", ""


def javascript_run(work: Path, mutant: Mutant | None) -> tuple[str, str]:
    tests = list(JAVASCRIPT_TESTS.values()) if mutant is None else [JAVASCRIPT_TESTS[mutant.source]]
    environment = dict(os.environ)
    if mutant:
        mutated_source = work / mutant.source.name
        replace_once(mutant.source, mutated_source, mutant.old, mutant.new)
        environment["OVERTE_MUTATION_TARGET"] = str(mutant.source)
        environment["OVERTE_MUTATION_SOURCE"] = str(mutated_source)
    for test in tests:
        result = command(["node", "--test", str(test)], ROOT / "common/tests/javascript", env=environment)
        if result.returncode:
            output = result.stdout + result.stderr
            return ("killed", output) if result.returncode == 1 and "AssertionError" in output else ("error", f"JavaScript harness crashed ({test.name}):\n{output}")
    return "survived", ""


def execute(scratch: Path, mutant: Mutant | None, family: str) -> tuple[str, str]:
    work = scratch / (mutant.name if mutant else f"baseline-{family}")
    work.mkdir()
    try:
        if family == "java":
            return java_run(work, mutant)
        if family == "javascript":
            return javascript_run(work, mutant)
        return native_run(work, family, mutant)
    except (OSError, RuntimeError) as error:
        return "error", f"mutation setup failed: {error}"


def write_report(path: Path, payload: dict) -> None:
    """Atomically publish valid JSON even when independent jobs share a workspace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2)
            output.write("\n")
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def report_lock_timeout() -> float:
    value = os.environ.get(
        "OVERTE_MUTATION_REPORT_LOCK_TIMEOUT_SECONDS",
        str(DEFAULT_REPORT_LOCK_TIMEOUT_SECONDS),
    )
    try:
        timeout = float(value)
    except ValueError as error:
        raise ValueError("mutation report lock timeout must be a non-negative number") from error
    if timeout < 0 or not math.isfinite(timeout):
        raise ValueError("mutation report lock timeout must be a non-negative number")
    return timeout


@contextmanager
def mutation_report_lock(report: Path, timeout: float):
    """Serialize complete mutation runs that publish the same report path."""
    report.parent.mkdir(parents=True, exist_ok=True)
    lock_path = report.parent / f".{report.name}.lock"
    with lock_path.open("a+b") as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"timed out waiting for mutation report lock after {timeout:g} seconds")
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def run_mutations(args: argparse.Namespace) -> int:
    selected = [mutant for mutant in MUTANTS if args.extended or not mutant.extended]
    results = []
    baselines = []
    # Keep compiler-heavy scratch data off a potentially quota-limited shared
    # /tmp. TemporaryDirectory still gives concurrent runs unique, cleaned paths.
    scratch_parent = ROOT / "build/tmp/mutation"
    scratch_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="overte-mutation-", dir=scratch_parent) as temporary:
        scratch = Path(temporary)
        for family in sorted({mutant.family for mutant in selected}):
            status, details = execute(scratch, None, family)
            baselines.append({"family": family, "status": status, "details": details if status == "error" else ""})
            if status != "survived":
                print(f"BASELINE ERROR [{family}]: {details}")
                write_report(args.report, {
                    "mode": "extended" if args.extended else "quick",
                    "seedPolicy": "fixed deterministic inputs in production-facing harnesses",
                    "baseline": baselines, "killed": 0, "survived": 0, "errors": 1,
                })
                return 2
        for mutant in selected:
            status, details = execute(scratch, mutant, mutant.family)
            results.append({"name": mutant.name, "family": mutant.family, "status": status})
            print(f"{status.upper()}: {mutant.name}")
            if status == "error":
                print(details)
    killed = sum(result["status"] == "killed" for result in results)
    survived = sum(result["status"] == "survived" for result in results)
    errors = sum(result["status"] == "error" for result in results)
    write_report(args.report, {
        "mode": "extended" if args.extended else "quick",
        "seedPolicy": "fixed deterministic inputs in production-facing harnesses",
        "baseline": baselines, "killed": killed, "survived": survived, "errors": errors, "mutants": results,
    })
    print(f"Critical policy mutation score: {killed}/{len(results)} killed; {errors} harness errors")
    return 1 if survived or errors else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extended", action="store_true", help="include the slower periodic mutation set")
    parser.add_argument("--report", type=Path, default=ROOT / "build/reports/mutation/critical-policies.json")
    args = parser.parse_args()
    try:
        timeout = report_lock_timeout()
    except ValueError as error:
        print(f"Invalid mutation report lock: {error}", file=sys.stderr)
        return 2
    try:
        with mutation_report_lock(args.report, timeout):
            args.report.unlink(missing_ok=True)
            return run_mutations(args)
    except TimeoutError as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
