#!/usr/bin/env python3
"""Bounded dependency checks for the documentation and server-console tools."""

from __future__ import annotations

import argparse
from pathlib import Path
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


def run(root: Path, projects: list[str]) -> None:
    if not projects or len(projects) != len(set(projects)) or any(p not in PROJECTS for p in projects):
        raise ValueError("expected unique, explicitly supported tool projects")
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
    parser.add_argument("--projects", required=True, help="Comma-separated supported project paths")
    args = parser.parse_args()
    run(args.root, args.projects.split(","))


if __name__ == "__main__":
    main()
