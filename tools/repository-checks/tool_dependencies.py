#!/usr/bin/env python3
"""Bounded tool checks, with an explicit trusted-controller S3 capability."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile


PROJECTS = ("server-console", "tools/jsdoc")
S3_PROJECT = "script-archive/marketplace/S3Server"
BROWSER_PROJECT = "browser-client"
PACKAGE_PROJECTS = (*PROJECTS, S3_PROJECT)
# Trusted definition only: these commands have not qualified a replacement for
# the existing browser/native journeys. npm run build retains avatar prebuild.
BROWSER_MANIFEST_SCRIPTS = {
    "prebuild": "node tools/prepare-default-avatar.mjs",
    "build": "tsc --noEmit && vite build && node tools/build-notices.mjs",
    "test": "tsx --test src/*.test.ts tests/*.test.ts tests/*.test.mjs gateway/*.test.mjs",
}
BROWSER_MANIFEST_COMMANDS = (
    ("npm", "ci", "--ignore-scripts", "--no-fund", "--no-audit"),
    ("npm", "audit", "--audit-level=low"),
    ("npm", "run", "build"),
    ("npm", "test"),
)
MANIFESTS = frozenset(f"{project}/{name}" for project in PROJECTS
                      for name in ("package.json", "package-lock.json"))


def affected_projects(paths: list[str], regular: bool = True, *, include_s3: bool = False,
                      include_browser: bool = False) -> tuple[str, ...]:
    """Only exact manifests and regular Markdown may share this narrow route."""
    projects = PACKAGE_PROJECTS if include_s3 else PROJECTS
    if include_browser:
        projects = (*projects, BROWSER_PROJECT)
    manifests = frozenset(f"{project}/{name}" for project in projects
                          for name in ("package.json", "package-lock.json"))
    if (not regular or not paths
            or any(path not in manifests and not path.endswith(".md") for path in paths)):
        return ()
    return tuple(project for project in projects
                 if any(path in manifests and path.startswith(project + "/") for path in paths))


def push_projects(root: Path, event: dict) -> tuple[str, ...]:
    """Read both sides of the exact protected push; uncertain inventory stays full."""
    if "before" not in event or "after" not in event:
        return ()
    repository = event.get("repository", {})
    if repository.get("full_name") != "noah-l-frank/overte" or repository.get("id") != 1319052603:
        raise ValueError("push repository identity mismatch")
    before, after = event["before"], event["after"]
    if any(not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
           for sha in (before, after)):
        raise ValueError("invalid push commit identity")
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True,
                                       stderr=subprocess.PIPE, timeout=30)
    if git("rev-parse", "HEAD").strip() != after:
        raise ValueError("checkout is not the exact push commit")
    if before == "0" * 40:
        return ()
    try:
        inventory = git("diff", "--raw", "--no-renames", "-z", before, after, "--")
    except subprocess.CalledProcessError:
        return ()  # Shallow or otherwise unavailable inventory requires full checks.
    fields = inventory.rstrip("\0").split("\0")
    if fields == [""]:
        return ()
    if len(fields) % 2:
        raise ValueError("incomplete push change inventory")
    paths, regular = [], True
    for index in range(0, len(fields), 2):
        metadata = fields[index].split()
        if len(metadata) != 5 or not metadata[0].startswith(":"):
            raise ValueError("invalid push change metadata")
        regular &= all(mode in {"000000", "100644"}
                       for mode in (metadata[0][1:], metadata[1]))
        paths.append(fields[index + 1])
    return affected_projects(paths, regular)


def validate_projects(projects: list[str], *, include_s3: bool = False, include_browser: bool = False) -> None:
    supported = PACKAGE_PROJECTS if include_s3 else PROJECTS
    if include_browser:
        supported = (*supported, BROWSER_PROJECT)
    if not projects or len(projects) != len(set(projects)) or any(p not in supported for p in projects):
        raise ValueError("expected unique, explicitly supported tool projects")


def _browser_manifest_profile(folder: Path) -> None:
    """Reject unsupported script changes before executing the finite profile."""
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("browser package directory must be ordinary")
    for name in ("package.json", "package-lock.json"):
        path = folder / name
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o111:
            raise ValueError("browser package manifests must be ordinary non-executable files")
    manifest = folder / "package.json"
    if manifest.stat().st_size > 100_000:
        raise ValueError("browser package manifest is oversized")
    document = json.loads(manifest.read_text())
    scripts = document.get("scripts") if isinstance(document, dict) else None
    if not isinstance(scripts, dict) or any(scripts.get(name) != command
            for name, command in BROWSER_MANIFEST_SCRIPTS.items()) or any(
            name in scripts for name in ("postbuild", "pretest", "posttest")):
        raise ValueError("browser package scripts require a reviewed manifest profile")


def run(root: Path, projects: list[str], *, include_s3: bool = False, include_browser: bool = False) -> None:
    # Existing callers retain their exact two-project capability. The trusted
    # staged package controller opts in only after recomputing the candidate.
    validate_projects(projects, include_s3=include_s3, include_browser=include_browser)
    for project in projects:
        folder = root / project
        def command(*args: str) -> None:
            subprocess.run(args, cwd=folder, check=True, timeout=240)
        if project == BROWSER_PROJECT:
            _browser_manifest_profile(folder)
            for arguments in BROWSER_MANIFEST_COMMANDS:
                command(*arguments)
            continue
        command("npm", "ci", "--ignore-scripts", "--no-fund", "--no-audit")
        command("npm", "audit", "--audit-level=low")
        if project == "server-console":
            command("npm", "test")
            command("node_modules/.bin/electron-packager", "--version")
        elif project == "tools/jsdoc":
            with tempfile.TemporaryDirectory(prefix="overte-jsdoc-check-") as output:
                command("node_modules/.bin/jsdoc", "root.js", "-c", "config.json", "-d", output)
        elif project == S3_PROJECT:
            command("npm", "test")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--projects", default="", help="Comma-separated supported project paths")
    parser.add_argument("--event", type=Path, help="Route a push or reusable caller instead of running checks")
    parser.add_argument("--output", type=Path, help="GitHub step output for routing")
    parser.add_argument("--changed-files", type=Path, help="Trusted sync file inventory for bounded tool checks")
    args = parser.parse_args()
    if args.event:
        event = json.loads(args.event.read_text())
        projects = push_projects(args.root, event)
        if "before" not in event and args.projects:
            selected = args.projects.split(",")
            validate_projects(selected)
            projects = tuple(selected)
        if args.output is None:
            parser.error("routing requires --output")
        with args.output.open("a") as output:
            output.write("projects=" + ",".join(projects) + "\n")
    else:
        if args.changed_files:
            changes = json.loads(args.changed_files.read_text())
            paths = [path for item in changes for path in (item["filename"], item.get("previous_filename"))
                     if path is not None]
            projects = affected_projects(paths)
            run(args.root, list(projects))
        else:
            run(args.root, args.projects.split(","))


if __name__ == "__main__":
    main()
