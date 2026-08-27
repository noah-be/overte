#!/usr/bin/env python3
"""Contract and negative tests for the credential-free Personal Team E2E kit."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import plistlib
import re
import stat
import tempfile
import warnings
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ios-personal-team-e2e-kit.yml"
BOOTSTRAP = ROOT / ".github/workflows/ios-bootstrap.yml"
DOCUMENTATION = ROOT / "docs/ios/PERSONAL_TEAM_E2E.md"
PROVENANCE_ARGUMENTS = (
    "overte-org/overte",
    123456,
    "refs/heads/apple-ios",
    ".github/workflows/ios-bootstrap.yml",
    ".github/workflows/ios-personal-team-e2e-kit.yml",
    987654,
    2,
)


def load_tool(filename: str, module_name: str):
    path = ROOT / "ios/ci" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def zip_entry(name: str, mode: int = stat.S_IFREG | 0o644) -> zipfile.ZipInfo:
    entry = zipfile.ZipInfo(name)
    entry.external_attr = mode << 16
    return entry


def write_overte_fixture(root: Path, bundle_id: str = "org.overte.interface.e2e") -> tuple[Path, Path]:
    ipa = root / "0042-OverteIOSClient-Release-device-unsigned.ipa"
    info = {
        "CFBundleIdentifier": bundle_id,
        "CFBundleExecutable": "Overte",
        "OverteE2ETestBuildContractVersion": 1,
        "UIFileSharingEnabled": True,
    }
    executable = b"arm64 fixture\0Rejected iOS E2E results path outside Documents\0"
    with zipfile.ZipFile(ipa, "w") as archive:
        archive.writestr(zip_entry("Payload/Overte.app/Info.plist"), plistlib.dumps(info))
        archive.writestr(
            zip_entry("Payload/Overte.app/Overte", stat.S_IFREG | 0o755), executable
        )
    manifest = root / "0042-OverteIOSClient-Release-device-unsigned.json"
    manifest.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "product": "overte-ios-integrated-client",
                "artifact": ipa.name,
                "sourceRevision": "a" * 40,
                "platform": "iphoneos",
                "architecture": "arm64",
                "configuration": "Release",
                "signed": False,
                "requiresSigning": True,
                "sha256": digest(ipa),
                "testBuildContractVersion": 1,
                "signing": {
                    "embeddedProvisioningProfile": False,
                    "applicationIdentifier": None,
                    "getTaskAllow": None,
                },
            }
        ),
        encoding="utf-8",
    )
    return ipa, manifest


def write_wda_fixture(root: Path, *, malicious: str | None = None) -> Path:
    path = root / "WebDriverAgentRunner-Runner.zip"
    app = "WebDriverAgentRunner-Runner.app"
    runner = {"CFBundleIdentifier": "com.facebook.WebDriverAgentRunner.xctrunner"}
    xctest = {"CFBundleIdentifier": "com.facebook.WebDriverAgentRunner"}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(zip_entry(f"{app}/", stat.S_IFDIR | 0o755), b"")
        archive.writestr(zip_entry(f"{app}/PlugIns/", stat.S_IFDIR | 0o755), b"")
        archive.writestr(
            zip_entry(
                f"{app}/PlugIns/WebDriverAgentRunner.xctest/",
                stat.S_IFDIR | 0o755,
            ),
            b"",
        )
        archive.writestr(zip_entry(f"{app}/Info.plist"), plistlib.dumps(runner))
        archive.writestr(
            zip_entry(f"{app}/WebDriverAgentRunner-Runner", stat.S_IFREG | 0o755),
            b"runner",
        )
        archive.writestr(
            zip_entry(f"{app}/PlugIns/WebDriverAgentRunner.xctest/Info.plist"),
            plistlib.dumps(xctest),
        )
        archive.writestr(
            zip_entry(
                f"{app}/PlugIns/WebDriverAgentRunner.xctest/Frameworks/"
                "WebDriverAgentLib.framework/",
                stat.S_IFDIR | 0o755,
            ),
            b"",
        )
        archive.writestr(
            zip_entry(
                f"{app}/PlugIns/WebDriverAgentRunner.xctest/Frameworks/"
                "WebDriverAgentLib.framework/Info.plist"
            ),
            plistlib.dumps({"CFBundleIdentifier": "com.facebook.WebDriverAgentLib"}),
        )
        archive.writestr(
            zip_entry(
                f"{app}/PlugIns/WebDriverAgentRunner.xctest/Frameworks/"
                "WebDriverAgentLib.framework/WebDriverAgentLib",
                stat.S_IFREG | 0o755,
            ),
            b"framework",
        )
        archive.writestr(
            zip_entry(
                f"{app}/PlugIns/WebDriverAgentRunner.xctest/WebDriverAgentRunner",
                stat.S_IFREG | 0o755,
            ),
            b"xctest",
        )
        # Upstream release packaging must not leak stale signing material into the kit.
        archive.writestr(zip_entry(f"{app}/embedded.mobileprovision"), b"private")
        archive.writestr(zip_entry(f"{app}/_CodeSignature/CodeResources"), b"signature")
        archive.writestr(
            zip_entry(f"{app}/PlugIns/WebDriverAgentRunner.xctest/_CodeSignature/CodeResources"),
            b"nested-signature",
        )
        if malicious == "traversal":
            archive.writestr(zip_entry("../escape"), b"escape")
        elif malicious == "symlink":
            archive.writestr(zip_entry(f"{app}/link", stat.S_IFLNK | 0o777), b"target")
        elif malicious == "duplicate":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(zip_entry(f"{app}/Info.plist"), plistlib.dumps(runner))
    return path


def write_fake_rcodesign(
    root: Path,
    *,
    omit_signature: bool = False,
    fail_inspection: bool = False,
    mutate_outer: bool = False,
    unsafe_output: bool = False,
    inspection_fault: str = "",
) -> Path:
    path = root / "rcodesign"
    path.write_text(
        """#!/usr/bin/env python3
import pathlib
import hashlib
import os
import sys

arguments = sys.argv[1:]
if arguments == ["--version"]:
    print("apple-codesign 0.29.0")
elif arguments[:-1] == ["sign", "--config-file", "/dev/null", "--timestamp-url", "none",
                       "--binary-identifier", "org.overte.WebDriverAgentRunner"]:
    if "RCODESIGN_TEST_CREDENTIAL" in os.environ:
        raise SystemExit(3)
    bundle = pathlib.Path(arguments[-1])
    executable = bundle / "WebDriverAgentRunner"
    framework = bundle / "Frameworks/WebDriverAgentLib.framework/WebDriverAgentLib"
    executable.write_bytes(executable.read_bytes() + b"\\0credential-free-adhoc\\0")
    framework.parent.mkdir(parents=True, exist_ok=True)
    framework.write_bytes(framework.read_bytes() + b"\\0credential-free-adhoc\\0")
    if not %s:
        for candidate in (bundle, bundle / "Frameworks/WebDriverAgentLib.framework"):
            signature = candidate / "_CodeSignature/CodeResources"
            signature.parent.mkdir()
            signature.write_bytes(b"credential-free code resources")
    if %s:
        outer = bundle.parents[1] / "WebDriverAgentRunner-Runner"
        outer.write_bytes(outer.read_bytes() + b"mutated")
    if %s:
        (bundle / "unsafe-link").symlink_to("WebDriverAgentRunner")
elif arguments[:-1] == ["print-signature-info", "--config-file", "/dev/null"]:
    if %s:
        raise SystemExit(2)
    executable = pathlib.Path(arguments[3])
    bundle = executable.parent
    identifier = ("com.facebook.WebDriverAgentLib" if executable.name == "WebDriverAgentLib"
                  else "org.overte.WebDriverAgentRunner")
    if %r == "wrong-identifier":
        identifier = "org.example.WrongIdentifier"
    print("code_directory:")
    print(f"file_sha256: {hashlib.sha256(executable.read_bytes()).hexdigest()}")
    print("  flags: CodeSignatureFlags(ADHOC)")
    print(f"  identifier: {identifier}")
    print("  digest_type: sha256")
    print("  slot_digests:")
    info_digest = hashlib.sha256((bundle / "Info.plist").read_bytes()).hexdigest()
    resources_digest = hashlib.sha256(
        (bundle / "_CodeSignature/CodeResources").read_bytes()
    ).hexdigest()
    print(f"  - 'Info (1): {info_digest}'")
    print(f"  - 'Resources (3): {resources_digest}'")
    print("cms: signed" if %r == "cms" else "cms: null")
    if %r == "team":
        print("team_identifier: PERSONALTEAM")
    if %r == "entitlements":
        print("entitlements: present")
else:
    raise SystemExit(2)
""" % (
            omit_signature,
            mutate_outer,
            unsafe_output,
            fail_inspection,
            inspection_fault,
            inspection_fault,
            inspection_fault,
            inspection_fault,
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def prepare_tool_signer(tool, root: Path, **options) -> Path:
    signer = write_fake_rcodesign(root, **options)
    tool.validate_rcodesign = lambda candidate: candidate if candidate == signer else None
    return signer


def assert_rcodesign_pin_contract() -> None:
    tool = load_tool("create-personal-team-e2e-kit.py", "personal_team_signer_pin")
    with tempfile.TemporaryDirectory(prefix="overte-personal-team-signer-") as temporary:
        root = Path(temporary)
        signer = write_fake_rcodesign(root).resolve()
        tool.RCODESIGN_EXECUTABLE_SHA256 = digest(signer)
        assert tool.validate_rcodesign(signer) == signer

        link = root / "linked-rcodesign"
        link.symlink_to(signer)
        for rejected in (link, Path("rcodesign")):
            try:
                tool.validate_rcodesign(rejected)
            except ValueError:
                pass
            else:
                raise AssertionError("Personal Team kit accepted an unsafe signer path")

        tool.RCODESIGN_EXECUTABLE_SHA256 = "0" * 64
        try:
            tool.validate_rcodesign(signer)
        except ValueError as error:
            assert "exact absolute pinned" in str(error)
        else:
            raise AssertionError("Personal Team kit accepted a signer digest mismatch")

        signer.write_text(
            signer.read_text(encoding="utf-8").replace(
                "apple-codesign 0.29.0", "apple-codesign 0.28.0"
            ),
            encoding="utf-8",
        )
        tool.RCODESIGN_EXECUTABLE_SHA256 = digest(signer)
        try:
            tool.validate_rcodesign(signer)
        except ValueError as error:
            assert "version differs" in str(error)
        else:
            raise AssertionError("Personal Team kit accepted a signer version mismatch")


def assert_workflow_contract() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    dispatch = bootstrap.split("  workflow_dispatch:\n", 1)[1].split(
        "  push:\n", 1
    )[0]
    dispatch_inputs = re.findall(r"^      [a-z][a-z0-9_]*:$", dispatch, re.MULTILINE)
    assert len(dispatch_inputs) <= 10
    assert "personal_team_overte_reuse_run_attempt" not in bootstrap
    assert re.search(r"^on:\n  workflow_call:", workflow, re.MULTILINE)
    assert not re.search(r"^  (?:workflow_dispatch|push|pull_request|schedule):", workflow, re.MULTILINE)
    assert "uses: ./.github/workflows/ios-integrated.yml" in workflow
    assert "e2e_test_build: true" in workflow
    assert "e2e_bundle_id: org.overte.interface.e2e" in workflow
    assert "XCUITEST_DRIVER_VERSION: 12.8.0" in workflow
    assert "WDA_VERSION: 16.8.0" in workflow
    assert "2cccc74b0cc3f56afd029accc3a4553c56d7269c6c403cbf161aaf095bc5c0b8" in workflow
    assert "38ec705d6fa2c7825513adbc9406d4fda5d6a084a8d3980ceff9a265e62f9623" in workflow
    assert "--root \"$KIT_ROOT/security-tools\" --tool rcodesign" in workflow
    assert "--rcodesign \"$KIT_ROOT/security-tools/rcodesign-0.29.0/rcodesign\"" in workflow
    assert "ios-personal-team-e2e-kit-v2-${{ github.run_id }}" in workflow
    assert "if: inputs.overte_reuse_run_id == '0'" in workflow
    assert "fetch_reusable_overte_artifact.py" in workflow
    assert "--run-id \"$OVERTE_REUSE_RUN_ID\"" in workflow
    assert "--run-attempt 1" in workflow
    assert "--assembly-revision \"$GITHUB_SHA\"" in workflow
    assert "--overte-reuse-provenance" in workflow
    assert "appium-webdriveragent\") != \"^16.8.0\"" in workflow
    assert "Overte-PersonalTeam-E2E-unsigned.ipa" in workflow
    assert "WebDriverAgentRunner-16.8.0-PersonalTeam-unsigned.ipa" in workflow
    assert "personal-team-e2e-kit.json" in workflow
    assert "retention-days: 7" in workflow
    for curl_guard in (
        "--max-filesize 536870912",
        "--connect-timeout 30",
        "--max-time 600",
        "--retry-all-errors",
    ):
        if workflow.count(curl_guard) != 2:
            raise AssertionError(f"both downloads must use {curl_guard}")
    for provenance_argument in (
        "--source-repository",
        "--source-repository-id",
        "--source-ref",
        "--workflow",
        "--reusable-workflow",
        "--run-id",
        "--run-attempt",
    ):
        assert provenance_argument in workflow
    if "secrets." in workflow or "environment:" in workflow:
        raise AssertionError("credential-free Personal Team workflow references signing secrets")
    upload = workflow[workflow.index("      - name: Upload public unsigned Personal Team kit") :]
    if "-signed.ipa" in upload or "personal-team-signed-handoff.json" in upload:
        raise AssertionError("workflow uploads locally signed Personal Team material")
    if "Sideloadly" in workflow:
        raise AssertionError("workflow must not automate or bundle proprietary Sideloadly")
    assert re.search(
        r"personal_team_e2e_kit:[\s\S]*type: boolean[\s\S]*default: false",
        bootstrap,
    )
    assert re.search(
        r"personal-team-e2e-kit:[\s\S]*inputs[.]personal_team_e2e_kit[\s\S]*"
        r"inputs[.]fedora_e2e_producer != true[\s\S]*uses: [.]/[.]github/workflows/"
        r"ios-personal-team-e2e-kit[.]yml",
        bootstrap,
    )
    assert '"$script_dir/personal-team-e2e-kit-contract-test.py"' in (
        ROOT / "ios/tests/run-tests.sh"
    ).read_text(encoding="utf-8")

    attestation_source = (
        ROOT / "ios/ci/create-personal-team-signed-attestation.py"
    ).read_text(encoding="utf-8")
    assert "stream.flush()" in attestation_source
    assert attestation_source.count("os.fsync(") >= 2
    assert "attestation output parent must be outside the checkout" in attestation_source

    documentation = DOCUMENTATION.read_text(encoding="utf-8")
    normalized_documentation = " ".join(documentation.split())
    for boundary in (
        "Variant A: Sideloadly installs directly",
        "Variant B: retain two signed IPA files",
        "not set `appium:prebuiltWDAPath`",
        "does not claim a cryptographic link",
        "derivationBinding: human-verified",
    ):
        assert " ".join(boundary.split()) in normalized_documentation
    assert "Sideloadly-signed export" not in documentation


def assert_tools_contract() -> None:
    kit_tool = load_tool("create-personal-team-e2e-kit.py", "personal_team_kit")
    attestation_tool = load_tool(
        "create-personal-team-signed-attestation.py", "personal_team_attestation"
    )
    with tempfile.TemporaryDirectory(prefix="overte-personal-team-") as temporary:
        root = Path(temporary)
        overte, overte_manifest = write_overte_fixture(root)
        upstream = write_wda_fixture(root)
        kit_tool.WDA_UPSTREAM_SHA256 = digest(upstream)
        signer = prepare_tool_signer(kit_tool, root)
        output = root / "kit"
        payload = kit_tool.create_kit(
            overte,
            overte_manifest,
            upstream,
            output,
            "a" * 40,
            "2029-01-01T00:00:00Z",
            *PROVENANCE_ARGUMENTS,
            signer,
        )
        assert payload["contract"] == "overte-ios-personal-team-e2e-kit-v2"
        assert payload["overteArtifactReuse"] is None
        assert payload["xcuitestDriverVersion"] == "12.8.0"
        assert payload["webDriverAgentVersion"] == "16.8.0"
        assert payload["webDriverAgentCredentialFreeSigning"] == {
            "nestedBundle": "PlugIns/WebDriverAgentRunner.xctest",
            "method": "ad-hoc",
            "outerRunnerBundleCodeResourcesPresent": False,
            "outerRunnerNewAdHocSignatureApplied": False,
            "outerRunnerProvisioned": False,
            "signer": "rcodesign",
            "signerVersion": "0.29.0",
            "signerExecutableSha256":
                "dab9a7465f96aba3c81e793775510f745b91a46b6418e89f7317b5d8fc7bcea2",
        }
        assert payload["desiredBundleIdentifiers"] == {
            "overte": "org.overte.interface.e2e",
            "wdaRunner": "org.overte.WebDriverAgentRunner.xctrunner",
            "wdaXCTest": "org.overte.WebDriverAgentRunner",
        }
        assert payload["humanSigningBoundary"] == {
            "method": "manual-sideloadly-personal-team",
            "derivationBinding": "human-verified",
            "signedBytesDerivableFromUnsignedKit": False,
            "maximumProfileLifetimeDays": 7,
        }
        assert payload["provenance"] == {
            "repository": "overte-org/overte",
            "repositoryId": 123456,
            "workflow": ".github/workflows/ios-bootstrap.yml",
            "reusableWorkflow": ".github/workflows/ios-personal-team-e2e-kit.yml",
            "ref": "refs/heads/apple-ios",
            "runId": 987654,
            "runAttempt": 2,
        }
        for kind in ("overte", "webDriverAgent"):
            artifact = payload["artifacts"][kind]
            candidate = output / artifact["name"]
            assert artifact["sha256"] == digest(candidate)
            assert artifact["size"] == candidate.stat().st_size
        wda = output / kit_tool.WDA_OUTPUT
        with zipfile.ZipFile(wda) as archive:
            names = archive.namelist()
            assert (
                "Payload/WebDriverAgentRunner-Runner.app/PlugIns/" in names
            )
            assert archive.getinfo(
                "Payload/WebDriverAgentRunner-Runner.app/PlugIns/"
            ).is_dir()
            assert (
                "Payload/WebDriverAgentRunner-Runner.app/PlugIns/"
                "WebDriverAgentRunner.xctest/_CodeSignature/CodeResources"
            ) in names
            assert (
                "Payload/WebDriverAgentRunner-Runner.app/PlugIns/"
                "WebDriverAgentRunner.xctest/Frameworks/WebDriverAgentLib.framework/"
                "_CodeSignature/CodeResources"
            ) in names
            assert not any(
                name.startswith("Payload/WebDriverAgentRunner-Runner.app/_CodeSignature/")
                for name in names
            )
            assert not any(name.endswith("embedded.mobileprovision") for name in names)
            runner = plistlib.loads(
                archive.read("Payload/WebDriverAgentRunner-Runner.app/Info.plist")
            )
            nested = plistlib.loads(
                archive.read(
                    "Payload/WebDriverAgentRunner-Runner.app/PlugIns/"
                    "WebDriverAgentRunner.xctest/Info.plist"
                )
            )
            assert runner["CFBundleIdentifier"] == "org.overte.WebDriverAgentRunner.xctrunner"
            assert runner["OverteE2EWebDriverAgentVersion"] == "16.8.0"
            assert runner["OverteE2EXCUITestDriverVersion"] == "12.8.0"
            assert nested["CFBundleIdentifier"] == "org.overte.WebDriverAgentRunner"
            assert b"credential-free-adhoc" in archive.read(
                "Payload/WebDriverAgentRunner-Runner.app/PlugIns/"
                "WebDriverAgentRunner.xctest/WebDriverAgentRunner"
            )

        signed_dir = root / "private-signed"
        signed_dir.mkdir(mode=0o700)
        signed_overte = signed_dir / attestation_tool.OVERTE_SIGNED_NAME
        signed_wda = signed_dir / attestation_tool.WDA_SIGNED_NAME
        signed_overte.write_bytes(b"manually re-signed Overte fixture")
        signed_wda.write_bytes(b"manually re-signed WDA fixture")
        signed_overte.chmod(0o600)
        signed_wda.chmod(0o600)
        attestation_path = signed_dir / "personal-team-signed-handoff.json"
        kit_manifest = output / kit_tool.MANIFEST_OUTPUT
        try:
            attestation_tool.create_attestation(
                kit_manifest,
                signed_overte,
                signed_wda,
                attestation_path,
                "2029-01-02T03:04:05Z",
                False,
                True,
                True,
            )
        except ValueError as error:
            assert "explicit human signing attestations" in str(error)
        else:
            raise AssertionError("attestation accepted a missing human boundary acknowledgement")
        handoff = attestation_tool.create_attestation(
            kit_manifest,
            signed_overte,
            signed_wda,
            attestation_path,
            "2029-01-02T03:04:05Z",
            True,
            True,
            True,
        )
        assert handoff["contract"] == "overte-ios-personal-team-signed-handoff-v1"
        assert handoff["notAfter"] == "2029-01-09T03:04:05Z"
        assert handoff["unsignedKitManifestSha256"] == digest(kit_manifest)
        assert handoff["humanAttestation"]["derivationBinding"] == "human-verified"
        assert "teamIdentifier" not in json.dumps(handoff)
        assert stat.S_IMODE(attestation_path.stat().st_mode) == 0o600

        signed_overte.chmod(0o644)
        try:
            attestation_tool.create_attestation(
                kit_manifest,
                signed_overte,
                signed_wda,
                signed_dir / "too-open-input.json",
                "2029-01-02T03:04:05Z",
                True,
                True,
                True,
            )
        except ValueError as error:
            assert "permissions" in str(error)
        else:
            raise AssertionError("attestation accepted a group-readable signed IPA")
        signed_overte.chmod(0o600)

        symlink_dir = root / "symlink-input"
        symlink_dir.mkdir(mode=0o700)
        linked_overte = symlink_dir / attestation_tool.OVERTE_SIGNED_NAME
        linked_overte.symlink_to(signed_overte)
        try:
            attestation_tool.create_attestation(
                kit_manifest,
                linked_overte,
                signed_wda,
                signed_dir / "symlink-input.json",
                "2029-01-02T03:04:05Z",
                True,
                True,
                True,
            )
        except ValueError as error:
            assert "symlink-free" in str(error)
        else:
            raise AssertionError("attestation accepted a symlinked signed IPA")

        open_parent = root / "open-parent"
        open_parent.mkdir(mode=0o755)
        try:
            attestation_tool.create_attestation(
                kit_manifest,
                signed_overte,
                signed_wda,
                open_parent / "handoff.json",
                "2029-01-02T03:04:05Z",
                True,
                True,
                True,
            )
        except ValueError as error:
            assert "permissions" in str(error)
        else:
            raise AssertionError("attestation accepted a non-private output parent")

        real_parent = root / "real-parent"
        real_parent.mkdir(mode=0o700)
        linked_parent = root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        try:
            attestation_tool.create_attestation(
                kit_manifest,
                signed_overte,
                signed_wda,
                linked_parent / "handoff.json",
                "2029-01-02T03:04:05Z",
                True,
                True,
                True,
            )
        except ValueError as error:
            assert "symlink-free" in str(error)
        else:
            raise AssertionError("attestation accepted a symlinked output parent")

        original_checkout = attestation_tool.CHECKOUT_ROOT
        attestation_tool.CHECKOUT_ROOT = root
        try:
            try:
                attestation_tool.create_attestation(
                    kit_manifest,
                    signed_overte,
                    signed_wda,
                    signed_dir / "inside-checkout.json",
                    "2029-01-02T03:04:05Z",
                    True,
                    True,
                    True,
                )
            except ValueError as error:
                assert "outside the checkout" in str(error)
            else:
                raise AssertionError("attestation accepted output inside the checkout")
        finally:
            attestation_tool.CHECKOUT_ROOT = original_checkout


def assert_negative_archives() -> None:
    tool = load_tool("create-personal-team-e2e-kit.py", "personal_team_negative")
    with tempfile.TemporaryDirectory(prefix="overte-personal-team-digest-") as temporary:
        root = Path(temporary)
        overte, manifest = write_overte_fixture(root)
        wda = write_wda_fixture(root)
        signer = prepare_tool_signer(tool, root)
        try:
            tool.create_kit(
                overte,
                manifest,
                wda,
                root / "rejected",
                "a" * 40,
                "2029-01-01T00:00:00Z",
                *PROVENANCE_ARGUMENTS,
                signer,
            )
        except ValueError as error:
            assert "SHA-256 mismatch" in str(error)
            assert not (root / "rejected").exists()
        else:
            raise AssertionError("Personal Team kit accepted an unpinned WDA archive")

    with tempfile.TemporaryDirectory(prefix="overte-personal-team-overte-digest-") as temporary:
        root = Path(temporary)
        overte, manifest = write_overte_fixture(root)
        wda = write_wda_fixture(root)
        overte.write_bytes(overte.read_bytes() + b"changed")
        tool.WDA_UPSTREAM_SHA256 = digest(wda)
        signer = prepare_tool_signer(tool, root)
        try:
            tool.create_kit(
                overte,
                manifest,
                wda,
                root / "rejected",
                "a" * 40,
                "2029-01-01T00:00:00Z",
                *PROVENANCE_ARGUMENTS,
                signer,
            )
        except ValueError as error:
            assert "manifest SHA-256" in str(error)
            assert not (root / "rejected").exists()
        else:
            raise AssertionError("Personal Team kit accepted changed Overte bytes")

    for attack in ("traversal", "symlink", "duplicate"):
        with tempfile.TemporaryDirectory(prefix=f"overte-personal-team-{attack}-") as temporary:
            root = Path(temporary)
            overte, manifest = write_overte_fixture(root)
            wda = write_wda_fixture(root, malicious=attack)
            tool.WDA_UPSTREAM_SHA256 = digest(wda)
            signer = prepare_tool_signer(tool, root)
            try:
                tool.create_kit(
                    overte,
                    manifest,
                    wda,
                    root / "rejected",
                    "a" * 40,
                    "2029-01-01T00:00:00Z",
                    *PROVENANCE_ARGUMENTS,
                    signer,
                )
            except ValueError:
                assert not (root / "rejected").exists()
            else:
                raise AssertionError(f"Personal Team kit accepted WDA {attack}")

    with tempfile.TemporaryDirectory(prefix="overte-personal-team-id-") as temporary:
        root = Path(temporary)
        overte, manifest = write_overte_fixture(root, "org.example.changed.e2e")
        wda = write_wda_fixture(root)
        tool.WDA_UPSTREAM_SHA256 = digest(wda)
        signer = prepare_tool_signer(tool, root)
        try:
            tool.create_kit(
                overte,
                manifest,
                wda,
                root / "rejected",
                "a" * 40,
                "2029-01-01T00:00:00Z",
                *PROVENANCE_ARGUMENTS,
                signer,
            )
        except ValueError as error:
            assert "fixed E2E bundle identifier" in str(error)
        else:
            raise AssertionError("Personal Team kit accepted a changed Overte bundle identifier")

    signing_failures = {
        "missing-signature": {"omit_signature": True},
        "failed-inspection": {"fail_inspection": True},
        "mutated-outer": {"mutate_outer": True},
        "unsafe-output": {"unsafe_output": True},
        "wrong-identifier": {"inspection_fault": "wrong-identifier"},
        "cms-signature": {"inspection_fault": "cms"},
        "team-identity": {"inspection_fault": "team"},
        "entitlements": {"inspection_fault": "entitlements"},
    }
    for failure, signer_options in signing_failures.items():
        with tempfile.TemporaryDirectory(prefix=f"overte-personal-team-{failure}-") as temporary:
            root = Path(temporary)
            isolated_tool = load_tool(
                "create-personal-team-e2e-kit.py", f"personal_team_{failure}"
            )
            overte, manifest = write_overte_fixture(root)
            wda = write_wda_fixture(root)
            isolated_tool.WDA_UPSTREAM_SHA256 = digest(wda)
            signer = prepare_tool_signer(
                isolated_tool, root, **signer_options,
            )
            try:
                isolated_tool.create_kit(
                    overte, manifest, wda, root / "rejected", "a" * 40,
                    "2029-01-01T00:00:00Z", *PROVENANCE_ARGUMENTS, signer,
                )
            except ValueError:
                assert not (root / "rejected").exists()
            else:
                raise AssertionError(f"Personal Team kit accepted {failure}")


def main() -> None:
    assert_workflow_contract()
    assert_rcodesign_pin_contract()
    assert_tools_contract()
    assert_negative_archives()
    print("PASS Personal Team E2E kit contract and negative tests")


if __name__ == "__main__":
    main()
