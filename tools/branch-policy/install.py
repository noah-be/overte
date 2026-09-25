#!/usr/bin/env python3
"""Install reviewed branch-name hooks into one repository's shared Git directory."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
TOOL = "overte-branch-name-guard"
HOOKS = ("reference-transaction", "pre-push")
PAYLOADS = {"check.py": "tools/branch-policy/check.py",
            "guard.py": "tools/branch-policy/guard.py",
            "branch-policy.json": ".github/branch-policy.json"}


class InstallError(ValueError):
    """Existing repository configuration must be reviewed before installation."""


def git(repository: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repository), *args], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise InstallError("cannot inspect repository Git configuration")
    return result.stdout.strip()


def no_symlink(path: Path) -> None:
    if path.is_symlink():
        raise InstallError(f"refusing symbolic link at {path}")


def locations(repository: Path) -> tuple[Path, Path, Path]:
    common = Path(git(repository, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    return common, common / "hooks", common / TOOL


def check_hooks_config(repository: Path) -> dict:
    paths = {repository.resolve(): False}
    records = git(repository, "worktree", "list", "--porcelain", "-z").split("\0\0")
    for record in records:
        fields = record.split("\0")
        for field in fields:
            if field.startswith("worktree "):
                paths[Path(field.removeprefix("worktree "))] = any(
                    value == "prunable" or value.startswith("prunable ") for value in fields)
    checked, unavailable = [], []
    for path, prunable in sorted(paths.items()):
        try:
            mode = path.stat().st_mode
        except FileNotFoundError:
            if not path.is_symlink() and prunable:
                unavailable.append(str(path))
                continue
            raise InstallError(f"cannot check hooks configuration of missing worktree {path}")
        except OSError as error:
            raise InstallError(f"cannot inspect worktree {path}") from error
        if not stat.S_ISDIR(mode):
            raise InstallError(f"worktree is not a directory: {path}")
        result = subprocess.run(["git", "-C", str(path), "config", "--get-all", "core.hooksPath"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            raise InstallError(f"core.hooksPath is configured for {path}; review existing hooks before installing")
        if result.returncode != 1:
            raise InstallError(f"cannot inspect hooks configuration for {path}")
        checked.append(str(path))
    return {"checked_worktrees": checked, "unavailable_prunable_worktrees": unavailable,
            "unavailable_prunable_count": len(unavailable)}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_manifest(payload: Path) -> dict | None:
    no_symlink(payload)
    if not payload.exists():
        return None
    manifest_path = payload / "manifest.json"
    no_symlink(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        valid = (manifest["tool"] == TOOL and manifest["schema"] == 1
                 and isinstance(manifest["version"], str) and re.fullmatch(r"[0-9a-f]{64}", manifest["version"])
                 and isinstance(manifest["hooks"], dict) and isinstance(manifest["files"], dict)
                 and set(manifest["hooks"]) == set(HOOKS)
                 and set(manifest["files"]) == set(PAYLOADS)
                 and all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                         for value in (*manifest["hooks"].values(), *manifest["files"].values())))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise InstallError("existing private hook payload has no valid ownership manifest") from error
    if not valid:
        raise InstallError("existing private hook payload is not managed by this installer")
    return manifest


def verify_existing(hooks: Path, payload: Path, manifest: dict | None) -> None:
    no_symlink(hooks)
    no_symlink(payload / "versions")
    for name in HOOKS:
        path = hooks / name
        no_symlink(path)
        if path.exists():
            if not path.is_file() or manifest is None or digest(path.read_bytes()) != manifest["hooks"][name]:
                raise InstallError(f"existing {name} hook is not an unchanged managed hook; preserve and review it")
    current = payload / "current"
    if current.exists() or current.is_symlink():
        if manifest is None or not current.is_symlink() or os.readlink(current) != "versions/" + manifest["version"]:
            raise InstallError("private hook version pointer was changed; review it before installing")


def hook_text(name: str, payload: Path, version: str) -> bytes:
    return ("#!/bin/sh\n# Managed by Overte branch-name guard.\nexec "
            + shlex.quote(sys.executable) + " -I -B " + shlex.quote(str(payload / "versions" / version / "guard.py"))
            + " " + shlex.quote(name) + ' "$@"\n').encode()


def atomic_file(path: Path, content: bytes, mode: int) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            os.fchmod(handle.fileno(), mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def source_files() -> dict[str, bytes]:
    files = {}
    for name, source in PAYLOADS.items():
        path = ROOT / source
        no_symlink(path)
        files[name] = path.read_bytes()
        if name.endswith(".py"):
            compile(files[name], str(path), "exec")
    spec = importlib.util.spec_from_file_location("branch_guard_install_check", ROOT / PAYLOADS["check.py"])
    if spec is None or spec.loader is None:
        raise InstallError("reviewed checker cannot be loaded")
    checker = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = checker
    spec.loader.exec_module(checker)
    policy = ROOT / PAYLOADS["branch-policy.json"]
    checker.validate_branch_name(checker.load_policy(policy), "main", checker.load_dependabot_targets(policy))
    return files


def install(repository: Path) -> dict:
    common, hooks, payload = locations(repository)
    check_hooks_config(repository)
    manifest = read_manifest(payload)
    verify_existing(hooks, payload, manifest)
    files = source_files()
    hashes = {name: digest(content) for name, content in files.items()}
    version = digest(json.dumps(hashes, sort_keys=True).encode())
    wrappers = {name: hook_text(name, payload, version) for name in HOOKS}
    next_manifest = {"schema": 1, "tool": TOOL, "version": version, "files": hashes,
                     "hooks": {name: digest(content) for name, content in wrappers.items()}}
    payload.mkdir(mode=0o700, exist_ok=True)
    versions = payload / "versions"
    versions.mkdir(mode=0o700, exist_ok=True)
    destination = versions / version
    no_symlink(destination)
    if destination.exists():
        if {path.name for path in destination.iterdir()} != set(files):
            raise InstallError("installed version has unexpected files")
        for name, content in files.items():
            no_symlink(destination / name)
            if (destination / name).read_bytes() != content:
                raise InstallError("installed version was modified; review it before updating")
    else:
        with tempfile.TemporaryDirectory(prefix=".version-", dir=versions) as temporary:
            stage = Path(temporary) / "payload"
            stage.mkdir(mode=0o700)
            for name, content in files.items():
                atomic_file(stage / name, content, 0o600)
            os.replace(stage, destination)
    hooks.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".activate-", dir=payload) as temporary:
        link = Path(temporary) / "current"
        link.symlink_to("versions/" + version)
        os.replace(link, payload / "current")
    for name, content in wrappers.items():
        atomic_file(hooks / name, content, 0o700)
    atomic_file(payload / "manifest.json", (json.dumps(next_manifest, indent=2) + "\n").encode(), 0o600)
    return status(repository)


def status(repository: Path) -> dict:
    common, hooks, payload = locations(repository)
    try:
        coverage = check_hooks_config(repository)
        manifest = read_manifest(payload)
        if manifest is None:
            raise InstallError("branch-name guard is not installed")
        verify_existing(hooks, payload, manifest)
        current = payload / "current"
        if not current.is_symlink():
            raise InstallError("installed version pointer is missing")
        for name in HOOKS:
            if not (hooks / name).is_file() or not os.access(hooks / name, os.X_OK):
                raise InstallError(f"installed {name} hook is missing or not executable")
        version = payload / "versions" / manifest["version"]
        no_symlink(version)
        for name, expected in manifest["files"].items():
            no_symlink(version / name)
            if digest((version / name).read_bytes()) != expected:
                raise InstallError("installed hook payload was modified")
        try:
            source_hashes = {name: digest((ROOT / relative).read_bytes()) for name, relative in PAYLOADS.items()}
            source_version = digest(json.dumps(source_hashes, sort_keys=True).encode())
        except OSError:
            source_version = None
        return {"installed": True, "git_common_dir": str(common), "version": manifest["version"],
                "reviewed_source_version": source_version,
                "source_matches_installed": None if source_version is None else source_version == manifest["version"],
                **coverage}
    except (InstallError, OSError) as error:
        return {"installed": False, "git_common_dir": str(common), "reason": str(error)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "status"), nargs="?", default="install")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        result = status(args.repository) if args.command == "status" else install(args.repository)
    except (InstallError, ValueError, OSError, SyntaxError, ImportError, AttributeError) as error:
        print(f"Branch name guard: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["installed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
