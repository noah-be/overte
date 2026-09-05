#!/usr/bin/env python3
"""Opaque boundary for the future SH-002 evidence validator.

This module deliberately knows nothing about the shared evidence schema.  The
deferred input is one executable adapter supplied by the accepted SH-002
handoff.  The adapter receives only the candidate metadata path and the two
already verified identity values.  Exit status zero means that SH-002 accepted
the binding; stdout and stderr are never retained or exposed here.
"""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


DEFERRED_INPUT_CONTRACT = (
    "an executable from the accepted SH-002 handoff that accepts "
    "--candidate-metadata PATH --expected-source-sha SHA40 "
    "--expected-artifact-sha256 SHA256 and returns zero only for a valid "
    "shared evidence binding"
)
DEFAULT_TIMEOUT_SECONDS = 30


class EvidenceBindingError(ValueError):
    """The external shared-evidence adapter did not establish a binding."""


def bind_shared_evidence(
    adapter: Path | None,
    candidate_metadata: Path,
    source_sha: str,
    artifact_sha256: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Return ``BOUND`` or ``DEFERRED`` without parsing shared evidence."""

    if adapter is None:
        return "DEFERRED"
    if not 1 <= timeout_seconds <= DEFAULT_TIMEOUT_SECONDS:
        raise EvidenceBindingError("shared evidence adapter timeout is out of bounds")

    adapter = adapter.resolve()
    if not adapter.is_file() or not os.access(adapter, os.X_OK):
        raise EvidenceBindingError("shared evidence adapter is not executable")

    command = [
        str(adapter),
        "--candidate-metadata",
        str(candidate_metadata.resolve()),
        "--expected-source-sha",
        source_sha,
        "--expected-artifact-sha256",
        artifact_sha256,
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="ios-evidence-import-") as scratch:
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONPYCACHEPREFIX"] = scratch
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=timeout_seconds,
                env=environment,
            )
    except subprocess.TimeoutExpired as error:
        raise EvidenceBindingError("shared evidence adapter timed out") from error
    if completed.returncode != 0:
        raise EvidenceBindingError("shared evidence adapter rejected the candidate")
    return "BOUND"
