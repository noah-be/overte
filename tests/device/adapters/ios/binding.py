"""iOS candidate preflight for the canonical Appium adapter, not install proof."""
# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
VERIFIER = ROOT / "ios/tools/candidate/verify_candidate_handoff.py"
# Forward the existing iOS consumer's CLI; do not parse Common evidence here.
INPUT_FLAGS = (
    "artifact-root", "repository", "expected-source-sha", "shared-contract-root",
    "identity-contract-root", "identity-record", "expected-inputs", "minimum-version",
    "expected-channel", "bootstrapPackages", "hostPackages", "targetPackages",
    "generatedOutputs", "spdx", "cyclonedx",
)


def configure_parser(parser):
    # Optional at parse time so cleanup still works after losing candidate files.
    parser.add_argument("--candidate-manifest")
    parser.add_argument("--expected-artifact-sha256")
    for flag in INPUT_FLAGS:
        parser.add_argument("--" + flag)


def candidate_preflight(args):
    values = [getattr(args, name.replace("-", "_"), None) for name in INPUT_FLAGS]
    if not args.candidate_manifest or any(not value for value in values):
        raise ValueError("OVT_IOS_CANDIDATE_INPUTS_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_source_sha or "") or not re.fullmatch(
            r"[0-9a-f]{64}", args.expected_artifact_sha256 or ""):
        raise ValueError("OVT_IOS_CANDIDATE_EXPECTATIONS_REJECTED")
    if not VERIFIER.is_file() or VERIFIER.is_symlink():
        raise ValueError("OVT_IOS_CANDIDATE_VERIFIER_UNAVAILABLE")
    command = [sys.executable, "-B", str(VERIFIER), args.candidate_manifest]
    for name, value in zip(INPUT_FLAGS, values):
        command.extend(["--" + name, value])
    # Never forward stage/execute flags. No simulator/device action is possible
    # through this invocation. Retain no raw output in the result or on disk.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output,
                                   stderr=errors, start_new_session=True)
        try:
            code = process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
            raise ValueError("OVT_IOS_CANDIDATE_PREFLIGHT_TIMEOUT") from None
        if code != 0 or output.tell() > 1024 * 1024 or errors.tell() > 1024 * 1024:
            raise ValueError("OVT_IOS_CANDIDATE_PREFLIGHT_REJECTED")
        output.seek(0)
        try:
            result = json.loads(output.read(1024 * 1024 + 1))
        except (ValueError, UnicodeError):
            raise ValueError("OVT_IOS_CANDIDATE_PREFLIGHT_REJECTED") from None
    if (not isinstance(result, dict) or
            result.get("status") != "IOS_CANDIDATE_BYTES_BOUND_VERIFICATION_PENDING" or
            result.get("sharedBuildInputJoin") != "BOUND_TO_INDEPENDENT_INPUTS" or
            result.get("simulator") != "NOT_EXECUTED" or
            not isinstance(result.get("artifactIdentity"), dict) or
            result["artifactIdentity"].get("artifactSha256") != args.expected_artifact_sha256):
        raise ValueError("OVT_IOS_CANDIDATE_PREFLIGHT_REJECTED")
    # Successful candidate checking is deliberately not returned as the Common
    # executionIdentity object. Actual installed-code association is unavailable.


def create_adapter(args, base_class):
    if args.platform != "ios":
        raise ValueError("OVT_IOS_NATIVE_PROFILE_REJECTED")
    if args.action != "cleanup":
        candidate_preflight(args)  # Fail before reading a target or opening I/O.

    class IOSCandidateAdapter(base_class):
        def describe(self, selector):
            candidate_preflight(args)  # Recheck mutable files at each observation.
            result = super().describe(selector)
            result.pop("executionIdentity", None)
            return result

        def ensure_session(self, selector):
            raise ValueError("OVT_IOS_INSTALLED_CODE_BINDING_UNAVAILABLE")

        def invoke(self, selector, operation, values):
            # Includes operations that bypass ensure_session in the base class.
            # The v003 bound runner normally rejects missing identity earlier.
            raise ValueError("OVT_IOS_INSTALLED_CODE_BINDING_UNAVAILABLE")

        # Inherit original cleanup without candidate revalidation, including its
        # independent process-stop fallback and failure reporting.

    return IOSCandidateAdapter("ios")
