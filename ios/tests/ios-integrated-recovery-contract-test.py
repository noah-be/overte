#!/usr/bin/env python3
"""Protect durable checkpoints and observability of the iOS integrated build."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ios-integrated.yml"

def require(pattern: str, text: str, message: str) -> None:
    if re.search(pattern, text, re.MULTILINE | re.DOTALL) is None:
        raise AssertionError(message)

def main() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    integrated = workflow[workflow.index("  integrated-configure:"):]
    names = [
        "Restore validated Conan package cache",
        "Probe durable Conan package checkpoint",
        "Restore durable Conan package checkpoint",
        "Restore partial Conan package checkpoint",
        "Resolve audited device dependencies",
        "Save partial Conan package checkpoint after dependency failure",
        "Validate and compact audited device dependencies",
        "Create durable Conan package checkpoint",
        "Upload durable Conan package checkpoint",
        "Save validated Conan package cache",
    ]
    positions = [integrated.index(name) for name in names]
    if positions != sorted(positions):
        raise AssertionError("Conan recovery stages are not fail-safe ordered")
    conan = integrated[positions[0]:positions[-1]]
    require(r"--kind conan", conan, "Conan must use the durable artifact format")
    require(r"resolve-device-dependencies\.outcome == 'failure'", conan,
            "dependency failure must save partial Conan progress")
    require(r"conan cache check-integrity \"\*\"[\s\S]*conan cache clean[\s\S]*conan cache check-integrity \"\*\"",
            conan, "only validated compact Conan state may become durable")
    require(r"retention-days: 30", conan, "durable Conan recovery must outlive cache eviction")

    for phase, raw_log in (
        ("conan-dependencies", "conan-dependencies.log"),
        ("conan-checkpoint", "conan-checkpoint.log"),
        ("client-configure", "configure.log"),
        ("client-build", "xcode-build.log"),
        ("client-package", "package.log"),
    ):
        require(rf"--phase {phase}[\s\S]*?--output-log [^\n]*{re.escape(raw_log)}",
                integrated, f"{phase} must retain complete output")
    for metric in ("--sample-interval 5", "--publish-interval 30", "--inactivity-timeout", "--max-runtime"):
        if integrated.count(metric) < 5:
            raise AssertionError(f"all long phases must expose telemetry: {metric}")
    require(r"Upload runner telemetry and bounded stall diagnostics[\s\S]*if: always\(\)", integrated,
            "resource and stall evidence must survive every job result")
    require(r"Sanitize failure diagnostics[\s\S]*ci-raw-diagnostics/\*\.log", integrated,
            "raw logs must be sanitized before upload")
    if re.search(r"actions/cache/(?:restore|save)@[0-9a-f]{40}[\s\S]{0,300}build-ios/device", integrated):
        raise AssertionError("absolute-path Xcode state must not be cached across runners")
    if "build-ios/device/CMakeCache.txt" in workflow:
        raise AssertionError("CMakeCache.txt must never enter recovery storage")
    print("iOS integrated recovery contract passed")

if __name__ == "__main__":
    main()
