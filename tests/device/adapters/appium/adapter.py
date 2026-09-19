#!/usr/bin/env python3
"""Compatibility entrypoint for the parent-owned shared Appium implementation."""
from pathlib import Path
import sys

DEVICE_ROOT = Path(__file__).resolve().parents[2]
if str(DEVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVICE_ROOT))
from adapters.shared_appium.adapter import AppiumAdapter, WebDriver, main  # noqa: E402,F401

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
