#!/usr/bin/env python3
"""Create, verify, and restore durable macOS Conan checkpoints.

The fast GitHub Actions cache is deliberately not the durability boundary for
the macOS dependency build.  This tool packages the useful Conan roots into a
self-describing artifact, validates the payload before extraction, and can find
the newest compatible artifact through the GitHub Actions artifact API.

No command, environment value, absolute path, or archive member is printed.
"""

from __future__ import annotations

import argparse
import bisect
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import threading
import time
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile


SCHEMA = 2
KIND = "overte-macos-conan-checkpoint"
ARCHIVE_FORMAT = "tar-chunks-v1"
ARCHIVE_PREFIX = "conan-cache.part-"
MANIFEST_NAME = "manifest.json"
ROOTS = ("p", "sources")
CHUNK_SIZE = 1024 * 1024
DEFAULT_ARCHIVE_CHUNK_BYTES = 384 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
DEFAULT_MAX_ARCHIVE_BYTES = 20 * 1024 * 1024 * 1024
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,240}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,240}$")


class CheckpointError(RuntimeError):
    """A local checkpoint is incompatible, corrupt, or unsafe."""


class RemoteError(CheckpointError):
    """The GitHub artifact service could not be queried reliably."""


class _SafeRedirectHandler(HTTPRedirectHandler):
    """Never forward the GitHub token to a cross-origin artifact redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        if urlsplit(req.full_url).netloc != urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


@contextmanager
def heartbeat(phase: str, interval: float) -> Iterator[None]:
    stop = threading.Event()
    started = time.monotonic()

    def publish() -> None:
        while not stop.wait(interval):
            print(
                f"conan-checkpoint phase={phase} status=active "
                f"elapsed_seconds={int(time.monotonic() - started)}",
                flush=True,
            )

    thread = threading.Thread(target=publish, name="checkpoint-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=max(1.0, interval + 1.0))


def _validate_identifier(value: str, label: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise CheckpointError(f"invalid {label}")
    return value


def _validate_repository_id(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CheckpointError("invalid repository id")
    return value


def _validate_branch(value: str) -> str:
    if (
        not SAFE_BRANCH.fullmatch(value)
        or value.startswith("/")
        or value.endswith("/")
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise CheckpointError("invalid branch")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _chunk_name(index: int) -> str:
    return f"{ARCHIVE_PREFIX}{index:05d}"


class ChunkReader(io.RawIOBase):
    """Seekable logical file backed by already-validated bounded chunks."""

    def __init__(self, paths: list[Path], sizes: list[int]):
        super().__init__()
        self.paths = paths
        self.sizes = sizes
        self.offsets = [0]
        for size in sizes:
            self.offsets.append(self.offsets[-1] + size)
        self.position = 0
        self.current_index = -1
        self.current = None

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_CUR:
            offset += self.position
        elif whence == os.SEEK_END:
            offset += self.offsets[-1]
        elif whence != os.SEEK_SET:
            raise ValueError("unsupported seek mode")
        if offset < 0:
            raise ValueError("negative seek position")
        self.position = offset
        return offset

    def _select(self, index: int):
        if index != self.current_index:
            if self.current is not None:
                self.current.close()
            self.current = self.paths[index].open("rb")
            self.current_index = index
        within = self.position - self.offsets[index]
        if self.current.tell() != within:
            self.current.seek(within)
        return self.current

    def read(self, size: int = -1) -> bytes:
        remaining_total = self.offsets[-1] - self.position
        if remaining_total <= 0:
            return b""
        if size is None or size < 0:
            size = remaining_total
        else:
            size = min(size, remaining_total)
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            index = bisect.bisect_right(self.offsets, self.position) - 1
            if index >= len(self.paths):
                break
            available = self.offsets[index + 1] - self.position
            wanted = min(remaining, available)
            data = self._select(index).read(wanted)
            if len(data) != wanted:
                raise OSError("checkpoint chunk ended unexpectedly")
            chunks.append(data)
            self.position += len(data)
            remaining -= len(data)
        return b"".join(chunks)

    def close(self) -> None:
        if self.current is not None:
            self.current.close()
            self.current = None
        super().close()


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("x", encoding="utf-8") as output:
            json.dump(payload, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sanitized_tar_info(member: tarfile.TarInfo) -> tarfile.TarInfo:
    member.uid = 0
    member.gid = 0
    member.uname = ""
    member.gname = ""
    # Never preserve setuid, setgid, or sticky bits from an ephemeral runner.
    member.mode &= 0o777
    return member


def create_checkpoint(
    conan_home: Path,
    output_dir: Path,
    key: str,
    repository_id: int,
    branch: str,
    *,
    heartbeat_interval: float = 30.0,
    archive_chunk_bytes: int = DEFAULT_ARCHIVE_CHUNK_BYTES,
) -> dict[str, object]:
    key = _validate_identifier(key, "checkpoint key")
    repository_id = _validate_repository_id(repository_id)
    branch = _validate_branch(branch)
    if archive_chunk_bytes <= 0 or archive_chunk_bytes > DEFAULT_ARCHIVE_CHUNK_BYTES:
        raise CheckpointError("invalid archive chunk size")
    conan_home = conan_home.resolve()
    if output_dir.exists():
        raise CheckpointError("checkpoint output already exists")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=".conan-checkpoint-create-", dir=output_dir.parent)
    )
    archive = temporary / ".conan-cache.tar.tmp"
    counters = {"entries": 0, "logical_bytes": 0}

    def count(member: tarfile.TarInfo) -> tarfile.TarInfo:
        counters["entries"] += 1
        if member.isfile():
            counters["logical_bytes"] += member.size
        return _sanitized_tar_info(member)

    try:
        try:
            with heartbeat("create", heartbeat_interval):
                with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as output:
                    for root_name in ROOTS:
                        source = conan_home / root_name
                        if source.is_symlink() or (source.exists() and not source.is_dir()):
                            raise CheckpointError("Conan checkpoint root is not a directory")
                        if source.exists():
                            output.add(source, arcname=root_name, recursive=True, filter=count)
                        else:
                            directory = tarfile.TarInfo(root_name)
                            directory.type = tarfile.DIRTYPE
                            directory.mode = 0o755
                            directory.mtime = int(time.time())
                            output.addfile(count(directory))
                archive_size = archive.stat().st_size
                archive_sha = _sha256(archive)
                chunks: list[dict[str, object]] = []
                with archive.open("rb") as source:
                    index = 0
                    while data := source.read(archive_chunk_bytes):
                        name = _chunk_name(index)
                        destination = temporary / name
                        with destination.open("xb") as output:
                            output.write(data)
                            output.flush()
                            os.fsync(output.fileno())
                        chunks.append(
                            {
                                "name": name,
                                "bytes": len(data),
                                "sha256": hashlib.sha256(data).hexdigest(),
                            }
                        )
                        index += 1
                archive.unlink()
        except CheckpointError:
            raise
        except (OSError, tarfile.TarError) as error:
            raise CheckpointError("checkpoint creation failed") from error

        manifest: dict[str, object] = {
            "schema": SCHEMA,
            "kind": KIND,
            "key": key,
            "provenance": {
                "repository_id": repository_id,
                "head_repository_id": repository_id,
                "head_branch": branch,
            },
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "roots": list(ROOTS),
            "archive": {
                "format": ARCHIVE_FORMAT,
                "bytes": archive_size,
                "sha256": archive_sha,
                "chunk_bytes": archive_chunk_bytes,
                "chunks": chunks,
                "entries": counters["entries"],
                "logical_bytes": counters["logical_bytes"],
            },
        }
        _atomic_json(temporary / MANIFEST_NAME, manifest)
        validate_checkpoint(temporary, key, repository_id, branch)
        os.replace(temporary, output_dir)
        print(
            "conan-checkpoint phase=create status=complete "
            f"entries={counters['entries']} archive_bytes={archive_size} "
            f"chunks={len(chunks)} chunk_bytes={archive_chunk_bytes}",
            flush=True,
        )
        return manifest
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _load_manifest(
    checkpoint_dir: Path,
    expected_key: str,
    expected_repository_id: int,
    expected_branch: str,
) -> dict[str, object]:
    expected_key = _validate_identifier(expected_key, "checkpoint key")
    expected_repository_id = _validate_repository_id(expected_repository_id)
    expected_branch = _validate_branch(expected_branch)
    path = checkpoint_dir / MANIFEST_NAME
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise CheckpointError("checkpoint manifest is too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CheckpointError("checkpoint manifest is unreadable") from error
    if not isinstance(payload, dict):
        raise CheckpointError("checkpoint manifest is not an object")
    if payload.get("schema") != SCHEMA or payload.get("kind") != KIND:
        raise CheckpointError("unsupported checkpoint format")
    if payload.get("key") != expected_key:
        raise CheckpointError("checkpoint compatibility key mismatch")
    provenance = payload.get("provenance")
    if (
        not isinstance(provenance, dict)
        or provenance.get("repository_id") != expected_repository_id
        or provenance.get("head_repository_id") != expected_repository_id
        or provenance.get("head_branch") != expected_branch
    ):
        raise CheckpointError("checkpoint provenance mismatch")
    if payload.get("roots") != list(ROOTS):
        raise CheckpointError("checkpoint root inventory mismatch")
    if not isinstance(payload.get("created_utc"), str):
        raise CheckpointError("checkpoint creation timestamp is missing")
    archive = payload.get("archive")
    if not isinstance(archive, dict) or archive.get("format") != ARCHIVE_FORMAT:
        raise CheckpointError("checkpoint archive metadata is invalid")
    size = archive.get("bytes")
    digest = archive.get("sha256")
    entries = archive.get("entries")
    logical_bytes = archive.get("logical_bytes")
    if not isinstance(size, int) or size <= 0:
        raise CheckpointError("checkpoint archive size is invalid")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise CheckpointError("checkpoint archive digest is invalid")
    if not isinstance(entries, int) or entries < len(ROOTS):
        raise CheckpointError("checkpoint entry count is invalid")
    if not isinstance(logical_bytes, int) or logical_bytes < 0:
        raise CheckpointError("checkpoint logical size is invalid")
    chunk_bytes = archive.get("chunk_bytes")
    chunks = archive.get("chunks")
    if (
        not isinstance(chunk_bytes, int)
        or chunk_bytes <= 0
        or chunk_bytes > DEFAULT_ARCHIVE_CHUNK_BYTES
        or not isinstance(chunks, list)
        or not chunks
    ):
        raise CheckpointError("checkpoint chunk inventory is invalid")
    declared_total = 0
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict) or chunk.get("name") != _chunk_name(index):
            raise CheckpointError("checkpoint chunk inventory is invalid")
        chunk_size = chunk.get("bytes")
        chunk_digest = chunk.get("sha256")
        if (
            not isinstance(chunk_size, int)
            or chunk_size <= 0
            or chunk_size > chunk_bytes
            or (index < len(chunks) - 1 and chunk_size != chunk_bytes)
            or not isinstance(chunk_digest, str)
            or not SHA256.fullmatch(chunk_digest)
        ):
            raise CheckpointError("checkpoint chunk metadata is invalid")
        declared_total += chunk_size
    if declared_total != size:
        raise CheckpointError("checkpoint chunk total mismatch")
    return payload


def _normalized_member_path(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\0" in name:
        raise CheckpointError("checkpoint contains an invalid member path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise CheckpointError("checkpoint contains an unsafe member path")
    if path.parts[0] not in ROOTS:
        raise CheckpointError("checkpoint contains an unexpected root")
    return path


def _normalized_link(member_path: PurePosixPath, link: str, hard: bool) -> PurePosixPath:
    if not link or "\\" in link or "\0" in link or PurePosixPath(link).is_absolute():
        raise CheckpointError("checkpoint contains an unsafe link")
    base = PurePosixPath() if hard else member_path.parent
    normalized = PurePosixPath(posixpath.normpath(str(base / link)))
    if normalized.is_absolute() or not normalized.parts or normalized.parts[0] not in ROOTS:
        raise CheckpointError("checkpoint link escapes the allowed roots")
    if any(part == ".." for part in normalized.parts):
        raise CheckpointError("checkpoint link escapes the allowed roots")
    return normalized


def _chunk_paths(
    checkpoint_dir: Path,
    manifest: dict[str, object],
    *,
    max_archive_bytes: int,
) -> tuple[list[Path], list[int]]:
    archive = manifest["archive"]
    assert isinstance(archive, dict)
    chunks = archive["chunks"]
    assert isinstance(chunks, list)
    paths: list[Path] = []
    sizes: list[int] = []
    aggregate = hashlib.sha256()
    total = 0
    for chunk in chunks:
        assert isinstance(chunk, dict)
        path = checkpoint_dir / str(chunk["name"])
        try:
            actual_size = path.stat().st_size
        except OSError as error:
            raise CheckpointError("checkpoint chunk is missing") from error
        if actual_size != chunk["bytes"]:
            raise CheckpointError("checkpoint chunk size mismatch")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while data := source.read(CHUNK_SIZE):
                total += len(data)
                if total > max_archive_bytes:
                    raise CheckpointError("checkpoint archive exceeds the safety limit")
                digest.update(data)
                aggregate.update(data)
        if digest.hexdigest() != chunk["sha256"]:
            raise CheckpointError("checkpoint chunk digest mismatch")
        paths.append(path)
        sizes.append(actual_size)
    if total != archive["bytes"] or aggregate.hexdigest() != archive["sha256"]:
        raise CheckpointError("checkpoint aggregate digest mismatch")
    return paths, sizes


def _archive_members(paths: list[Path], sizes: list[int]) -> list[tarfile.TarInfo]:
    members: list[tarfile.TarInfo] = []
    seen: set[PurePosixPath] = set()
    try:
        with ChunkReader(paths, sizes) as logical_archive, tarfile.open(
            fileobj=logical_archive, mode="r:"
        ) as archive:
            for member in archive:
                path = _normalized_member_path(member.name)
                if path in seen:
                    raise CheckpointError("checkpoint contains duplicate members")
                seen.add(path)
                if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
                    raise CheckpointError("checkpoint contains a special file")
                if member.issym():
                    _normalized_link(path, member.linkname, False)
                elif member.islnk():
                    _normalized_link(path, member.linkname, True)
                members.append(member)
    except (OSError, tarfile.TarError) as error:
        raise CheckpointError("checkpoint archive is unreadable") from error
    if not all(PurePosixPath(root) in seen for root in ROOTS):
        raise CheckpointError("checkpoint archive is missing a required root")
    return members


def _validated_parts(
    checkpoint_dir: Path,
    manifest: dict[str, object],
    max_archive_bytes: int,
) -> tuple[list[Path], list[int], list[tarfile.TarInfo]]:
    paths, sizes = _chunk_paths(
        checkpoint_dir, manifest, max_archive_bytes=max_archive_bytes
    )
    members = _archive_members(paths, sizes)
    archive_metadata = manifest["archive"]
    assert isinstance(archive_metadata, dict)
    if len(members) != archive_metadata["entries"]:
        raise CheckpointError("checkpoint entry count mismatch")
    logical_size = sum(member.size for member in members if member.isfile())
    if logical_size != archive_metadata["logical_bytes"]:
        raise CheckpointError("checkpoint logical size mismatch")
    return paths, sizes, members


def validate_checkpoint(
    checkpoint_dir: Path,
    expected_key: str,
    expected_repository_id: int,
    expected_branch: str,
    *,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> dict[str, object]:
    manifest = _load_manifest(
        checkpoint_dir, expected_key, expected_repository_id, expected_branch
    )
    _validated_parts(checkpoint_dir, manifest, max_archive_bytes)
    return manifest


def _destination(root: Path, member: tarfile.TarInfo) -> Path:
    relative = _normalized_member_path(member.name)
    return root.joinpath(*relative.parts)


def _ensure_directory(path: Path, root: Path) -> None:
    relative = path.relative_to(root)
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.exists():
            if cursor.is_symlink() or not cursor.is_dir():
                raise CheckpointError("checkpoint extraction encountered an unsafe parent")
        else:
            cursor.mkdir(mode=0o755)


def _extract_validated(
    paths: list[Path],
    sizes: list[int],
    members: list[tarfile.TarInfo],
    destination: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    member_by_name = {member.name: member for member in members}
    try:
        with ChunkReader(paths, sizes) as logical_archive, tarfile.open(
            fileobj=logical_archive, mode="r:"
        ) as archive:
            # Directories and regular files are materialized before links.  A
            # symlink can therefore never redirect a later file extraction.
            for member in members:
                if not member.isdir():
                    continue
                target = _destination(destination, member)
                _ensure_directory(target, destination)
            for member in members:
                if not member.isfile():
                    continue
                target = _destination(destination, member)
                _ensure_directory(target.parent, destination)
                source = archive.extractfile(member_by_name[member.name])
                if source is None:
                    raise CheckpointError("checkpoint file payload is missing")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, CHUNK_SIZE)
                target.chmod(member.mode & 0o777)
                os.utime(target, (member.mtime, member.mtime), follow_symlinks=False)
            for member in members:
                if not member.islnk():
                    continue
                target = _destination(destination, member)
                _ensure_directory(target.parent, destination)
                link = _normalized_link(
                    _normalized_member_path(member.name), member.linkname, True
                )
                source = destination.joinpath(*link.parts)
                if not source.exists() or not source.is_file() or source.is_symlink():
                    raise CheckpointError("checkpoint hard-link target is invalid")
                os.link(source, target)
            for member in members:
                if not member.issym():
                    continue
                target = _destination(destination, member)
                _ensure_directory(target.parent, destination)
                _normalized_link(
                    _normalized_member_path(member.name), member.linkname, False
                )
                os.symlink(member.linkname, target)
            for member in sorted(
                (item for item in members if item.isdir()),
                key=lambda item: len(PurePosixPath(item.name).parts),
                reverse=True,
            ):
                target = _destination(destination, member)
                target.chmod(member.mode & 0o777)
                os.utime(target, (member.mtime, member.mtime), follow_symlinks=False)
    except CheckpointError:
        raise
    except (OSError, tarfile.TarError) as error:
        raise CheckpointError("checkpoint extraction failed") from error


def _remove_path(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def restore_checkpoint(
    checkpoint_dir: Path,
    conan_home: Path,
    expected_key: str,
    expected_repository_id: int,
    expected_branch: str,
    *,
    heartbeat_interval: float = 30.0,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> dict[str, object]:
    conan_home = conan_home.resolve()
    conan_home.mkdir(parents=True, exist_ok=True)
    with heartbeat("validate", heartbeat_interval):
        manifest = _load_manifest(
            checkpoint_dir,
            expected_key,
            expected_repository_id,
            expected_branch,
        )
        paths, sizes, members = _validated_parts(
            checkpoint_dir, manifest, max_archive_bytes
        )

    staging = Path(
        tempfile.mkdtemp(prefix=".conan-checkpoint-restore-", dir=conan_home.parent)
    )
    extracted = staging / "payload"
    backups: dict[str, Path] = {}
    installed: list[str] = []
    try:
        with heartbeat("extract", heartbeat_interval):
            _extract_validated(paths, sizes, members, extracted)
        for root_name in ROOTS:
            source = extracted / root_name
            target = conan_home / root_name
            backup = staging / f"backup-{root_name}"
            if target.exists() or target.is_symlink():
                os.replace(target, backup)
                backups[root_name] = backup
            os.replace(source, target)
            installed.append(root_name)
    except Exception as error:
        for root_name in reversed(installed):
            _remove_path(conan_home / root_name)
            backup = backups.get(root_name)
            if backup is not None and backup.exists():
                os.replace(backup, conan_home / root_name)
        for root_name, backup in backups.items():
            target = conan_home / root_name
            if root_name not in installed and backup.exists() and not target.exists():
                os.replace(backup, target)
        if isinstance(error, CheckpointError):
            raise
        raise CheckpointError("checkpoint installation failed") from error
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print("conan-checkpoint phase=restore status=complete roots=2", flush=True)
    return manifest


def _token(environment_name: str) -> str:
    token = os.environ.get(environment_name, "")
    if not token:
        raise RemoteError("GitHub artifact token is unavailable")
    return token


def _api_url(api_base: str, repository: str, suffix: str) -> str:
    if not REPOSITORY.fullmatch(repository):
        raise RemoteError("invalid GitHub repository identifier")
    owner, name = repository.split("/", 1)
    return (
        f"{api_base.rstrip('/')}/repos/{quote(owner, safe='')}/"
        f"{quote(name, safe='')}/{suffix.lstrip('/')}"
    )


def _open_api(url: str, token: str):
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "overte-macos-conan-checkpoint",
        },
    )
    try:
        return build_opener(_SafeRedirectHandler()).open(request, timeout=60)
    except HTTPError as error:
        raise RemoteError(f"GitHub artifact request failed with HTTP {error.code}") from error
    except (OSError, URLError) as error:
        raise RemoteError("GitHub artifact request failed") from error


def _api_json(url: str, token: str) -> dict[str, object]:
    try:
        with _open_api(url, token) as response:
            payload = response.read(16 * 1024 * 1024 + 1)
    except RemoteError:
        raise
    except OSError as error:
        raise RemoteError("GitHub artifact response could not be read") from error
    if len(payload) > 16 * 1024 * 1024:
        raise RemoteError("GitHub artifact response is too large")
    try:
        parsed = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RemoteError("GitHub artifact response is invalid") from error
    if not isinstance(parsed, dict):
        raise RemoteError("GitHub artifact response is not an object")
    return parsed


def select_candidates(
    payload: dict[str, object],
    artifact_name: str,
    repository_id: int,
    branch: str,
) -> list[dict[str, object]]:
    _validate_identifier(artifact_name, "artifact name")
    repository_id = _validate_repository_id(repository_id)
    branch = _validate_branch(branch)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise RemoteError("GitHub artifact inventory is invalid")
    candidates: list[dict[str, object]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = artifact.get("id")
        workflow_run = artifact.get("workflow_run")
        if (
            artifact.get("name") == artifact_name
            and artifact.get("expired") is False
            and isinstance(artifact_id, int)
            and artifact_id > 0
            and isinstance(artifact.get("size_in_bytes"), int)
            and artifact["size_in_bytes"] > 0
            and isinstance(workflow_run, dict)
            and workflow_run.get("repository_id") == repository_id
            and workflow_run.get("head_repository_id") == repository_id
            and workflow_run.get("head_branch") == branch
        ):
            candidates.append(artifact)
    candidates.sort(key=lambda item: int(item["id"]), reverse=True)
    return candidates


def list_candidates(
    repository: str,
    artifact_name: str,
    repository_id: int,
    branch: str,
    token: str,
    api_base: str,
) -> list[dict[str, object]]:
    query_name = quote(artifact_name, safe="")
    url = _api_url(
        api_base,
        repository,
        f"actions/artifacts?name={query_name}&per_page=100",
    )
    return select_candidates(
        _api_json(url, token), artifact_name, repository_id, branch
    )


def _write_outputs(path: Path | None, values: dict[str, str]) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            if not re.fullmatch(r"[a-z_]+", key) or "\n" in value or "\r" in value:
                raise CheckpointError("invalid GitHub output value")
            output.write(f"{key}={value}\n")


def probe_remote(
    repository: str,
    artifact_name: str,
    repository_id: int,
    branch: str,
    token: str,
    api_base: str,
    github_output: Path | None,
) -> list[dict[str, object]]:
    candidates = list_candidates(
        repository, artifact_name, repository_id, branch, token, api_base
    )
    values = {"found": "false", "artifact_id": ""}
    if candidates:
        values = {"found": "true", "artifact_id": str(candidates[0]["id"])}
    _write_outputs(github_output, values)
    print(
        "conan-checkpoint phase=probe status=complete "
        f"compatible_candidates={len(candidates)}",
        flush=True,
    )
    return candidates


def _download_artifact(
    repository: str,
    artifact_id: int,
    token: str,
    api_base: str,
    destination: Path,
    max_download_bytes: int,
) -> None:
    url = _api_url(api_base, repository, f"actions/artifacts/{artifact_id}/zip")
    written = 0
    try:
        with _open_api(url, token) as response, destination.open("xb") as output:
            while chunk := response.read(CHUNK_SIZE):
                written += len(chunk)
                if written > max_download_bytes:
                    raise CheckpointError("remote checkpoint exceeds the safety limit")
                output.write(chunk)
    except (CheckpointError, RemoteError):
        raise
    except OSError as error:
        raise RemoteError("remote checkpoint download failed") from error


def _unpack_artifact_zip(
    artifact_zip: Path,
    checkpoint_dir: Path,
    expected_key: str,
    expected_repository_id: int,
    expected_branch: str,
    max_archive_bytes: int,
) -> None:
    try:
        with zipfile.ZipFile(artifact_zip) as archive:
            files = [item for item in archive.infolist() if not item.is_dir()]
            manifests = [item for item in files if item.filename == MANIFEST_NAME]
            if len(manifests) != 1:
                raise CheckpointError("remote artifact manifest inventory is invalid")
            manifest_info = manifests[0]
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise CheckpointError("remote checkpoint manifest is too large")
            try:
                manifest = json.loads(archive.read(manifest_info))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise CheckpointError("remote checkpoint manifest is unreadable") from error
            if not isinstance(manifest, dict) or manifest.get("key") != expected_key:
                raise CheckpointError("remote checkpoint compatibility key mismatch")
            provenance = manifest.get("provenance")
            if (
                not isinstance(provenance, dict)
                or provenance.get("repository_id") != expected_repository_id
                or provenance.get("head_repository_id") != expected_repository_id
                or provenance.get("head_branch") != expected_branch
            ):
                raise CheckpointError("remote checkpoint provenance mismatch")
            metadata = manifest.get("archive")
            if not isinstance(metadata, dict):
                raise CheckpointError("remote checkpoint archive metadata is invalid")
            chunk_metadata = metadata.get("chunks")
            if not isinstance(chunk_metadata, list):
                raise CheckpointError("remote checkpoint chunk inventory is invalid")
            expected_names = {MANIFEST_NAME}
            for index, chunk in enumerate(chunk_metadata):
                if (
                    not isinstance(chunk, dict)
                    or chunk.get("name") != _chunk_name(index)
                ):
                    raise CheckpointError("remote checkpoint chunk inventory is invalid")
                expected_names.add(str(chunk["name"]))
            if len(files) != len(expected_names) or {item.filename for item in files} != expected_names:
                raise CheckpointError("remote artifact inventory is invalid")
            for item in files:
                mode = (item.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise CheckpointError("remote artifact contains a link")
            checkpoint_dir.mkdir(parents=True, exist_ok=False)
            _atomic_json(checkpoint_dir / MANIFEST_NAME, manifest)
            extracted_total = 0
            for chunk in chunk_metadata:
                assert isinstance(chunk, dict)
                name = str(chunk["name"])
                info = archive.getinfo(name)
                declared_size = chunk.get("bytes")
                if (
                    not isinstance(declared_size, int)
                    or info.file_size != declared_size
                    or extracted_total + declared_size > max_archive_bytes
                ):
                    raise CheckpointError("remote checkpoint chunk size mismatch")
                digest = hashlib.sha256()
                with archive.open(info) as source, (checkpoint_dir / name).open("xb") as output:
                    while data := source.read(CHUNK_SIZE):
                        extracted_total += len(data)
                        if extracted_total > max_archive_bytes:
                            raise CheckpointError("remote checkpoint exceeds the safety limit")
                        digest.update(data)
                        output.write(data)
                if digest.hexdigest() != chunk.get("sha256"):
                    raise CheckpointError("remote checkpoint chunk digest mismatch")
            if extracted_total != metadata.get("bytes"):
                raise CheckpointError("remote checkpoint aggregate size mismatch")
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise CheckpointError("remote artifact is unreadable") from error


def restore_latest_remote(
    repository: str,
    artifact_name: str,
    token: str,
    api_base: str,
    expected_key: str,
    expected_repository_id: int,
    expected_branch: str,
    conan_home: Path,
    github_output: Path | None,
    *,
    heartbeat_interval: float = 30.0,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> bool:
    candidates = list_candidates(
        repository,
        artifact_name,
        expected_repository_id,
        expected_branch,
        token,
        api_base,
    )
    for candidate in candidates:
        artifact_id = int(candidate["id"])
        temporary = Path(tempfile.mkdtemp(prefix="conan-checkpoint-download-"))
        try:
            artifact_zip = temporary / "artifact.zip"
            with heartbeat("download", heartbeat_interval):
                _download_artifact(
                    repository,
                    artifact_id,
                    token,
                    api_base,
                    artifact_zip,
                    max_archive_bytes + MAX_MANIFEST_BYTES + 1024 * 1024,
                )
            checkpoint_dir = temporary / "checkpoint"
            with heartbeat("artifact-unpack", heartbeat_interval):
                _unpack_artifact_zip(
                    artifact_zip,
                    checkpoint_dir,
                    expected_key,
                    expected_repository_id,
                    expected_branch,
                    max_archive_bytes,
                )
            restore_checkpoint(
                checkpoint_dir,
                conan_home,
                expected_key,
                expected_repository_id,
                expected_branch,
                heartbeat_interval=heartbeat_interval,
                max_archive_bytes=max_archive_bytes,
            )
            _write_outputs(
                github_output,
                {"restored": "true", "artifact_id": str(artifact_id)},
            )
            return True
        except RemoteError:
            raise
        except CheckpointError:
            print(
                "conan-checkpoint phase=restore status=rejected "
                f"artifact_id={artifact_id}",
                file=sys.stderr,
                flush=True,
            )
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
    _write_outputs(github_output, {"restored": "false", "artifact_id": ""})
    print(
        "conan-checkpoint phase=restore status=unavailable; "
        "dependency resolution will create a replacement",
        flush=True,
    )
    return False


def _normalize_digest(value: str) -> str:
    if value.startswith("sha256:"):
        value = value[7:]
    if not SHA256.fullmatch(value):
        raise RemoteError("uploaded artifact digest is invalid")
    return value


def verify_remote_contents(
    repository: str,
    artifact_id: int,
    token: str,
    api_base: str,
    expected_key: str,
    expected_repository_id: int,
    expected_branch: str,
) -> None:
    temporary = Path(tempfile.mkdtemp(prefix="conan-checkpoint-verify-upload-"))
    try:
        artifact_zip = temporary / "artifact.zip"
        with heartbeat("verify-upload-download", 30.0):
            _download_artifact(
                repository,
                artifact_id,
                token,
                api_base,
                artifact_zip,
                DEFAULT_MAX_ARCHIVE_BYTES + MAX_MANIFEST_BYTES + 1024 * 1024,
            )
        checkpoint_dir = temporary / "checkpoint"
        with heartbeat("verify-upload-contents", 30.0):
            _unpack_artifact_zip(
                artifact_zip,
                checkpoint_dir,
                expected_key,
                expected_repository_id,
                expected_branch,
                DEFAULT_MAX_ARCHIVE_BYTES,
            )
            validate_checkpoint(
                checkpoint_dir,
                expected_key,
                expected_repository_id,
                expected_branch,
            )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def verify_remote(
    repository: str,
    artifact_id: int,
    artifact_name: str,
    expected_digest: str,
    expected_key: str,
    expected_repository_id: int,
    expected_branch: str,
    token: str,
    api_base: str,
    *,
    attempts: int = 24,
    retry_interval: float = 5.0,
) -> None:
    if attempts <= 0 or retry_interval < 0:
        raise CheckpointError("invalid remote verification retry policy")
    expected = _normalize_digest(expected_digest)
    last_error: RemoteError | None = None
    payload: dict[str, object] | None = None
    for attempt in range(1, attempts + 1):
        try:
            candidate = _api_json(
                _api_url(api_base, repository, f"actions/artifacts/{artifact_id}"), token
            )
            if (
                candidate.get("id") != artifact_id
                or candidate.get("name") != artifact_name
                or candidate.get("expired") is not False
                or not isinstance(candidate.get("size_in_bytes"), int)
                or candidate["size_in_bytes"] <= 0
            ):
                raise RemoteError("uploaded artifact metadata validation failed")
            remote_digest = candidate.get("digest")
            if (
                not isinstance(remote_digest, str)
                or _normalize_digest(remote_digest) != expected
            ):
                raise RemoteError("uploaded artifact digest validation failed")
            workflow_run = candidate.get("workflow_run")
            if (
                not isinstance(workflow_run, dict)
                or workflow_run.get("repository_id") != expected_repository_id
                or workflow_run.get("head_repository_id") != expected_repository_id
                or workflow_run.get("head_branch") != expected_branch
            ):
                raise RemoteError("uploaded artifact provenance validation failed")
            payload = candidate
            break
        except RemoteError as error:
            last_error = error
            if attempt == attempts:
                raise
            print(
                "conan-checkpoint phase=verify-upload status=pending "
                f"attempt={attempt}",
                flush=True,
            )
            time.sleep(retry_interval)
    if payload is None:
        assert last_error is not None
        raise last_error
    verify_remote_contents(
        repository,
        artifact_id,
        token,
        api_base,
        expected_key,
        expected_repository_id,
        expected_branch,
    )
    print(
        "conan-checkpoint phase=verify-upload status=complete "
        f"artifact_id={artifact_id} bytes={payload['size_in_bytes']}",
        flush=True,
    )


def _common_remote(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--api-base", default="https://api.github.com")
    parser.add_argument("--repository-id", type=int, required=True)
    parser.add_argument("--branch", required=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--conan-home", type=Path, required=True)
    create.add_argument("--output-dir", type=Path, required=True)
    create.add_argument("--key", required=True)
    create.add_argument("--repository-id", type=int, required=True)
    create.add_argument("--branch", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--checkpoint-dir", type=Path, required=True)
    verify.add_argument("--key", required=True)
    verify.add_argument("--repository-id", type=int, required=True)
    verify.add_argument("--branch", required=True)

    restore = subparsers.add_parser("restore")
    restore.add_argument("--checkpoint-dir", type=Path, required=True)
    restore.add_argument("--conan-home", type=Path, required=True)
    restore.add_argument("--key", required=True)
    restore.add_argument("--repository-id", type=int, required=True)
    restore.add_argument("--branch", required=True)

    probe = subparsers.add_parser("probe")
    _common_remote(probe)
    probe.add_argument("--github-output", type=Path)

    remote_restore = subparsers.add_parser("restore-remote")
    _common_remote(remote_restore)
    remote_restore.add_argument("--conan-home", type=Path, required=True)
    remote_restore.add_argument("--key", required=True)
    remote_restore.add_argument("--github-output", type=Path)

    remote_verify = subparsers.add_parser("verify-remote")
    _common_remote(remote_verify)
    remote_verify.add_argument("--artifact-id", type=int, required=True)
    remote_verify.add_argument("--expected-digest", required=True)
    remote_verify.add_argument("--key", required=True)

    arguments = parser.parse_args()
    try:
        if arguments.operation == "create":
            create_checkpoint(
                arguments.conan_home,
                arguments.output_dir,
                arguments.key,
                arguments.repository_id,
                arguments.branch,
            )
        elif arguments.operation == "verify":
            validate_checkpoint(
                arguments.checkpoint_dir,
                arguments.key,
                arguments.repository_id,
                arguments.branch,
            )
            print("conan-checkpoint phase=verify status=complete", flush=True)
        elif arguments.operation == "restore":
            restore_checkpoint(
                arguments.checkpoint_dir,
                arguments.conan_home,
                arguments.key,
                arguments.repository_id,
                arguments.branch,
            )
        elif arguments.operation == "probe":
            probe_remote(
                arguments.repository,
                arguments.artifact_name,
                arguments.repository_id,
                arguments.branch,
                _token(arguments.token_env),
                arguments.api_base,
                arguments.github_output,
            )
        elif arguments.operation == "restore-remote":
            restore_latest_remote(
                arguments.repository,
                arguments.artifact_name,
                _token(arguments.token_env),
                arguments.api_base,
                arguments.key,
                arguments.repository_id,
                arguments.branch,
                arguments.conan_home,
                arguments.github_output,
            )
        else:
            verify_remote(
                arguments.repository,
                arguments.artifact_id,
                arguments.artifact_name,
                arguments.expected_digest,
                arguments.key,
                arguments.repository_id,
                arguments.branch,
                _token(arguments.token_env),
                arguments.api_base,
            )
    except CheckpointError as error:
        print(f"conan-checkpoint error: {error}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
