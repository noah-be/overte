#!/usr/bin/env python3
"""Dispatch or fetch one exact Personal-Team kit run without a latest fallback."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import create_preinstalled_attestation as CONTRACT
import sync_fedora_artifacts as SYNC


MAX_ARCHIVE_BYTES = 5 * 1024 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
MAX_RATIO = 100
EXPECTED_NAMES = {
    "Overte-PersonalTeam-E2E-unsigned.ipa": 4 * 1024 * 1024 * 1024,
    "WebDriverAgentRunner-16.8.0-PersonalTeam-unsigned.ipa": 4 * 1024 * 1024 * 1024,
    "personal-team-e2e-kit.json": 1024 * 1024,
}
DISPATCH_PATTERNS = {
    "personal_team_e2e_kit": r"true",
    "qt_host_cache_key": r"overte-qt-host-v2-[A-Za-z0-9._-]{1,190}-contract-[0-9a-f]{64}",
    "qt_ios_cache_key": r"overte-qt-ios-v2-[A-Za-z0-9._-]{1,190}-contract-[0-9a-f]{64}",
    "qt_host_artifact_prefix": r"overte-qt-host-checkpoint-v1-[0-9a-f]{32}",
    "qt_ios_artifact_prefix": r"overte-qt-ios-checkpoint-v1-[0-9a-f]{32}",
}


def fail(message: str) -> "NoReturn":
    raise SYNC.HandoffError(message)


def api_json(url: str, token: str, *, opener=None) -> dict:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        fail("public kit API URL is outside GitHub")
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": SYNC.API_VERSION,
        "User-Agent": "overte-fedora-ios-personal-team-kit/1",
    })
    try:
        with (opener or urllib.request.build_opener(SYNC.SafeRedirectHandler())).open(
                request, timeout=60) as response:
            payload = response.read(4 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        fail(f"public GitHub API request failed with HTTP {error.code}")
    except urllib.error.URLError as error:
        fail(f"public GitHub API request failed: {type(error.reason).__name__}")
    if len(payload) > 4 * 1024 * 1024:
        fail("public GitHub API response exceeded its safety limit")
    try:
        value = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError):
        fail("public GitHub API response is invalid")
    if not isinstance(value, dict):
        fail("public GitHub API response is not an object")
    return value


def dispatch_inputs(arguments: argparse.Namespace) -> dict[str, str]:
    values = {
        "personal_team_e2e_kit": "true",
        "qt_host_cache_key": arguments.qt_host_cache_key,
        "qt_ios_cache_key": arguments.qt_ios_cache_key,
        "qt_host_artifact_prefix": arguments.qt_host_artifact_prefix,
        "qt_ios_artifact_prefix": arguments.qt_ios_artifact_prefix,
    }
    for name, pattern in DISPATCH_PATTERNS.items():
        value = values[name]
        if not isinstance(value, str) or not SYNC.re.fullmatch(pattern, value):
            fail(f"Personal-Team dispatch input {name} is invalid")
    return values


def select_run(arguments: argparse.Namespace, token: str) -> dict:
    explicit = arguments.run_id is not None or arguments.run_attempt is not None
    if explicit:
        if (not isinstance(arguments.run_id, int) or arguments.run_id <= 0
                or not isinstance(arguments.run_attempt, int) or arguments.run_attempt <= 0):
            fail("explicit run ID and positive run attempt must be supplied together")
        base = f"https://api.github.com/repos/{arguments.repository}"
        return SYNC.verify_run(
            api_json(f"{base}/actions/runs/{arguments.run_id}", token), arguments.run_id,
            expected_attempt=arguments.run_attempt, require_complete=True,
        )

    api = SYNC.GitHubApi(arguments.repository, token)
    run_id = api.dispatch(dispatch_inputs(arguments))
    print(f"Personal-Team kit run {run_id} attempt 1 selected; waiting.")
    return SYNC.wait_for_run(
        api, run_id, 1, arguments.timeout_seconds, arguments.poll_seconds,
    )


def select_artifact(payload: dict, run: dict) -> dict:
    artifacts = payload.get("artifacts")
    expected_name = f"ios-personal-team-e2e-kit-v1-{run['id']}-{run['run_attempt']}"
    if (not isinstance(artifacts, list) or payload.get("total_count") != len(artifacts)):
        fail("public kit artifact list is incomplete")
    matches = [item for item in artifacts if isinstance(item, dict)
               and item.get("name") == expected_name]
    if len(matches) != 1:
        fail("selected workflow attempt has no unique Personal-Team kit")
    item = matches[0]
    workflow_run = item.get("workflow_run")
    if (item.get("expired") is not False or not isinstance(item.get("id"), int)
            or not isinstance(item.get("digest"), str)
            or not SYNC.re.fullmatch(r"sha256:[0-9a-f]{64}", item["digest"])
            or item.get("archive_download_url") !=
            f"https://api.github.com/repos/{SYNC.DEFAULT_REPOSITORY}/actions/artifacts/"
            f"{item.get('id')}/zip"
            or not isinstance(workflow_run, dict) or workflow_run.get("id") != run["id"]
            or workflow_run.get("repository_id") != run["repository"]["id"]
            or workflow_run.get("head_repository_id") != run["repository"]["id"]
            or workflow_run.get("head_branch") != SYNC.PROTECTED_REF
            or workflow_run.get("head_sha") != run["head_sha"]):
        fail("public kit artifact provenance is invalid")
    return item


def download(url: str, destination: Path, token: str, *, opener=None) -> None:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": SYNC.API_VERSION,
        "User-Agent": "overte-fedora-ios-personal-team-kit/1",
    })
    try:
        with (opener or urllib.request.build_opener(SYNC.SafeRedirectHandler())).open(
                request, timeout=120) as response, destination.open("xb") as output:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > MAX_ARCHIVE_BYTES:
                    fail("public kit archive exceeded its download limit")
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def extract(archive_path: Path, destination: Path) -> None:
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile):
        fail("public kit artifact is not a valid ZIP")
    with archive:
        entries = archive.infolist()
        if len(entries) != 3 or {entry.filename for entry in entries} != set(EXPECTED_NAMES):
            fail("public kit artifact does not contain its exact three files")
        total = 0
        for entry in entries:
            path = PurePosixPath(entry.filename)
            mode = (entry.external_attr >> 16) & 0o170000
            limit = EXPECTED_NAMES[entry.filename]
            if (path.is_absolute() or len(path.parts) != 1 or "\\" in entry.filename
                    or entry.is_dir() or entry.flag_bits & 1
                    or mode not in {0, stat.S_IFREG}
                    or not 0 < entry.file_size <= limit
                    or entry.compress_size <= 0
                    or entry.file_size > entry.compress_size * MAX_RATIO):
                fail("public kit ZIP metadata violates its extraction limits")
            total += entry.file_size
        if total > MAX_TOTAL_BYTES:
            fail("public kit ZIP expands beyond its cumulative limit")
        destination.mkdir(mode=0o755)
        try:
            for entry in entries:
                target = destination / entry.filename
                copied = 0
                with archive.open(entry) as source, target.open("xb") as output:
                    while block := source.read(
                            min(1024 * 1024, EXPECTED_NAMES[entry.filename] - copied + 1)):
                        copied += len(block)
                        if copied > EXPECTED_NAMES[entry.filename]:
                            fail("public kit member exceeded its extraction limit")
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
                if copied != entry.file_size:
                    fail("public kit member differs from ZIP metadata")
                target.chmod(0o644)
        except BaseException:
            shutil.rmtree(destination, ignore_errors=True)
            raise


def run(arguments: argparse.Namespace) -> int:
    if arguments.repository != SYNC.DEFAULT_REPOSITORY:
        fail("public kit repository must be the protected Overte producer")
    if (not arguments.destination.is_absolute()
            or SYNC.inside_repository(arguments.destination)
            or SYNC.has_symlink_component(arguments.destination)
            or arguments.destination.exists()):
        fail("public kit selection/destination is unsafe")
    token = os.environ.get("OVERTE_GITHUB_TOKEN", "")
    if not token or any(character in token for character in "\r\n"):
        fail("OVERTE_GITHUB_TOKEN is required for the selected Actions workflow")
    base = f"https://api.github.com/repos/{arguments.repository}"
    run = select_run(arguments, token)
    artifact = select_artifact(
        api_json(
            f"{base}/actions/runs/{run['id']}/artifacts?per_page=100", token
        ), run
    )
    parent = arguments.destination.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    temporary = Path(tempfile.mkdtemp(prefix=".personal-kit-", dir=parent))
    archive = temporary / "artifact.zip"
    output = temporary / "output"
    try:
        download(artifact["archive_download_url"], archive, token)
        if SYNC.sha256_file(archive) != artifact["digest"].removeprefix("sha256:"):
            fail("public kit artifact failed its GitHub archive digest")
        extract(archive, output)
        archive.unlink()
        manifest = CONTRACT.validate_kit(
            output / "personal-team-e2e-kit.json", private=False
        )
        if (manifest["sourceRevision"] != run["head_sha"]
                or manifest["provenance"] != {
                    "repository": arguments.repository,
                    "repositoryId": run["repository"]["id"],
                    "workflow": ".github/workflows/ios-bootstrap.yml",
                    "reusableWorkflow": ".github/workflows/ios-personal-team-e2e-kit.yml",
                    "ref": "refs/heads/apple-ios", "runId": run["id"],
                    "runAttempt": run["run_attempt"],
                }):
            fail("public kit manifest does not match the selected workflow attempt")
        for role, name in {
            "overte": "Overte-PersonalTeam-E2E-unsigned.ipa",
            "webDriverAgent": "WebDriverAgentRunner-16.8.0-PersonalTeam-unsigned.ipa",
        }.items():
            path = output / name
            metadata = manifest["artifacts"][role]
            if path.stat().st_size != metadata["size"] or SYNC.sha256_file(path) != metadata["sha256"]:
                fail("public kit file differs from its exact manifest hash")
        output.replace(arguments.destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        if arguments.destination.exists():
            shutil.rmtree(arguments.destination, ignore_errors=True)
        raise
    shutil.rmtree(temporary, ignore_errors=True)
    print("PASS: explicit public Personal-Team kit workflow attempt verified")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=SYNC.DEFAULT_REPOSITORY)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--run-attempt", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=8 * 60 * 60)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--qt-host-cache-key", default="")
    parser.add_argument("--qt-ios-cache-key", default="")
    parser.add_argument("--qt-host-artifact-prefix", default="")
    parser.add_argument("--qt-ios-artifact-prefix", default="")
    parser.add_argument("--destination", type=Path, required=True)
    try:
        arguments = parser.parse_args()
        if arguments.timeout_seconds <= 0 or not 1 <= arguments.poll_seconds <= 300:
            fail("timeout and polling interval must be positive and bounded")
        return run(arguments)
    except (SYNC.HandoffError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
