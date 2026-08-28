#!/usr/bin/env python3
"""iOS-owned device-free tests for the offline Personal-Team WDA signer."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile


DEVICE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = DEVICE_ROOT / "ios" / "sign_personal_team_wda.py"
SPEC = importlib.util.spec_from_file_location("sign_personal_team_wda", SCRIPT)
assert SPEC and SPEC.loader
SIGN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SIGN)


class IosPersonalTeamWdaSigningTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-wda-sign-test-")
        self.root = Path(self.temporary.name).resolve()
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.profile_dir = self.private / "profile"
        self.profile_dir.mkdir(mode=0o700)
        self.input = self.private / SIGN.KIT_WDA_NAME
        self.manifest = self.private / "personal-team-e2e-kit.json"
        self.p12 = self.private / "identity.p12"
        self.password = self.private / "password.txt"
        self.profile = self.profile_dir / "wda.mobileprovision"
        self.device_udid = self.private / "device-udid.txt"
        self.apple_root = self.private / "AppleRootCA.pem"
        self.output = self.private / "wda-signed.ipa"
        self.record = self.private / "resigner-record.jsonl"
        self.rcodesign_record = self.private / "rcodesign-record.jsonl"
        self.resigner = self.private / "resigner"
        self.rcodesign = self.private / "rcodesign"
        self.p12.write_bytes(b"p12 fixture")
        self.password.write_text("correct horse battery staple\n", encoding="utf-8")
        self.profile.write_bytes(b"profile fixture")
        self.device_udid.write_text(
            "00008110-0012345678901234\n", encoding="ascii"
        )
        self.apple_root.write_bytes(b"public Apple root fixture")
        self.apple_root.chmod(0o644)
        for path in (self.p12, self.password, self.profile, self.device_udid):
            path.chmod(0o600)
        self.make_unsigned_wda()
        self.make_kit_manifest()
        self.make_fake_resigner()
        self.make_fake_rcodesign()

    def tearDown(self):
        self.temporary.cleanup()

    def test_external_tool_is_killed_and_reaped_when_signing_is_interrupted(self):
        process = mock.Mock(pid=9123)
        process.poll.return_value = None
        process.wait.side_effect = [
            SIGN.SigningError("offline WDA signing was interrupted"),
            0,
        ]
        with mock.patch.object(SIGN.subprocess, "Popen", return_value=process), \
                mock.patch.object(SIGN.os, "killpg") as kill_group, \
                self.assertRaisesRegex(SIGN.SigningError, "interrupted"):
            SIGN.run_process(
                ["/private/pinned-tool"], {}, self.private, "interrupted-tool"
            )

        kill_group.assert_called_once_with(9123, SIGN.signal.SIGKILL)
        self.assertEqual(
            [mock.call(timeout=SIGN.PROCESS_TIMEOUT_SECONDS), mock.call(timeout=5)],
            process.wait.call_args_list,
        )
        process.kill.assert_not_called()

    @staticmethod
    def plist(bundle_id: str, executable: str, package: str, **extra) -> bytes:
        return plistlib.dumps({
            "CFBundleIdentifier": bundle_id,
            "CFBundleExecutable": executable,
            "CFBundlePackageType": package,
            **extra,
        }, fmt=plistlib.FMT_BINARY, sort_keys=True)

    def make_unsigned_wda(self, *, duplicate: bool = False,
                          signing_material: bool = False) -> None:
        root = "Payload/WebDriverAgentRunner-Runner.app"
        xctest = root + "/PlugIns/WebDriverAgentRunner.xctest"
        framework = xctest + "/Frameworks/WebDriverAgentLib.framework"
        self.input.unlink(missing_ok=True)
        with zipfile.ZipFile(self.input, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(root + "/Info.plist", self.plist(
                SIGN.SOURCE_BUNDLE_IDS["runner"], "WebDriverAgentRunner-Runner", "APPL",
                OverteE2EWebDriverAgentVersion="16.8.0",
                OverteE2EXCUITestDriverVersion="12.8.0",
            ))
            if duplicate:
                archive.writestr(root + "/Info.plist", b"duplicate")
            archive.writestr(root + "/WebDriverAgentRunner-Runner", b"runner macho")
            archive.writestr(xctest + "/Info.plist", self.plist(
                SIGN.SOURCE_BUNDLE_IDS["xctest"], "WebDriverAgentRunner", "BNDL"
            ))
            archive.writestr(xctest + "/WebDriverAgentRunner", b"xctest macho")
            archive.writestr(framework + "/Info.plist", self.plist(
                SIGN.SOURCE_BUNDLE_IDS["framework"], "WebDriverAgentLib", "FMWK"
            ))
            archive.writestr(framework + "/WebDriverAgentLib", b"framework macho")
            if signing_material:
                archive.writestr(xctest + "/_CodeSignature/CodeResources", b"old")
        self.input.chmod(0o600)

    def make_kit_manifest(self, *, wda_sha256: str | None = None) -> None:
        digest = wda_sha256 or hashlib.sha256(self.input.read_bytes()).hexdigest()
        value = {
            "schemaVersion": 1,
            "contract": SIGN.KIT_CONTRACT,
            "sourceRevision": "a" * 40,
            "createdAt": "2026-08-27T00:00:00Z",
            "provenance": {
                "repository": "noah-be/overte",
                "repositoryId": 123,
                "workflow": ".github/workflows/ios-bootstrap.yml",
                "reusableWorkflow": ".github/workflows/ios-personal-team-e2e-kit.yml",
                "ref": "refs/heads/apple-ios",
                "runId": 456,
                "runAttempt": 1,
            },
            "overteArtifactReuse": None,
            "xcuitestDriverVersion": "12.8.0",
            "webDriverAgentVersion": "16.8.0",
            "webDriverAgentCredentialFreeSigning": {
                "nestedBundle": SIGN.WDA_XCTEST,
                "method": "unsigned-requires-recursive-personal-team-signing",
                "outerRunnerBundleCodeResourcesPresent": False,
                "nestedBundleCodeResourcesPresent": False,
                "outerRunnerProvisioned": False,
            },
            "desiredBundleIdentifiers": {
                "overte": "org.overte.interface.e2e",
                "wdaRunner": SIGN.SOURCE_BUNDLE_IDS["runner"],
                "wdaXCTest": SIGN.SOURCE_BUNDLE_IDS["xctest"],
            },
            "humanSigningBoundary": {
                "method": "manual-sideloadly-personal-team",
                "derivationBinding": "human-verified",
                "signedBytesDerivableFromUnsignedKit": False,
                "maximumProfileLifetimeDays": 7,
            },
            "upstream": {
                "webDriverAgentUrl":
                "https://github.com/appium/WebDriverAgent/releases/download/v16.8.0/"
                "WebDriverAgentRunner-Runner.zip",
                "webDriverAgentSha256":
                "38ec705d6fa2c7825513adbc9406d4fda5d6a084a8d3980ceff9a265e62f9623",
            },
            "artifacts": {
                "overte": {"name": "Overte-PersonalTeam-E2E-unsigned.ipa",
                           "sha256": "b" * 64, "size": 1},
                "webDriverAgent": {"name": SIGN.KIT_WDA_NAME,
                                   "sha256": digest,
                                   "size": self.input.stat().st_size},
            },
        }
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        self.manifest.chmod(0o600)

    def make_fake_resigner(self, *, version: str = "v0.3.1",
                           omit_outer_profile: bool = False,
                           add_debug_symbols: bool = False,
                           signing_exit: int = 0) -> None:
        source = f'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import plistlib
import sys
import zipfile
RECORD = Path({str(self.record)!r})
args = sys.argv[1:]
with RECORD.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({{"args": args, "passwordPresent": bool(os.environ.get("P12_PASSWORD"))}}) + "\\n")
if args == ["--version"]:
    print("resigner version {version}")
    raise SystemExit(0)
if "--only-verify" in args:
    raise SystemExit(0)
if {signing_exit}:
    print(os.environ.get("P12_PASSWORD", ""))
    print(os.environ.get("P12_PASSWORD", ""), file=sys.stderr)
    raise SystemExit({signing_exit})
target = Path(args[-1])
profile_dir = Path(args[args.index("--profile") + 1])
profile = next(profile_dir.glob("*.mobileprovision")).read_bytes()
remaps = {{}}
for index, value in enumerate(args):
    if value == "--bundle-id-remap":
        old, new = args[index + 1].split("=", 1)
        remaps[old] = new
temporary = target.with_suffix(".new")
root = "Payload/WebDriverAgentRunner-Runner.app"
xctest = root + "/PlugIns/WebDriverAgentRunner.xctest"
framework = xctest + "/Frameworks/WebDriverAgentLib.framework"
with zipfile.ZipFile(target) as original, zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
    has_xctest = any(
        entry.filename == xctest or entry.filename.startswith(xctest + "/")
        for entry in original.infolist()
    )
    for entry in original.infolist():
        data = original.read(entry)
        if entry.filename in {{root + "/Info.plist", xctest + "/Info.plist", framework + "/Info.plist"}}:
            value = plistlib.loads(data)
            value["CFBundleIdentifier"] = remaps.get(
                value["CFBundleIdentifier"], value["CFBundleIdentifier"]
            )
            data = plistlib.dumps(value, fmt=plistlib.FMT_BINARY, sort_keys=True)
        elif entry.filename == xctest + "/WebDriverAgentRunner":
            data = b"resigner-signed xctest with unwanted app entitlements"
        output.writestr(entry.filename, data)
    output.writestr(root + "/_CodeSignature/CodeResources", b"outer seal")
    if not {omit_outer_profile!r}:
        output.writestr(root + "/embedded.mobileprovision", profile)
    if has_xctest:
        output.writestr(xctest + "/_CodeSignature/CodeResources", b"xctest seal")
    if {add_debug_symbols!r}:
        output.writestr(
            xctest + ".dSYM/Contents/Resources/DWARF/WebDriverAgentRunner",
            b"non-runtime debug symbols",
        )
os.replace(temporary, target)
'''
        self.resigner.write_text(source, encoding="utf-8")
        self.resigner.chmod(0o700)

    def make_fake_rcodesign(self, *, verify_exit: int = 0,
                            verify_failure_name: str = "") -> None:
        source = f'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import plistlib
import sys
args = sys.argv[1:]
with Path({str(self.rcodesign_record)!r}).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({{"args": args, "passwordPresent": bool(os.environ.get("P12_PASSWORD"))}}) + "\\n")
if args == ["--version"]:
    print("apple-codesign 0.29.0")
    raise SystemExit(0)
if args and args[0] == "sign":
    if any(Path(args[-1]).rglob("*.dSYM")):
        raise SystemExit(12)
    application = Path(args[-1])
    xctest = application / "PlugIns/WebDriverAgentRunner.xctest"
    framework = xctest / "Frameworks/WebDriverAgentLib.framework"
    for bundle in (application, xctest, framework):
        signature = bundle / "_CodeSignature"
        signature.mkdir(mode=0o700, parents=True, exist_ok=True)
        (signature / "CodeResources").write_bytes(b"recursive seal")
    raise SystemExit(0)
if args and args[0] == "verify":
    if {verify_failure_name!r} and Path(args[-1]).name.startswith({verify_failure_name!r}):
        raise SystemExit(8)
    raise SystemExit({verify_exit})
if args and args[0] == "print-signature-info":
    executable = Path(args[-1]).name
    identifiers = {{
        "runner-executable": "local.personal.wda",
        "xctest-executable": "org.overte.WebDriverAgentRunner",
        "framework-executable": "com.facebook.WebDriverAgentLib",
    }}
    identifier = identifiers[executable]
    if executable.startswith("runner"):
        entitlements = {{
            "application-identifier": "TEAM123456.local.personal.wda",
            "com.apple.developer.team-identifier": "TEAM123456",
        }}
    signature = {{
        "code_directory": {{
            "identifier": identifier,
            "team_name": "TEAM123456",
        }},
        "cms": {{
            "certificates": [{{
                "apple_team_id": "TEAM123456",
                "apple_certificate_profile": "apple-development",
            }}],
            "signers": [{{"signature_verifies": True}}],
        }},
    }}
    if executable.startswith("runner"):
        lines = plistlib.dumps(entitlements, fmt=plistlib.FMT_XML).decode().splitlines()
        signature["entitlements_plist"] = lines
        signature["entitlements_der_plist"] = lines
    print(json.dumps([{{"entity": {{"mach_o": {{"signature": signature}}}}}}]))
    raise SystemExit(0)
raise SystemExit(3)
'''
        self.rcodesign.write_text(source, encoding="utf-8")
        self.rcodesign.chmod(0o700)

    def profile_value(self, *, bundle_id: str = "local.personal.wda",
                      expiry_hours: int = 72, age_hours: int = 1) -> dict:
        team = "TEAM123456"
        now = datetime.now(timezone.utc)
        return {
            "TeamIdentifier": [team],
            "ApplicationIdentifierPrefix": [team],
            "CreationDate": now - timedelta(hours=age_hours),
            "ExpirationDate": now + timedelta(hours=expiry_hours),
            "LocalProvision": True,
            "IsXcodeManaged": True,
            "TimeToLive": 7,
            "ProvisionedDevices": ["00008110-0012345678901234"],
            "Platform": ["iOS"],
            "DeveloperCertificates": [b"certificate"],
            "Entitlements": {
                "application-identifier": f"{team}.{bundle_id}",
                "com.apple.developer.team-identifier": team,
                "get-task-allow": True,
            },
        }

    def arguments(self) -> argparse.Namespace:
        return argparse.Namespace(
            unsigned_wda_ipa=self.input,
            unsigned_kit_manifest=self.manifest,
            p12_file=self.p12,
            p12_password_file=self.password,
            profile_file=self.profile,
            device_udid_file=self.device_udid,
            apple_root_ca_pem=self.apple_root,
            resigner=self.resigner,
            rcodesign=self.rcodesign,
            output_ipa=self.output,
        )

    def records(self) -> list[dict]:
        return [json.loads(line) for line in self.record.read_text(encoding="utf-8").splitlines()]

    def run_with_fakes(self) -> int:
        with mock.patch.object(SIGN, "require_pinned_tool"), mock.patch.object(
                SIGN, "require_apple_root"), mock.patch.object(
                SIGN, "verify_profile_payload",
                return_value=self.profile_value()), mock.patch.object(
                SIGN, "verify_p12_identity", return_value=b"certificate"), mock.patch.object(
                SIGN, "verify_signer_leaf"):
            return SIGN.run(self.arguments())

    def test_success_remaps_only_provisioned_runner_and_keeps_nested_identities(self):
        self.assertEqual(0, self.run_with_fakes())
        self.assertTrue(self.output.is_file())
        self.assertEqual(0o600, self.output.stat().st_mode & 0o777)
        records = self.records()
        self.assertEqual(4, len(records))
        signing = records[1]
        self.assertTrue(signing["passwordPresent"])
        self.assertNotIn("correct horse battery staple", signing["args"])
        remaps = {
            signing["args"][index + 1]
            for index, value in enumerate(signing["args"])
            if value == "--bundle-id-remap"
        }
        self.assertEqual({
            SIGN.SOURCE_BUNDLE_IDS["runner"] + "=local.personal.wda"
        }, remaps)
        self.assertFalse(records[2]["passwordPresent"])
        self.assertIn("--only-verify", records[2]["args"])
        self.assertFalse(records[3]["passwordPresent"])
        self.assertIn("--only-verify", records[3]["args"])
        with zipfile.ZipFile(self.output) as archive:
            names = set(archive.namelist())
            nested = ("Payload/WebDriverAgentRunner-Runner.app/PlugIns/"
                      "WebDriverAgentRunner.xctest/")
            self.assertNotIn(nested + "embedded.mobileprovision", names)
            self.assertIn(nested + "_CodeSignature/CodeResources", names)
            self.assertIn(
                nested + "Frameworks/WebDriverAgentLib.framework/"
                "_CodeSignature/CodeResources", names,
            )
            self.assertEqual(
                b"xctest macho",
                archive.read(nested + "WebDriverAgentRunner"),
            )
            self.assertEqual(
                "local.personal.wda",
                plistlib.loads(archive.read(
                    "Payload/WebDriverAgentRunner-Runner.app/Info.plist"
                ))["CFBundleIdentifier"],
            )
            self.assertEqual(
                SIGN.SOURCE_BUNDLE_IDS["xctest"],
                plistlib.loads(archive.read(nested + "Info.plist"))[
                    "CFBundleIdentifier"
                ],
            )
            self.assertEqual(
                SIGN.SOURCE_BUNDLE_IDS["framework"],
                plistlib.loads(archive.read(
                    nested + "Frameworks/WebDriverAgentLib.framework/Info.plist"
                ))["CFBundleIdentifier"],
            )

        rcodesign_records = [
            json.loads(line) for line in self.rcodesign_record.read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        signing = next(
            record for record in rcodesign_records
            if record["args"] and record["args"][0] == "sign"
        )
        self.assertFalse(signing["passwordPresent"])
        self.assertNotIn("correct horse battery staple", "\n".join(signing["args"]))
        self.assertIn(str(self.password), signing["args"])
        self.assertEqual(1, signing["args"].count("--entitlements-xml-file"))
        self.assertFalse(any(
            value.startswith("PlugIns/WebDriverAgentRunner.xctest:")
            for value in signing["args"]
        ))
        self.assertIn("--timestamp-url", signing["args"])
        self.assertIn("none", signing["args"])

    def test_recursive_rcodesign_strips_non_runtime_debug_symbols(self):
        self.make_fake_resigner(add_debug_symbols=True)
        self.assertEqual(0, self.run_with_fakes())
        with zipfile.ZipFile(self.output) as archive:
            self.assertFalse(any(".dSYM/" in name for name in archive.namelist()))

    def test_framework_rcodesign_failure_is_not_hidden_by_outer_verification(self):
        self.make_fake_rcodesign(verify_failure_name="framework")
        with self.assertRaisesRegex(SIGN.SigningError, "framework-rcodesign failed"):
            self.run_with_fakes()
        self.assertFalse(self.output.exists())

    def test_password_is_not_forwarded_or_left_in_private_temporary_logs(self):
        self.make_fake_resigner(signing_exit=9)
        with self.assertRaisesRegex(SIGN.SigningError, "resigner-sign failed"):
            self.run_with_fakes()
        self.assertFalse(self.output.exists())
        signing = self.records()[1]
        self.assertTrue(signing["passwordPresent"])
        self.assertNotIn("correct horse battery staple", "\n".join(signing["args"]))
        self.assertFalse(any(item.name.startswith(".wda-sign-")
                             for item in self.private.iterdir()))

    def test_private_modes_symlinks_hardlinks_and_existing_output_fail(self):
        with mock.patch.object(SIGN, "require_pinned_tool"), mock.patch.object(
                SIGN, "require_apple_root"):
            self.p12.chmod(0o644)
            with self.assertRaisesRegex(SIGN.SigningError, "mode-0600"):
                SIGN.validate_paths(self.arguments())
            self.p12.chmod(0o600)
            self.profile_dir.chmod(0o755)
            with self.assertRaisesRegex(SIGN.SigningError, "mode-0700"):
                SIGN.validate_paths(self.arguments())
            self.profile_dir.chmod(0o700)
            alternate = self.private / "alternate.p12"
            os.link(self.p12, alternate)
            arguments = self.arguments()
            arguments.p12_file = alternate
            with self.assertRaisesRegex(SIGN.SigningError, "singly-linked"):
                SIGN.validate_paths(arguments)
            alternate.unlink()
            symlink = self.private / "linked.p12"
            symlink.symlink_to(self.p12)
            arguments.p12_file = symlink
            with self.assertRaisesRegex(
                    SIGN.SigningError, "normalized absolute|symbolic links"):
                SIGN.validate_paths(arguments)
            self.output.write_bytes(b"existing")
            self.output.chmod(0o600)
            arguments.p12_file = self.p12
            with self.assertRaisesRegex(SIGN.SigningError, "must not already exist"):
                SIGN.validate_paths(arguments)

    def test_private_inputs_and_pinned_tools_reject_unsafe_ancestry(self):
        unsafe = self.root / "unsafe"
        unsafe.mkdir(mode=0o777)
        unsafe.chmod(0o777)
        protected_child = unsafe / "protected"
        protected_child.mkdir(mode=0o700)

        for field in (
            "unsigned_wda_ipa", "unsigned_kit_manifest", "p12_file",
            "p12_password_file", "profile_file", "device_udid_file",
        ):
            arguments = self.arguments()
            source = getattr(arguments, field)
            relocated = protected_child / f"{field}-{source.name}"
            relocated.write_bytes(source.read_bytes())
            relocated.chmod(0o600)
            setattr(arguments, field, relocated)
            with self.subTest(field=field), self.assertRaisesRegex(
                    SIGN.SigningError, "ancestry"):
                SIGN.validate_paths(arguments)

        for name, source in (
            ("resigner", self.resigner), ("rcodesign", self.rcodesign)
        ):
            unsafe_tool = protected_child / name
            unsafe_tool.write_bytes(source.read_bytes())
            unsafe_tool.chmod(0o700)
            with self.subTest(tool=name), self.assertRaisesRegex(
                    SIGN.SigningError, "ancestry"):
                SIGN.require_pinned_tool(unsafe_tool, name)

        unsafe_root = protected_child / "AppleRootCA.pem"
        unsafe_root.write_bytes(self.apple_root.read_bytes())
        unsafe_root.chmod(0o644)
        with self.assertRaisesRegex(SIGN.SigningError, "ancestry"):
            SIGN.require_apple_root(unsafe_root)

        arguments = self.arguments()
        arguments.output_ipa = protected_child / "output.ipa"
        with mock.patch.object(SIGN, "require_pinned_tool"), mock.patch.object(
                SIGN, "require_apple_root"), self.assertRaisesRegex(
                    SIGN.SigningError, "ancestry"):
            SIGN.validate_paths(arguments)

    def test_atomic_publication_never_replaces_a_raced_output(self):
        target = self.private / "complete-private-output.ipa"
        target.write_bytes(b"verified output")
        target.chmod(0o600)
        self.output.write_bytes(b"raced output")
        self.output.chmod(0o600)
        with self.assertRaisesRegex(SIGN.SigningError, "appeared during signing"):
            SIGN.publish_no_replace(target, self.output)
        self.assertEqual(b"raced output", self.output.read_bytes())
        self.assertEqual(b"verified output", target.read_bytes())

    def test_profile_requires_explicit_unexpired_development_app_id(self):
        device = "00008110-0012345678901234"
        wildcard = self.profile_value()
        wildcard["Entitlements"]["application-identifier"] = "TEAM123456.*"
        with self.assertRaisesRegex(SIGN.SigningError, "explicit development bundle"):
            SIGN.profile_identity(wildcard, device)
        with self.assertRaisesRegex(SIGN.SigningError, "less than 24 hours"):
            SIGN.profile_identity(self.profile_value(expiry_hours=1), device)
        distribution = self.profile_value()
        distribution["Entitlements"]["get-task-allow"] = False
        with self.assertRaisesRegex(SIGN.SigningError, "explicit development bundle"):
            SIGN.profile_identity(distribution, device)
        wrong_device = self.profile_value()
        with self.assertRaisesRegex(SIGN.SigningError, "complete Personal-Team"):
            SIGN.profile_identity(wrong_device, "00008110-0099999999999999")
        wrong_platform = self.profile_value()
        wrong_platform["Platform"] = ["macOS"]
        with self.assertRaisesRegex(SIGN.SigningError, "complete Personal-Team"):
            SIGN.profile_identity(wrong_platform, device)

        for key in ("LocalProvision", "IsXcodeManaged", "TimeToLive"):
            not_personal = self.profile_value()
            del not_personal[key]
            with self.subTest(missing=key), self.assertRaisesRegex(
                    SIGN.SigningError, "complete Personal-Team"):
                SIGN.profile_identity(not_personal, device)
        for key, wrong_value in (
            ("LocalProvision", False), ("IsXcodeManaged", False),
            ("TimeToLive", 365),
        ):
            not_personal = self.profile_value()
            not_personal[key] = wrong_value
            with self.subTest(invalid=key), self.assertRaisesRegex(
                    SIGN.SigningError, "complete Personal-Team"):
                SIGN.profile_identity(not_personal, device)
        universal = self.profile_value()
        universal["ProvisionsAllDevices"] = True
        with self.assertRaisesRegex(SIGN.SigningError, "complete Personal-Team"):
            SIGN.profile_identity(universal, device)
        too_long = self.profile_value(expiry_hours=6 * 24, age_hours=2 * 24)
        with self.assertRaisesRegex(SIGN.SigningError, "seven-day Personal-Team"):
            SIGN.profile_identity(too_long, device)
        future = self.profile_value()
        future["CreationDate"] = datetime.now(timezone.utc) + timedelta(hours=1)
        with self.assertRaisesRegex(SIGN.SigningError, "seven-day Personal-Team"):
            SIGN.profile_identity(future, device)

    def test_unsigned_archive_rejects_duplicates_and_existing_signatures(self):
        self.make_unsigned_wda(duplicate=True)
        with self.assertRaisesRegex(SIGN.SigningError, "duplicate members"):
            SIGN.inspect_unsigned_wda(self.input)
        self.make_unsigned_wda(signing_material=True)
        with self.assertRaisesRegex(SIGN.SigningError, "signing material"):
            SIGN.inspect_unsigned_wda(self.input)

    def test_wrong_version_incomplete_output_and_crypto_failure_fail_closed(self):
        self.make_fake_resigner(version="v0.3.0")
        with self.assertRaisesRegex(SIGN.SigningError, "required v0.3.1"):
            self.run_with_fakes()
        self.make_fake_resigner(omit_outer_profile=True)
        with self.assertRaisesRegex(SIGN.SigningError, "profile or CodeResources"):
            self.run_with_fakes()
        self.make_fake_resigner()
        self.make_fake_rcodesign(verify_exit=8)
        with self.assertRaisesRegex(SIGN.SigningError, "runner-rcodesign failed"):
            self.run_with_fakes()
        self.assertFalse(self.output.exists())

    def test_pinned_tool_hash_is_required(self):
        lock = self.private / "lock.json"
        lock.write_text(json.dumps({
            "appium": {"iosSecurity": {
                "resigner": {"executableSha256": hashlib.sha256(
                    self.resigner.read_bytes()).hexdigest()},
                "rcodesign": {"executableSha256": hashlib.sha256(
                    self.rcodesign.read_bytes()).hexdigest()},
            }},
        }), encoding="utf-8")
        with mock.patch.object(SIGN, "LOCK_FILE", lock):
            self.assertEqual(self.resigner, SIGN.require_pinned_tool(
                self.resigner, "resigner"
            ))
            self.assertEqual(self.rcodesign, SIGN.require_pinned_tool(
                self.rcodesign, "rcodesign"
            ))
        value = json.loads(lock.read_text(encoding="utf-8"))
        value["appium"]["iosSecurity"]["resigner"]["executableSha256"] = "0" * 64
        lock.write_text(json.dumps(value), encoding="utf-8")
        with mock.patch.object(SIGN, "LOCK_FILE", lock), self.assertRaisesRegex(
                SIGN.SigningError, "pinned SHA-256"):
            SIGN.require_pinned_tool(self.resigner, "resigner")

    def test_kit_manifest_sha_binding_is_mandatory(self):
        SIGN.validate_kit_manifest(self.manifest, self.input)
        self.make_kit_manifest(wda_sha256="0" * 64)
        with self.assertRaisesRegex(SIGN.SigningError, "SHA-256/size-bound"):
            SIGN.validate_kit_manifest(self.manifest, self.input)

    def test_p12_has_exactly_one_matching_profile_identity(self):
        config = SIGN.write_task_openssl_config(self.private)
        commands = []

        def fake_process(command, environment, _work, label, **kwargs):
            commands.append((command, environment.copy()))
            destination = kwargs.get("stdout_destination")
            if label == "p12-certificates":
                destination.write_bytes(
                    b"-----BEGIN CERTIFICATE-----\nfixture\n"
                    b"-----END CERTIFICATE-----\n"
                )
            elif label == "p12-private-keys":
                destination.write_bytes(
                    b"-----BEGIN PRIVATE KEY-----\nfixture\n"
                    b"-----END PRIVATE KEY-----\n"
                )
            elif label == "p12-leaf-der":
                destination.write_bytes(b"certificate")
            elif label in {"p12-certificate-public", "p12-key-public"}:
                destination.write_bytes(b"same public key")
            elif label == "p12-leaf-subject":
                return "subject=CN=Apple Development,OU=TEAM123456,O=Example,C=US"
            if destination is not None:
                destination.chmod(0o600)
            return ""

        with mock.patch.object(SIGN.shutil, "which", return_value="/usr/bin/openssl"), \
                mock.patch.object(SIGN, "run_process", side_effect=fake_process):
            leaf = SIGN.verify_p12_identity(
                self.p12, "correct horse battery staple", self.profile_value(),
                "TEAM123456", config, self.private,
            )
        self.assertEqual(b"certificate", leaf)
        self.assertTrue(all("correct horse battery staple" not in command
                            for command, _environment in commands))
        self.assertEqual(
            2,
            sum(environment.get("P12_PASSWORD") == "correct horse battery staple"
                for _command, environment in commands),
        )
        p12_commands = [
            command for command, _environment in commands
            if len(command) > 1 and command[1] == "pkcs12"
        ]
        self.assertEqual(2, len(p12_commands))
        self.assertTrue(all("-legacy" in command for command in p12_commands))

        def duplicate_certificates(command, environment, work, label, **kwargs):
            result = fake_process(command, environment, work, label, **kwargs)
            if label == "p12-certificates":
                destination = kwargs["stdout_destination"]
                destination.write_bytes(destination.read_bytes() * 2)
            return result

        second = self.private / "second-p12-check"
        second.mkdir(mode=0o700)
        second_config = SIGN.write_task_openssl_config(second)
        with mock.patch.object(SIGN.shutil, "which", return_value="/usr/bin/openssl"), \
                mock.patch.object(SIGN, "run_process", side_effect=duplicate_certificates), \
                self.assertRaisesRegex(SIGN.SigningError, "exactly one leaf"):
            SIGN.verify_p12_identity(
                self.p12, "secret", self.profile_value(), "TEAM123456",
                second_config, second,
            )

    def test_real_openssl_fixture_proves_p12_key_leaf_and_local_config(self):
        openssl = SIGN.shutil.which("openssl")
        if not openssl:
            self.skipTest("OpenSSL is unavailable")
        key = self.private / "fixture-private.pem"
        certificate = self.private / "fixture-certificate.pem"
        subprocess.run(
            [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(key), "-out", str(certificate), "-days", "2",
             "-subj", "/C=US/O=Overte Fixture/OU=TEAM123456/CN=Fixture"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )
        subprocess.run(
            [openssl, "pkcs12", "-export", "-inkey", str(key), "-in",
             str(certificate), "-out", str(self.p12), "-passout",
             "env:FIXTURE_PASSWORD"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            env={"PATH": os.environ.get("PATH", ""), "FIXTURE_PASSWORD": "fixture"},
        )
        leaf_der = subprocess.run(
            [openssl, "x509", "-in", str(certificate), "-outform", "DER"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True,
        ).stdout
        self.p12.chmod(0o600)
        work = self.private / "real-p12-work"
        work.mkdir(mode=0o700)
        config = SIGN.write_task_openssl_config(work)
        sha1_payload = work / "payload.plist"
        sha1_cms = work / "payload.cms"
        sha1_verified = work / "payload.verified"
        sha1_payload.write_bytes(b"task-local sha1 policy fixture")
        local_environment = {
            "PATH": os.environ.get("PATH", ""),
            "OPENSSL_CONF": str(config),
        }
        subprocess.run(
            [openssl, "cms", "-sign", "-binary", "-nodetach", "-md", "sha1",
             "-in", str(sha1_payload), "-signer", str(certificate), "-inkey",
             str(key), "-outform", "DER", "-out", str(sha1_cms)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            env=local_environment,
        )
        subprocess.run(
            [openssl, "cms", "-verify", "-binary", "-inform", "DER",
             "-purpose", "any", "-CAfile", str(certificate), "-in",
             str(sha1_cms), "-out", str(sha1_verified)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            env=local_environment,
        )
        self.assertEqual(sha1_payload.read_bytes(), sha1_verified.read_bytes())
        profile = self.profile_value()
        profile["DeveloperCertificates"] = [leaf_der]
        self.assertEqual(
            leaf_der,
            SIGN.verify_p12_identity(
                self.p12, "fixture", profile, "TEAM123456", config, work
            ),
        )

    def test_profile_cms_uses_pinned_root_and_task_local_sha1_policy(self):
        calls = []

        def fake_process(command, environment, _work, _label, **_kwargs):
            calls.append((command, environment))
            output = _kwargs.get("stdout_destination")
            if output is None:
                output = Path(command[command.index("-out") + 1])
            if command[1] == "x509":
                output.write_bytes(b"root der fixture")
            else:
                output.write_bytes(plistlib.dumps(self.profile_value()))
            output.chmod(0o600)
            return ""

        config = SIGN.write_task_openssl_config(self.private)
        with mock.patch.object(SIGN.shutil, "which", return_value="/usr/bin/openssl"), \
                mock.patch.object(SIGN, "APPLE_ROOT_CA_DER_SHA256", hashlib.sha256(
                    b"root der fixture").hexdigest()), mock.patch.object(
                    SIGN, "run_process", side_effect=fake_process):
            value = SIGN.verify_profile_payload(
                self.profile, self.apple_root, config, self.private
            )
        self.assertEqual(["TEAM123456"], value["TeamIdentifier"])
        cms_command, cms_environment = calls[1]
        self.assertIn("-CAfile", cms_command)
        self.assertNotIn("-noverify", cms_command)
        self.assertNotIn("-nosigs", cms_command)
        self.assertEqual(str(config), cms_environment["OPENSSL_CONF"])

    def test_signature_metadata_must_bind_cms_team_and_entitlements(self):
        team = "TEAM123456"
        bundle_id = "local.personal.wda"
        entitlements = {
            "application-identifier": f"{team}.{bundle_id}",
            "com.apple.developer.team-identifier": team,
        }
        lines = plistlib.dumps(
            entitlements, fmt=plistlib.FMT_XML
        ).decode().splitlines()
        signature = {
            "code_directory": {"identifier": bundle_id, "team_name": team},
            "cms": {
                "certificates": [{
                    "apple_team_id": team,
                    "apple_certificate_profile": "apple-development",
                }],
                "signers": [{"signature_verifies": True}],
            },
            "entitlements_plist": lines,
            "entitlements_der_plist": lines,
        }

        def value():
            copied = json.loads(json.dumps(signature))
            return [{"entity": {"mach_o": {"signature": copied}}}]

        SIGN.parse_signature_info(
            value(), "runner", team, bundle_id, require_entitlements=True
        )
        with self.assertRaisesRegex(SIGN.SigningError, "nested code"):
            SIGN.parse_signature_info(
                value(), "xctest", team, bundle_id,
                require_entitlements=False,
            )
        empty_lines = plistlib.dumps(
            {}, fmt=plistlib.FMT_XML
        ).decode().splitlines()
        for metadata in (
                {"entitlements_plist": empty_lines},
                {"entitlements_der_plist": empty_lines},
                {
                    "entitlements_plist": empty_lines,
                    "entitlements_der_plist": empty_lines,
                },
                {"entitlements_plist": None}):
            with self.subTest(metadata=tuple(metadata)):
                empty_nested = value()
                empty_nested_signature = empty_nested[0]["entity"]["mach_o"][
                    "signature"
                ]
                empty_nested_signature["code_directory"]["identifier"] = (
                    SIGN.SOURCE_BUNDLE_IDS["xctest"]
                )
                del empty_nested_signature["entitlements_plist"]
                del empty_nested_signature["entitlements_der_plist"]
                empty_nested_signature.update(metadata)
                with self.assertRaisesRegex(
                        SIGN.SigningError, "entitlement metadata"):
                    SIGN.parse_signature_info(
                        empty_nested, "xctest", team,
                        SIGN.SOURCE_BUNDLE_IDS["xctest"],
                        require_entitlements=False,
                    )
        clean_nested = value()
        clean_nested_signature = clean_nested[0]["entity"]["mach_o"]["signature"]
        clean_nested_signature["code_directory"]["identifier"] = (
            SIGN.SOURCE_BUNDLE_IDS["xctest"]
        )
        del clean_nested_signature["entitlements_plist"]
        del clean_nested_signature["entitlements_der_plist"]
        SIGN.parse_signature_info(
            clean_nested, "xctest", team,
            SIGN.SOURCE_BUNDLE_IDS["xctest"],
            require_entitlements=False,
        )
        wrong_nested_identity = json.loads(json.dumps(clean_nested))
        wrong_nested_identity[0]["entity"]["mach_o"]["signature"][
            "code_directory"
        ]["identifier"] = bundle_id
        with self.assertRaisesRegex(SIGN.SigningError, "code-directory identity"):
            SIGN.parse_signature_info(
                wrong_nested_identity, "xctest", team,
                SIGN.SOURCE_BUNDLE_IDS["xctest"],
                require_entitlements=False,
            )
        missing_cms = value()
        missing_cms[0]["entity"]["mach_o"]["signature"]["cms"] = None
        with self.assertRaisesRegex(SIGN.SigningError, "no cryptographic CMS"):
            SIGN.parse_signature_info(
                missing_cms, "runner", team, bundle_id,
                require_entitlements=True,
            )
        wrong_team = value()
        wrong_team[0]["entity"]["mach_o"]["signature"]["cms"][
            "certificates"
        ][0]["apple_team_id"] = "OTHER12345"
        with self.assertRaisesRegex(SIGN.SigningError, "selected Apple team"):
            SIGN.parse_signature_info(
                wrong_team, "runner", team, bundle_id,
                require_entitlements=True,
            )
        wrong_entitlements = value()
        other_lines = plistlib.dumps({
            **entitlements,
            "application-identifier": f"{team}.different.bundle",
        }, fmt=plistlib.FMT_XML).decode().splitlines()
        wrong_entitlements[0]["entity"]["mach_o"]["signature"][
            "entitlements_plist"
        ] = other_lines
        wrong_entitlements[0]["entity"]["mach_o"]["signature"][
            "entitlements_der_plist"
        ] = other_lines
        with self.assertRaisesRegex(SIGN.SigningError, "selected profile identity"):
            SIGN.parse_signature_info(
                wrong_entitlements, "runner", team, bundle_id,
                require_entitlements=True,
            )

    def test_signed_archive_rejects_content_outside_fixed_application(self):
        self.assertEqual(0, self.run_with_fakes())
        rewritten = self.private / "rewritten.ipa"
        with zipfile.ZipFile(self.output) as original, zipfile.ZipFile(
                rewritten, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for entry in original.infolist():
                output.writestr(entry, original.read(entry))
            output.writestr("unexpected/private.txt", b"unexpected")
        rewritten.chmod(0o600)
        with self.assertRaisesRegex(SIGN.SigningError, "outside its fixed"):
            SIGN.inspect_signed_wda(
                rewritten, "local.personal.wda", self.profile.read_bytes()
            )

    def test_signed_framework_must_not_embed_a_profile(self):
        self.assertEqual(0, self.run_with_fakes())
        rewritten = self.private / "framework-profile.ipa"
        framework_profile = (
            "Payload/WebDriverAgentRunner-Runner.app/PlugIns/"
            "WebDriverAgentRunner.xctest/Frameworks/"
            "WebDriverAgentLib.framework/embedded.mobileprovision"
        )
        with zipfile.ZipFile(self.output) as original, zipfile.ZipFile(
                rewritten, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for entry in original.infolist():
                output.writestr(entry, original.read(entry))
            output.writestr(framework_profile, self.profile.read_bytes())
        rewritten.chmod(0o600)
        with self.assertRaisesRegex(SIGN.SigningError, "framework must never embed"):
            SIGN.inspect_signed_wda(
                rewritten, "local.personal.wda", self.profile.read_bytes()
            )


if __name__ == "__main__":
    unittest.main()
