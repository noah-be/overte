"""Bind the original SH-009 offline CLI to the already verified iOS evidence bytes."""
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from shared_release import verify_release

SBOM_MANIFEST = "781c58dff5aba47b76ab52e50ceb5530956bd8b8d41876b7d6fe017b4d01753e"
IDENTITY_MANIFEST = "0938dcc56f67b30c4402d2bb56719b84f15628b1e3d6b5bc617bf4b93b01a1d4"
PAIR_STATUS = "SBOM_PAIR_VALID_CONTENT_VERIFICATION_PENDING"


def verify_pair(root, identity_root, spdx, cyclonedx, source, artifact, evidence_hashes):
    cli = verify_release(root, SBOM_MANIFEST, "tools/sbom/verify-sbom-pair.py", executable=False)
    identity = verify_release(identity_root, IDENTITY_MANIFEST,
                              "provenance/artifact_identity.py", executable=False)
    with tempfile.TemporaryDirectory(prefix="ios-sbom-pair-") as temporary:
        scratch = Path(temporary)
        # Validate the exact evidence bytes already bound by SH-009, not a later
        # replacement of the producer's mutable paths. No common schema copied.
        for key, path in (("spdx", spdx), ("cyclonedx", cyclonedx)):
            if path.is_symlink() or not path.is_file():
                raise ValueError("IOS_SBOM_INPUT")
            with path.open("rb") as stream:
                data = stream.read(16 * 1024 * 1024 + 1)
            if not 0 < len(data) <= 16 * 1024 * 1024 or \
                    hashlib.sha256(data).hexdigest() != evidence_hashes[key]:
                raise ValueError("IOS_SBOM_BYTES")
            (scratch / key).write_bytes(data)
        env = dict(os.environ, PYTHONPATH=str(identity.parent), PYTHONDONTWRITEBYTECODE="1")
        env.pop("PYTHONHOME", None)
        # Use the caller's qualified validation interpreter, never install tools
        # into build inputs. Missing official validators fail closed in the CLI.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            python_flags = ["-B"] + (["-S"] if sys.flags.no_site else [])
            result = subprocess.run([sys.executable, *python_flags, str(cli),
                "--spdx", str(scratch / "spdx"), "--cyclonedx", str(scratch / "cyclonedx"),
                "--expected-source-sha", source, "--expected-artifact-sha256", artifact],
                cwd=scratch, env=env, stdin=subprocess.DEVNULL, stdout=output,
                stderr=errors, timeout=30)
            if result.returncode or output.tell() > 65536 or errors.tell() > 65536:
                raise ValueError("IOS_SBOM_REJECTED")
            output.seek(0)
            summary = json.loads(output.read(65537))
        if not isinstance(summary, dict) or summary.get("status") != PAIR_STATUS or \
                summary.get("sourceRevision") != source or summary.get("artifactSha256") != artifact:
            raise ValueError("IOS_SBOM_RESULT")
        return summary
