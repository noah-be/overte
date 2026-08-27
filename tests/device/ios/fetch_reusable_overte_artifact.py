#!/usr/bin/env python3
"""Fetch one exact prior unsigned Overte E2E artifact for kit repackaging."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import zipfile

import sync_fedora_artifacts as SYNC


CONTRACT = "overte-ios-reusable-e2e-client-v1"
IPA_RE = re.compile(r"[0-9]{4}-OverteIOSClient-Release-device-unsigned[.]ipa")
MANIFEST_RE = re.compile(r"[0-9]{4}-OverteIOSClient-Release-device-unsigned[.]json")
MAX_ARCHIVE_BYTES = 5 * 1024 * 1024 * 1024
MAX_IPA_BYTES = 4 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_RATIO = 250


def fail(message: str) -> "NoReturn":
    raise SYNC.HandoffError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def select_artifact(api: SYNC.GitHubApi, run: dict) -> dict:
    if run["run_attempt"] != 1:
        fail("legacy reusable Overte artifacts are accepted only from attempt 1")
    run_number = run.get("run_number")
    if not isinstance(run_number, int) or run_number <= 0:
        fail("reusable Overte run number is invalid")
    expected_name = (
        f"{run_number}-overte-ios-integrated-e2e-unsigned-{run['id']}"
    )
    matches = [item for item in api.artifacts(run["id"])
               if item.get("name") == expected_name]
    if len(matches) != 1:
        fail("selected run has no unique reusable unsigned Overte artifact")
    artifact = matches[0]
    workflow_run = artifact.get("workflow_run")
    digest = artifact.get("digest")
    expected_url = (
        f"https://api.github.com/repos/{SYNC.DEFAULT_REPOSITORY}/actions/"
        f"artifacts/{artifact.get('id')}/zip"
    )
    if (
        artifact.get("expired") is not False
        or not isinstance(artifact.get("id"), int)
        or artifact["id"] <= 0
        or not isinstance(artifact.get("size_in_bytes"), int)
        or not 0 < artifact["size_in_bytes"] <= MAX_ARCHIVE_BYTES
        or not isinstance(digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        or artifact.get("archive_download_url") != expected_url
        or not isinstance(workflow_run, dict)
        or workflow_run.get("id") != run["id"]
        or workflow_run.get("repository_id") != run["repository"]["id"]
        or workflow_run.get("head_repository_id") != run["repository"]["id"]
        or workflow_run.get("head_branch") != SYNC.PROTECTED_REF
        or workflow_run.get("head_sha") != run["head_sha"]
        or not isinstance(artifact.get("created_at"), str)
        or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            artifact["created_at"],
        ) is None
    ):
        fail("reusable Overte artifact provenance is invalid")
    return artifact


def extract(archive_path: Path, destination: Path) -> tuple[Path, Path]:
    if (archive_path.is_symlink() or not archive_path.is_file()
            or not 0 < archive_path.stat().st_size <= MAX_ARCHIVE_BYTES):
        fail("reusable Overte Actions archive size is invalid")
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile):
        fail("reusable Overte artifact is not a valid ZIP")
    with archive:
        entries = archive.infolist()
        if len(entries) != 2:
            fail("reusable Overte artifact must contain exactly two files")
        names: set[str] = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            mode = (entry.external_attr >> 16) & 0o170000
            limit = MAX_IPA_BYTES if IPA_RE.fullmatch(entry.filename) else \
                MAX_MANIFEST_BYTES if MANIFEST_RE.fullmatch(entry.filename) else 0
            if (
                not limit
                or path.is_absolute()
                or len(path.parts) != 1
                or "\\" in entry.filename
                or entry.filename in names
                or entry.is_dir()
                or entry.flag_bits & 1
                or mode not in {0, stat.S_IFREG}
                or not 0 < entry.file_size <= limit
                or entry.compress_size <= 0
                or entry.file_size > entry.compress_size * MAX_RATIO
            ):
                fail("reusable Overte artifact contains an unsafe member")
            names.add(entry.filename)
        ipa_names = [name for name in names if IPA_RE.fullmatch(name)]
        manifest_names = [name for name in names if MANIFEST_RE.fullmatch(name)]
        if len(ipa_names) != 1 or len(manifest_names) != 1 \
                or ipa_names[0].removesuffix(".ipa") != \
                manifest_names[0].removesuffix(".json"):
            fail("reusable Overte IPA/manifest pair is inconsistent")
        destination.mkdir(mode=0o700)
        try:
            for entry in entries:
                target = destination / entry.filename
                limit = MAX_IPA_BYTES if entry.filename.endswith(".ipa") \
                    else MAX_MANIFEST_BYTES
                copied = 0
                with archive.open(entry) as source, target.open("xb") as output:
                    while block := source.read(min(1024 * 1024, limit - copied + 1)):
                        copied += len(block)
                        if copied > limit:
                            fail("reusable Overte member exceeded its extraction limit")
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
                if copied != entry.file_size:
                    fail("reusable Overte member differs from ZIP metadata")
                target.chmod(0o600)
        except BaseException:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        return destination / ipa_names[0], destination / manifest_names[0]


def run(arguments: argparse.Namespace) -> dict:
    if arguments.repository != SYNC.DEFAULT_REPOSITORY:
        fail("reusable Overte repository must be the protected producer")
    if arguments.run_attempt != 1:
        fail("legacy reusable Overte artifacts require explicit attempt 1")
    if (not isinstance(arguments.assembly_revision, str)
            or SYNC.REVISION_RE.fullmatch(arguments.assembly_revision) is None):
        fail("reusable Overte assembly revision is invalid")
    if (not arguments.destination.is_absolute()
            or SYNC.has_symlink_component(arguments.destination)
            or arguments.destination.exists()):
        fail("reusable Overte destination is unsafe")
    token = os.environ.get("OVERTE_GITHUB_TOKEN", "")
    api = SYNC.GitHubApi(arguments.repository, token)
    selected_run = SYNC.verify_run(
        api.run(arguments.run_id), arguments.run_id,
        expected_attempt=arguments.run_attempt, require_complete=True,
    )
    comparison = api.request(
        "GET",
        f"{api.base}/compare/{selected_run['head_sha']}...{arguments.assembly_revision}",
    )
    if (comparison.get("status") not in {"ahead", "identical"}
            or not isinstance(comparison.get("merge_base_commit"), dict)
            or comparison["merge_base_commit"].get("sha") != selected_run["head_sha"]):
        fail("reusable Overte revision is not an ancestor of the kit assembly")
    artifact = select_artifact(api, selected_run)
    parent = arguments.destination.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix=".overte-reuse-", dir=parent))
    archive = temporary / "artifact.zip"
    output = temporary / "output"
    try:
        api.download(artifact["archive_download_url"], archive)
        archive_digest = artifact["digest"].removeprefix("sha256:")
        if sha256_file(archive) != archive_digest:
            fail("reusable Overte artifact failed its GitHub archive digest")
        ipa, manifest = extract(archive, output)
        try:
            integrated = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            fail("reusable Overte integrated manifest is invalid")
        if (not isinstance(integrated, dict)
                or integrated.get("sourceRevision") != selected_run["head_sha"]
                or integrated.get("artifact") != ipa.name
                or integrated.get("sha256") != sha256_file(ipa)):
            fail("reusable Overte integrated manifest differs from its source run")
        metadata = {
            "schemaVersion": 1,
            "contract": CONTRACT,
            "assemblyRevision": arguments.assembly_revision,
            "sourceRevision": selected_run["head_sha"],
            "provenance": {
                "repository": arguments.repository,
                "repositoryId": selected_run["repository"]["id"],
                "workflow": ".github/workflows/ios-bootstrap.yml",
                "ref": "refs/heads/apple-ios",
                "runId": selected_run["id"],
                "runAttempt": 1,
                "runNumber": selected_run["run_number"],
                "artifactId": artifact["id"],
                "artifactName": artifact["name"],
                "artifactSize": artifact["size_in_bytes"],
                "artifactCreatedAt": artifact["created_at"],
                "actionsArchiveSha256": archive_digest,
            },
            "artifacts": {
                "overte": {"name": ipa.name, "size": ipa.stat().st_size,
                            "sha256": sha256_file(ipa)},
                "integratedManifest": {
                    "name": manifest.name, "size": manifest.stat().st_size,
                    "sha256": sha256_file(manifest),
                },
            },
        }
        metadata_path = output / "overte-reuse-provenance.json"
        with metadata_path.open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        metadata_path.chmod(0o600)
        archive.unlink()
        output.replace(arguments.destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        if arguments.destination.exists():
            shutil.rmtree(arguments.destination, ignore_errors=True)
        raise
    shutil.rmtree(temporary, ignore_errors=True)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=SYNC.DEFAULT_REPOSITORY)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--assembly-revision", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    try:
        run(parser.parse_args())
        print("PASS: exact reusable unsigned Overte artifact verified")
        return 0
    except (SYNC.HandoffError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
