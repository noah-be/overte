#!/usr/bin/env python3
"""Create and restore validated iOS toolchain prefixes via workflow artifacts."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile


SCHEMA = 1
ARCHIVE_NAME = "checkpoint.tar.gz"
MANIFEST_NAME = "manifest.json"
API_JSON_LIMIT = 16 * 1024 * 1024
DOWNLOAD_LIMITS = {
    "host": 512 * 1024 * 1024,
    "ios": 512 * 1024 * 1024,
    "v8": 512 * 1024 * 1024,
    "conan": 2 * 1024 * 1024 * 1024,
}
MANIFEST_LIMIT = 64 * 1024
ARCHIVE_LIMITS = {
    "host": 384 * 1024 * 1024,
    "ios": 384 * 1024 * 1024,
    "v8": 384 * 1024 * 1024,
    "conan": 1536 * 1024 * 1024,
}
MEMBER_LIMITS = {"host": 100_000, "ios": 100_000, "v8": 100_000, "conan": 500_000}
EXPANDED_LIMITS = {
    "host": 2 * 1024 * 1024 * 1024,
    "ios": 2 * 1024 * 1024 * 1024,
    "v8": 2 * 1024 * 1024 * 1024,
    "conan": 10 * 1024 * 1024 * 1024,
}


def fail(message: str) -> "None":
    raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tar_info(path: Path, relative: Path) -> tarfile.TarInfo:
    info = tarfile.TarInfo(relative.as_posix())
    metadata = path.lstat()
    info.mode = stat.S_IMODE(metadata.st_mode)
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    if stat.S_ISDIR(metadata.st_mode):
        info.type = tarfile.DIRTYPE
    elif stat.S_ISLNK(metadata.st_mode):
        info.type = tarfile.SYMTYPE
        info.linkname = os.readlink(path)
    elif stat.S_ISREG(metadata.st_mode):
        info.type = tarfile.REGTYPE
        info.size = metadata.st_size
    else:
        fail(f"unsupported file type in Qt prefix: {path}")
    return info


def create_archive(prefix: Path, archive: Path, kind: str) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as output:
                paths = sorted(prefix.rglob("*"), key=lambda item: item.relative_to(prefix).as_posix())
                if len(paths) > MEMBER_LIMITS[kind]:
                    fail("checkpoint prefix exceeds the member limit")
                expanded = sum(path.lstat().st_size for path in paths if path.is_file() and not path.is_symlink())
                if expanded > EXPANDED_LIMITS[kind]:
                    fail("checkpoint prefix exceeds the expanded-size limit")
                for path in paths:
                    relative = path.relative_to(prefix)
                    info = _tar_info(path, relative)
                    if info.isreg():
                        with path.open("rb") as source:
                            output.addfile(info, source)
                    else:
                        output.addfile(info)
    os.replace(temporary, archive)
    if archive.stat().st_size > ARCHIVE_LIMITS[kind]:
        archive.unlink()
        fail("checkpoint archive exceeds the compressed-size limit")


def create(args: argparse.Namespace) -> None:
    prefix = Path(args.prefix).resolve()
    if not prefix.is_dir():
        fail(f"{args.kind} checkpoint prefix is not a directory: {prefix}")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ARCHIVE_NAME
    create_archive(prefix, archive, args.kind)
    manifest = {
        "schema": SCHEMA,
        "kind": args.kind,
        "cacheKey": args.cache_key,
        "producerRepositoryId": int(args.producer_repository_id),
        "producerBranch": args.producer_branch,
        "archive": ARCHIVE_NAME,
        "sha256": sha256(archive),
        "size": archive.stat().st_size,
    }
    (output / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def select_artifact(
    artifacts: list[dict], prefix: str, expected_repository_id: int, expected_branch: str
) -> dict | None:
    candidates = [
        artifact
        for artifact in artifacts
        if artifact.get("name", "").startswith(prefix + "-")
        and not artifact.get("expired", False)
        and artifact.get("workflow_run", {}).get("repository_id") == expected_repository_id
        and artifact.get("workflow_run", {}).get("head_repository_id") == expected_repository_id
        and artifact.get("workflow_run", {}).get("head_branch") == expected_branch
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.get("created_at", ""), int(item.get("id", 0))))


def _read_limited(response, limit: int, output=None) -> bytes:
    collected = bytearray()
    total = 0
    while True:
        chunk = response.read(min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            fail("GitHub response exceeds its safety limit")
        if output is None:
            collected.extend(chunk)
        else:
            output.write(chunk)
    return bytes(collected)


def _github_request(url: str, token: str, limit: int = API_JSON_LIMIT) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "overte-qt-checkpoint",
        },
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return _read_limited(response, limit)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                fail("GitHub artifact API remained unavailable after four verified-TLS attempts")
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def download_artifact(url: str, token: str, destination: Path, limit: int, opener=None) -> None:
    opener = opener or urllib.request.build_opener(_NoRedirect()).open
    authenticated = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "overte-qt-checkpoint",
        },
    )
    try:
        first = opener(authenticated)
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise
        first = error
    try:
        location = first.headers.get("Location")
        if not location:
            fail("GitHub artifact download did not provide a redirect")
    finally:
        first.close()
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme != "https" or not parsed.netloc:
        fail("GitHub artifact redirect is not a safe HTTPS URL")
    anonymous = urllib.request.Request(location, headers={"User-Agent": "overte-qt-checkpoint"})
    with opener(anonymous) as response, destination.open("wb") as output:
        _read_limited(response, limit, output)


def find_latest(prefix: str, expected_repository_id: int, expected_branch: str) -> tuple[dict | None, str]:
    token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or repository.count("/") != 1:
        fail("GITHUB_TOKEN (or GH_TOKEN) and owner/repository GITHUB_REPOSITORY are required")
    encoded_repo = "/".join(urllib.parse.quote(part, safe="") for part in repository.split("/"))
    artifacts: list[dict] = []
    for page in range(1, 101):
        url = f"https://api.github.com/repos/{encoded_repo}/actions/artifacts?per_page=100&page={page}"
        payload = json.loads(_github_request(url, token))
        batch = payload.get("artifacts", [])
        artifacts.extend(batch)
        if len(batch) < 100:
            break
    artifact = select_artifact(artifacts, prefix, expected_repository_id, expected_branch)
    return artifact, token


def download_latest(
    prefix: str, expected_repository_id: int, expected_branch: str, destination: Path, kind: str
) -> dict | None:
    artifact, token = find_latest(prefix, expected_repository_id, expected_branch)
    if artifact is None:
        return None
    download_artifact(artifact["archive_download_url"], token, destination, DOWNLOAD_LIMITS[kind])
    return artifact


def _safe_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        fail(f"unsafe archive path: {name!r}")
    return path


def unpack_payload(workflow_zip: Path, destination: Path, kind: str) -> None:
    with zipfile.ZipFile(workflow_zip) as source:
        infos = source.infolist()
        names = [info.filename for info in infos]
        if names.count(ARCHIVE_NAME) != 1 or names.count(MANIFEST_NAME) != 1 or len(infos) != 2:
            fail("workflow artifact must contain exactly two unique root files")
        entries = {info.filename: info for info in infos}
        for name in (ARCHIVE_NAME, MANIFEST_NAME):
            info = entries[name]
            if info.is_dir():
                fail(f"workflow artifact entry is not a file: {name}")
            limit = MANIFEST_LIMIT if name == MANIFEST_NAME else ARCHIVE_LIMITS[kind]
            if info.file_size > limit:
                fail(f"workflow artifact entry exceeds its safety limit: {name}")
            with source.open(info) as incoming, (destination / name).open("wb") as outgoing:
                _read_limited(incoming, limit, outgoing)


def validate_manifest(directory: Path, kind: str, cache_key: str) -> Path:
    try:
        manifest_path = directory / MANIFEST_NAME
        if manifest_path.stat().st_size > MANIFEST_LIMIT:
            fail("checkpoint manifest exceeds its safety limit")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid checkpoint manifest: {error}")
    if manifest.get("schema") != SCHEMA:
        fail("unsupported checkpoint manifest schema")
    if manifest.get("kind") != kind or manifest.get("cacheKey") != cache_key:
        fail("checkpoint kind or cache key does not match the request")
    if manifest.get("archive") != ARCHIVE_NAME:
        fail("checkpoint manifest names an unexpected archive")
    archive = directory / ARCHIVE_NAME
    if sha256(archive) != manifest.get("sha256"):
        fail("checkpoint archive SHA-256 mismatch")
    if archive.stat().st_size != manifest.get("size"):
        fail("checkpoint archive size mismatch")
    return archive


def _safe_link(member: tarfile.TarInfo) -> None:
    target = PurePosixPath(member.linkname)
    combined = PurePosixPath(member.name).parent / target
    depth = 0
    if target.is_absolute() or "\\" in member.linkname:
        fail(f"unsafe link target: {member.linkname!r}")
    for part in combined.parts:
        depth += -1 if part == ".." else (0 if part in ("", ".") else 1)
        if depth < 0:
            fail(f"link escapes checkpoint root: {member.name!r}")


def safe_extract(archive: Path, destination: Path, kind: str = "host") -> None:
    with tarfile.open(archive, "r:gz") as source:
        members = []
        expanded = 0
        for member in source:
            if len(members) >= MEMBER_LIMITS[kind]:
                fail("checkpoint archive exceeds the member limit")
            if member.isreg():
                expanded += member.size
                if expanded > EXPANDED_LIMITS[kind]:
                    fail("checkpoint archive exceeds the expanded-size limit")
            _safe_name(member.name)
            if member.issym() or member.islnk():
                _safe_link(member)
            elif not (member.isdir() or member.isreg()):
                fail(f"unsupported checkpoint archive member: {member.name!r}")
            members.append(member)
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                os.chmod(target, member.mode & 0o777)
            elif member.isreg():
                target.parent.mkdir(parents=True, exist_ok=True)
                incoming = source.extractfile(member)
                if incoming is None:
                    fail(f"cannot read checkpoint member: {member.name!r}")
                with incoming, target.open("wb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                os.chmod(target, member.mode & 0o777)
            elif member.issym():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(member.linkname, target)
            else:
                fail("hard links are not accepted in checkpoint archives")


def set_outputs(path: Path, **values: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={'true' if value else 'false'}\n")


def is_fresh(artifact: dict, max_age_days: int) -> bool:
    try:
        created = dt.datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return False
    age = dt.datetime.now(dt.timezone.utc) - created
    return dt.timedelta(0) <= age <= dt.timedelta(days=max_age_days)


def probe(args: argparse.Namespace) -> None:
    artifact, _ = find_latest(
        args.artifact_prefix, int(args.expected_repository_id), args.expected_branch
    )
    available = artifact is not None
    set_outputs(
        Path(args.github_output),
        available=available,
        fresh=available and is_fresh(artifact, args.max_age_days),
    )


def restore(args: argparse.Namespace) -> None:
    output = Path(args.github_output)
    install_root = Path(args.install_root)
    target_name = {
        "host": "macos", "ios": "ios", "v8": "v8-ios", "conan": "conan-home"
    }[args.kind]
    target_root = install_root / target_name
    with tempfile.TemporaryDirectory(prefix="overte-qt-checkpoint-") as temporary_name:
        temporary = Path(temporary_name)
        workflow_zip = temporary / "artifact.zip"
        try:
            artifact = download_latest(
                args.artifact_prefix,
                int(args.expected_repository_id),
                args.expected_branch,
                workflow_zip,
                args.kind,
            )
        except urllib.error.HTTPError as error:
            fail(f"GitHub artifact API failed with HTTP {error.code}")
        if artifact is None:
            set_outputs(output, available=False, fresh=False, restored=False)
            return
        fresh = is_fresh(artifact, args.max_age_days)
        payload = temporary / "payload"
        payload.mkdir()
        unpack_payload(workflow_zip, payload, args.kind)
        archive = validate_manifest(payload, args.kind, args.cache_key)
        manifest = json.loads((payload / MANIFEST_NAME).read_text(encoding="utf-8"))
        if manifest.get("producerRepositoryId") != int(args.expected_repository_id):
            fail("checkpoint manifest repository does not match the request")
        if manifest.get("producerBranch") != args.expected_branch:
            fail("checkpoint manifest branch does not match the request")
        install_root.mkdir(parents=True, exist_ok=True)
        staged = install_root / f".{target_root.name}.restore-{os.getpid()}"
        if target_root.exists() or staged.exists():
            fail(f"Qt install root already exists: {target_root}")
        staged.mkdir(parents=True)
        try:
            safe_extract(archive, staged, args.kind)
            os.replace(staged, target_root)
        finally:
            if staged.exists():
                shutil.rmtree(staged)
    set_outputs(output, available=True, fresh=fresh, restored=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    commands = result.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--prefix", required=True)
    create_parser.add_argument("--kind", choices=("host", "ios", "v8", "conan"), required=True)
    create_parser.add_argument("--cache-key", required=True)
    create_parser.add_argument("--producer-repository-id", required=True)
    create_parser.add_argument("--producer-branch", required=True)
    create_parser.add_argument("--output-dir", required=True)
    create_parser.set_defaults(handler=create)
    restore_parser = commands.add_parser("restore")
    restore_parser.add_argument("--artifact-prefix", required=True)
    restore_parser.add_argument("--kind", choices=("host", "ios", "v8", "conan"), required=True)
    restore_parser.add_argument("--cache-key", required=True)
    restore_parser.add_argument("--expected-repository-id", required=True, type=int)
    restore_parser.add_argument("--expected-branch", required=True)
    restore_parser.add_argument("--max-age-days", type=int, default=21)
    restore_parser.add_argument("--install-root", required=True)
    restore_parser.add_argument("--github-output", required=True)
    restore_parser.set_defaults(handler=restore)
    probe_parser = commands.add_parser("probe")
    probe_parser.add_argument("--artifact-prefix", required=True)
    probe_parser.add_argument("--expected-repository-id", required=True, type=int)
    probe_parser.add_argument("--expected-branch", required=True)
    probe_parser.add_argument("--max-age-days", type=int, default=21)
    probe_parser.add_argument("--github-output", required=True)
    probe_parser.set_defaults(handler=probe)
    return result


def main() -> None:
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
