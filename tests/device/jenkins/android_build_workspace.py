#!/usr/bin/env python3
"""Run one Android build in an isolated checkout and Conan home.

Phone and Pico mutate overlapping generated paths below ``android/``.  Conan
cache separation alone therefore cannot make the two builds safe.  This
wrapper clones the exact clean source commit into a private ephemeral checkout,
sets job-private Gradle/temp paths, holds the role-specific Conan lock for the
whole child process, and optionally exports only the fixed role APK.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import NoReturn, Sequence

import conan_cache_manager as conan


ROOT_MARKER = ".overte-android-build-root-v1"
WORKSPACE_MARKER = ".overte-android-build-workspace-v1"
FORMAT = "1\n"
COMMIT = re.compile(r"^[0-9a-f]{40}$")
ROLE_ENTRYPOINT = {
    "android-phone": "android/phone/build.sh",
    "android-pico": "android/vr/pico/build.sh",
}
ROLE_ARTIFACT = {
    "android-phone": (
        "android/phone/apps/phoneInterface/build/outputs/apk/debug/"
        "phoneInterface-debug.apk"
    ),
    "android-pico": (
        "android/vr/pico/apps/picoInterface/build/outputs/apk/debug/"
        "picoInterface-debug.apk"
    ),
}


class WorkspaceError(RuntimeError):
    """A build-workspace safety precondition was not satisfied."""


def fail(message: str) -> NoReturn:
    raise WorkspaceError(message)


def normalized(path: Path, purpose: str) -> Path:
    try:
        value = conan.checked_absolute(path.expanduser(), purpose)
        conan.reject_sensitive_path(value)
        conan.reject_symlink_components(value, purpose)
    except conan.CacheError as error:
        fail(str(error))
    return value


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def private_directory(path: Path, purpose: str) -> None:
    try:
        conan.private_mode(path, "directory")
    except conan.CacheError as error:
        fail(f"{purpose}: {error}")


class InitializationLock:
    """A short blocking lock used only to create/verify the managed root."""

    def __init__(self, path: Path) -> None:
        self.path = normalized(path, "build-root initialization lock")
        self.descriptor: int | None = None

    def __enter__(self) -> "InitializationLock":
        parent = self.path.parent
        if not parent.is_dir() or parent.is_symlink():
            fail("build-root parent must be an existing non-symlink directory")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        self.descriptor = os.open(self.path, flags, 0o600)
        value = os.fstat(self.descriptor)
        if not stat.S_ISREG(value.st_mode):
            fail("build-root initialization lock is not a regular file")
        if hasattr(os, "geteuid") and value.st_uid != os.geteuid():
            fail("build-root initialization lock is owned by another account")
        os.fchmod(self.descriptor, 0o600)
        fcntl.flock(self.descriptor, fcntl.LOCK_EX)
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None


class BuildWorkspaceRoot:
    def __init__(self, root: Path) -> None:
        self.root = normalized(root, "build workspace root")
        try:
            conan.reject_default_cache(self.root)
        except conan.CacheError as error:
            fail(str(error))
        self.workspaces = self.root / "workspaces"

    def initialize(self) -> None:
        parent = self.root.parent
        if not parent.exists() or not parent.is_dir() or parent.is_symlink():
            fail("build workspace root parent must be an existing non-symlink directory")
        lock = parent / f".{self.root.name}.overte-build-init.lock"
        with InitializationLock(lock):
            if self.root.exists() or self.root.is_symlink():
                value = self.root.lstat()
                if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
                    fail("managed build workspace root is not a safe directory")
                if hasattr(os, "geteuid") and value.st_uid != os.geteuid():
                    fail("managed build workspace root is owned by another account")
                entries = list(self.root.iterdir())
                marker = self.root / ROOT_MARKER
                if not marker.is_file() or marker.is_symlink():
                    if entries:
                        fail("refusing to adopt a non-empty unmarked build workspace root")
                    private_directory(self.root, "build workspace root")
                    conan.secure_file(marker, FORMAT)
            else:
                self.root.mkdir(mode=0o700)
                private_directory(self.root, "build workspace root")
                conan.secure_file(self.root / ROOT_MARKER, FORMAT)

            marker = self.root / ROOT_MARKER
            try:
                conan.private_mode(marker, "file")
            except conan.CacheError as error:
                fail(str(error))
            if marker.read_text(encoding="utf-8") != FORMAT:
                fail("managed build workspace root has an unsupported format")
            self.workspaces.mkdir(mode=0o700, exist_ok=True)
            private_directory(self.workspaces, "build workspace directory")

    def create(self, role: str) -> Path:
        self.initialize()
        value = Path(tempfile.mkdtemp(prefix=f"{role}-", dir=self.workspaces))
        private_directory(value, "job build workspace")
        conan.secure_file(value / WORKSPACE_MARKER, f"1\nrole={role}\n")
        return value

    def remove(self, workspace: Path, role: str) -> None:
        workspace = normalized(workspace, "job build workspace")
        expected_parent = self.workspaces
        marker = workspace / WORKSPACE_MARKER
        if (workspace.parent != expected_parent or not workspace.name.startswith(f"{role}-")
                or marker.is_symlink() or not marker.is_file()
                or marker.read_text(encoding="utf-8") != f"1\nrole={role}\n"):
            fail("refusing to remove an unrecognized build workspace")
        shutil.rmtree(workspace)


def git(source: Path, *arguments: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(source), *arguments], text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE, check=False,
    )


def source_commit(source: Path) -> str:
    if not source.is_dir() or not (source / ".git").exists():
        fail("source must be a Git working tree")
    status = git(source, "status", "--porcelain=v1", "--untracked-files=no", capture=True)
    if status.returncode:
        fail("source Git status could not be verified")
    if status.stdout:
        fail("source has tracked changes; commit them before an isolated build")
    revision = git(source, "rev-parse", "--verify", "HEAD^{commit}", capture=True)
    commit = revision.stdout.strip()
    if revision.returncode or not COMMIT.fullmatch(commit):
        fail("source HEAD is not an exact Git commit")
    return commit


def clone_exact(source: Path, checkout: Path, commit: str) -> None:
    result = subprocess.run(
        ["git", "clone", "--quiet", "--no-local", "--no-hardlinks", "--no-checkout",
         "--", str(source), str(checkout)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False,
    )
    if result.returncode:
        fail("the isolated source clone failed")
    result = git(checkout, "checkout", "--quiet", "--detach", commit)
    if result.returncode:
        fail("the isolated source checkout failed")
    actual = git(checkout, "rev-parse", "HEAD", capture=True)
    if actual.returncode or actual.stdout.strip() != commit:
        fail("the isolated checkout does not match the requested commit")


def checked_artifact_directory(path: Path, source: Path, build_root: Path,
                               conan_root: Path) -> Path:
    output = normalized(path, "artifact output directory")
    if (output == source or is_within(output, source) or output == build_root
            or is_within(output, build_root) or output == conan_root
            or is_within(output, conan_root)):
        fail("artifact output must be outside source and managed state roots")
    if output.exists() or output.is_symlink():
        fail("artifact output directory must not already exist")
    if not output.parent.exists() or not output.parent.is_dir() or output.parent.is_symlink():
        fail("artifact output parent must be an existing non-symlink directory")
    return output


def export_artifact(checkout: Path, role: str, destination: Path, commit: str) -> None:
    relative = ROLE_ARTIFACT[role]
    artifact = checkout / relative
    try:
        conan.reject_symlink_components(artifact, "Android build artifact")
    except conan.CacheError as error:
        fail(str(error))
    if not artifact.is_file() or artifact.is_symlink():
        fail("the successful build did not produce its expected role APK")
    destination.mkdir(mode=0o700)
    private_directory(destination, "artifact output directory")
    copied = destination / artifact.name
    shutil.copyfile(artifact, copied)
    copied.chmod(0o600)
    manifest = {
        "schemaVersion": 1,
        "role": role,
        "sourceRevision": commit,
        "artifact": artifact.name,
    }
    conan.secure_file(
        destination / "build-workspace-manifest.json",
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
    )


def child_environment(workspace: Path, checkout: Path, state: Path, role: str,
                      conan_home: Path) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("PICO_QT_SOURCE_DIR", "PICO_QT_BUILD_DIR", "PICO_TBB_PACKAGE_DIR",
                 "PICO_DRACO_PACKAGE_DIR"):
        environment.pop(name, None)
    gradle = state / "gradle"
    temporary = state / "tmp"
    phone_temporary = state / "phone-tmp"
    for directory in (state, gradle, temporary, phone_temporary):
        directory.mkdir(mode=0o700, exist_ok=True)
        private_directory(directory, "job-private build state")
    environment.update({
        "CONAN_HOME": str(conan_home),
        "GRADLE_USER_HOME": str(gradle),
        "TMPDIR": str(temporary),
        "WORKSPACE": str(checkout),
        "GITHUB_WORKSPACE": str(checkout),
        "OVERTE_CI_WORKSPACE": str(checkout),
        "OVERTE_ANDROID_BUILD_WORKSPACE": str(workspace),
        "OVERTE_ANDROID_BUILD_ROLE": role,
        "PHONE_PREBUILT_TMPDIR": str(phone_temporary / "prebuilt"),
        "PHONE_BUILD_TMPDIR": str(phone_temporary / "package"),
    })
    if role == "android-phone":
        environment["PHONE_SHARED_CONAN_HOME"] = str(conan_home)
    else:
        environment.pop("PHONE_SHARED_CONAN_HOME", None)
    return environment


def parse(values: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="clean source Git working tree")
    parser.add_argument("--build-root", required=True, type=Path,
                        help="dedicated private root outside the source checkout")
    parser.add_argument("--conan-root", required=True, type=Path,
                        help="dedicated Conan cache-manager root")
    parser.add_argument("--role", required=True, choices=tuple(ROLE_ENTRYPOINT))
    parser.add_argument("--seed", type=Path,
                        help="optional recursively read-only Conan seed")
    parser.add_argument("--seed-lock", type=Path,
                        help="shared lock required together with --seed")
    parser.add_argument("--artifact-dir", type=Path,
                        help="optional new directory receiving the fixed role APK")
    parser.add_argument("--keep-workspace", action="store_true",
                        help="retain the private checkout for trusted diagnostics")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args(values)


def execute(arguments: argparse.Namespace) -> int:
    source = normalized(arguments.source, "source checkout")
    build = BuildWorkspaceRoot(arguments.build_root)
    conan_root = normalized(arguments.conan_root, "Conan cache root")
    if (build.root == source or is_within(build.root, source) or is_within(source, build.root)
            or conan_root == source or is_within(conan_root, source)
            or is_within(source, conan_root) or conan_root == build.root
            or is_within(conan_root, build.root) or is_within(build.root, conan_root)):
        fail("source, build root, and Conan root must be disjoint")
    commit = source_commit(source)
    artifact_directory = None
    if arguments.artifact_dir is not None:
        artifact_directory = checked_artifact_directory(
            arguments.artifact_dir, source, build.root, conan_root)
    command = list(arguments.command)
    if command[:1] == ["--"]:
        command.pop(0)
    if not command:
        command = [f"./{ROLE_ENTRYPOINT[arguments.role]}", "all"]

    manager = conan.CacheManager(conan_root)
    manager.initialize()
    workspace: Path | None = None
    try:
        with manager.role_lock(arguments.role):
            conan_home = manager.ensure_home(
                arguments.role, seed=arguments.seed, seed_lock=arguments.seed_lock)
            workspace = build.create(arguments.role)
            checkout = workspace / "source"
            clone_exact(source, checkout, commit)
            environment = child_environment(
                workspace, checkout, workspace / "state", arguments.role, conan_home)
            print(f"Running the isolated {arguments.role} build at source revision {commit}.")
            result = subprocess.run(command, cwd=checkout, env=environment, check=False)
            returncode = result.returncode if result.returncode >= 0 else 128 + abs(result.returncode)
            if returncode == 0 and artifact_directory is not None:
                export_artifact(checkout, arguments.role, artifact_directory, commit)
            return returncode
    finally:
        if workspace is not None and workspace.exists() and not arguments.keep_workspace:
            build.remove(workspace, arguments.role)


def main(values: Sequence[str] | None = None) -> int:
    try:
        with conan.restricted_umask():
            return execute(parse(values))
    except (WorkspaceError, conan.CacheError, OSError) as error:
        message = str(error)
        for name in conan.SENSITIVE_ENVIRONMENT:
            secret = os.environ.get(name, "")
            if secret:
                message = message.replace(secret, "<private-selector>")
        print(f"error: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
