#!/usr/bin/env python3
"""Lock the protected, privacy-minimal Fedora iOS artifact producer."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import plistlib
import re
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ios-fedora-e2e-producer.yml"
BOOTSTRAP = ROOT / ".github/workflows/ios-bootstrap.yml"


def require(pattern: str, text: str, message: str) -> None:
    if re.search(pattern, text, re.MULTILINE | re.DOTALL) is None:
        raise AssertionError(message)


def reject_direct_shell_inputs(text: str) -> None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "run: |":
            continue
        indentation = len(line) - len(line.lstrip())
        cursor = index + 1
        while cursor < len(lines):
            nested = lines[cursor]
            if nested.strip() and len(nested) - len(nested.lstrip()) <= indentation:
                break
            if "${{ inputs." in nested:
                raise AssertionError("workflow interpolates an input directly into shell")
            cursor += 1


def load_manifest_tool():
    path = ROOT / "ios/ci/create-fedora-e2e-manifest.py"
    spec = importlib.util.spec_from_file_location("fedora_e2e_manifest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_inner_zip_tool():
    path = ROOT / "ios/ci/create-age-inner-zip.py"
    spec = importlib.util.spec_from_file_location("fedora_e2e_inner_zip", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    require(r"^on:\n  workflow_call:", workflow,
            "producer must only be callable through its registered entrypoint")
    if re.search(r"^  (?:workflow_dispatch|push|pull_request|schedule):", workflow, re.MULTILINE):
        raise AssertionError("signed producer must not have a direct or automatic trigger")
    require(r"^  workflow_dispatch:", bootstrap,
            "registered bootstrap entrypoint must remain manually dispatchable")
    require(r"fedora_e2e_producer:[\s\S]*uses: [.]/[.]github/workflows/"
            r"ios-fedora-e2e-producer[.]yml", bootstrap,
            "bootstrap must explicitly select the reusable protected producer")
    require(r"inputs[.]fedora_e2e_producer[\s\S]*inputs[.]integrated != true[\s\S]*"
            r"inputs[.]world_evidence != true", bootstrap,
            "producer dispatch must be exclusive from existing expensive modes")
    reject_direct_shell_inputs(workflow)
    reject_direct_shell_inputs(bootstrap)
    require(r"environment: ios-fedora-e2e-signing", workflow, "signing must use a protected environment")
    require(r"uses: [.]/[.]github/workflows/ios-integrated[.]yml", workflow,
            "producer must reuse the integrated Full Client build")
    require(r"e2e_test_build: true", workflow, "producer must opt into E2E markers")
    require(r'GITHUB_REF" == "refs/heads/apple-ios', workflow, "producer must reject unprotected branches")
    require(r'GITHUB_WORKFLOW_REF" == "[$]GITHUB_REPOSITORY/[.]github/workflows/'
            r'ios-bootstrap[.]yml@refs/heads/apple-ios', workflow,
            "producer must bind provenance to the protected dispatch workflow ref")
    require(r'GITHUB_WORKFLOW_SHA" == "[$]GITHUB_SHA', workflow,
            "producer workflow and source revision must be identical")
    for secret in (
        "IOS_E2E_SIGNING_P12_BASE64",
        "IOS_E2E_SIGNING_P12_PASSWORD",
        "IOS_E2E_APP_PROFILE_BASE64",
        "IOS_E2E_WDA_PROFILE_BASE64",
        "IOS_E2E_TEAM_IDENTIFIER",
        "IOS_E2E_KEYCHAIN_PASSWORD",
        "IOS_E2E_LAB_AGE_RECIPIENT",
    ):
        require(rf"secrets[.]{secret}", workflow, f"missing protected secret gate {secret}")
    require(r"security create-keychain[\s\S]*security import", workflow,
            "credentials must use a temporary keychain")
    require(r"if: always\(\)[\s\S]*security delete-keychain", workflow,
            "temporary keychain cleanup must be unconditional")
    for version in (
        "XCUITEST_DRIVER_VERSION: 12.8.0",
        "WDA_VERSION: 16.8.0",
        "RESIGNER_VERSION: 0.3.1",
        "AGE_VERSION: 1.2.1",
    ):
        assert version in workflow
    assert ('[[ "$("$PRIVATE_ROOT/tools/resigner" --version)" == '
            '"resigner version v${RESIGNER_VERSION}" ]]') in workflow
    for digest in (
        "2cccc74b0cc3f56afd029accc3a4553c56d7269c6c403cbf161aaf095bc5c0b8",
        "38ec705d6fa2c7825513adbc9406d4fda5d6a084a8d3980ceff9a265e62f9623",
        "b3661dd4020dcd1d93b42a2a8a25d6d240d243a443cd3144af54454f62639f85",
        "c21a973358e7ae6d511fe4e40afca8c2c4c25ac173e31ea9f8b78b97f003b0cd",
        "cf79875bd5970dc2dac60c87fa50cee1ff1f9a41b0eb273f65e174aff37c367a",
        "424e1d64438a730626540b2e01e98d132a64214442ca9465b3e82336d12e633e",
    ):
        assert digest in workflow
    require(r"wda-package/Payload[\s\S]*WebDriverAgentRunner-Runner-[^\n]*signed[.]ipa", workflow,
            "WDA must be exported as a standard Payload IPA")
    for marker in (
        "OverteE2EWebDriverAgentVersion",
        "OverteE2EXCUITestDriverVersion",
    ):
        require(
            rf'{marker}["\]]+\s*=\s*["\[]', workflow,
            f"protected producer must inject the final WDA marker {marker}",
        )
    require(r"unsigned E2E client bytes do not match their manifest", workflow,
            "same-run unsigned input must be bound to its integrated manifest")
    for provenance_argument in (
        "--created-at",
        "--source-repository",
        "--source-repository-id",
        "--source-ref",
        "--workflow",
        "--reusable-workflow",
        "--run-id",
        "--run-attempt",
    ):
        assert provenance_argument in workflow
    require(
        r'WDA_RUNNER_BUNDLE_ID="[$][{]WDA_BUNDLE_ID[}][.]xctrunner"[\s\S]*'
        r'com[.]facebook[.]WebDriverAgentRunner[.]xctrunner=[$]WDA_RUNNER_BUNDLE_ID[\s\S]*'
        r'--expected-bundle-id "[$]WDA_RUNNER_BUNDLE_ID"',
        workflow,
        "Appium base ID must produce an .xctrunner runner and manifest bundle",
    )
    if "--udid" in workflow or "ProvisionedDevices" in workflow:
        raise AssertionError("producer must not accept or emit device identifiers")
    if "inputs.macos_runner" in workflow or "Audited macOS 26 runner used for build and signing" in workflow:
        raise AssertionError("signed producer must not expose a dispatchable runner")
    if workflow.count("runs-on: macos-26") != 1 or "macos_runner: macos-26" not in workflow:
        raise AssertionError("build and secret-bearing signing must use audited macos-26")
    assert "# v7.0.1" in workflow and "# v7.0.0" not in workflow
    assert "OUTPUT_ROOT" not in workflow
    for namespace in (
        "^overte-qt-host-v2-",
        "^overte-qt-ios-v2-",
        "^overte-qt-host-checkpoint-v1-",
        "^overte-qt-ios-checkpoint-v1-",
    ):
        assert namespace in workflow
    require(r"IOS_E2E_LAB_AGE_RECIPIENT[\s\S]*age1\[0-9a-z\]\{58\}", workflow,
            "age recipient must come from the protected environment and be validated")
    require(r"create-age-inner-zip[.]py[\s\S]*age[^\n]*--encrypt[\s\S]*test ! -e \"[$]SIGNED_ROOT\"",
            workflow, "plaintext pairs must be encrypted and removed before upload")
    upload_boundary = workflow[workflow.index("      - name: Upload encrypted Overte"):]
    if "steps.signed.outputs" in upload_boundary or re.search(r"path:.*(?:[.]ipa|[.]manifest)", upload_boundary):
        raise AssertionError("upload boundary may expose signed plaintext")
    assert "steps.encrypted.outputs.overte_age" in upload_boundary
    assert "steps.encrypted.outputs.wda_age" in upload_boundary
    if workflow.count("retention-days: 1") != 2:
        raise AssertionError("both signed candidates must be one-day artifacts")

    tool = load_manifest_tool()
    profile = {
        "TeamIdentifier": ["ABCDE12345"],
        "Entitlements": {"application-identifier": "ABCDE12345.org.overte.*"},
        "DeveloperCertificates": [b"authorized certificate"],
        # Privacy regression fixture: this input must never enter the manifest.
        "ProvisionedDevices": ["REDACTED-DEVICE-IDENTIFIER"],
        "ExpirationDate": dt.datetime(2030, 1, 2, tzinfo=dt.timezone.utc),
    }
    entitlements = {
        "application-identifier": "ABCDE12345.org.overte.interface.e2e",
        "com.apple.developer.team-identifier": "ABCDE12345",
    }
    info = {"CFBundleIdentifier": "org.overte.interface.e2e"}
    application_id, expiration = tool.validate_signing(
        profile, entitlements, info, b"authorized certificate",
        "org.overte.interface.e2e", "ABCDE12345",
        now=dt.datetime(2029, 1, 1, tzinfo=dt.timezone.utc),
    )
    global_wildcard = profile | {
        "Entitlements": {"application-identifier": "ABCDE12345.*"}
    }
    try:
        tool.validate_signing(
            global_wildcard,
            entitlements,
            info,
            b"authorized certificate",
            "org.overte.interface.e2e",
            "ABCDE12345",
            now=dt.datetime(2029, 1, 1, tzinfo=dt.timezone.utc),
        )
    except ValueError as error:
        assert "does not authorize" in str(error)
    else:
        raise AssertionError("global TEAM.* provisioning wildcard was accepted")
    try:
        tool.validate_signing(
            profile,
            entitlements,
            info,
            b"different certificate",
            "org.overte.interface.e2e",
            "ABCDE12345",
            now=dt.datetime(2029, 1, 1, tzinfo=dt.timezone.utc),
        )
    except ValueError as error:
        assert "not authorized by the profile" in str(error)
    else:
        raise AssertionError("profile accepted a different code-signing certificate")
    provenance = {
        "created_at": "2029-01-01T00:00:00Z",
        "source_repository": "overte-org/overte",
        "source_repository_id": 123456,
        "source_ref": "refs/heads/apple-ios",
        "workflow": ".github/workflows/ios-bootstrap.yml",
        "reusable_workflow": ".github/workflows/ios-fedora-e2e-producer.yml",
        "run_id": 987654,
        "run_attempt": 2,
    }
    overte = tool.build_manifest(
        kind="overte-app", source_revision="a" * 40,
        artifact_name="0001-OverteIOSClient-Release-device-signed.ipa",
        artifact_sha256="b" * 64, artifact_size=123,
        bundle_id="org.overte.interface.e2e", team_id="ABCDE12345",
        application_identifier=application_id, profile_expiration=expiration,
        **provenance,
    )
    assert overte == {
        "schemaVersion": 1,
        "contract": "overte-ios-fedora-e2e-artifact-v1",
        "kind": "overte-app",
        "sourceRevision": "a" * 40,
        "createdAt": "2029-01-01T00:00:00Z",
        "notAfter": "2029-01-02T00:00:00Z",
        "provenance": {
            "repository": "overte-org/overte",
            "repositoryId": 123456,
            "workflow": ".github/workflows/ios-bootstrap.yml",
            "reusableWorkflow": ".github/workflows/ios-fedora-e2e-producer.yml",
            "ref": "refs/heads/apple-ios",
            "runId": 987654,
            "runAttempt": 2,
        },
        "artifact": {"name": "0001-OverteIOSClient-Release-device-signed.ipa", "sha256": "b" * 64, "size": 123},
        "bundle": {"id": "org.overte.interface.e2e"},
        "signing": {
            "signed": True,
            "teamIdentifier": "ABCDE12345",
            "applicationIdentifier": "ABCDE12345.org.overte.interface.e2e",
            "profileExpiration": "2030-01-02T00:00:00Z",
        },
        "testBuildContractVersion": 1,
    }
    xctest_metadata = {
        "bundle": {"id": "org.overte.WebDriverAgentRunner"},
        "signing": {
            "signed": True,
            "teamIdentifier": "ABCDE12345",
            "applicationIdentifier": "ABCDE12345.org.overte.WebDriverAgentRunner",
            "profileExpiration": expiration,
        },
    }
    wda = tool.build_manifest(
        kind="webdriveragent", source_revision="a" * 40,
        artifact_name="WebDriverAgentRunner-Runner-16.8.0-signed.ipa",
        artifact_sha256="c" * 64, artifact_size=456,
        bundle_id="org.overte.WebDriverAgentRunner.xctrunner", team_id="ABCDE12345",
        application_identifier="ABCDE12345.org.overte.WebDriverAgentRunner.xctrunner",
        profile_expiration=expiration,
        xctest=xctest_metadata,
        **provenance,
    )
    assert wda["toolchain"] == {"xcuitestDriver": "12.8.0", "webdriverAgent": "16.8.0"}
    assert wda["bundle"] == {"id": "org.overte.WebDriverAgentRunner.xctrunner"}
    assert wda["xctest"] == xctest_metadata
    assert wda["signing"]["applicationIdentifier"].endswith(
        ".org.overte.WebDriverAgentRunner.xctrunner"
    )
    tool.validate_wda_toolchain_info({
        "OverteE2EWebDriverAgentVersion": "16.8.0",
        "OverteE2EXCUITestDriverVersion": "12.8.0",
    })
    try:
        tool.validate_wda_toolchain_info({
            "OverteE2EWebDriverAgentVersion": "16.8.0",
        })
    except ValueError as error:
        assert "pairing markers" in str(error)
    else:
        raise AssertionError("producer accepted final WDA without XCUITest pairing marker")

    with tempfile.TemporaryDirectory(prefix="overte-wda-xctest-") as temporary:
        runner_app = Path(temporary) / "WebDriverAgentRunner-Runner.app"
        xctest = runner_app / "PlugIns/WebDriverAgentRunner.xctest"
        xctest.mkdir(parents=True)
        (xctest / "embedded.mobileprovision").write_bytes(b"profile fixture")
        with (xctest / "Info.plist").open("wb") as stream:
            plistlib.dump(
                {"CFBundleIdentifier": "org.overte.WebDriverAgentRunner"}, stream
            )

        nested_profile = {
            "TeamIdentifier": ["ABCDE12345"],
            "Entitlements": {
                "application-identifier": "ABCDE12345.org.overte.*"
            },
            "DeveloperCertificates": [b"authorized certificate"],
            "ExpirationDate": dt.datetime(2030, 1, 2, tzinfo=dt.timezone.utc),
        }
        nested_entitlements = {
            "application-identifier": "ABCDE12345.org.overte.WebDriverAgentRunner",
            "com.apple.developer.team-identifier": "ABCDE12345",
        }

        def fake_signing_command(command: list[str], _description: str) -> bytes:
            if command[0] == "security":
                return plistlib.dumps(nested_profile)
            if "--entitlements" in command:
                return plistlib.dumps(nested_entitlements)
            if "--extract-certificates" in command:
                prefix = Path(command[command.index("--extract-certificates") + 1])
                Path(f"{prefix}0").write_bytes(b"authorized certificate")
            return b""

        validated_xctest = tool.validate_wda_xctest(
            runner_app,
            "org.overte.WebDriverAgentRunner.xctrunner",
            "ABCDE12345",
            command_runner=fake_signing_command,
        )
        assert validated_xctest == xctest_metadata
        nested_entitlements["application-identifier"] = (
            "ABCDE12345.org.overte.WebDriverAgentRunner.xctrunner"
        )
        try:
            tool.validate_wda_xctest(
                runner_app,
                "org.overte.WebDriverAgentRunner.xctrunner",
                "ABCDE12345",
                command_runner=fake_signing_command,
            )
        except ValueError as error:
            assert "application identifier mismatch" in str(error)
        else:
            raise AssertionError("WDA XCTest accepted the Runner application identifier")
    serialized = json.dumps((overte, wda))
    assert "REDACTED-DEVICE-IDENTIFIER" not in serialized

    expiring_xctest = xctest_metadata | {
        "signing": xctest_metadata["signing"] | {
            "profileExpiration": "2029-01-01T12:00:00Z"
        }
    }
    try:
        tool.build_manifest(
            kind="webdriveragent", source_revision="a" * 40,
            artifact_name="WebDriverAgentRunner-Runner-16.8.0-signed.ipa",
            artifact_sha256="c" * 64, artifact_size=456,
            bundle_id="org.overte.WebDriverAgentRunner.xctrunner",
            team_id="ABCDE12345",
            application_identifier="ABCDE12345.org.overte.WebDriverAgentRunner.xctrunner",
            profile_expiration=expiration,
            xctest=expiring_xctest,
            **provenance,
        )
    except ValueError as error:
        assert "one-day artifact boundary" in str(error)
    else:
        raise AssertionError("manifest accepted WDA whose nested profile expires too soon")

    inner_zip_tool = load_inner_zip_tool()
    with tempfile.TemporaryDirectory(prefix="overte-age-inner-") as temporary:
        root = Path(temporary)
        ipa = root / overte["artifact"]["name"]
        ipa.write_bytes(b"signed IPA fixture")
        manifest_payload = overte | {
            "artifact": {
                "name": ipa.name,
                "sha256": hashlib.sha256(ipa.read_bytes()).hexdigest(),
                "size": ipa.stat().st_size,
            }
        }
        manifest = root / f"{ipa.stem}.manifest.json"
        manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
        inner = root / "private.zip"
        assert inner_zip_tool.create_inner_zip(inner, ipa, manifest) == [
            ipa.name,
            manifest.name,
        ]
        with zipfile.ZipFile(inner) as archive:
            assert archive.namelist() == [ipa.name, manifest.name]
            assert all(
                info.compress_type == zipfile.ZIP_STORED
                for info in archive.infolist()
            )
        manifest_payload["artifact"]["sha256"] = "0" * 64
        manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
        try:
            inner_zip_tool.create_inner_zip(root / "rejected.zip", ipa, manifest)
        except ValueError as error:
            assert "digest or size" in str(error)
        else:
            raise AssertionError("inner ZIP accepted a manifest with the wrong digest")

    with tempfile.TemporaryDirectory(prefix="overte-fedora-manifest-") as temporary:
        root = Path(temporary)
        app = root / "Overte.app"
        app.mkdir()
        (app / "Info.plist").write_bytes(b"plist")
        (app / "embedded.mobileprovision").write_bytes(b"profile")
        artifact = root / "Overte.ipa"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr("Payload/Overte.app/Info.plist", b"plist")
            archive.writestr("Payload/Overte.app/embedded.mobileprovision", b"profile")
            archive.writestr(
                "Payload/Overte.app/Overte",
                b"prefix " + tool.E2E_BINARY_MARKER + b" suffix",
            )
        tool.validate_archive(artifact, "Payload/Overte.app", app)
        tool.validate_overte_e2e_archive(
            artifact,
            "Payload/Overte.app",
            {
                "CFBundlePackageType": "APPL",
                "CFBundleExecutable": "Overte",
                "OverteE2ETestBuildContractVersion": 1,
                "UIFileSharingEnabled": True,
            },
        )
        no_boundary = root / "Overte-without-e2e-boundary.ipa"
        with zipfile.ZipFile(no_boundary, "w") as archive:
            archive.writestr("Payload/Overte.app/Overte", b"normal binary")
        try:
            tool.validate_overte_e2e_archive(
                no_boundary,
                "Payload/Overte.app",
                {
                    "CFBundlePackageType": "APPL",
                    "CFBundleExecutable": "Overte",
                    "OverteE2ETestBuildContractVersion": 1,
                    "UIFileSharingEnabled": True,
                },
            )
        except ValueError as error:
            assert "opt-in E2E runtime boundary" in str(error)
        else:
            raise AssertionError("manifest generator accepted an unmarked E2E executable")
        (app / "Info.plist").write_bytes(b"different plist")
        try:
            tool.validate_archive(artifact, "Payload/Overte.app", app)
        except ValueError as error:
            assert "final IPA and audited app disagree" in str(error)
        else:
            raise AssertionError("manifest generator audited a plist outside final IPA bytes")
        (app / "Info.plist").write_bytes(b"plist")
        with zipfile.ZipFile(artifact, "a") as archive:
            archive.writestr("outside.txt", b"rejected")
        try:
            tool.validate_archive(artifact, "Payload/Overte.app", app)
        except ValueError as error:
            assert "outside its application root" in str(error)
        else:
            raise AssertionError("manifest generator accepted IPA content outside Payload app")

    integrated = (ROOT / ".github/workflows/ios-integrated.yml").read_text(encoding="utf-8")
    assert "e2e_test_build:" in integrated and "e2e_bundle_id:" in integrated
    assert "--e2e-test-build" in integrated and integrated.count("retention-days: 1") >= 2
    reject_direct_shell_inputs(integrated)
    consumer = (ROOT / "ios/tools/verify-runtime-candidate.py").read_text(encoding="utf-8")
    assert "verify_fedora_candidate" in consumer and "require_e2e_contract" in consumer
    print("iOS Fedora E2E producer contract passed")


if __name__ == "__main__":
    main()
