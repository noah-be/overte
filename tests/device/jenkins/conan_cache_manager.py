#!/usr/bin/env python3
"""Fail-closed Conan 2 cache isolation for Android build jobs.

The manager gives the Phone and Pico build roles different writable Conan
homes.  ``run`` keeps the role lock for the complete child process, which is
the safe integration point for Jenkins and local automation.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Iterator, NoReturn, Sequence


ROLES = ("android-phone", "android-pico")
ROOT_MARKER = ".overte-conan-cache-root-v1"
HOME_MARKER = ".overte-conan-home-v1"
ENV_MARKER = "OVERTE_CONAN_CACHE_FORMAT=1"
SENSITIVE_ENVIRONMENT = (
    "OVERTE_DEVICE_TARGET_SELECTOR",
    "ANDROID_SERIAL",
    "ADB_SERIAL",
    "PICO_DEVICE_SERIAL",
)


class CacheError(RuntimeError):
    """A cache safety precondition was not satisfied."""


def fail(message: str) -> NoReturn:
    raise CacheError(message)


def private_mode(path: Path, expected_type: str) -> None:
    """Validate ownership/type, then remove access for group and other."""
    reject_symlink_components(path, f"managed {expected_type}")
    value = path.lstat()
    if stat.S_ISLNK(value.st_mode):
        fail(f"managed {expected_type} must not be a symbolic link")
    if expected_type == "directory" and not stat.S_ISDIR(value.st_mode):
        fail("managed cache path is not a directory")
    if expected_type == "file" and not stat.S_ISREG(value.st_mode):
        fail("managed cache path is not a regular file")
    if hasattr(os, "geteuid") and value.st_uid != os.geteuid():
        fail(f"managed {expected_type} is not owned by the current account")
    path.chmod(0o700 if expected_type == "directory" else 0o600)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def checked_absolute(path: Path, purpose: str) -> Path:
    if not path.is_absolute():
        fail(f"{purpose} must be an absolute path")
    value = os.fspath(path)
    if any(character in value for character in ("\0", "\n", "\r")):
        fail(f"{purpose} contains an unsupported character")
    return Path(os.path.abspath(path))


def reject_symlink_components(path: Path, purpose: str) -> None:
    """Reject a symlink at any existing component of an absolute path.

    Checking only the leaf is insufficient: an apparently ordinary managed
    root such as ``/safe/link/cache`` can still escape through ``link``.  Stop
    at the first missing component because no later lexical component can
    exist without its parent.
    """
    path = checked_absolute(path, purpose)
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            value = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(value.st_mode):
            fail(f"{purpose} must not contain symbolic-link components")


def reject_default_cache(path: Path) -> None:
    """Never manage, replace, or create inside the user's normal Conan cache."""
    absolute = checked_absolute(path, "managed cache path")
    default = checked_absolute(Path.home() / ".conan2", "default Conan cache")
    reject_symlink_components(absolute, "managed cache path")
    reject_symlink_components(default, "default Conan cache")
    if absolute == default or is_within(absolute, default) or is_within(default, absolute):
        fail("the managed root must be separate from the default Conan cache")


def reject_sensitive_path(path: Path) -> None:
    value = os.fspath(path)
    for name in SENSITIVE_ENVIRONMENT:
        secret = os.environ.get(name, "")
        if len(secret) >= 3 and secret in value:
            # Deliberately do not reproduce either the path or the selector.
            fail("a managed path contains a private target selector")


def secure_file(path: Path, content: str, *, replace_managed_env: bool = False) -> None:
    path = checked_absolute(path, "output file")
    reject_symlink_components(path, "output file")
    reject_default_cache(path)
    reject_sensitive_path(path)
    parent = path.parent
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        fail("output parent must be an existing non-symlink directory")

    if path.exists() or path.is_symlink():
        value = path.lstat()
        if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
            fail("managed output is not a safe regular file")
        if hasattr(os, "geteuid") and value.st_uid != os.geteuid():
            fail("managed output is owned by another account")
        if not replace_managed_env:
            fail("managed file already exists")
        first_line = path.read_text(encoding="utf-8").splitlines()[:1]
        if first_line != [ENV_MARKER]:
            fail("refusing to replace an unmanaged environment file")
        private_mode(path, "file")

    descriptor, temporary_name = tempfile.mkstemp(prefix=".overte-conan-env-", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        private_mode(path, "file")
    finally:
        if temporary.exists():
            temporary.unlink()


class FileLock:
    """A private, non-blocking advisory lock."""

    def __init__(self, path: Path, *, shared: bool, label: str,
                 blocking: bool = False) -> None:
        self.path = checked_absolute(path, f"{label} lock")
        self.shared = shared
        self.label = label
        self.blocking = blocking
        self.descriptor: int | None = None

    def __enter__(self) -> "FileLock":
        reject_symlink_components(self.path, f"{self.label} lock")
        reject_default_cache(self.path)
        reject_sensitive_path(self.path)
        parent = self.path.parent
        if not parent.exists() or not parent.is_dir() or parent.is_symlink():
            fail(f"{self.label} lock parent is not a safe directory")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            self.descriptor = os.open(self.path, flags, 0o600)
            value = os.fstat(self.descriptor)
            if not stat.S_ISREG(value.st_mode):
                fail(f"{self.label} lock is not a regular file")
            if hasattr(os, "geteuid") and value.st_uid != os.geteuid():
                fail(f"{self.label} lock is owned by another account")
            os.fchmod(self.descriptor, 0o600)
            operation = fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX
            if not self.blocking:
                operation |= fcntl.LOCK_NB
            fcntl.flock(self.descriptor, operation)
        except BlockingIOError:
            self.close()
            fail(f"{self.label} cache is already in use")
        except Exception:
            self.close()
            raise
        return self

    def close(self) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()


class CacheManager:
    def __init__(self, root: Path) -> None:
        self.root = checked_absolute(root, "cache root")
        reject_default_cache(self.root)
        reject_sensitive_path(self.root)
        self.homes = self.root / "homes"
        self.locks = self.root / "locks"
        self.temporary = self.root / "tmp"

    def initialize(self) -> None:
        reject_symlink_components(self.root, "managed cache root")
        parent = self.root.parent
        if not parent.exists() or not parent.is_dir() or parent.is_symlink():
            fail("managed cache root parent must be an existing non-symlink directory")
        initialization_lock = parent / f".{self.root.name}.overte-conan-init.lock"
        with FileLock(initialization_lock, shared=False, label="cache initialization",
                      blocking=True):
            self._initialize_locked()

    def _initialize_locked(self) -> None:
        if self.root.exists() or self.root.is_symlink():
            value = self.root.lstat()
            if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
                fail("managed cache root is not a safe directory")
            if hasattr(os, "geteuid") and value.st_uid != os.geteuid():
                fail("managed cache root is owned by another account")
            marker = self.root / ROOT_MARKER
            entries = list(self.root.iterdir())
            if not marker.is_file():
                if entries:
                    fail("refusing to adopt a non-empty unmarked cache root")
                private_mode(self.root, "directory")
                secure_file(marker, "1\n")
            else:
                private_mode(self.root, "directory")
        else:
            self.root.mkdir(parents=True, mode=0o700)
            private_mode(self.root, "directory")
            secure_file(self.root / ROOT_MARKER, "1\n")

        private_mode(self.root / ROOT_MARKER, "file")
        if (self.root / ROOT_MARKER).read_text(encoding="utf-8") != "1\n":
            fail("managed cache root has an unsupported format")
        for directory in (self.homes, self.locks, self.temporary):
            directory.mkdir(mode=0o700, exist_ok=True)
            private_mode(directory, "directory")

    def role_home(self, role: str) -> Path:
        if role not in ROLES:
            fail("unsupported build role")
        return self.homes / role

    def role_lock(self, role: str) -> FileLock:
        self.initialize()
        self.role_home(role)
        return FileLock(self.locks / f"{role}.lock", shared=False, label=role)

    @staticmethod
    def seed_snapshot(seed: Path) -> tuple[tuple[object, ...], ...]:
        """Validate a physically read-only, ordinary-file seed tree."""
        reject_symlink_components(seed, "seed")
        if not seed.exists() or seed.is_symlink() or not seed.is_dir():
            fail("seed must be an existing non-symlink directory")
        snapshot: list[tuple[object, ...]] = []
        for base, directories, files in os.walk(seed, followlinks=False):
            base_path = Path(base)
            names = [*directories, *files]
            for name in sorted(names):
                child = base_path / name
                value = child.lstat()
                relative = child.relative_to(seed).as_posix()
                if stat.S_ISLNK(value.st_mode):
                    fail("seed must not contain symbolic links")
                if not (stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode)):
                    fail("seed contains an unsupported file type")
                if value.st_mode & 0o222:
                    fail("seed must be recursively read-only")
                if value.st_mode & 0o077:
                    fail("seed must be private to the current account")
                if hasattr(os, "geteuid") and value.st_uid != os.geteuid():
                    fail("seed must be owned by the current account")
                snapshot.append((relative, stat.S_IFMT(value.st_mode), value.st_mode & 0o777,
                                 value.st_size, value.st_mtime_ns))
        root_value = seed.lstat()
        if root_value.st_mode & 0o222:
            fail("seed must be recursively read-only")
        if root_value.st_mode & 0o077:
            fail("seed must be private to the current account")
        if hasattr(os, "geteuid") and root_value.st_uid != os.geteuid():
            fail("seed must be owned by the current account")
        return tuple(snapshot)

    @staticmethod
    def make_private_writable(root: Path) -> None:
        for base, directories, files in os.walk(root, topdown=False, followlinks=False):
            base_path = Path(base)
            for name in files:
                child = base_path / name
                if child.is_symlink() or not child.is_file():
                    fail("copied cache contains an unsupported file")
                child.chmod(0o600)
            for name in directories:
                child = base_path / name
                if child.is_symlink() or not child.is_dir():
                    fail("copied cache contains an unsupported directory")
                child.chmod(0o700)
            base_path.chmod(0o700)

    def clone_seed(self, role: str, seed: Path, seed_lock: Path) -> Path:
        seed = checked_absolute(seed, "seed")
        seed_lock = checked_absolute(seed_lock, "seed lock")
        reject_default_cache(seed)
        reject_default_cache(seed_lock)
        reject_sensitive_path(seed)
        reject_sensitive_path(seed_lock)
        if seed_lock == seed or is_within(seed_lock, seed):
            fail("seed lock must be outside the immutable seed")

        home = self.role_home(role)
        if home.exists() or home.is_symlink():
            fail("role cache appeared while it was being initialized")

        with FileLock(seed_lock, shared=True, label="seed"):
            before = self.seed_snapshot(seed)
            staging = Path(tempfile.mkdtemp(prefix=f"{role}-", dir=self.temporary))
            try:
                result = subprocess.run(
                    ["cp", "--archive", "--reflink=auto", "--", f"{seed}/.", str(staging)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
                if result.returncode:
                    fail("the locked seed could not be copied")
                if self.seed_snapshot(seed) != before:
                    fail("the seed changed while it was locked")
                self.make_private_writable(staging)
                secure_file(staging / HOME_MARKER, f"1\nrole={role}\n")
                staging.rename(home)
            except Exception:
                if staging.exists() and is_within(staging, self.temporary):
                    shutil.rmtree(staging)
                raise
        return home

    def ensure_home(self, role: str, *, seed: Path | None = None,
                    seed_lock: Path | None = None) -> Path:
        home = self.role_home(role)
        if seed is None and seed_lock is not None:
            fail("a seed lock is valid only together with a seed")
        if seed is not None and seed_lock is None:
            fail("using a seed requires an explicit seed lock")

        if home.exists() or home.is_symlink():
            private_mode(home, "directory")
            marker = home / HOME_MARKER
            if not marker.is_file() or marker.is_symlink():
                fail("role cache is missing its ownership marker")
            private_mode(marker, "file")
            expected = f"1\nrole={role}\n"
            if marker.read_text(encoding="utf-8") != expected:
                fail("role cache marker does not match its build role")
            return home

        if seed is not None:
            return self.clone_seed(role, seed, seed_lock)  # type: ignore[arg-type]

        home.mkdir(mode=0o700)
        private_mode(home, "directory")
        secure_file(home / HOME_MARKER, f"1\nrole={role}\n")
        return home

    def write_environment(self, role: str, home: Path, output: Path) -> None:
        entries = [
            ENV_MARKER,
            f"OVERTE_CONAN_CACHE_ROLE={role}",
            f"CONAN_HOME={home}",
        ]
        if role == "android-phone":
            # android/phone/build.sh otherwise redirects selected dependency
            # commands to PHONE_SHARED_CONAN_HOME or the user's ~/.conan2.
            entries.append(f"PHONE_SHARED_CONAN_HOME={home}")
        content = "\n".join((*entries, ""))
        secure_file(output, content, replace_managed_env=True)


@contextmanager
def restricted_umask() -> Iterator[None]:
    previous = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(previous)


def add_cache_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", required=True, type=Path,
                        help="absolute dedicated manager root (never ~/.conan2)")
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument("--seed", type=Path,
                        help="optional recursively read-only Conan seed directory")
    parser.add_argument("--seed-lock", type=Path,
                        help="absolute shared lock file required with --seed")


def arguments(values: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    prepare = commands.add_parser("prepare", help="create/verify one role cache")
    add_cache_arguments(prepare)
    prepare.add_argument("--env-file", required=True, type=Path,
                         help="private Jenkins withEnv KEY=value file")
    run = commands.add_parser("run", help="hold the role lock while running a build")
    add_cache_arguments(run)
    run.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args(values)


def execute(args: argparse.Namespace) -> int:
    manager = CacheManager(args.root)
    manager.initialize()
    with manager.role_lock(args.role):
        home = manager.ensure_home(args.role, seed=args.seed, seed_lock=args.seed_lock)
        if args.action == "prepare":
            manager.write_environment(args.role, home, args.env_file)
            print(f"Conan cache environment prepared for {args.role}.")
            return 0

        command = list(args.command)
        if command[:1] == ["--"]:
            command.pop(0)
        if not command:
            fail("run requires a command after --")
        environment = os.environ.copy()
        environment["CONAN_HOME"] = str(home)
        environment["OVERTE_CONAN_CACHE_ROLE"] = args.role
        if args.role == "android-phone":
            environment["PHONE_SHARED_CONAN_HOME"] = str(home)
        print(f"Running build with the isolated {args.role} Conan cache.")
        result = subprocess.run(command, env=environment, check=False)
        return result.returncode if result.returncode >= 0 else 128 + abs(result.returncode)


def main(values: Sequence[str] | None = None) -> int:
    with restricted_umask():
        return execute(arguments(values))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CacheError, OSError) as error:
        message = str(error)
        for name in SENSITIVE_ENVIRONMENT:
            secret = os.environ.get(name, "")
            if secret:
                message = message.replace(secret, "<private-selector>")
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(2)
