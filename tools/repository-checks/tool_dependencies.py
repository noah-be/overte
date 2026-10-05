#!/usr/bin/env python3
"""Bounded dependency checks for the documentation and server-console tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile


PROJECTS = ("server-console", "tools/jsdoc")
MANIFESTS = frozenset(f"{project}/{name}" for project in PROJECTS
                      for name in ("package.json", "package-lock.json"))


def affected_projects(paths: list[str], regular: bool = True) -> tuple[str, ...]:
    """Only exact manifests and regular Markdown may share this narrow route."""
    if (not regular or not paths
            or any(path not in MANIFESTS and not path.endswith(".md") for path in paths)):
        return ()
    return tuple(project for project in PROJECTS
                 if any(path in MANIFESTS and path.startswith(project + "/") for path in paths))


def push_projects(root: Path, event: dict) -> tuple[str, ...]:
    """Read both sides of the exact protected push; uncertain inventory stays full."""
    if "before" not in event or "after" not in event:
        return ()
    repository = event.get("repository", {})
    if repository.get("full_name") != "noah-be/overte" or repository.get("id") != 1319052603:
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


def validate_projects(projects: list[str]) -> None:
    if not projects or len(projects) != len(set(projects)) or any(p not in PROJECTS for p in projects):
        raise ValueError("expected unique, explicitly supported tool projects")


def run(root: Path, projects: list[str]) -> None:
    validate_projects(projects)
    for project in projects:
        folder = root / project
        def command(*args: str) -> None:
            subprocess.run(args, cwd=folder, check=True, timeout=240)
        command("npm", "ci", "--ignore-scripts", "--no-fund", "--no-audit")
        command("npm", "audit", "--audit-level=low")
        if project == "server-console":
            command("npm", "test")
            command("node_modules/.bin/electron-packager", "--version")
        else:
            with tempfile.TemporaryDirectory(prefix="overte-jsdoc-check-") as output:
                command("node_modules/.bin/jsdoc", "root.js", "-c", "config.json", "-d", output)


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
