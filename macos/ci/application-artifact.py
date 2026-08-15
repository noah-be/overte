#!/usr/bin/env python3
"""Package and verify provenance for a native macOS application artifact.

The manifest deliberately covers every Mach-O image in the bundle.  It does
not trust file extensions: ``file`` identifies Mach-O payloads and ``lipo``
reports their architecture slices.  Tool paths are injectable so the complete
contract can be tested without macOS hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


SCHEMA_VERSION = 1
KIND = "overte-macos-application-artifact"
MANIFEST_MAX_BYTES = 4 * 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
MAIN_EXECUTABLE = "Contents/MacOS/Overte"
TARGET_ARCHITECTURES = ("arm64", "x86_64")

ROOT_FIELDS = {"schema_version", "kind", "provenance", "build", "application"}
PROVENANCE_FIELDS = {
    "repository", "repository_id", "workflow", "ref", "sha", "run_id", "run_attempt",
}
BUILD_FIELDS = {
    "target_arch", "xcode_version", "xcode_build", "sdk_version", "build_type",
    "deployment_target",
}
APPLICATION_FIELDS = {
    "bundle_name", "main_executable", "main_sha256", "mach_o",
}
MACH_O_FIELDS = {"path", "sha256", "architectures"}

REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
WORKFLOW = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml\Z")
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){0,3}\Z")
XCODE_BUILD = re.compile(r"[A-Za-z0-9.()_-]{1,64}\Z")
BUILD_TYPE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
ARCHITECTURE = re.compile(r"[A-Za-z0-9_]+\Z")


class ArtifactError(RuntimeError):
    """The bundle, provenance, or manifest is invalid or incompatible."""


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ArtifactError(f"invalid {label}")
    return value


def _validated_ref(value: str) -> str:
    if not isinstance(value, str) or not value.startswith(("refs/heads/", "refs/tags/")):
        raise ArtifactError("invalid ref")
    if len(value) > 255 or any(ord(character) < 32 for character in value):
        raise ArtifactError("invalid ref")
    suffix = value.split("/", 2)[2]
    if not suffix or value.endswith("/") or any(part in ("", ".", "..") for part in suffix.split("/")):
        raise ArtifactError("invalid ref")
    return value


def _validated_metadata(metadata: dict[str, object]) -> dict[str, object]:
    if set(metadata) != {"provenance", "build"}:
        raise ArtifactError("metadata fields do not match schema 1")
    provenance = metadata.get("provenance")
    build = metadata.get("build")
    if not isinstance(provenance, dict) or set(provenance) != PROVENANCE_FIELDS:
        raise ArtifactError("provenance fields do not match schema 1")
    if not isinstance(build, dict) or set(build) != BUILD_FIELDS:
        raise ArtifactError("build fields do not match schema 1")

    repository = provenance.get("repository")
    if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
        raise ArtifactError("invalid repository")
    _positive_integer(provenance.get("repository_id"), "repository id")
    workflow = provenance.get("workflow")
    if not isinstance(workflow, str) or not WORKFLOW.fullmatch(workflow):
        raise ArtifactError("invalid workflow")
    _validated_ref(provenance.get("ref") if isinstance(provenance.get("ref"), str) else "")
    sha = provenance.get("sha")
    if not isinstance(sha, str) or not GIT_SHA.fullmatch(sha):
        raise ArtifactError("invalid commit SHA")
    _positive_integer(provenance.get("run_id"), "run id")
    _positive_integer(provenance.get("run_attempt"), "run attempt")

    target_arch = build.get("target_arch")
    if target_arch not in TARGET_ARCHITECTURES:
        raise ArtifactError("invalid target architecture")
    for field in ("xcode_version", "sdk_version", "deployment_target"):
        value = build.get(field)
        if not isinstance(value, str) or not VERSION.fullmatch(value):
            raise ArtifactError(f"invalid {field.replace('_', ' ')}")
    xcode_build = build.get("xcode_build")
    if not isinstance(xcode_build, str) or not XCODE_BUILD.fullmatch(xcode_build):
        raise ArtifactError("invalid Xcode build")
    build_type = build.get("build_type")
    if not isinstance(build_type, str) or not BUILD_TYPE.fullmatch(build_type):
        raise ArtifactError("invalid build type")
    return {
        "provenance": dict(provenance),
        "build": dict(build),
    }


def metadata_from_values(
        *, repository: str, repository_id: int, workflow: str, ref: str, sha: str,
        run_id: int, run_attempt: int, target_arch: str, xcode_version: str,
        xcode_build: str, sdk_version: str, build_type: str,
        deployment_target: str,
) -> dict[str, object]:
    """Build and validate the expected provenance supplied by a workflow."""
    return _validated_metadata({
        "provenance": {
            "repository": repository,
            "repository_id": repository_id,
            "workflow": workflow,
            "ref": ref,
            "sha": sha,
            "run_id": run_id,
            "run_attempt": run_attempt,
        },
        "build": {
            "target_arch": target_arch,
            "xcode_version": xcode_version,
            "xcode_build": xcode_build,
            "sdk_version": sdk_version,
            "build_type": build_type,
            "deployment_target": deployment_target,
        },
    })


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(HASH_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as error:
        raise ArtifactError("could not hash bundle member") from error
    return digest.hexdigest()


def _run_tool(tool: Path, arguments: list[str], label: str) -> bytes:
    try:
        result = subprocess.run(
            [str(tool), *arguments], check=False, capture_output=True,
            timeout=30, env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ArtifactError(f"{label} tool failed") from error
    if result.returncode != 0:
        raise ArtifactError(f"{label} tool failed")
    return result.stdout.strip()


def _bundle_files(app: Path) -> list[tuple[str, Path]]:
    if not app.is_dir() or app.is_symlink() or app.suffix != ".app":
        raise ArtifactError("application bundle is missing or unsafe")

    def walk_failed(_error: OSError) -> None:
        raise ArtifactError("could not enumerate application bundle")

    files: list[tuple[str, Path]] = []
    for root, directories, names in os.walk(
            app, topdown=True, onerror=walk_failed, followlinks=False,
    ):
        root_path = Path(root)
        directories[:] = sorted(
            name for name in directories if not (root_path / name).is_symlink()
        )
        for name in sorted(names):
            path = root_path / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(app).as_posix()
            if any(ord(character) < 32 for character in relative):
                raise ArtifactError("bundle member has an unsafe path")
            files.append((relative, path))
    return sorted(files)


def inspect_mach_o_bundle(
        app: Path, target_arch: str, *, file_tool: Path, lipo_tool: Path,
) -> list[dict[str, object]]:
    """Return a stable, hashed inventory and require the target slice everywhere."""
    if target_arch not in TARGET_ARCHITECTURES:
        raise ArtifactError("invalid target architecture")
    inventory: list[dict[str, object]] = []
    for relative, path in _bundle_files(app):
        description = _run_tool(file_tool, ["-b", str(path)], "file")
        if b"Mach-O" not in description:
            continue
        try:
            architecture_text = _run_tool(
                lipo_tool, ["-archs", str(path)], "lipo",
            ).decode("ascii")
        except UnicodeDecodeError as error:
            raise ArtifactError(
                f"invalid Mach-O architecture list for {relative}"
            ) from error
        architectures = sorted(set(architecture_text.split()))
        if not architectures or any(not ARCHITECTURE.fullmatch(item) for item in architectures):
            raise ArtifactError(f"invalid Mach-O architecture list for {relative}")
        if target_arch not in architectures:
            raise ArtifactError(f"Mach-O bundle member lacks {target_arch}: {relative}")
        inventory.append({
            "path": relative,
            "sha256": _sha256(path),
            "architectures": architectures,
        })
    if not inventory:
        raise ArtifactError("application bundle contains no Mach-O images")
    return inventory


def _application_manifest(
        app: Path, metadata: dict[str, object], *, file_tool: Path, lipo_tool: Path,
) -> dict[str, object]:
    validated = _validated_metadata(metadata)
    main = app / MAIN_EXECUTABLE
    if not main.is_file() or main.is_symlink():
        raise ArtifactError("main application executable is missing or unsafe")
    target_arch = str(validated["build"]["target_arch"])
    inventory = inspect_mach_o_bundle(
        app, target_arch, file_tool=file_tool, lipo_tool=lipo_tool,
    )
    by_path = {str(item["path"]): item for item in inventory}
    if MAIN_EXECUTABLE not in by_path:
        raise ArtifactError("main application executable is not Mach-O")
    main_sha = _sha256(main)
    if by_path[MAIN_EXECUTABLE]["sha256"] != main_sha:
        raise ArtifactError("main executable digest is inconsistent")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "provenance": validated["provenance"],
        "build": validated["build"],
        "application": {
            "bundle_name": app.name,
            "main_executable": MAIN_EXECUTABLE,
            "main_sha256": main_sha,
            "mach_o": inventory,
        },
    }


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or path.is_dir():
            raise ArtifactError("manifest path is unsafe")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent,
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(payload, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except ArtifactError:
        raise
    except (OSError, TypeError) as error:
        raise ArtifactError("could not write application manifest") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def package_application(
        app: Path, manifest_path: Path, metadata: dict[str, object], *,
        file_tool: Path = Path("/usr/bin/file"), lipo_tool: Path = Path("/usr/bin/lipo"),
) -> dict[str, object]:
    """Inspect a bundle and atomically write its strict provenance manifest."""
    manifest = _application_manifest(
        app, metadata, file_tool=file_tool, lipo_tool=lipo_tool,
    )
    _atomic_json(manifest_path, manifest)
    return manifest


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactError("manifest contains duplicate JSON fields")
        result[key] = value
    return result


def _load_manifest(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ArtifactError("manifest is missing or unsafe")
    try:
        if path.stat().st_size > MANIFEST_MAX_BYTES:
            raise ArtifactError("manifest exceeds the size limit")
        payload = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
        )
    except ArtifactError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArtifactError("manifest is unreadable") from error
    if not isinstance(payload, dict):
        raise ArtifactError("manifest root must be an object")
    return payload


def _validate_manifest_schema(payload: dict[str, object]) -> dict[str, object]:
    schema_version = payload.get("schema_version")
    if (
        set(payload) != ROOT_FIELDS
        or isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise ArtifactError("manifest root fields do not match schema 1")
    if payload.get("kind") != KIND:
        raise ArtifactError("manifest kind mismatch")
    metadata = _validated_metadata({
        "provenance": payload.get("provenance"),
        "build": payload.get("build"),
    })
    application = payload.get("application")
    if not isinstance(application, dict) or set(application) != APPLICATION_FIELDS:
        raise ArtifactError("application fields do not match schema 1")
    if not isinstance(application.get("bundle_name"), str) or not application["bundle_name"].endswith(".app"):
        raise ArtifactError("invalid bundle name")
    if application.get("main_executable") != MAIN_EXECUTABLE:
        raise ArtifactError("main executable path mismatch")
    main_sha = application.get("main_sha256")
    if not isinstance(main_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", main_sha):
        raise ArtifactError("invalid main executable digest")
    entries = application.get("mach_o")
    if not isinstance(entries, list) or not entries:
        raise ArtifactError("Mach-O inventory is empty")
    previous = ""
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != MACH_O_FIELDS:
            raise ArtifactError("Mach-O inventory fields do not match schema 1")
        member = entry.get("path")
        digest = entry.get("sha256")
        architectures = entry.get("architectures")
        if (
            not isinstance(member, str) or not member or member.startswith("/")
            or any(part in ("", ".", "..") for part in member.split("/"))
            or any(ord(character) < 32 for character in member)
        ):
            raise ArtifactError("invalid Mach-O inventory path")
        if member in seen or member < previous:
            raise ArtifactError("Mach-O inventory is duplicated or unsorted")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ArtifactError("invalid Mach-O inventory digest")
        if (
            not isinstance(architectures, list) or not architectures
            or any(not isinstance(item, str) or not ARCHITECTURE.fullmatch(item) for item in architectures)
            or architectures != sorted(set(architectures))
        ):
            raise ArtifactError("invalid Mach-O inventory architectures")
        if metadata["build"]["target_arch"] not in architectures:
            raise ArtifactError("manifest contains an incompatible Mach-O image")
        seen.add(member)
        previous = member
    if MAIN_EXECUTABLE not in seen:
        raise ArtifactError("manifest does not cover the main executable")
    return payload


def verify_application(
        app: Path, manifest_path: Path, expected_metadata: dict[str, object], *,
        file_tool: Path = Path("/usr/bin/file"), lipo_tool: Path = Path("/usr/bin/lipo"),
) -> dict[str, object]:
    """Fail closed unless manifest, expected provenance, and bundle all agree."""
    expected = _validated_metadata(expected_metadata)
    recorded = _validate_manifest_schema(_load_manifest(manifest_path))
    if recorded["provenance"] != expected["provenance"]:
        raise ArtifactError("application provenance mismatch")
    if recorded["build"] != expected["build"]:
        raise ArtifactError("application build metadata mismatch")
    current = _application_manifest(
        app, expected, file_tool=file_tool, lipo_tool=lipo_tool,
    )
    if recorded["application"] != current["application"]:
        raise ArtifactError("application bundle does not match its manifest")
    return recorded


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", type=int, required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--target-arch", choices=TARGET_ARCHITECTURES, required=True)
    parser.add_argument("--xcode-version", required=True)
    parser.add_argument("--xcode-build", required=True)
    parser.add_argument("--sdk-version", required=True)
    parser.add_argument("--build-type", required=True)
    parser.add_argument("--deployment-target", required=True)
    parser.add_argument("--file-tool", type=Path, default=Path("/usr/bin/file"))
    parser.add_argument("--lipo-tool", type=Path, default=Path("/usr/bin/lipo"))


def _metadata_from_arguments(arguments: argparse.Namespace) -> dict[str, object]:
    return metadata_from_values(
        repository=arguments.repository,
        repository_id=arguments.repository_id,
        workflow=arguments.workflow,
        ref=arguments.ref,
        sha=arguments.sha,
        run_id=arguments.run_id,
        run_attempt=arguments.run_attempt,
        target_arch=arguments.target_arch,
        xcode_version=arguments.xcode_version,
        xcode_build=arguments.xcode_build,
        sdk_version=arguments.sdk_version,
        build_type=arguments.build_type,
        deployment_target=arguments.deployment_target,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("package", "verify"):
        _add_common_arguments(subparsers.add_parser(name))
    arguments = parser.parse_args()
    try:
        metadata = _metadata_from_arguments(arguments)
        if arguments.command == "package":
            manifest = package_application(
                arguments.app, arguments.manifest, metadata,
                file_tool=arguments.file_tool, lipo_tool=arguments.lipo_tool,
            )
        else:
            manifest = verify_application(
                arguments.app, arguments.manifest, metadata,
                file_tool=arguments.file_tool, lipo_tool=arguments.lipo_tool,
            )
    except ArtifactError as error:
        print(f"application artifact error: {error}", file=sys.stderr, flush=True)
        return 1
    print(json.dumps({
        "kind": KIND,
        "mach_o_count": len(manifest["application"]["mach_o"]),
        "mode": arguments.command,
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
