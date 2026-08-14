#!/usr/bin/env python3
"""Fail-closed source contract for the normalized Sideloadly IPA workflow."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/ios-sideload-repackage.yml").read_text(
    encoding="utf-8"
)
SWIFT = (ROOT / "ios/ci/verify-apple-bundle.swift").read_text(encoding="utf-8")


def require(pattern: str, message: str) -> None:
    if re.search(pattern, WORKFLOW, re.MULTILINE | re.DOTALL) is None:
        raise AssertionError(message)


if re.search(r"(?m)^\s*(pull_request|pull_request_target|schedule):", WORKFLOW):
    raise AssertionError("untrusted or scheduled events must not repackage an IPA")
require(r"push:[\s\S]*branches:[\s\S]*apple-ios", "push execution must be branch-bound")
require(
    r"push:[\s\S]*paths:[\s\S]*ios-sideload-repackage[.]yml",
    "automatic execution must be limited to the repackaging implementation",
)
require(r"(?m)^\s*actions:\s*read\s*$", "cross-run artifact access must be read-only")
require(r"(?m)^\s*contents:\s*read\s*$", "source checkout must be read-only")
require(r"persist-credentials:\s*false", "checkout credentials must not persist")
require(r"expected_sha256:[\s\S]*bundle_id:", "identity inputs must be explicit")
require(r"head_branch[^\n]*apple-ios", "only the reviewed branch may produce input")
require(r"normalize-sideload-ipa[.]py", "the guarded normalizer must run")
require(r"ditto -x -k", "Apple ditto must re-extract the normalized IPA")
require(
    r"ditto -c -k --norsrc --keepParent[\s\\]*\n\s*\"\$SIDELOAD_ROOT/native-payload/Payload\"",
    "the downloadable IPA must be repacked by Apple ditto without resource forks",
)
require(
    r"source-expanded[\s\S]*verify-apple-bundle[.]swift[^\n]*SOURCE_BUNDLE_ID",
    "the original producer bundle must establish the Foundation baseline",
)
require(r"plutil -lint", "Apple plutil must validate the final Info.plist")
require(r"PlistBuddy[^\n]*CFBundleIdentifier", "Apple metadata lookup must verify the ID")
require(r"xcrun swift ios/ci/verify-apple-bundle[.]swift", "Foundation must parse the iOS app")
require(r"if-no-files-found:\s*error", "missing normalized outputs must fail closed")
require(r"retention-days:\s*30", "the corrected candidate must remain downloadable")

for action, digest in {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "actions/upload-artifact": "b7c566a772e6b6bfb58ed0dc250532a479d7789f",
}.items():
    require(
        rf"uses:\s*{re.escape(action)}@{digest}\b",
        f"{action} must remain pinned to the reviewed commit",
    )

for token in [
    "PropertyListSerialization.propertyList",
    'info["CFBundleIdentifier"] as? String == expectedBundleIdentifier',
    'info["CFBundlePackageType"] as? String == "APPL"',
    'info["CFBundleExecutable"] as? String',
    "isExecutableFile",
]:
    if token not in SWIFT:
        raise AssertionError(f"native Apple bundle verifier lost required boundary: {token}")

print("Sideload repackaging workflow contract passed")
