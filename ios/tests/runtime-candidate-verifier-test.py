#!/usr/bin/env python3
"""Host tests for the simulator and signed-iPad runtime candidate verifier."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import importlib.util
import json
import plistlib
import stat
import struct
import subprocess
import sys
import tempfile
import warnings
import zipfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]
TOOL = IOS_ROOT / "tools/verify-runtime-candidate.py"
REVISION = "a" * 40


def macho_fixture(mode: str) -> bytes:
    platform = 7 if mode == "simulator" else 2
    command = struct.pack("<IIIIII", 0x32, 24, platform, 0, 0, 0)
    header = struct.pack(
        "<IiiIIIII", 0xFEEDFACF, 0x0100000C, 0, 2, 1, len(command), 0, 0
    )
    return header + command + b"fixture payload"


def load_verifier():
    specification = importlib.util.spec_from_file_location("runtime_candidate", TOOL)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def write_archive(
    path: Path,
    mode: str,
    *,
    macho_mode: str | None = None,
    info_updates: dict | None = None,
    extra_entries: list[tuple[str, bytes | str | None]] | None = None,
    omit: set[str] | None = None,
) -> None:
    root = "Overte.app" if mode == "simulator" else "Payload/Overte.app"
    bundle_info = {
        "CFBundleExecutable": "Overte",
        "CFBundleIdentifier": "org.overte.interface.dev",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "CFBundleSupportedPlatforms": [
            "iPhoneSimulator" if mode == "simulator" else "iPhoneOS"
        ],
        "UIDeviceFamily": [1, 2],
        "LSRequiresIPhoneOS": True,
    }
    for key, value in (info_updates or {}).items():
        if value is None:
            bundle_info.pop(key, None)
        else:
            bundle_info[key] = value
    entries: list[tuple[str, bytes | str | None]] = [
        (
            f"{root}/Info.plist",
            plistlib.dumps(bundle_info),
        ),
        (f"{root}/Overte", macho_fixture(macho_mode or mode)),
        (f"{root}/PrivacyInfo.xcprivacy", b"privacy fixture"),
    ]
    if mode == "ipad":
        entries.extend(
            [
                (f"{root}/embedded.mobileprovision", b"profile fixture"),
                (f"{root}/_CodeSignature/CodeResources", b"signature fixture"),
            ]
        )
    entries.extend(extra_entries or [])
    omit = omit or set()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in entries:
                if name in omit:
                    continue
                if data is None:
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, "../../outside")
                else:
                    if name.endswith("/Overte"):
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFREG | 0o755) << 16
                        archive.writestr(info, data)
                    else:
                        archive.writestr(name, data)


def write_candidate(
    root: Path,
    mode: str,
    *,
    macho_mode: str | None = None,
    info_updates: dict | None = None,
    manifest_updates: dict | None = None,
    extra_entries: list[tuple[str, bytes | str | None]] | None = None,
    omit: set[str] | None = None,
) -> tuple[dict, str]:
    if mode == "simulator":
        artifact_name = "0042-OverteIOSClient-Debug-simulator.zip"
        platform = "iphonesimulator"
        signed = False
    else:
        artifact_name = "0042-OverteIOSClient-Debug-device-signed.ipa"
        platform = "iphoneos"
        signed = True
    artifact = root / artifact_name
    write_archive(
        artifact,
        mode,
        macho_mode=macho_mode,
        info_updates=info_updates,
        extra_entries=extra_entries,
        omit=omit,
    )
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_name = str(Path(artifact_name).with_suffix(".json"))
    payload = {
        "schemaVersion": 1,
        "product": "overte-ios-integrated-client",
        "buildNumber": 42,
        "artifact": artifact_name,
        "manifest": manifest_name,
        "sha256": digest,
        "sourceRevision": REVISION,
        "platform": platform,
        "architecture": "arm64",
        "signed": signed,
        "requiresSigning": False,
        "signing": {
            "embeddedProvisioningProfile": mode == "ipad",
            "applicationIdentifier": (
                "TESTTEAM.org.overte.interface.dev" if mode == "ipad" else None
            ),
            "getTaskAllow": mode == "ipad",
        },
        "windowsVm": {"sharedFolderRelativePath": artifact_name},
    }
    payload.update(manifest_updates or {})
    (root / "LATEST-OverteIOSClient.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    (root / "LATEST-OverteIOSClient.txt").write_text(
        artifact_name + "\n", encoding="utf-8"
    )
    (root / manifest_name).write_text(json.dumps(payload), encoding="utf-8")
    return payload, digest


def expect_failure(callable_object, expected: str) -> None:
    try:
        callable_object()
    except ValueError as error:
        assert expected in str(error), (expected, str(error))
    else:
        raise AssertionError(f"unsafe runtime candidate accepted; expected {expected!r}")


def isolated_case(parent: Path, name: str) -> Path:
    path = parent / name
    path.mkdir()
    return path


def main() -> None:
    verifier = load_verifier()
    with tempfile.TemporaryDirectory(prefix="overte-runtime-candidate-") as temporary:
        root = Path(temporary)

        simulator = isolated_case(root, "simulator-success")
        simulator_payload, simulator_digest = write_candidate(simulator, "simulator")
        simulator_plan = verifier.verify_candidate(
            simulator, "simulator", REVISION, simulator_digest
        )
        assert simulator_plan == {
            "schemaVersion": 1,
            "mode": "simulator",
            "artifact": simulator_payload["artifact"],
            "sourceRevision": REVISION,
            "sha256": simulator_digest,
            "platform": "iphonesimulator",
            "bundleIdentifier": "org.overte.interface.dev",
            "applicationIdentifier": None,
            "appRoot": "Overte.app",
        }

        ipad = isolated_case(root, "ipad-success")
        ipad_payload, ipad_digest = write_candidate(ipad, "ipad")
        ipad_plan = verifier.verify_candidate(ipad, "ipad", REVISION, ipad_digest)
        assert ipad_plan["artifact"] == ipad_payload["artifact"]
        assert ipad_plan["appRoot"] == "Payload/Overte.app"
        assert ipad_plan["platform"] == "iphoneos"

        github_output = root / "github-output"
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(simulator),
                "--mode",
                "simulator",
                "--expected-source-revision",
                REVISION,
                "--expected-sha256",
                simulator_digest,
                "--github-output",
                str(github_output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout) == simulator_plan
        output_lines = github_output.read_text(encoding="utf-8").splitlines()
        assert f"artifact={simulator_payload['artifact']}" in output_lines
        assert f"bundle_id={simulator_plan['bundleIdentifier']}" in output_lines
        assert any(line.startswith("runtime_plan={") for line in output_lines)

        revision_case = isolated_case(root, "revision-mismatch")
        _, digest = write_candidate(revision_case, "simulator")
        expect_failure(
            lambda: verifier.verify_candidate(revision_case, "simulator", "b" * 40, digest),
            "source revision mismatch",
        )
        expect_failure(
            lambda: verifier.verify_candidate(revision_case, "simulator", REVISION, "0" * 64),
            "SHA-256 mismatch",
        )

        manifest_case = isolated_case(root, "numbered-manifest-mismatch")
        payload, digest = write_candidate(manifest_case, "simulator")
        numbered = manifest_case / payload["manifest"]
        broken = payload | {"sourceRevision": "b" * 40}
        numbered.write_text(json.dumps(broken), encoding="utf-8")
        expect_failure(
            lambda: verifier.verify_candidate(manifest_case, "simulator", REVISION, digest),
            "numbered artifact manifest differ",
        )

        unsafe_name = isolated_case(root, "unsafe-artifact-name")
        payload, digest = write_candidate(unsafe_name, "simulator")
        old_artifact = unsafe_name / payload["artifact"]
        injected_name = "0042-OverteIOSClient-$(id)-simulator.zip"
        old_artifact.rename(unsafe_name / injected_name)
        payload["artifact"] = injected_name
        payload["manifest"] = injected_name[:-4] + ".json"
        payload["windowsVm"]["sharedFolderRelativePath"] = injected_name
        (unsafe_name / "LATEST-OverteIOSClient.json").write_text(json.dumps(payload))
        (unsafe_name / "LATEST-OverteIOSClient.txt").write_text(injected_name + "\n")
        (unsafe_name / payload["manifest"]).write_text(json.dumps(payload))
        expect_failure(
            lambda: verifier.verify_candidate(unsafe_name, "simulator", REVISION, digest),
            "artifact name is unsafe",
        )

        unsafe_entries = (
            ("traversal", "../escape", b"escape"),
            ("absolute", "/escape", b"escape"),
            ("backslash", "Overte.app\\escape", b"escape"),
        )
        for case_name, entry_name, content in unsafe_entries:
            case = isolated_case(root, f"unsafe-{case_name}")
            _, digest = write_candidate(
                case, "simulator", extra_entries=[(entry_name, content)]
            )
            expect_failure(
                lambda case=case, digest=digest: verifier.verify_candidate(
                    case, "simulator", REVISION, digest
                ),
                "unsafe ZIP entry",
            )

        duplicate = isolated_case(root, "duplicate-entry")
        _, digest = write_candidate(
            duplicate,
            "simulator",
            extra_entries=[("Overte.app/PrivacyInfo.xcprivacy", b"duplicate")],
        )
        expect_failure(
            lambda: verifier.verify_candidate(duplicate, "simulator", REVISION, digest),
            "duplicate ZIP entries",
        )

        multiple_apps = isolated_case(root, "multiple-app-roots")
        _, digest = write_candidate(
            multiple_apps,
            "simulator",
            extra_entries=[("Other.app/Info.plist", b"not a real plist")],
        )
        expect_failure(
            lambda: verifier.verify_candidate(multiple_apps, "simulator", REVISION, digest),
            "exactly one application root",
        )

        escaping_link = isolated_case(root, "escaping-symlink")
        _, digest = write_candidate(
            escaping_link,
            "simulator",
            extra_entries=[("Overte.app/Frameworks/escape", None)],
        )
        expect_failure(
            lambda: verifier.verify_candidate(escaping_link, "simulator", REVISION, digest),
            "symlink escapes",
        )

        metadata_link = isolated_case(root, "metadata-symlink")
        _, digest = write_candidate(
            metadata_link,
            "simulator",
            extra_entries=[("__MACOSX/escape", None)],
        )
        expect_failure(
            lambda: verifier.verify_candidate(metadata_link, "simulator", REVISION, digest),
            "metadata must not contain symlinks",
        )

        wrong_simulator_platform = isolated_case(root, "wrong-simulator-platform")
        _, digest = write_candidate(
            wrong_simulator_platform,
            "simulator",
            manifest_updates={"platform": "iphoneos"},
        )
        expect_failure(
            lambda: verifier.verify_candidate(
                wrong_simulator_platform, "simulator", REVISION, digest
            ),
            "platform mismatch",
        )

        wrong_macho_platform = isolated_case(root, "wrong-macho-platform")
        _, digest = write_candidate(
            wrong_macho_platform,
            "simulator",
            macho_mode="ipad",
        )
        expect_failure(
            lambda: verifier.verify_candidate(
                wrong_macho_platform, "simulator", REVISION, digest
            ),
            "wrong Apple platform",
        )

        for key, expected in (
            ("CFBundleShortVersionString", "marketing version"),
            ("CFBundleVersion", "build version"),
        ):
            missing_version = isolated_case(root, f"missing-{key.lower()}")
            _, digest = write_candidate(
                missing_version,
                "simulator",
                info_updates={key: None},
            )
            expect_failure(
                lambda missing_version=missing_version, digest=digest: verifier.verify_candidate(
                    missing_version, "simulator", REVISION, digest
                ),
                expected,
            )

        wrong_simulator_signing = isolated_case(root, "wrong-simulator-signing")
        _, digest = write_candidate(
            wrong_simulator_signing,
            "simulator",
            manifest_updates={"signed": True},
        )
        expect_failure(
            lambda: verifier.verify_candidate(
                wrong_simulator_signing, "simulator", REVISION, digest
            ),
            "simulator artifact signing metadata",
        )

        wrong_product = isolated_case(root, "wrong-product")
        _, digest = write_candidate(
            wrong_product,
            "simulator",
            manifest_updates={"product": "overte-ios-bootstrap"},
        )
        expect_failure(
            lambda: verifier.verify_candidate(wrong_product, "simulator", REVISION, digest),
            "product mismatch",
        )

        simulator_nested_root = isolated_case(root, "simulator-nested-root")
        _, digest = write_candidate(
            simulator_nested_root,
            "simulator",
            extra_entries=[("wrapper/readme.txt", b"unexpected wrapper")],
        )
        expect_failure(
            lambda: verifier.verify_candidate(
                simulator_nested_root, "simulator", REVISION, digest
            ),
            "outside Overte.app",
        )

        unsigned_ipad = isolated_case(root, "unsigned-ipad")
        _, digest = write_candidate(
            unsigned_ipad,
            "ipad",
            manifest_updates={"signed": False, "requiresSigning": True},
        )
        expect_failure(
            lambda: verifier.verify_candidate(unsigned_ipad, "ipad", REVISION, digest),
            "signed device artifact",
        )

        wrong_ipad_platform = isolated_case(root, "wrong-ipad-platform")
        _, digest = write_candidate(
            wrong_ipad_platform,
            "ipad",
            manifest_updates={"platform": "iphonesimulator"},
        )
        expect_failure(
            lambda: verifier.verify_candidate(
                wrong_ipad_platform, "ipad", REVISION, digest
            ),
            "iPad candidate platform mismatch",
        )

        unconfirmed_profile = isolated_case(root, "unconfirmed-profile")
        _, digest = write_candidate(
            unconfirmed_profile,
            "ipad",
            manifest_updates={
                "signing": {
                    "embeddedProvisioningProfile": False,
                    "applicationIdentifier": None,
                    "getTaskAllow": None,
                }
            },
        )
        expect_failure(
            lambda: verifier.verify_candidate(
                unconfirmed_profile, "ipad", REVISION, digest
            ),
            "does not confirm an embedded provisioning profile",
        )

        wrong_application_identifier = isolated_case(root, "wrong-application-identifier")
        _, digest = write_candidate(
            wrong_application_identifier,
            "ipad",
            manifest_updates={
                "signing": {
                    "embeddedProvisioningProfile": True,
                    "applicationIdentifier": "TESTTEAM.org.example.other",
                    "getTaskAllow": True,
                }
            },
        )
        expect_failure(
            lambda: verifier.verify_candidate(
                wrong_application_identifier, "ipad", REVISION, digest
            ),
            "application identifier mismatch",
        )

        missing_profile = isolated_case(root, "missing-profile")
        profile_name = "Payload/Overte.app/embedded.mobileprovision"
        _, digest = write_candidate(missing_profile, "ipad", omit={profile_name})
        expect_failure(
            lambda: verifier.verify_candidate(missing_profile, "ipad", REVISION, digest),
            "embedded provisioning profile",
        )

        missing_signature = isolated_case(root, "missing-signature")
        signature_name = "Payload/Overte.app/_CodeSignature/CodeResources"
        _, digest = write_candidate(missing_signature, "ipad", omit={signature_name})
        expect_failure(
            lambda: verifier.verify_candidate(
                missing_signature, "ipad", REVISION, digest
            ),
            "code-signature resources",
        )

        limits = isolated_case(root, "bounded-archive")
        _, digest = write_candidate(limits, "simulator")
        original_archive_limit = verifier.MAX_ARCHIVE_BYTES
        original_expanded_limit = verifier.MAX_EXPANDED_BYTES
        original_member_limit = verifier.MAX_MEMBERS
        try:
            verifier.MAX_ARCHIVE_BYTES = 1
            expect_failure(
                lambda: verifier.verify_candidate(limits, "simulator", REVISION, digest),
                "runtime size limit",
            )
            verifier.MAX_ARCHIVE_BYTES = original_archive_limit
            verifier.MAX_EXPANDED_BYTES = 1
            expect_failure(
                lambda: verifier.verify_candidate(limits, "simulator", REVISION, digest),
                "expands beyond",
            )
            verifier.MAX_EXPANDED_BYTES = original_expanded_limit
            verifier.MAX_MEMBERS = 1
            expect_failure(
                lambda: verifier.verify_candidate(limits, "simulator", REVISION, digest),
                "too many entries",
            )
        finally:
            verifier.MAX_ARCHIVE_BYTES = original_archive_limit
            verifier.MAX_EXPANDED_BYTES = original_expanded_limit
            verifier.MAX_MEMBERS = original_member_limit

    print("PASS simulator and signed-iPad runtime candidate verifier tests")


if __name__ == "__main__":
    main()
