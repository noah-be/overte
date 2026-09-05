#!/usr/bin/env python3
"""Compose the locked Qt source tree without network or Git access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


class SourceStoreError(RuntimeError):
    pass


EXPECTED_COMPONENTS = {
    "qt5-superproject": "qt5",
    "qtbase": "qt5/qtbase",
    "qtdeclarative": "qt5/qtdeclarative",
    "qtgraphicaleffects": "qt5/qtgraphicaleffects",
    "qtimageformats": "qt5/qtimageformats",
    "qtlocation": "qt5/qtlocation",
    "qtlocation-mapboxgl": "qt5/qtlocation/src/3rdparty/mapbox-gl-native",
    "qtmultimedia": "qt5/qtmultimedia",
    "qtquickcontrols": "qt5/qtquickcontrols",
    "qtquickcontrols2": "qt5/qtquickcontrols2",
    "qtscxml": "qt5/qtscxml",
    "qtsvg": "qt5/qtsvg",
    "qttools": "qt5/qttools",
    "qtwebchannel": "qt5/qtwebchannel",
    "qtwebsockets": "qt5/qtwebsockets",
    "qtwebview": "qt5/qtwebview",
    "qtxmlpatterns": "qt5/qtxmlpatterns",
}

EXPECTED_ARCHIVE_LIMITS = {
    "max_archive_bytes": 512 * 1024 * 1024,
    "max_component_unpacked_bytes": 2 * 1024 * 1024 * 1024,
    "max_total_unpacked_bytes": 16 * 1024 * 1024 * 1024,
    "max_members_per_archive": 300_000,
}


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SourceStoreError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict:
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates
        )
    except (OSError, ValueError) as error:
        raise SourceStoreError(f"invalid manifest: {error}") from error
    validate_manifest(document)
    return document


def validate_manifest(document: dict) -> None:
    if document.get("schema_version") != 1:
        raise SourceStoreError("unsupported manifest schema")
    if document.get("status") != "SOURCE_ARCHIVES_LOCKED_LICENSE_HASHES_PENDING":
        raise SourceStoreError("unexpected qualification status")
    if document.get("source_authority") != {
        "package": "overte-fdroid-buildpath-prework/00-source-graph-design",
        "sha256sums_sha256": (
            "7129917d10c59b808903d61925fdbc751e1dada80bc6c0ca3759d4a2b728035a"
        ),
    }:
        raise SourceStoreError("source authority changed")
    if document.get("archive_limits") != EXPECTED_ARCHIVE_LIMITS:
        raise SourceStoreError("archive safety limits changed")
    components = document.get("components")
    if not isinstance(components, list) or len(components) != len(EXPECTED_COMPONENTS):
        raise SourceStoreError("exactly 17 Qt source components are required")
    identifiers = set()
    destinations = set()
    for component in components:
        required = {
            "id",
            "role",
            "commit",
            "canonical_url",
            "sha256",
            "store_name",
            "destination",
            "strip_components",
        }
        if set(component) != required:
            raise SourceStoreError(f"invalid component fields: {component.get('id')}")
        identifier = component["id"]
        if identifier in identifiers:
            raise SourceStoreError(f"duplicate component: {identifier}")
        identifiers.add(identifier)
        destination = PurePosixPath(component["destination"])
        if (
            destination.is_absolute()
            or ".." in destination.parts
            or not destination.parts
            or destination.parts[0] != "qt5"
        ):
            raise SourceStoreError(f"unsafe destination: {destination}")
        if str(destination) in destinations:
            raise SourceStoreError(f"duplicate destination: {destination}")
        destinations.add(str(destination))
        sha256 = component["sha256"]
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise SourceStoreError(f"invalid SHA-256: {identifier}")
        try:
            int(sha256, 16)
        except ValueError as error:
            raise SourceStoreError(f"invalid SHA-256: {identifier}") from error
        if component["store_name"] != f"{sha256}.tar.gz":
            raise SourceStoreError(f"non-content-addressed source: {identifier}")
        if not component["canonical_url"].startswith("https://invent.kde.org/qt/qt/"):
            raise SourceStoreError(f"source is outside the Qt archive authority: {identifier}")
        if component["commit"] not in component["canonical_url"]:
            raise SourceStoreError(f"URL is not commit-bound: {identifier}")
        if len(component["commit"]) != 40:
            raise SourceStoreError(f"invalid commit: {identifier}")
        try:
            int(component["commit"], 16)
        except ValueError as error:
            raise SourceStoreError(f"invalid commit: {identifier}") from error
        if component["strip_components"] != 1:
            raise SourceStoreError(f"unexpected strip count: {identifier}")
    if {component["id"]: component["destination"] for component in components} != EXPECTED_COMPONENTS:
        raise SourceStoreError("Qt component/destination allowlist changed")
    forbidden = set(document.get("forbidden_components", []))
    if identifiers & forbidden:
        raise SourceStoreError("forbidden Qt component admitted")
    if forbidden != {
        "qtdeclarative-test262",
        "qtwebengine",
        "qtxmlpatterns-testsuite",
    }:
        raise SourceStoreError("forbidden Qt component set changed")
    if document.get("isolated_network") != "NONE":
        raise SourceStoreError("composition must be network-free")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stripped_member_path(member: tarfile.TarInfo, strip_components: int) -> Path | None:
    source = PurePosixPath(member.name)
    if source.is_absolute() or ".." in source.parts:
        raise SourceStoreError(f"unsafe archive path: {member.name}")
    clean_parts = tuple(part for part in source.parts if part not in ("", "."))
    if len(clean_parts) <= strip_components:
        return None
    return Path(*clean_parts[strip_components:])


def _validate_link(member: tarfile.TarInfo, relative: Path) -> None:
    target = PurePosixPath(member.linkname)
    if target.is_absolute():
        raise SourceStoreError(f"absolute archive link: {member.name}")
    combined = PurePosixPath(relative.parent.as_posix(), target)
    depth = 0
    for part in combined.parts:
        if part in ("", "."):
            continue
        if part == "..":
            depth -= 1
        else:
            depth += 1
        if depth < 0:
            raise SourceStoreError(f"escaping archive link: {member.name}")


def extract_archive(
    archive: Path,
    destination: Path,
    strip_components: int,
    max_unpacked_bytes: int = EXPECTED_ARCHIVE_LIMITS[
        "max_component_unpacked_bytes"
    ],
    max_members: int = EXPECTED_ARCHIVE_LIMITS["max_members_per_archive"],
) -> tuple[int, int]:
    with tarfile.open(archive, mode="r:gz") as source:
        members = []
        member_paths = set()
        unpacked_bytes = 0
        for member in source.getmembers():
            relative = _stripped_member_path(member, strip_components)
            if relative is None:
                continue
            if relative in member_paths:
                raise SourceStoreError(f"duplicate archive path: {member.name}")
            member_paths.add(relative)
            if len(member_paths) > max_members:
                raise SourceStoreError("archive member limit exceeded")
            unpacked_bytes += member.size
            if unpacked_bytes > max_unpacked_bytes:
                raise SourceStoreError("archive unpacked-size limit exceeded")
            if member.isdev() or member.isfifo() or member.islnk():
                raise SourceStoreError(f"unsupported archive member: {member.name}")
            if member.issym():
                _validate_link(member, relative)
            members.append((member, relative))
        for member, relative in members:
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.issym():
                os.symlink(member.linkname, target)
                continue
            if not member.isfile():
                raise SourceStoreError(f"unsupported archive type: {member.name}")
            extracted = source.extractfile(member)
            if extracted is None:
                raise SourceStoreError(f"unreadable archive member: {member.name}")
            with extracted, target.open("xb") as output:
                shutil.copyfileobj(extracted, output)
            mode = 0o755 if member.mode & stat.S_IXUSR else 0o644
            target.chmod(mode)
        return len(member_paths), unpacked_bytes


def compose(manifest_path: Path, source_store: Path, output: Path) -> dict:
    manifest_path = manifest_path.resolve(strict=True)
    source_store = source_store.resolve(strict=True)
    output = output.absolute()
    if not source_store.is_dir():
        raise SourceStoreError("source store is not a directory")
    if output.exists():
        raise SourceStoreError("output path already exists")
    document = load_manifest(manifest_path)
    parent = output.parent
    if not parent.is_dir():
        raise SourceStoreError("output parent does not exist")
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=parent))
    try:
        total_unpacked_bytes = 0
        for component in document["components"]:
            archive = source_store / component["store_name"]
            if not archive.is_file():
                raise SourceStoreError(f"source missing: {component['id']}")
            if archive.stat().st_size > document["archive_limits"]["max_archive_bytes"]:
                raise SourceStoreError(f"source exceeds size limit: {component['id']}")
            actual = sha256_file(archive)
            if actual != component["sha256"]:
                raise SourceStoreError(f"source digest mismatch: {component['id']}")
            destination = stage / component["destination"]
            destination.mkdir(parents=True, exist_ok=True)
            _, unpacked_bytes = extract_archive(
                archive,
                destination,
                component["strip_components"],
                document["archive_limits"]["max_component_unpacked_bytes"],
                document["archive_limits"]["max_members_per_archive"],
            )
            total_unpacked_bytes += unpacked_bytes
            if total_unpacked_bytes > document["archive_limits"][
                "max_total_unpacked_bytes"
            ]:
                raise SourceStoreError("total unpacked-size limit exceeded")
        attestation = {
            "schema_version": 1,
            "status": "COMPOSED_UNQUALIFIED_LICENSE_HASHES_PENDING",
            "manifest_sha256": sha256_file(manifest_path),
            "component_count": len(document["components"]),
            "total_unpacked_bytes": total_unpacked_bytes,
            "component_sha256": {
                component["id"]: component["sha256"]
                for component in document["components"]
            },
        }
        (stage / "COMPOSITION.json").write_text(
            json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        stage.rename(output)
        return attestation
    except Exception:
        shutil.rmtree(stage)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-store", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        attestation = compose(
            arguments.manifest, arguments.source_store, arguments.output
        )
    except SourceStoreError as error:
        parser.error(str(error))
    print(json.dumps(attestation, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
