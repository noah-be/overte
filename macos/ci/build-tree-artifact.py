#!/usr/bin/env python3
"""Persist a resumable macOS Ninja tree outside the evictable Actions cache.

The archive format and remote transport deliberately reuse the hardened Conan
checkpoint implementation.  This adapter changes the protected root and
format identity, rejects archives without a complete Ninja graph, and omits
reproducible application/test products.  Object files, generated sources,
Ninja dependency state, and link inputs remain recoverable.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile


CORE_PATH = Path(__file__).with_name("conan-checkpoint.py")
SPEC = importlib.util.spec_from_file_location("overte_artifact_checkpoint_core", CORE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - installation invariant
    raise RuntimeError("checkpoint archive core is unavailable")
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)

# These globals are intentionally format parameters in the shared archive
# core.  A build-tree artifact can therefore never be accepted as a Conan
# artifact (or vice versa), even when compatibility keys happen to match.
core.KIND = "overte-macos-build-tree-checkpoint"
core.ARCHIVE_PREFIX = "build-tree.part-"
core.ROOTS = ("build",)

COMPLETE_KEY = ".overte-macos-complete-key"
REQUIRED_MEMBERS = {
    "build/CMakeCache.txt",
    "build/build.ninja",
    "build/.overte-ninja-checkpoint.json",
    f"build/{COMPLETE_KEY}",
}
SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]{1,240}$")
EPHEMERAL_TOP_LEVEL = {
    "application-archive",
    "application-artifact",
    "macos-online-smoke",
    "macos-performance",
    "macos-profile-performance",
    "macos-smoke",
    "macos-startup-preflight",
}


def excluded_from_resume(path: PurePosixPath) -> bool:
    """Return true only for reproducible products not needed to resume Ninja."""
    parts = path.parts
    if not parts or parts[0] != "build":
        return False
    if any(part.endswith(".app") for part in parts[1:]):
        return True
    return len(parts) > 1 and parts[1] in EPHEMERAL_TOP_LEVEL


def safe_root(root: Path) -> Path:
    resolved = root.resolve()
    if resolved == Path(resolved.anchor):
        raise core.CheckpointError("refusing to manage a build tree at a filesystem root")
    return resolved


def installed_complete_key(root: Path) -> str:
    marker = root / "build" / COMPLETE_KEY
    try:
        value = marker.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise core.CheckpointError("build-tree checkpoint has no readable complete key") from error
    if not SAFE_KEY.fullmatch(value):
        raise core.CheckpointError("build-tree checkpoint has an invalid complete key")
    return value


def validate_build_archive(
    paths: list[Path],
    sizes: list[int],
    members: list[core.tarfile.TarInfo],
    expected_complete_key: str | None = None,
) -> None:
    member_names = {member.name for member in members if member.isfile()}
    if not REQUIRED_MEMBERS.issubset(member_names):
        raise core.CheckpointError("build-tree checkpoint is missing required Ninja state")
    if any(excluded_from_resume(PurePosixPath(member.name)) for member in members):
        raise core.CheckpointError("build-tree checkpoint contains an ephemeral product")

    # Read just the tiny marker from the same already validated archive pass.
    marker_value: str | None = None
    with core.ChunkReader(paths, sizes) as archive_data, core.tarfile.open(
        fileobj=archive_data, mode="r:"
    ) as archive:
        marker = archive.extractfile(f"build/{COMPLETE_KEY}")
        if marker is not None:
            raw = marker.read(1024)
            if marker.read(1):
                raise core.CheckpointError("build-tree complete key is too large")
            try:
                marker_value = raw.decode("utf-8").strip()
            except UnicodeError as error:
                raise core.CheckpointError("build-tree complete key is unreadable") from error
    if marker_value is None or not SAFE_KEY.fullmatch(marker_value):
        raise core.CheckpointError("build-tree checkpoint has an invalid complete key")
    if expected_complete_key is not None and marker_value != expected_complete_key:
        raise core.CheckpointError("build-tree checkpoint complete key mismatch")


def validate_build_checkpoint(
    checkpoint_dir: Path,
    key: str,
    repository_id: int,
    branch: str,
    expected_complete_key: str | None = None,
) -> dict[str, object]:
    return core.validate_checkpoint(
        checkpoint_dir,
        key,
        repository_id,
        branch,
        archive_validator=lambda paths, sizes, members: validate_build_archive(
            paths, sizes, members, expected_complete_key
        ),
    )


def create_checkpoint(
    root: Path,
    output_dir: Path,
    key: str,
    complete_key: str,
    repository_id: int,
    branch: str,
) -> None:
    root = safe_root(root)
    if installed_complete_key(root) != complete_key:
        raise core.CheckpointError("installed build tree is not the requested complete generation")
    core.create_checkpoint(
        root,
        output_dir,
        key,
        repository_id,
        branch,
        exclude=excluded_from_resume,
        archive_validator=lambda paths, sizes, members: validate_build_archive(
            paths, sizes, members, complete_key
        ),
    )
    print("build-tree-artifact phase=create status=complete", flush=True)


def restore_checkpoint(
    checkpoint_dir: Path,
    root: Path,
    key: str,
    repository_id: int,
    branch: str,
) -> None:
    root = safe_root(root)
    core.restore_checkpoint(
        checkpoint_dir,
        root,
        key,
        repository_id,
        branch,
        archive_validator=validate_build_archive,
    )
    installed_complete_key(root)
    print("build-tree-artifact phase=restore status=complete", flush=True)


def restore_latest_remote(
    repository: str,
    artifact_name: str,
    token: str,
    api_base: str,
    key: str,
    repository_id: int,
    branch: str,
    root: Path,
    github_output: Path | None,
) -> bool:
    root = safe_root(root)
    candidates = core.list_candidates(
        repository, artifact_name, repository_id, branch, token, api_base
    )
    for candidate in candidates:
        artifact_id = int(candidate["id"])
        temporary = Path(tempfile.mkdtemp(prefix="build-tree-artifact-download-"))
        try:
            artifact_zip = temporary / "artifact.zip"
            with core.heartbeat("build-tree-download", 30.0):
                core._download_artifact(
                    repository,
                    artifact_id,
                    token,
                    api_base,
                    artifact_zip,
                    core.DEFAULT_MAX_ARCHIVE_BYTES + core.MAX_MANIFEST_BYTES + 1024 * 1024,
                )
            checkpoint_dir = temporary / "checkpoint"
            core._unpack_artifact_zip(
                artifact_zip,
                checkpoint_dir,
                key,
                repository_id,
                branch,
                core.DEFAULT_MAX_ARCHIVE_BYTES,
            )
            restore_checkpoint(checkpoint_dir, root, key, repository_id, branch)
            core._write_outputs(
                github_output, {"restored": "true", "artifact_id": str(artifact_id)}
            )
            return True
        except core.RemoteError:
            raise
        except core.CheckpointError:
            print(
                "build-tree-artifact phase=restore status=rejected "
                f"artifact_id={artifact_id}",
                file=sys.stderr,
                flush=True,
            )
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
    core._write_outputs(github_output, {"restored": "false", "artifact_id": ""})
    print(
        "build-tree-artifact phase=restore status=unavailable; using fast-cache state",
        flush=True,
    )
    return False


def verify_remote_contents(
    repository: str,
    artifact_id: int,
    token: str,
    api_base: str,
    key: str,
    repository_id: int,
    branch: str,
    complete_key: str,
) -> None:
    temporary = Path(tempfile.mkdtemp(prefix="build-tree-artifact-verify-"))
    try:
        artifact_zip = temporary / "artifact.zip"
        core._download_artifact(
            repository,
            artifact_id,
            token,
            api_base,
            artifact_zip,
            core.DEFAULT_MAX_ARCHIVE_BYTES + core.MAX_MANIFEST_BYTES + 1024 * 1024,
        )
        checkpoint_dir = temporary / "checkpoint"
        core._unpack_artifact_zip(
            artifact_zip,
            checkpoint_dir,
            key,
            repository_id,
            branch,
            core.DEFAULT_MAX_ARCHIVE_BYTES,
        )
        validate_build_checkpoint(
            checkpoint_dir,
            key,
            repository_id,
            branch,
            expected_complete_key=complete_key,
        )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def artifact_prune_plan(
    candidates: list[dict[str, object]], active_artifact_id: int, retain_previous: int
) -> list[int]:
    if active_artifact_id <= 0 or retain_previous < 0:
        raise core.CheckpointError("invalid build-tree artifact retention policy")
    ids = sorted((
        int(candidate["id"])
        for candidate in candidates
        if isinstance(candidate.get("id"), int) and int(candidate["id"]) > 0
    ), reverse=True)
    if len(ids) != len(set(ids)):
        raise core.CheckpointError("duplicate build-tree artifact identity")
    if active_artifact_id not in ids:
        raise core.CheckpointError("verified build-tree artifact is absent from inventory")
    previous = [artifact_id for artifact_id in ids if artifact_id != active_artifact_id]
    keep = {active_artifact_id, *previous[:retain_previous]}
    return sorted(artifact_id for artifact_id in ids if artifact_id not in keep)


def delete_artifact(repository: str, artifact_id: int, token: str, api_base: str) -> None:
    request = core.Request(
        core._api_url(api_base, repository, f"actions/artifacts/{artifact_id}"),
        method="DELETE",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "overte-macos-build-tree-checkpoint",
        },
    )
    try:
        with core.urlopen(request, timeout=60) as response:
            if response.status not in (200, 204):
                raise core.RemoteError("build-tree artifact deletion returned an unexpected status")
    except core.HTTPError as error:
        raise core.RemoteError("build-tree artifact deletion failed") from error
    except (OSError, core.URLError) as error:
        raise core.RemoteError("build-tree artifact deletion failed") from error


def prune_remote(
    repository: str,
    artifact_name: str,
    repository_id: int,
    branch: str,
    token: str,
    api_base: str,
    active_artifact_id: int,
    retain_previous: int,
    execute: bool,
) -> list[int]:
    candidates = core.list_candidates(
        repository, artifact_name, repository_id, branch, token, api_base
    )
    delete = artifact_prune_plan(candidates, active_artifact_id, retain_previous)
    if execute:
        for artifact_id in delete:
            delete_artifact(repository, artifact_id, token, api_base)
    print(
        "build-tree-artifact phase=prune "
        f"status={'executed' if execute else 'planned'} entries={len(delete)}",
        flush=True,
    )
    return delete


def add_remote_arguments(
    parser: argparse.ArgumentParser, *, include_key: bool = True
) -> None:
    parser.add_argument("--repository", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--repository-id", type=int, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--api-base", default="https://api.github.com")
    if include_key:
        parser.add_argument("--key", required=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="operation", required=True)

    create = commands.add_parser("create")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--output-dir", type=Path, required=True)
    create.add_argument("--key", required=True)
    create.add_argument("--complete-key", required=True)
    create.add_argument("--repository-id", type=int, required=True)
    create.add_argument("--branch", required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--checkpoint-dir", type=Path, required=True)
    verify.add_argument("--key", required=True)
    verify.add_argument("--complete-key")
    verify.add_argument("--repository-id", type=int, required=True)
    verify.add_argument("--branch", required=True)

    restore = commands.add_parser("restore")
    restore.add_argument("--checkpoint-dir", type=Path, required=True)
    restore.add_argument("--root", type=Path, required=True)
    restore.add_argument("--key", required=True)
    restore.add_argument("--repository-id", type=int, required=True)
    restore.add_argument("--branch", required=True)

    remote_restore = commands.add_parser("restore-remote")
    add_remote_arguments(remote_restore)
    remote_restore.add_argument("--root", type=Path, required=True)
    remote_restore.add_argument("--github-output", type=Path)

    remote_verify = commands.add_parser("verify-remote")
    add_remote_arguments(remote_verify)
    remote_verify.add_argument("--artifact-id", type=int, required=True)
    remote_verify.add_argument("--expected-digest", required=True)
    remote_verify.add_argument("--complete-key", required=True)

    remote_prune = commands.add_parser("prune-remote")
    add_remote_arguments(remote_prune, include_key=False)
    remote_prune.add_argument("--active-artifact-id", type=int, required=True)
    remote_prune.add_argument("--retain-previous", type=int, default=1)
    remote_prune.add_argument("--execute", action="store_true")

    arguments = parser.parse_args()
    try:
        if arguments.operation == "create":
            create_checkpoint(
                arguments.root,
                arguments.output_dir,
                arguments.key,
                arguments.complete_key,
                arguments.repository_id,
                arguments.branch,
            )
        elif arguments.operation == "verify":
            validate_build_checkpoint(
                arguments.checkpoint_dir,
                arguments.key,
                arguments.repository_id,
                arguments.branch,
                expected_complete_key=arguments.complete_key,
            )
            print("build-tree-artifact phase=verify status=complete", flush=True)
        elif arguments.operation == "restore":
            restore_checkpoint(
                arguments.checkpoint_dir,
                arguments.root,
                arguments.key,
                arguments.repository_id,
                arguments.branch,
            )
        elif arguments.operation == "restore-remote":
            restore_latest_remote(
                arguments.repository,
                arguments.artifact_name,
                core._token(arguments.token_env),
                arguments.api_base,
                arguments.key,
                arguments.repository_id,
                arguments.branch,
                arguments.root,
                arguments.github_output,
            )
        elif arguments.operation == "verify-remote":
            complete_key = arguments.complete_key

            def build_tree_verifier(
                repository: str,
                artifact_id: int,
                token: str,
                api_base: str,
                key: str,
                repository_id: int,
                branch: str,
            ) -> None:
                verify_remote_contents(
                    repository,
                    artifact_id,
                    token,
                    api_base,
                    key,
                    repository_id,
                    branch,
                    complete_key,
                )

            core.verify_remote_contents = build_tree_verifier
            core.verify_remote(
                arguments.repository,
                arguments.artifact_id,
                arguments.artifact_name,
                arguments.expected_digest,
                arguments.key,
                arguments.repository_id,
                arguments.branch,
                core._token(arguments.token_env),
                arguments.api_base,
            )
            print("build-tree-artifact phase=verify-upload status=complete", flush=True)
        else:
            prune_remote(
                arguments.repository,
                arguments.artifact_name,
                arguments.repository_id,
                arguments.branch,
                core._token(arguments.token_env),
                arguments.api_base,
                arguments.active_artifact_id,
                arguments.retain_previous,
                arguments.execute,
            )
    except core.CheckpointError as error:
        print(f"build-tree-artifact error: {error}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
