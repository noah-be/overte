#!/usr/bin/env python3
"""Inject a strictly validated online-loading benchmark case into JavaScript."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile


SAFE_LABEL = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SAFE_NAVIGATION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-mode", choices=("cold", "warm"), required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--run-index", type=int, required=True)
    parser.add_argument("--location-label", required=True)
    parser.add_argument("--location-sha256", required=True)
    parser.add_argument("--navigation-id", required=True)
    parser.add_argument("--runner-class", choices=("diagnostic", "hardware"), required=True)
    arguments = parser.parse_args()
    if not 1 <= arguments.concurrency <= 64:
        parser.error("--concurrency is outside 1..64")
    if not 1 <= arguments.run_index <= 20:
        parser.error("--run-index is outside 1..20")
    if not SAFE_LABEL.fullmatch(arguments.location_label):
        parser.error("--location-label is invalid")
    if not SHA256.fullmatch(arguments.location_sha256):
        parser.error("--location-sha256 is invalid")
    if not SAFE_NAVIGATION_ID.fullmatch(arguments.navigation_id):
        parser.error("--navigation-id is invalid")
    payload = {
        "cache_mode": arguments.cache_mode,
        "concurrency": arguments.concurrency,
        "run_index": arguments.run_index,
        "location_label": arguments.location_label,
        "location_sha256": arguments.location_sha256,
        "navigation_id": arguments.navigation_id,
        "runner_class": arguments.runner_class,
    }
    try:
        template = arguments.template.read_text(encoding="utf-8")
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        if arguments.output.is_symlink():
            raise OSError("refusing to replace symlink")
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{arguments.output.name}.", dir=arguments.output.parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write("var OVERTE_MACOS_ONLINE_LOADING_CASE = ")
                json.dump(payload, output, sort_keys=True)
                output.write(";\n")
                output.write(template)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, arguments.output)
            os.chmod(arguments.output, 0o600)
        finally:
            temporary.unlink(missing_ok=True)
    except OSError as error:
        print(f"online loading case generation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(payload, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
