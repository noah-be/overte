#!/usr/bin/env python3
"""Central, local iOS release gate. No implicit build, installation or publication."""
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys

from common import Context, GROUPS, STATIC, HERE, ROOT, digest, git, json_read, private_directory
from scope import Scope, swift_scope
import source_checks
import artifacts
import build as build_checks
import device as device_checks

TOOL_VERSION_COMMANDS = {
    "gitleaks": ["version"], "grype": ["version"], "cppcheck": ["--version"],
    "shellcheck": ["--version"], "cmakelint": ["--version"], "ruff": ["--version"],
    "swiftc": ["--version"], "cmake": ["--version"], "conan": ["--version"],
    "xcodebuild": ["-version"], "xcrun": ["--version"],
    "eslint": ["--version"],
}


def versions(ctx, selected, scope):
    tools = set()
    if set(selected) & {"secrets", "artifact"}:
        tools.add("gitleaks")
    if "dependencies" in selected:
        tools.add("grype")
    if "static" in selected:
        tools.update(("cppcheck", "shellcheck", "cmakelint", "ruff", "eslint"))
        if swift_scope(scope.paths)[0]:
            tools.add("swiftc")
    if "artifact" in selected:
        tools.add("xcrun")
    if "build" in selected and ctx.config.get("executeBuild"):
        tools.update(("cmake", "conan", "xcodebuild", "xcrun"))
    locks = ctx.config.get("toolLocks", {})
    for tool in sorted(tools):
        path = shutil.which(tool)
        result = ctx.command("version-" + tool, [tool, *TOOL_VERSION_COMMANDS[tool]], timeout=60)
        if not path or result is None or result.returncode:
            continue
        raw = result.stdout + result.stderr
        actual = {"binarySha256": digest(Path(path).resolve()), "versionOutputSha256": hashlib.sha256(raw).hexdigest()}
        ctx.tool_versions[tool] = actual
        ctx.need(locks.get(tool) == actual, "tool-lock-" + tool,
                 f"{tool} must match its reviewed executable and version-output hashes.",
                 next_step="Review installed tool provenance and copy its recorded hashes into private toolLocks; never auto-accept unknown versions.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", nargs="?", default="all", choices=["all", "static-only", *GROUPS])
    parser.add_argument("--config", type=Path, default=os.environ.get("OVERTE_IOS_RELEASE_CONFIG"))
    parser.add_argument("--output", type=Path, required=True, help="New private directory outside the repository")
    parser.add_argument("--execute-build", action="store_true", help="Run a cold unsigned macOS device build and Xcode analysis")
    parser.add_argument("--execute-device", action="store_true", help="Run existing suites on dedicated configured physical lab devices (may install/upgrade/restart)")
    args = parser.parse_args()
    os.umask(0o077)
    ctx = None
    try:
        config = {}
        if args.config:
            config_path = Path(args.config).expanduser().absolute()
            if config_path.is_symlink() or config_path.stat().st_mode & 0o077 or config_path.is_relative_to(ROOT):
                raise ValueError("configuration must be a private regular file outside the checkout")
            config = json_read(config_path)
            if config.get("schemaVersion") != 1:
                raise ValueError("unsupported configuration version")
        config.update(executeBuild=args.execute_build, executeDevice=args.execute_device)
        selected = tuple(GROUPS) if args.group == "all" else STATIC if args.group == "static-only" else (args.group,)
        output = private_directory(args.output)
        ctx = Context(config, output, selected)
        scope = Scope(ctx)
        ctx.group = selected[0]
        ctx.need(not git("status", "--porcelain").strip(), "source-uncommitted",
                 "Release evidence requires a committed, clean source tree; local inspection findings still follow.")
        versions(ctx, selected, scope)
        actions = {key: getattr(source_checks, key) for key in STATIC}
        actions.update(build=build_checks.build, artifact=artifacts.artifact,
                       functional=device_checks.device, robustness=device_checks.device,
                       distribution=artifacts.distribution)
        actions["long-running"] = device_checks.device
        for group in selected:
            ctx.group = group
            print(f"Checking: {GROUPS[group]}", flush=True)
            try:
                actions[group](ctx, scope)
                if group == "build" and ctx.config.get("executeBuild"):
                    # The source-stage dependency inventory precedes build execution.
                    # Join the graph actually resolved in this cold build before acceptance.
                    ctx.group = "dependencies"
                    source_checks.resolved_dependency_join(ctx)
                    ctx.group = group
                if group == "artifact" and "build" in selected:
                    exact = bool(ctx.artifact and getattr(ctx, "build_app_tree", None) == artifacts.tree_digest(ctx.artifact))
                    if not exact and ctx.config.get("distribution") != "sideload-unsigned":
                        review = ctx.config.get("reviews", {}).get("signed-build-binding", {})
                        ctx.need(review.get("unsignedAppTreeSha256") == getattr(ctx, "build_app_tree", None)
                                 and bool(getattr(ctx, "build_app_tree", None)), "signed-clean-binding",
                                 "Re-signing review must identify the exact unsigned clean-build tree.")
                        ctx.review("signed-build-binding", "Review re-signing provenance and unchanged product payload between clean output and final signed IPA.", artifact=True)
                    else:
                        ctx.need(exact, "clean-artifact-binding", "Candidate app bytes must match the retained clean-build output.")
            except Exception as error:
                # Do not leak parser input, command argv, usernames, private paths or secrets.
                ctx.add("check-incomplete", "FAIL", message=f"Check could not finish ({type(error).__name__}); no success inferred.",
                        next_step="Inspect private input/configuration and the group's last completed tool log.", critical=True)
        ctx.group = selected[-1]
        if git("rev-parse", "HEAD").strip() != ctx.revision:
            ctx.add("source-changed", "FAIL", message="Source revision changed while checks were running.", critical=True)
        scope.verify_unchanged(ctx)
        return ctx.finish()
    except Exception as error:
        if ctx:
            ctx.add("pipeline-error", "FAIL", message=f"Pipeline incomplete ({type(error).__name__}).", critical=True)
            ctx.finish()
        else:
            print(f"Configuration/setup error ({type(error).__name__}); no checks completed.", file=sys.stderr)
            print("IOS RELEASE CHECK: FAIL")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
