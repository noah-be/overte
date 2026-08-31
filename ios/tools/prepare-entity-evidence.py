#!/usr/bin/env python3
"""Create a minimal offline entity-gate evidence handoff from an exported log."""

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

REVISION = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")


def load_gate_validator():
    path = Path(__file__).with_name("validate-entity-gate-log.py")
    spec = importlib.util.spec_from_file_location("entity_gate_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load entity gate validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(log: Path, output: Path, metadata: dict) -> Path:
    if output.exists() or output.with_suffix(".zip").exists():
        raise ValueError("output directory or ZIP already exists")
    raw = log.read_bytes()
    validator = load_gate_validator()
    report = validator.validate(raw.decode("utf-8", errors="replace").splitlines())
    if not report["accepted"]:
        raise ValueError("entity gate log is incomplete: " + "; ".join(report["errors"]))
    canonical = []
    for item in report["evidence"]:
        fields = " ".join(f"{key}={value}" for key, value in item["fields"].items())
        canonical.append(f"{validator.PREFIX} {item['gate']} {fields}".rstrip())
    canonical_bytes = ("\n".join(canonical) + "\n").encode()
    output.mkdir(parents=False)
    (output / "entity-gates.log").write_bytes(canonical_bytes)
    (output / "entity-gates.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    handoff = {
        "schemaVersion": 1, **metadata,
        "rawLogSha256": hashlib.sha256(raw).hexdigest(),
        "canonicalGateLogSha256": hashlib.sha256(canonical_bytes).hexdigest(),
        "gateCount": len(report["evidence"]), "accepted": True,
        "containsRawDeviceLog": False,
    }
    (output / "handoff.json").write_text(json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Path(shutil.make_archive(str(output), "zip", root_dir=output))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path, help="already exported iPad text log")
    parser.add_argument("output", type=Path, help="new evidence-directory path")
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--os-version", required=True)
    parser.add_argument("--device-model", required=True)
    args = parser.parse_args()
    if REVISION.fullmatch(args.source_revision) is None:
        parser.error("--source-revision must be a lowercase 40-character Git SHA")
    if DIGEST.fullmatch(args.bundle_sha256) is None:
        parser.error("--bundle-sha256 must be a lowercase SHA-256")
    metadata = {"sourceRevision": args.source_revision, "bundleSha256": args.bundle_sha256,
                "formFactor": "ipad", "osVersion": args.os_version, "deviceModel": args.device_model}
    try:
        archive = prepare(args.log, args.output, metadata)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Prepared offline iPad entity evidence: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
