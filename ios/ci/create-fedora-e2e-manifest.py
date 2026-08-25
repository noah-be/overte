#!/usr/bin/env python3
"""Verify a signed IPA and emit the privacy-minimal Fedora E2E artifact contract."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import plistlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath


CONTRACT = "overte-ios-fedora-e2e-artifact-v1"
XCUITEST_DRIVER = "12.8.0"
WEBDRIVER_AGENT = "16.8.0"
REVISION = re.compile(r"[0-9a-f]{40}")
BUNDLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*(?:[.][A-Za-z0-9][A-Za-z0-9-]*)+")
TEAM_ID = re.compile(r"[A-Z0-9]{10}")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,191}[.]ipa")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], description: str) -> bytes:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode:
        raise ValueError(f"{description} failed")
    return completed.stdout


def validate_archive(artifact: Path, expected_root: str, app: Path) -> None:
    with zipfile.ZipFile(artifact) as archive:
        names: set[str] = set()
        app_roots: set[str] = set()
        for entry in archive.infolist():
            raw = entry.filename[:-1] if entry.filename.endswith("/") else entry.filename
            if not raw:
                continue
            path = PurePosixPath(raw)
            if path.is_absolute() or ".." in path.parts or "\\" in raw or "\0" in raw:
                raise ValueError("IPA contains an unsafe archive path")
            normalized = str(path)
            if normalized in names:
                raise ValueError("IPA contains duplicate archive entries")
            names.add(normalized)
            if (
                normalized != "Payload"
                and normalized != expected_root
                and not normalized.startswith(expected_root + "/")
            ):
                if normalized != "__MACOSX" and not normalized.startswith("__MACOSX/"):
                    raise ValueError("IPA contains content outside its application root")
            for index, part in enumerate(path.parts):
                if part.endswith(".app"):
                    app_roots.add("/".join(path.parts[: index + 1]))
        if app_roots != {expected_root}:
            raise ValueError(f"IPA must contain exactly {expected_root}")
        for relative in ("Info.plist", "embedded.mobileprovision"):
            member = f"{expected_root}/{relative}"
            if member not in names or archive.read(member) != (app / relative).read_bytes():
                raise ValueError(f"final IPA and audited app disagree on {relative}")
        nested = app / "PlugIns/WebDriverAgentRunner.xctest"
        if nested.is_dir() and not nested.is_symlink():
            for relative in ("Info.plist", "embedded.mobileprovision"):
                member = f"{expected_root}/PlugIns/WebDriverAgentRunner.xctest/{relative}"
                if member not in names or archive.read(member) != (nested / relative).read_bytes():
                    raise ValueError(f"final IPA and audited WDA XCTest disagree on {relative}")


def profile_authorizes_application_id(
    profile_identifier: object, application_identifier: str, expected_team_id: str
) -> bool:
    if profile_identifier == application_identifier:
        return True
    if not isinstance(profile_identifier, str):
        return False
    if profile_identifier.count("*") != 1 or not profile_identifier.endswith("*"):
        return False
    prefix = profile_identifier[:-1]
    team_prefix = f"{expected_team_id}."
    if prefix == team_prefix or not prefix.startswith(team_prefix):
        return False
    return application_identifier.startswith(prefix) and len(application_identifier) > len(prefix)


def validate_signing(
    profile: object,
    entitlements: object,
    info: object,
    expected_bundle_id: str,
    expected_team_id: str,
    now: dt.datetime | None = None,
) -> tuple[str, str]:
    if not all(isinstance(value, dict) for value in (profile, entitlements, info)):
        raise ValueError("signing metadata root is invalid")
    assert isinstance(profile, dict)
    assert isinstance(entitlements, dict)
    assert isinstance(info, dict)
    if BUNDLE_ID.fullmatch(expected_bundle_id) is None:
        raise ValueError("expected bundle identifier is invalid")
    if TEAM_ID.fullmatch(expected_team_id) is None:
        raise ValueError("expected team identifier is invalid")
    if info.get("CFBundleIdentifier") != expected_bundle_id:
        raise ValueError("signed bundle identifier mismatch")
    teams = profile.get("TeamIdentifier")
    profile_entitlements = profile.get("Entitlements")
    if teams != [expected_team_id] or not isinstance(profile_entitlements, dict):
        raise ValueError("provisioning profile team metadata mismatch")
    application_identifier = f"{expected_team_id}.{expected_bundle_id}"
    if entitlements.get("application-identifier") != application_identifier:
        raise ValueError("signature application identifier mismatch")
    if entitlements.get("com.apple.developer.team-identifier") != expected_team_id:
        raise ValueError("signature team identifier mismatch")
    profile_identifier = profile_entitlements.get("application-identifier")
    if not profile_authorizes_application_id(
        profile_identifier, application_identifier, expected_team_id
    ):
        raise ValueError("profile application identifier does not authorize the bundle")
    expiration = profile.get("ExpirationDate")
    if not isinstance(expiration, dt.datetime):
        raise ValueError("provisioning profile has no expiration date")
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=dt.timezone.utc)
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    if expiration <= current:
        raise ValueError("provisioning profile is expired")
    return application_identifier, expiration.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def validate_signed_bundle(
    app: Path,
    expected_bundle_id: str,
    expected_team_id: str,
    *,
    deep: bool = False,
    command_runner=run,
) -> tuple[dict, str, str]:
    if app.is_symlink() or not app.is_dir():
        raise ValueError("signed application bundle is invalid")
    profile_path = app / "embedded.mobileprovision"
    if profile_path.is_symlink() or not profile_path.is_file():
        raise ValueError("signed application bundle has no provisioning profile")
    verify = ["codesign", "--verify"]
    if deep:
        verify.append("--deep")
    verify.extend(("--strict", str(app)))
    command_runner(verify, "code signature verification")
    profile = plistlib.loads(
        command_runner(["security", "cms", "-D", "-i", str(profile_path)], "profile decoding")
    )
    entitlements = plistlib.loads(
        command_runner(["codesign", "-d", "--entitlements", ":-", str(app)], "entitlement extraction")
    )
    with (app / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    application_identifier, expiration = validate_signing(
        profile,
        entitlements,
        info,
        expected_bundle_id,
        expected_team_id,
    )
    return info, application_identifier, expiration


def validate_wda_xctest(
    runner_app: Path,
    expected_runner_bundle_id: str,
    expected_team_id: str,
    *,
    command_runner=run,
) -> None:
    suffix = ".xctrunner"
    if not expected_runner_bundle_id.endswith(suffix):
        raise ValueError("WebDriverAgent runner bundle identifier must end in .xctrunner")
    expected_test_bundle_id = expected_runner_bundle_id[: -len(suffix)]
    xctest = runner_app / "PlugIns/WebDriverAgentRunner.xctest"
    _info, application_identifier, _expiration = validate_signed_bundle(
        xctest,
        expected_test_bundle_id,
        expected_team_id,
        command_runner=command_runner,
    )
    expected_application_identifier = f"{expected_team_id}.{expected_test_bundle_id}"
    if application_identifier != expected_application_identifier:
        raise ValueError("WebDriverAgent XCTest application identifier mismatch")


def build_manifest(
    *,
    kind: str,
    source_revision: str,
    artifact_name: str,
    artifact_sha256: str,
    artifact_size: int,
    bundle_id: str,
    team_id: str,
    application_identifier: str,
    profile_expiration: str,
) -> dict:
    payload = {
        "schemaVersion": 1,
        "contract": CONTRACT,
        "kind": kind,
        "sourceRevision": source_revision,
        "artifact": {
            "name": artifact_name,
            "sha256": artifact_sha256,
            "size": artifact_size,
        },
        "bundle": {"id": bundle_id},
        "signing": {
            "signed": True,
            "teamIdentifier": team_id,
            "applicationIdentifier": application_identifier,
            "profileExpiration": profile_expiration,
        },
    }
    if kind == "overte-app":
        payload["testBuildContractVersion"] = 1
    else:
        payload["toolchain"] = {
            "xcuitestDriver": XCUITEST_DRIVER,
            "webdriverAgent": WEBDRIVER_AGENT,
        }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("overte-app", "webdriveragent"), required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--expected-bundle-id", required=True)
    parser.add_argument("--expected-team-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if REVISION.fullmatch(args.source_revision) is None:
            raise ValueError("source revision must be a lowercase 40-character Git SHA")
        if SAFE_NAME.fullmatch(args.artifact.name) is None:
            raise ValueError("artifact name is unsafe")
        if args.app.is_symlink() or not args.app.is_dir():
            raise ValueError("audited application bundle is invalid")
        if not args.artifact.is_file() or args.artifact.stat().st_size <= 0:
            raise ValueError("signed IPA is missing or empty")
        expected_app_name = "Overte.app" if args.kind == "overte-app" else "WebDriverAgentRunner-Runner.app"
        if args.kind == "webdriveragent" and not args.expected_bundle_id.endswith(".xctrunner"):
            raise ValueError("WebDriverAgent runner bundle identifier must end in .xctrunner")
        if args.app.name != expected_app_name:
            raise ValueError("application root does not match artifact kind")
        expected_root = f"Payload/{expected_app_name}"
        validate_archive(args.artifact, expected_root, args.app)
        info, application_identifier, expiration = validate_signed_bundle(
            args.app,
            args.expected_bundle_id,
            args.expected_team_id,
            deep=True,
        )
        if args.kind == "webdriveragent":
            validate_wda_xctest(
                args.app,
                args.expected_bundle_id,
                args.expected_team_id,
            )
        if args.kind == "overte-app":
            if info.get("OverteE2ETestBuildContractVersion") != 1 or info.get("UIFileSharingEnabled") is not True:
                raise ValueError("Overte IPA does not contain the E2E test-build contract")
        payload = build_manifest(
            kind=args.kind,
            source_revision=args.source_revision,
            artifact_name=args.artifact.name,
            artifact_sha256=sha256_file(args.artifact),
            artifact_size=args.artifact.stat().st_size,
            bundle_id=args.expected_bundle_id,
            team_id=args.expected_team_id,
            application_identifier=application_identifier,
            profile_expiration=expiration,
        )
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, zipfile.BadZipFile, plistlib.InvalidFileException) as error:
        print(f"error: signed Fedora E2E artifact rejected: {error}", file=sys.stderr)
        return 1
    print(f"PASS signed {args.kind} Fedora E2E artifact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
