#!/usr/bin/env python3
"""Fail when Phone production code enters the repository without test ownership."""

import glob
import json
import pathlib
import re
import sys

ALLOWED_RUNTIME_BOUNDARIES = {
    "android/apps/phoneInterface/src/main/java/org/overte/phone/PhoneInterfaceActivity.java",
    "android/apps/phoneInterface/src/PhoneUrlHandler.cpp",
}


def fail(message):
    raise ValueError(message)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: phone-test-inventory-test.py <repository-root>")
    root = pathlib.Path(sys.argv[1]).resolve()
    inventory_path = root / "android/tests/phone-test-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    catalog = json.loads(
        (root / "android/tests/suite/catalog.json").read_text(encoding="utf-8")
    )
    catalog_ids = {suite["id"] for suite in catalog["suites"]}
    missing_suites = sorted(set(inventory["required_catalog_suites"]) - catalog_ids)
    if missing_suites:
        fail(f"Phone inventory test runners are absent from suite catalog: {missing_suites}")

    discovered = set()
    for pattern in inventory["scope"]["globs"]:
        discovered.update(
            pathlib.Path(item).resolve().relative_to(root).as_posix()
            for item in glob.glob(str(root / pattern), recursive=True)
            if pathlib.Path(item).is_file()
        )

    tested = inventory["tested"]
    boundaries = inventory["runtime_boundaries"]
    classified = set(tested) | set(boundaries)
    missing = sorted(discovered - classified)
    stale = sorted(classified - discovered)
    overlap = sorted(set(tested) & set(boundaries))
    if missing:
        fail(f"Phone production files lack test ownership: {missing}")
    if stale:
        fail(f"Phone inventory contains stale production paths: {stale}")
    if overlap:
        fail(f"Phone files cannot be both tested and runtime-only: {overlap}")
    if set(boundaries) != ALLOWED_RUNTIME_BOUNDARIES:
        fail(
            "runtime-boundary allowlist changed without validator review: "
            f"actual={sorted(boundaries)}"
        )

    for production, evidence in tested.items():
        if not evidence:
            fail(f"tested entry has no evidence: {production}")
        absent = [path for path in evidence if not (root / path).is_file()]
        if absent:
            fail(f"test evidence for {production} does not exist: {absent}")
        component = pathlib.Path(production).stem
        evidence_text = "\n".join(
            (root / path).read_text(encoding="utf-8", errors="replace")
            for path in evidence
        )
        if component not in evidence_text:
            fail(
                f"test evidence does not reference production component {component}: "
                f"{production}"
            )
    for production, reason in boundaries.items():
        if not isinstance(reason, str) or len(reason.strip()) < 24:
            fail(f"runtime boundary needs a specific rationale: {production}")

    bootstrap = (root / "scripts/+android_phoneInterface/defaultScripts.js").read_text(
        encoding="utf-8"
    )
    match = re.search(r"PHONE_DEFAULT_SCRIPTS\s*=\s*\[(.*?)\];", bootstrap, re.DOTALL)
    if not match:
        fail("could not parse PHONE_DEFAULT_SCRIPTS")
    defaults = re.findall(r'"([^"\n]+\.js)"', match.group(1))
    if not defaults or len(defaults) != len(set(defaults)):
        fail("Phone default scripts are empty or contain duplicates")
    default_tested = inventory["default_script_tested"]
    default_boundaries = inventory["default_script_runtime_boundaries"]
    default_classified = set(default_tested) | set(default_boundaries)
    unowned_defaults = sorted(set(defaults) - default_classified)
    stale_defaults = sorted(default_classified - set(defaults))
    if unowned_defaults:
        fail(f"Phone default scripts lack test ownership: {unowned_defaults}")
    if stale_defaults:
        fail(f"default-script inventory is stale: {stale_defaults}")
    for script, evidence in default_tested.items():
        production_path = root / "scripts" / script
        if not production_path.is_file():
            fail(f"default production script does not exist: {script}")
        absent = [path for path in evidence if not (root / path).is_file()]
        if absent:
            fail(f"default script evidence for {script} does not exist: {absent}")
        component = pathlib.Path(script).name
        evidence_text = "\n".join(
            (root / path).read_text(encoding="utf-8", errors="replace")
            for path in evidence
        )
        if component not in evidence_text:
            fail(f"default script evidence does not reference {component}: {script}")

    print(
        "Phone test inventory passed: "
        f"{len(discovered)} scoped files and {len(defaults)} default scripts classified."
    )


if __name__ == "__main__":
    main()
