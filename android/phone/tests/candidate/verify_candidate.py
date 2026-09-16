#!/usr/bin/env python3
"""Phone SH-009 byte binding and optional SH-002 tier join; no acceptance claim."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "provenance"))
from artifact_identity import EVIDENCE_KEYS, IdentityError, read_record, require, validate
sys.path.insert(0, str(ROOT / "tests/device/schema"))
from android_build_evidence import validate as validate_build_evidence

CHANNELS = ("source-proof", "internal-candidate", "fdroid-candidate")


def verify_candidate(record_path, artifact, evidence, expected_source, expected_inputs_path,
                     expected_version, minimum_version, channel, *, build_evidence=None,
                     expected_artifact_sha256=None):
    require((build_evidence is None) == (expected_artifact_sha256 is None),
            "PHONE_BUILD_EVIDENCE_ARGUMENTS_INCOMPLETE")
    record = read_record(record_path)
    inputs = read_record(expected_inputs_path)
    require(type(expected_version) is int and 0 < expected_version < 2**31,
            "PHONE_EXPECTED_VERSION")
    require(record.get("product") == "android-phone", "PHONE_PRODUCT")
    require(channel in CHANNELS and record.get("channel") == channel, "PHONE_CHANNEL")
    require(type(record.get("versionCode")) is int and record["versionCode"] == expected_version,
            "PHONE_VERSION")
    # SPDX/CycloneDX and the three graph inventories are separate documents,
    # not six labels pointing at one file or hardlink. Check before hashing.
    paths = [Path(record_path), Path(artifact), Path(expected_inputs_path)]
    paths += [Path(evidence[key]) for key in EVIDENCE_KEYS]
    if build_evidence is not None:
        paths.append(Path(build_evidence))
    seen = set()
    for path in paths:
        require(path.is_file() and not path.is_symlink(), "PHONE_REGULAR_INPUT")
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        require(identity not in seen, "PHONE_REUSED_INPUT")
        seen.add(identity)
    bound = validate(record, artifact, evidence, expected_source, inputs, minimum_version)
    if build_evidence is None:
        return bound  # Explicitly unqualified byte-only diagnostics remain usable.
    tiers = validate_build_evidence(build_evidence, record_path, artifact,
                                    expected_inputs_path, expected_source,
                                    expected_artifact_sha256, "android-phone")
    # Shared rereads its inputs. Do not let a changed record bypass the original
    # Phone product/version/channel and SH009 inventory/signature checks above.
    require(read_record(record_path) == record and read_record(expected_inputs_path) == inputs,
            "PHONE_CANDIDATE_CHANGED")
    require(validate(record, artifact, evidence, expected_source, inputs, minimum_version) == bound,
            "PHONE_CANDIDATE_CHANGED")
    return tiers  # Return the original Shared status, never a Phone build PASS.


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "PHONE_CANDIDATE_ARGUMENTS_REJECTED\n")

    def parse_args(self, args=None, namespace=None):
        values = list(sys.argv[1:] if args is None else args)
        seen = set()
        for value in values:
            if value.startswith("--"):
                option = value.split("=", 1)[0]
                if option in seen:
                    self.error("duplicate option")
                seen.add(option)
        return super().parse_args(values, namespace)


def main(argv=None):
    parser = PrivateParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-inputs", required=True, type=Path)
    parser.add_argument("--expected-version-code", required=True, type=int)
    parser.add_argument("--minimum-version-code", required=True, type=int)
    parser.add_argument("--channel", required=True, choices=CHANNELS)
    parser.add_argument("--build-evidence", type=Path)
    parser.add_argument("--expected-artifact-sha256")
    for key in EVIDENCE_KEYS:
        parser.add_argument("--" + key, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_candidate(args.record, args.artifact,
                         {key: getattr(args, key) for key in EVIDENCE_KEYS},
                         args.expected_source_sha, args.expected_inputs, args.expected_version_code,
                         args.minimum_version_code, args.channel,
                         build_evidence=args.build_evidence,
                         expected_artifact_sha256=args.expected_artifact_sha256)
    except (IdentityError, OSError, KeyError, TypeError, ValueError, RecursionError):
        print("PHONE_CANDIDATE_REJECTED", file=sys.stderr)
        return 1
    print(result["status"] if args.build_evidence is not None
          else "PHONE_CANDIDATE_BYTES_BOUND_VERIFICATION_PENDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
