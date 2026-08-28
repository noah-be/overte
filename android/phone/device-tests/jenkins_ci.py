#!/usr/bin/env python3
"""Android Phone registration entry point for the shared device CI helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SHARED_HELPER = REPOSITORY_ROOT / "tests/device/jenkins/run_ci.py"
PHONE_SUITES = {
    "asset-smoke",
    "domain-smoke",
    "lifecycle-stability",
    "smoke",
    "sound-smoke",
    "stability",
    "vertical-locomotion",
}


def load_shared_helper():
    spec = importlib.util.spec_from_file_location("overte_device_run_ci", SHARED_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError("shared device CI helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    helper = load_shared_helper()
    helper.SUITES.update(PHONE_SUITES)
    return helper.main()


if __name__ == "__main__":
    raise SystemExit(main())
