#!/usr/bin/env python3
"""Install exact open-source age/rcodesign pins into private Fedora state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import stat
import sys
import tarfile
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEVICE_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = DEVICE_ROOT / "toolchain.lock.json"
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 64 * 1024 * 1024
MEMBERS = {
    "age": "age/age",
    "rcodesign": "apple-codesign-{version}-x86_64-unknown-linux-musl/rcodesign",
}


class ToolError(RuntimeError):
    """A pinned iOS security tool could not be installed safely."""


def fail(message: str) -> "NoReturn":
    raise ToolError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def has_symlink_component(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
        if not current.exists():
            break
    return False


def private_directory(path: Path) -> Path:
    if has_symlink_component(path) or path.exists() and not path.is_dir():
        fail("security tool root must be a real directory")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
    return path


def download(artifact: dict, destination: Path) -> None:
    url = artifact.get("url")
    expected = artifact.get("sha256")
    parsed = urlparse(url) if isinstance(url, str) else None
    if (
        parsed is None or parsed.scheme != "https" or parsed.hostname != "github.com"
        or not isinstance(expected, str) or len(expected) != 64
    ):
        fail("iOS security tool lock contains an invalid artifact")
    if destination.is_file() and sha256_file(destination) == expected:
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    request = Request(url, headers={"User-Agent": "overte-ios-security-tools/1"})
    try:
        with urlopen(request, timeout=60) as response, temporary.open("xb") as output:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > MAX_ARCHIVE_BYTES:
                    fail("iOS security tool archive exceeds the safety limit")
                output.write(block)
    except (HTTPError, URLError, OSError) as error:
        temporary.unlink(missing_ok=True)
        fail(f"iOS security tool download failed: {type(error).__name__}")
    if sha256_file(temporary) != expected:
        temporary.unlink(missing_ok=True)
        fail("iOS security tool archive failed its pinned SHA-256")
    if os.name != "nt":
        temporary.chmod(0o600)
    temporary.replace(destination)


def extract_executable(archive_path: Path, member_name: str, destination: Path,
                       expected_sha256: str) -> None:
    try:
        archive = tarfile.open(archive_path, mode="r:gz")
    except (OSError, tarfile.TarError):
        fail("iOS security tool is not a valid tar archive")
    with archive:
        members = archive.getmembers()
        matches = [member for member in members if member.name == member_name]
        if len(matches) != 1 or not matches[0].isreg():
            fail("iOS security tool archive lacks its exact executable")
        member = matches[0]
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.size > MAX_EXECUTABLE_BYTES:
            fail("iOS security tool archive member is unsafe")
        source = archive.extractfile(member)
        if source is None:
            fail("iOS security tool executable is unreadable")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".tool-", dir=destination.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                while block := source.read(1024 * 1024):
                    output.write(block)
            temporary.chmod(0o700)
            if sha256_file(temporary) != expected_sha256:
                fail("iOS security tool executable failed its pinned SHA-256")
            temporary.replace(destination)
        finally:
            source.close()
            temporary.unlink(missing_ok=True)


def install(root: Path) -> dict[str, Path]:
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        fail("pinned iOS security tools currently support x86-64 Linux only")
    root = private_directory(root)
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    entries = lock["appium"]["iosSecurity"]
    result: dict[str, Path] = {}
    for name in ("age", "rcodesign"):
        entry = entries[name]
        version_root = private_directory(root / f"{name}-{entry['version']}")
        archive_path = version_root / "artifact.tar.gz"
        executable = version_root / name
        if not executable.is_file() or sha256_file(executable) != entry["executableSha256"]:
            download(entry["artifact"], archive_path)
            extract_executable(
                archive_path, MEMBERS[name].format(version=entry["version"]),
                executable, entry["executableSha256"],
            )
        if os.name != "nt":
            executable.chmod(0o700)
        result[name] = executable
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    try:
        tools = install(parser.parse_args().root)
        print(f"PASS: installed {len(tools)} pinned iOS security tools")
        return 0
    except (ToolError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
