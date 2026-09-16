#!/usr/bin/env python3
"""Phone-owned installed-candidate binding around the original Android adapter."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[4]
for directory in (ROOT, ROOT / "tests/device", ROOT / "android/phone/tests/candidate"):
    sys.path.insert(0, str(directory))
from adapters.android.adapter import AndroidAdapter
from adapters.common import emit, parse_operation_arguments
from verify_candidate import CHANNELS, EVIDENCE_KEYS, PrivateParser as CandidateParser, verify_candidate
from artifact_identity import digest_file, require


class VerifiedCandidate:
    """Original SH-009 inputs, not a new receipt schema or source attestation."""
    def __init__(self, arguments):
        self.arguments = arguments

    def verify(self):
        args = self.arguments
        return verify_candidate(args.record, args.artifact,
                                {key: getattr(args, key) for key in EVIDENCE_KEYS},
                                args.expected_source_sha, args.expected_inputs,
                                args.expected_version_code, args.minimum_version_code, args.channel,
                                build_evidence=getattr(args, "build_evidence", None),
                                expected_artifact_sha256=getattr(args, "expected_artifact_sha256", None))


class PhoneAdapter(AndroidAdapter):
    def __init__(self, candidate=None):
        super().__init__("phone")
        self.candidate = candidate

    def installed_apk_path(self, target):
        raw = self.adb.shell(target, "pm", "path", self.profile["package"])
        require(len(raw) <= 8192, "PHONE_INSTALL_PATH_SIZE")
        paths = raw.splitlines()
        # Single-APK distribution only. A base APK plus splits is not equivalent
        # to the independently frozen monolithic candidate bytes.
        require(len(paths) == 1 and paths[0].startswith("package:"), "PHONE_SINGLE_APK_REQUIRED")
        path = paths[0][len("package:"):]
        require(re.fullmatch(r"/data/app/[A-Za-z0-9_./=+~-]+/base\.apk", path) is not None
                and str(PurePosixPath(path)) == path
                and ".." not in PurePosixPath(path).parts, "PHONE_INSTALL_PATH_REJECTED")
        return path

    def installed_identity(self, target):
        bound = self.candidate.verify()
        before = self.installed_apk_path(target)
        # Only a constrained PackageManager-returned absolute path reaches the
        # original ADB transport, whose shell primitive does not quote arguments.
        raw = self.adb.shell(target, "sha256sum", before)
        match = re.fullmatch(r"([0-9a-f]{64})  " + re.escape(before) + r"\n?", raw)
        require(match is not None and match.group(1) == bound["artifactSha256"],
                "PHONE_INSTALLED_BYTES_MISMATCH")
        require(self.installed_apk_path(target) == before, "PHONE_INSTALL_CHANGED")
        require(self.candidate.verify() == bound, "PHONE_CANDIDATE_CHANGED")
        return dict(schemaVersion=1, sourceRevision=bound["sourceRevision"],
                    artifactSha256=bound["artifactSha256"], installedCandidateVerified=True)

    def describe(self, target):
        description = super().describe(target)
        if self.candidate is not None:
            description["executionIdentity"] = self.installed_identity(target)
        return description

    def require_bound_operation(self, operation, values):
        if self.candidate is not None:
            if operation == "app.install":
                bound = self.candidate.verify()
                require(type(values) is dict and type(values.get("path")) is str,
                        "PHONE_INSTALL_ARGUMENTS")
                require(digest_file(values["path"]) == bound["artifactSha256"],
                        "PHONE_INSTALL_FOREIGN_CANDIDATE")
            # An upgrade intentionally changes candidates and needs its separate
            # signed upgrade workflow, not a one-candidate SH-004 run.
            require(operation != "app.upgrade", "PHONE_BOUND_UPGRADE_UNSUPPORTED")

    def invoke(self, target, operation, values):
        self.require_bound_operation(operation, values)
        result = super().invoke(target, operation, values)
        if self.candidate is not None and operation == "app.install":
            self.installed_identity(target)
        return result


class PrivateParser(CandidateParser):
    def error(self, message):
        self.exit(2, "PHONE_ADAPTER_ARGUMENTS_REJECTED\n")


def parse_args(argv=None):
    parser = PrivateParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("discover", "describe", "invoke", "cleanup"))
    parser.add_argument("--target")
    parser.add_argument("--operation")
    parser.add_argument("--arguments", default="{}")
    for flag in ("record", "artifact", "expected-inputs", *EVIDENCE_KEYS):
        parser.add_argument("--" + flag, type=Path)
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--expected-version-code", type=int)
    parser.add_argument("--minimum-version-code", type=int)
    parser.add_argument("--channel", choices=CHANNELS)
    parser.add_argument("--build-evidence", type=Path)
    parser.add_argument("--expected-artifact-sha256")
    return parser.parse_args(argv)


def main(argv=None, adapter_class=None):
    args = parse_args(argv)
    try:
        fields = ("record", "artifact", "expected_inputs", "expected_source_sha",
                  "expected_version_code", "minimum_version_code", "channel", *EVIDENCE_KEYS)
        configured = [getattr(args, key) is not None for key in fields]
        require(not any(configured) or all(configured), "PHONE_CANDIDATE_ARGUMENTS_INCOMPLETE")
        tier_configured = (args.build_evidence is not None, args.expected_artifact_sha256 is not None)
        require(not any(tier_configured) or (all(tier_configured) and all(configured)),
                "PHONE_BUILD_EVIDENCE_ARGUMENTS_INCOMPLETE")
        candidate = VerifiedCandidate(args) if all(configured) else None
        if candidate is not None and args.action != "cleanup":
            candidate.verify()  # Fail before any discovery/device call.
        adapter = (PhoneAdapter if adapter_class is None else adapter_class)(candidate)
        if args.action == "discover":
            emit(adapter.discover())
        elif args.action == "cleanup":
            emit(adapter.cleanup(adapter.cleanup_target(args.target)))
        else:
            target = adapter.selected_target(args.target, args.action)
            if args.action == "describe":
                emit(adapter.describe(target))
            else:
                require(bool(args.operation), "PHONE_OPERATION_REQUIRED")
                emit(adapter.invoke(target, args.operation, parse_operation_arguments(args.arguments)))
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, RecursionError):
        # Neither selectors, installed paths nor rejected metadata reach exports.
        print("PHONE_ADAPTER_REJECTED", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
