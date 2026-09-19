"""Cold unsigned iOS Release build, never signing, installing or publishing."""
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import shutil
import sys

from artifacts import extract_zip, tree_digest
from common import ROOT, digest, git, json_read, write_json
from scope import file_api_scope

TOOLCHAIN_ENV = {"qt-ios": "OVERTE_IOS_QT_ROOT", "qt-host": "OVERTE_IOS_QT_HOST_ROOT",
                 "v8": "OVERTE_IOS_V8_ROOT", "moltenvk": "OVERTE_IOS_MOLTENVK_ROOT"}


def check_project(ctx, payload):
    project = payload.get("project", {})
    ctx.need("Overte" in project.get("targets", []) and "Release" in project.get("configurations", []),
             "xcode-project-surface", "Generated project must expose the Full Client target and Release configuration.")
    if "Overte" not in project.get("schemes", []):
        ctx.add("xcode-scheme", "WARNING", message="No shared Overte scheme reported; the gate explicitly builds by target. Review scheme requirements for distribution tooling.")
    ctx.inventories["xcode-project"] = payload


def check_settings(ctx, payload):
    targets = [x for x in payload if x.get("target") == "Overte"]
    if not ctx.need(len(targets) == 1, "xcode-settings-target", "Release build settings must identify exactly one Overte target."):
        return
    s = targets[0]["buildSettings"]
    for key, expected in {"CONFIGURATION": "Release", "PLATFORM_NAME": "iphoneos", "SDKROOT": "iphoneos"}.items():
        value = s.get(key, "")
        ctx.need(expected in value.lower() if key == "SDKROOT" else value == expected,
                 "setting-" + key, f"Resolved Xcode {key} must select the device Release configuration.")
    ctx.need(s.get("PRODUCT_BUNDLE_IDENTIFIER") == ctx.config.get("bundleIdentifier"), "setting-bundle", "Resolved bundle ID differs from release intent.")
    ctx.need(s.get("ARCHS", "").split() == ["arm64"], "setting-arch", "Release must build arm64 device architecture only.")
    ctx.need(s.get("IPHONEOS_DEPLOYMENT_TARGET") == "17.0", "setting-deployment", "Deployment target differs from ios/versions.env.")
    ctx.need(s.get("GCC_OPTIMIZATION_LEVEL") not in (None, "", "0"), "setting-optimization", "Release optimization must be enabled.")
    ctx.need(s.get("DEBUG_INFORMATION_FORMAT") == "dwarf-with-dsym", "setting-symbols", "Release must produce a separate dSYM.")
    ctx.need(s.get("ENABLE_TESTABILITY") != "YES", "setting-testability", "Release must not enable testability.")
    flags = " ".join(str(s.get(k, "")) for k in ("GCC_PREPROCESSOR_DEFINITIONS", "OTHER_CFLAGS", "OTHER_CPLUSPLUSFLAGS", "OTHER_SWIFT_FLAGS"))
    ctx.need(not re.search(r"(?:^|\s)(?:-D)?(?:DEBUG(?:=1)?|OVERTE_IOS_E2E_TEST_BUILD(?:=1)?|OVERTE_IOS_WORLD_OBSERVATION_BUILD(?:=1)?)(?:\s|$)", flags),
             "setting-debug-flags", "Debug/test/world observation definitions must be absent.")
    for key in ("STRIP_INSTALLED_PRODUCT", "COPY_PHASE_STRIP", "DEAD_CODE_STRIPPING"):
        if s.get(key) != "YES":
            ctx.add("setting-" + key, "WARNING", message=f"Resolved {key} is not YES; inspect artifact symbols and dead code.")
    ctx.inventories["xcode-settings"] = payload


def build(ctx, scope):
    if not ctx.config.get("executeBuild"):
        return consume_receipt(ctx)
    if not ctx.need(not any(x["status"] == "FAIL" and x["rule"].startswith("tool-") for x in ctx.findings),
                    "build-tool-prerequisites", "Resolve tool availability and provenance before executing a cold build."):
        return
    if not ctx.need(platform.system() == "Darwin", "build-host", "A macOS Apple Silicon Xcode host is required."):
        return
    if not ctx.need(not git("status", "--porcelain").strip(), "clean-source", "Commit all intended changes before a clean build; the source checkout must be clean."):
        return
    settings = ctx.config.get("cleanBuild", {})
    lock = Path(settings.get("conanLock", ""))
    if not ctx.need(lock.is_file() and settings.get("conanLockSha256") == digest(lock),
                    "conan-lock", "A reviewed hash-bound iOS Conan lockfile is required."):
        return
    artifacts = settings.get("inputs", {})
    if not ctx.need(set(artifacts) == set(TOOLCHAIN_ENV), "build-inputs", "Provide hashed ZIP inputs for qt-ios, qt-host, v8 and moltenvk."):
        return
    source = ctx.output / "clean-source"
    result = ctx.command("clone", ["git", "clone", "--no-hardlinks", "--no-checkout", ROOT, source], timeout=900)
    if result is None or result.returncode:
        return
    result = ctx.command("checkout", ["git", "checkout", "--detach", ctx.revision], cwd=source)
    if result is None or result.returncode:
        return
    submodules = git("ls-files", "--stage", root=source)
    if not ctx.need(not any(line.startswith("160000 ") for line in submodules.splitlines()),
                    "submodule-inputs", "Submodules need an explicit pinned provisioning extension before this cold-build driver can proceed."):
        return
    out = source / "build-ios/release-gate"
    out.mkdir(parents=True)
    ctx.build_source, ctx.build_dir = source, out
    # Do not inherit signing, compiler-launcher or developer-specific dependency selectors.
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "DEVELOPER_DIR", "SYSTEMROOT"}}
    env.update(CONAN_HOME=str(ctx.output / "conan-home"), PYTHONNOUSERSITE="1",
               CCACHE_DISABLE="1", SCCACHE_DISABLE="1", ZERO_AR_DATE="1",
               SOURCE_DATE_EPOCH=git("show", "-s", "--format=%ct").strip())
    inputs_report = {}
    for kind, variable in TOOLCHAIN_ENV.items():
        item = artifacts[kind]
        archive = Path(item["archive"])
        if not ctx.need(archive.is_file() and digest(archive) == item.get("sha256"), "build-input-hash", f"Invalid immutable input: {kind}"):
            return
        destination = source / "build-ios/external" / kind
        destination.mkdir(parents=True)
        extract_zip(archive, destination, max_bytes=40 * 1024**3)
        root = (destination / item.get("root", ".")).resolve()
        if not ctx.need(root.is_relative_to(destination) and root.is_dir(), "build-input-root", f"Invalid root for {kind}"):
            return
        env[variable] = str(root)
        inputs_report[kind] = {"sha256": item["sha256"], "root": item.get("root", ".")}
    sdk = ctx.command("sdk-path", ["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], env=env)
    if sdk is None or sdk.returncode:
        return
    env["OVERTE_IOS_DEVICE_SDK_PATH"] = sdk.stdout.decode().strip()
    query = out / ".cmake/api/v1/query"
    query.mkdir(parents=True)
    (query / "codemodel-v2").touch()
    (query / "cache-v2").touch()
    (query / "cmakeFiles-v1").touch()
    conan = out / "conan"
    conan.mkdir()
    commands = [
        ("swift-host-helper", ["xcrun", "swiftc", "-frontend", "-parse", "ios/ci/verify-apple-bundle.swift"]),
        ("host-contracts", ["bash", "ios/tests/run-tests.sh"]),
        ("conan-remote", ["conan", "remote", "add", "overte", "https://artifactory.overte.org/artifactory/api/conan/overte"]),
        ("export-onetbb", ["conan", "export", "ios/conan/recipes/onetbb", "--user=overte", "--channel=ios-static"]),
        ("export-webrtc", ["conan", "export", "ios/conan/recipes/webrtc-audio-processing", "--user=overte", "--channel=ios-static"]),
        ("conan-install", ["conan", "install", "ios", "--profile:host=ios/conan/profiles/ios-arm64",
                            "--profile:build=ios/conan/profiles/macos-arm64", "--build=missing",
                            "--options=overte-ios-dependencies/*:with_graphics_toolchain=True",
                            "--lockfile=" + str(lock.resolve()), "--output-folder=" + str(conan), "--format=json"]),
        ("configure", ["bash", "ios/build-ios.sh", "configure", "--platform", "device", "--configuration", "Release",
                       "--client-graph", "--build-dir", str(out), "--bundle-id", ctx.config["bundleIdentifier"]]),
        ("compile", ["cmake", "--build", out, "--config", "Release", "--target", "Overte", "--parallel", str(settings.get("jobs", 4)),
                     "--", "MARKETING_VERSION=" + ctx.config["marketingVersion"], "CURRENT_PROJECT_VERSION=" + str(ctx.config["buildNumber"])]),
    ]
    completed = []
    for name, command in commands:
        result = ctx.command(name, command, cwd=source, env=env, timeout=8 * 3600)
        if result is None or result.returncode:
            return
        completed.append(name)
        if name == "host-contracts" and re.search(rb"\bSKIP\b", result.stdout + result.stderr):
            ctx.add("host-contract-skipped", "FAIL", message="Host contract suite skipped prerequisites; prepare required host dependencies and rerun.", critical=True)
        if name == "conan-install":
            graph = conan / "graph.json"
            graph.write_bytes(result.stdout)
            ctx.generated_conan_graph = graph
            audit = ctx.command("resolved-conan-audit", [sys.executable, source / "ios/tools/audit-conan-graph.py", graph], cwd=source, env=env)
            if audit is None or audit.returncode:
                return
    projects = list(out.glob("*.xcodeproj"))
    if not ctx.need(len(projects) == 1, "xcode-project", "Expected exactly one generated root Xcode project."):
        return
    base = ["xcodebuild", "-project", projects[0], "-target", "Overte", "-configuration", "Release", "-sdk", "iphoneos", "CODE_SIGNING_ALLOWED=NO",
            "MARKETING_VERSION=" + ctx.config["marketingVersion"], "CURRENT_PROJECT_VERSION=" + str(ctx.config["buildNumber"])]
    listing = ctx.command("project-list", ["xcodebuild", "-project", projects[0], "-list", "-json"], cwd=source, env=env)
    if listing is None or listing.returncode:
        return
    import json
    project = json.loads(listing.stdout)
    check_project(ctx, project)
    resolved = ctx.command("settings", [*base, "-showBuildSettings", "-json"], cwd=source, env=env)
    if resolved is None or resolved.returncode:
        return
    payload = json.loads(resolved.stdout)
    check_settings(ctx, payload)
    file_api_scope(ctx, out, source)
    analysis = ctx.command("clang-analyzer", [*base, "analyze", "RUN_CLANG_STATIC_ANALYZER=YES",
                                             "CLANG_ANALYZER_OUTPUT=plist", "CLANG_ANALYZER_OUTPUT_DIR=" + str(ctx.output / "clang-analysis")],
                           cwd=source, env=env, timeout=8 * 3600)
    if analysis is None or analysis.returncode:
        return
    diagnostics = analysis.stdout + analysis.stderr
    if re.search(rb"warning:.*\[(?:core|unix|osx|security|cplusplus|deadcode)\.", diagnostics):
        ctx.add("clang-analysis-diagnostics", "FAIL", message="Clang analyzer reported a defect; review the private analyzer log.", critical=True)
    elif b"warning:" in diagnostics:
        ctx.add("clang-compiler-warnings", "WARNING", message="Compiler diagnostics need triage; see the private analyzer log.")
    app = out / "interface/Release-iphoneos/Overte.app"
    if not ctx.need(app.is_dir(), "built-app", "The clean build did not produce the expected Full Client app."):
        return
    dsym = app.with_name("Overte.app.dSYM") / "Contents/Resources/DWARF/Overte"
    ctx.command("dsym-content", [sys.executable, source / "ios/tools/verify-dsym-content.py", dsym], cwd=source, env=env)
    app_uuid = ctx.command("app-uuid", ["xcrun", "dwarfdump", "--uuid", app / "Overte"], env=env)
    dsym_uuid = ctx.command("dsym-uuid", ["xcrun", "dwarfdump", "--uuid", dsym], env=env)
    if app_uuid and dsym_uuid:
        pattern = rb"UUID: ([0-9A-Fa-f-]+) \(arm64\)"
        left, right = re.findall(pattern, app_uuid.stdout), re.findall(pattern, dsym_uuid.stdout)
        ctx.need(len(left) == 1 and left == right, "dsym-binding", "dSYM must contain the same arm64 UUID as the application.")
    sha = tree_digest(app)
    ctx.build_app_tree = sha
    status = "FAIL" if any(x["group"] == "build" and x["status"] == "FAIL" for x in ctx.findings) else "PASS"
    receipt = {"schemaVersion": 1, "sourceRevision": ctx.revision, "status": status,
        "appTreeSha256": sha, "source": str(source), "buildDirectory": str(out),
        "settings": payload, "project": project, "inputs": inputs_report, "conanLockSha256": digest(lock),
        "completed": completed + ["clang-analyzer", "dsym"], "toolVersions": ctx.tool_versions}
    write_json(ctx.output / "clean-build-receipt.json", receipt)
    if not ctx.config.get("artifact"):
        ctx.config.update(artifact=str(app), artifactSha256=sha)
    ctx.review("clean-build-inputs", "Review immutable SDK/package provenance, host tool versions and undeclared absolute dependency paths.")


def consume_receipt(ctx):
    name = ctx.config.get("cleanBuildReceipt")
    if not ctx.need(name, "clean-build-evidence", "Supply a previous cold-build receipt or explicitly request --execute-build on macOS."):
        return
    receipt = json_read(Path(name))
    ctx.need(receipt.get("schemaVersion") == 1 and receipt.get("status") == "PASS"
             and receipt.get("sourceRevision") == ctx.revision,
             "clean-build-binding", "Cold-build receipt must have passed at the exact current revision.")
    required = {"swift-host-helper", "host-contracts", "conan-remote", "export-onetbb", "export-webrtc", "conan-install", "configure", "compile", "clang-analyzer", "dsym"}
    ctx.need(required <= set(receipt.get("completed", [])), "clean-build-steps", "Cold-build receipt lacks required completed steps.")
    ctx.need(set(receipt.get("inputs", {})) == set(TOOLCHAIN_ENV) and re.fullmatch(r"[a-f0-9]{64}", receipt.get("conanLockSha256", "")),
             "clean-build-inputs", "Cold-build receipt lacks immutable dependency inputs.")
    check_settings(ctx, receipt["settings"])
    check_project(ctx, receipt["project"])
    ctx.build_app_tree = receipt.get("appTreeSha256")
    source, build = Path(receipt["source"]), Path(receipt["buildDirectory"])
    ctx.need(git("rev-parse", "HEAD", root=source).strip() == ctx.revision, "receipt-source", "Retained clean checkout differs from receipt.")
    file_api_scope(ctx, build, source)
    ctx.review("clean-build-inputs", "Review retained build receipt, private logs and immutable toolchain provenance; this receipt is local evidence, not a signed attestation.")
