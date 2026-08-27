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
from urllib.request import HTTPRedirectHandler, Request, build_opener


LOCK_FILE = Path(__file__).with_name("toolchain.lock.json")
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 64 * 1024 * 1024
MAX_TAR_ENTRIES = 128
MAX_TAR_DECLARED_BYTES = 192 * 1024 * 1024
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
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
        fail("security tool root must be owned by the current account")
    if os.name != "nt":
        path.chmod(0o700)
    return path


class SafeReleaseRedirect(HTTPRedirectHandler):
    """Allow only the HTTPS hosts used by pinned GitHub release assets."""

    HOSTS = {
        "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
    }

    def redirect_request(self, request, fp, code, msg, headers, new_url):
        parsed = urlparse(new_url)
        if parsed.scheme != "https" or parsed.hostname not in self.HOSTS:
            fail("iOS security tool download was redirected outside GitHub release storage")
        return super().redirect_request(request, fp, code, msg, headers, new_url)


def download(artifact: dict, destination: Path, *, opener=None) -> None:
    url = artifact.get("url")
    expected = artifact.get("sha256")
    parsed = urlparse(url) if isinstance(url, str) else None
    if (
        parsed is None or parsed.scheme != "https" or parsed.hostname != "github.com"
        or not isinstance(expected, str) or len(expected) != 64
    ):
        fail("iOS security tool lock contains an invalid artifact")
    if (not destination.is_symlink() and destination.is_file()
            and sha256_file(destination) == expected):
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    request = Request(url, headers={"User-Agent": "overte-ios-security-tools/1"})
    opener = opener or build_opener(SafeReleaseRedirect())
    try:
        with opener.open(request, timeout=60) as response, temporary.open("xb") as output:
            final_url = urlparse(response.geturl())
            if final_url.scheme != "https" or final_url.hostname not in SafeReleaseRedirect.HOSTS:
                fail("iOS security tool response came from an unapproved host")
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > MAX_ARCHIVE_BYTES:
                    fail("iOS security tool archive exceeds the safety limit")
                output.write(block)
    except (HTTPError, URLError, OSError, ToolError) as error:
        temporary.unlink(missing_ok=True)
        if isinstance(error, ToolError):
            raise
        fail(f"iOS security tool download failed: {type(error).__name__}")
    if sha256_file(temporary) != expected:
        temporary.unlink(missing_ok=True)
        fail("iOS security tool archive failed its pinned SHA-256")
    if os.name != "nt":
        temporary.chmod(0o600)
    temporary.replace(destination)


def extract_executable(archive_path: Path, member_name: str, destination: Path,
                       expected_sha256: str) -> None:
    if (archive_path.is_symlink() or not archive_path.is_file()
            or not 0 < archive_path.stat().st_size <= MAX_ARCHIVE_BYTES):
        fail("iOS security tool archive size is invalid")
    try:
        archive = tarfile.open(archive_path, mode="r:gz")
    except (OSError, tarfile.TarError):
        fail("iOS security tool is not a valid tar archive")
    with archive:
        matches = []
        count = 0
        declared = 0
        for member in archive:
            count += 1
            declared += max(0, member.size)
            if count > MAX_TAR_ENTRIES or declared > MAX_TAR_DECLARED_BYTES:
                fail("iOS security tool tar metadata exceeds the safety limit")
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or "\\" in member.name
                    or member.issym() or member.islnk() or member.isdev() or member.isfifo()):
                fail("iOS security tool tar contains an unsafe member")
            if member.name == member_name:
                matches.append(member)
        if len(matches) != 1 or not matches[0].isreg():
            fail("iOS security tool archive lacks its exact executable")
        member = matches[0]
        path = PurePosixPath(member.name)
        if (path.is_absolute() or ".." in path.parts or member.size <= 0
                or member.size > MAX_EXECUTABLE_BYTES
                or declared > archive_path.stat().st_size * 20):
            fail("iOS security tool archive member is unsafe")
        source = archive.extractfile(member)
        if source is None:
            fail("iOS security tool executable is unreadable")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".tool-", dir=destination.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                total = 0
                while block := source.read(1024 * 1024):
                    total += len(block)
                    if total > MAX_EXECUTABLE_BYTES:
                        fail("iOS security tool executable exceeded its extraction limit")
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
            if total != member.size:
                fail("iOS security tool executable size differs from tar metadata")
            temporary.chmod(0o700)
            if sha256_file(temporary) != expected_sha256:
                fail("iOS security tool executable failed its pinned SHA-256")
            temporary.replace(destination)
        finally:
            source.close()
            temporary.unlink(missing_ok=True)


def install(root: Path, requested: tuple[str, ...] | None = None) -> dict[str, Path]:
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        fail("pinned iOS security tools currently support x86-64 Linux only")
    names = tuple(MEMBERS) if requested is None else requested
    if not names or len(set(names)) != len(names) or any(name not in MEMBERS for name in names):
        fail("requested iOS security tool selection is invalid")
    root = private_directory(root)
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    entries = lock["appium"]["iosSecurity"]
    result: dict[str, Path] = {}
    for name in names:
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
    parser.add_argument(
        "--tool", action="append", choices=tuple(MEMBERS), dest="tools",
        help="install only this exact pin; may be repeated (default: all)",
    )
    try:
        arguments = parser.parse_args()
        tools = install(arguments.root, tuple(arguments.tools) if arguments.tools else None)
        print(f"PASS: installed {len(tools)} pinned iOS security tools")
        return 0
    except (ToolError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
