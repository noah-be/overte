#!/usr/bin/env python3
"""Invoke an Overte device adapter from a test module."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def load_command(manifest_path: Path) -> list[str]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        raise ValueError("unsupported adapter manifest schema")
    command = payload.get("command")
    if not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part for part in command):
        raise ValueError("adapter command must be a non-empty string list")
    executable = Path(command[0])
    if not executable.is_absolute():
        executable = manifest_path.parent / executable
    return [str(executable.resolve()), *command[1:]]


def invoke(manifest: Path, target: str, operation: str,
           arguments: dict[str, object] | None = None) -> object:
    command = load_command(manifest)
    result = subprocess.run(
        [*command, "invoke", "--target", target, "--operation", operation,
         "--arguments", json.dumps(arguments or {}, separators=(",", ":"))],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "adapter operation failed"
        raise RuntimeError(detail.replace(target, "<target>"))
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("adapter returned invalid JSON") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation")
    parser.add_argument("--arguments", default="{}")
    args = parser.parse_args()
    manifest_value = os.environ.get("OVERTE_DEVICE_ADAPTER_MANIFEST")
    target = os.environ.get("OVERTE_DEVICE_TARGET_SELECTOR")
    if not manifest_value or not target:
        parser.error("device harness environment is incomplete")
    arguments = json.loads(args.arguments)
    if not isinstance(arguments, dict):
        parser.error("--arguments must be a JSON object")
    json.dump(invoke(Path(manifest_value), target, args.operation, arguments), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

